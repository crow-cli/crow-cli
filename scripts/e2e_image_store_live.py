#!/usr/bin/env python
"""Live e2e: image store against a REAL RustFS container.

Boots an ephemeral rustfs/rustfs container (SNSD), then drives the real
MemoryClient through the full seam:
  1. S3 reachable  -> resolve_image_store picks HybridReadStore(S3, FS)
  2. save a message with an inline base64 image -> object lands in the bucket
  3. load + hydrate -> identical base64 comes back
  4. legacy FS image (pre-placed) still hydrates through the hybrid read
  5. container killed -> next init falls back to FsImageStore

Usage:
  uv --project . run python scripts/e2e_image_store_live.py
"""

import asyncio
import base64
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3
import httpx

from crow_cli.agent.memory import MemoryClient
from crow_cli.memory.image_store import FsImageStore, HybridReadStore

PORT = 19000
ENDPOINT = f"http://127.0.0.1:{PORT}"
CONTAINER = "crow-rustfs-e2e"
BUCKET = "crow-images"
ACCESS_KEY = "crowe2e"
SECRET_KEY = "crowe2e"

PNG_BYTES = bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, 1, 2, 3, 4])
PNG_B64 = base64.b64encode(PNG_BYTES).decode()


def docker(*args: str) -> str:
    return subprocess.run(
        ["docker", *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def start_rustfs() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    docker(
        "run", "-d", "--name", CONTAINER,
        "-p", f"{PORT}:9000",
        "-e", f"RUSTFS_ACCESS_KEY={ACCESS_KEY}",
        "-e", f"RUSTFS_SECRET_KEY={SECRET_KEY}",
        "-e", "RUSTFS_ADDRESS=0.0.0.0:9000",
        "-e", "RUSTFS_UNSAFE_BYPASS_DISK_CHECK=true",
        "rustfs/rustfs:latest", "/data",
    )
    for _ in range(60):
        try:
            r = httpx.get(f"{ENDPOINT}/health", timeout=1.0)
            if r.status_code < 500:
                print(f"[ok] rustfs healthy at {ENDPOINT}")
                return
        except httpx.HTTPError:
            pass
        time.sleep(1)
    raise SystemExit("[FAIL] rustfs never became healthy")


def stop_rustfs() -> None:
    subprocess.run(["docker", "rm", "-f", CONTAINER], capture_output=True)
    print("[ok] container removed")


def write_config(config_dir: Path) -> None:
    (config_dir / "config.yaml").write_text(
        f"db_uri: sqlite:///{config_dir / 'crow.db'}\n"
        "image_store:\n"
        "  s3:\n"
        f"    endpoint: {ENDPOINT}\n"
        f"    bucket: {BUCKET}\n"
        f"    access_key: {ACCESS_KEY}\n"
        f"    secret_key: {SECRET_KEY}\n"
    )


def image_msg() -> dict:
    return {
        "role": "tool",
        "tool_call_id": "e2e-c1",
        "content": [
            {"type": "text", "text": "live rustfs drill"},
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{PNG_B64}"},
            },
        ],
    }


async def run() -> None:
    tmp = Path(tempfile.mkdtemp(prefix="crow-rustfs-e2e-"))
    write_config(tmp)

    # ---- 1-3: S3 up — store choice, write into bucket, hydrate back ----
    async with MemoryClient(config_dir=tmp) as client:
        assert isinstance(client.image_store, HybridReadStore), (
            f"expected HybridReadStore, got {type(client.image_store).__name__}"
        )
        print("[ok] resolve_image_store picked S3 (HybridReadStore)")

        agent_id = "e2e-rustfs-1-1"
        await client.create_agent(
            agent_id=agent_id, session_id="e2e-rustfs", agent_idx=1,
            cwd="/tmp", system_prompt="sp", tool_definitions=[],
            request_params={}, model_identifier="m",
        )
        await client.add_message(agent_id, image_msg())

        # object actually landed in the bucket (checked via independent client)
        s3 = boto3.client(
            "s3", endpoint_url=ENDPOINT,
            aws_access_key_id=ACCESS_KEY, aws_secret_access_key=SECRET_KEY,
            region_name="us-east-1",
        )
        keys = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])]
        assert len(keys) == 1 and keys[0].endswith(".png"), f"bucket keys: {keys}"
        print(f"[ok] object in bucket: {keys[0]}")

        # stored row carries an image_ref, NOT base64
        _, stored = await client.load(agent_id)
        ref = stored[0]["content"][1]
        assert ref["type"] == "image_ref" and ref["path"] == keys[0]
        print("[ok] sqlite row carries image_ref only")

        # hydrated load round-trips the exact bytes
        _, hydrated = await client.load(agent_id, hydrate=True)
        url = hydrated[0]["content"][1]["image_url"]["url"]
        assert url == f"data:image/png;base64,{PNG_B64}"
        print("[ok] hydrate round-trip: identical base64")

        # ---- 4: legacy FS image still hydrates through the hybrid read ----
        images_dir = client.images_dir
        fs = FsImageStore(images_dir)
        fs.put("legacydeadbeef.png", PNG_BYTES)
        await client.add_message(
            agent_id,
            {
                "role": "tool",
                "tool_call_id": "e2e-c2",
                "content": [{"type": "image_ref", "path": "legacydeadbeef.png", "mime": "image/png"}],
            },
        )
        _, hydrated2 = await client.load(agent_id, hydrate=True)
        url2 = hydrated2[1]["content"][0]["image_url"]["url"]
        assert url2 == f"data:image/png;base64,{PNG_B64}"
        print("[ok] legacy FS image hydrates via hybrid read-fallback")

    # ---- 5: kill the container -> next init falls back to FS ----
    stop_rustfs()
    async with MemoryClient(config_dir=tmp) as client:
        assert isinstance(client.image_store, FsImageStore), (
            f"expected FsImageStore fallback, got {type(client.image_store).__name__}"
        )
        print("[ok] endpoint down -> FsImageStore fallback")

    print("\nE2E-IMAGE-STORE-OK")


if __name__ == "__main__":
    if subprocess.run(["docker", "pull", "rustfs/rustfs:latest"], capture_output=True).returncode != 0:
        print("[..] pull failed — trying cached image")
    start_rustfs()
    try:
        asyncio.run(run())
    finally:
        stop_rustfs()
