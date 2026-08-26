"""Phase 3 (image-store sprint): S3 store, probe/fallback, hybrid reads.

S3 is exercised against a real local S3 server (moto ThreadedMotoServer) so
the custom-endpoint path goes through genuine HTTP + boto3 — justified mock:
network service. Everything else is real code: resolve_image_store,
FsImageStore, HybridReadStore, config overrides.
"""

import base64

import pytest
from moto.server import ThreadedMotoServer

from crow_cli.config.config import Config, apply_config_overrides
from crow_cli.memory.image_store import (
    FsImageStore,
    HybridReadStore,
    S3ImageStore,
    resolve_image_store,
)

PNG = base64.b64encode(bytes([0x89, 0x50, 0x4E, 0x47, 9, 9, 9])).decode()


@pytest.fixture()
def s3_endpoint():
    server = ThreadedMotoServer(ip_address="127.0.0.1", port=0)
    server.start()
    host, port = server.get_host_and_port()
    yield f"http://{host}:{port}"
    server.stop()


def _s3_store(endpoint, bucket="crow-images"):
    return S3ImageStore(
        endpoint=endpoint, bucket=bucket, access_key="test", secret_key="test"
    )


def _image_msg():
    return {
        "role": "tool",
        "tool_call_id": "c1",
        "content": [
            {"type": "text", "text": "screenshot"},
            {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{PNG}"}},
        ],
    }


def test_s3_store_roundtrip_and_bucket_bootstrap(s3_endpoint):
    # bucket does not exist yet — constructor must probe + create it
    store = _s3_store(s3_endpoint)
    assert not store.exists("abc123.png")
    store.put("abc123.png", b"imagedata")
    assert store.exists("abc123.png")
    assert store.get("abc123.png") == b"imagedata"
    assert store.get("missing.png") is None


def test_extract_and_hydrate_through_s3_store(s3_endpoint):
    from crow_cli.memory.messages import extract_images, hydrate_message

    store = _s3_store(s3_endpoint)
    stored = extract_images(_image_msg(), store)
    ref = stored["content"][1]
    assert ref["type"] == "image_ref"
    assert store.exists(ref["path"])

    hydrated = hydrate_message(stored, store)
    assert hydrated["content"][1]["image_url"]["url"] == f"data:image/png;base64,{PNG}"


def test_resolve_falls_back_when_endpoint_dead(tmp_path):
    # port 1 on loopback refuses instantly — startup must not stall
    store = resolve_image_store(
        {
            "endpoint": "http://127.0.0.1:1",
            "bucket": "crow-images",
            "access_key": "x",
            "secret_key": "y",
        },
        tmp_path / "images",
    )
    assert isinstance(store, FsImageStore)


def test_resolve_no_config_means_fs(tmp_path):
    assert isinstance(resolve_image_store(None, tmp_path), FsImageStore)
    assert isinstance(resolve_image_store({}, tmp_path), FsImageStore)


def test_resolve_picks_s3_when_reachable(s3_endpoint, tmp_path):
    store = resolve_image_store(
        {
            "endpoint": s3_endpoint,
            "bucket": "crow-images",
            "access_key": "test",
            "secret_key": "test",
        },
        tmp_path / "images",
    )
    assert isinstance(store, HybridReadStore)


def test_hybrid_read_serves_legacy_fs_images(s3_endpoint, tmp_path):
    primary = _s3_store(s3_endpoint)
    fs = FsImageStore(tmp_path / "images")
    fs.put("legacy.jpg", b"oldbytes")  # predates the S3 switch
    hybrid = HybridReadStore(primary, fs)

    assert hybrid.get("legacy.jpg") == b"oldbytes"  # FS fallback
    hybrid.put("new.jpg", b"newbytes")  # writes go to S3
    assert primary.get("new.jpg") == b"newbytes"
    assert fs.get("new.jpg") is None


def test_config_override_expands_env_refs(tmp_path, monkeypatch):
    monkeypatch.setenv("RUSTFS_ACCESS_KEY", "ak-from-env")
    monkeypatch.setenv("RUSTFS_SECRET_KEY", "sk-from-env")
    override = tmp_path / "dev.yaml"
    override.write_text(
        "image_store:\n"
        "  s3:\n"
        "    endpoint: http://coast-after-3:9000\n"
        "    bucket: crow-images\n"
        "    access_key: ${RUSTFS_ACCESS_KEY}\n"
        "    secret_key: ${RUSTFS_SECRET_KEY}\n"
    )
    cfg = Config(config_dir=tmp_path)
    cfg = apply_config_overrides(cfg, override)
    s3 = cfg.image_store["s3"]
    assert s3["endpoint"] == "http://coast-after-3:9000"
    assert s3["access_key"] == "ak-from-env"
    assert s3["secret_key"] == "sk-from-env"

