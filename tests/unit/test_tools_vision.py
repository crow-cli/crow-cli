"""vision(mode="file"|"webcam") — the Python channel: VisionResult with the
image-blob repr, ImageStore write-through at call time (content-addressed
keys, dedupe free), dynamic mode recording, and raised VisionErrors."""

import pytest

from crow_cli.memory.db import create_database
from crow_cli.memory.image_store import FsImageStore
from crow_cli.memory.messages import image_key
from crow_cli.tools import vision
from crow_cli.tools.register import begin_cell, clear, pending
from crow_cli.tools.results import VisionError, VisionResult
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker


@pytest.fixture(autouse=True)
def _clean():
    clear()
    yield
    clear()


@pytest.fixture
def images_dir(tmp_path):
    d = tmp_path / "images"
    begin_cell(session_id="s1", parent_tool_call_id="t/c", images_dir=str(d))
    return d


def _make_png(path, w=64, h=48, color=(0, 0, 255)):
    import numpy as np
    import cv2

    frame = np.zeros((h, w, 3), dtype=np.uint8)
    frame[:, :] = color
    assert cv2.imwrite(str(path), frame)
    return path


@pytest.mark.asyncio
async def test_file_mode_stores_and_returns_result(tmp_path, images_dir):
    src = _make_png(tmp_path / "shot.png")
    result = await vision(mode="file", path=str(src))

    assert isinstance(result, VisionResult)
    assert result
    assert result.mime == "image/png"
    assert (result.width, result.height) == (64, 48)
    assert result.source == str(src)

    # Bytes landed in the store under the content-addressed key.
    blob = (images_dir / result.key).read_bytes()
    assert blob.startswith(b"\x89PNG")
    assert image_key(blob, "image/png") == result.key

    # Plain dataclass repr — display, not a channel. The refs ride
    # llm_images(); nothing about the LLM lives in the string.
    assert repr(result).startswith("VisionResult(key=")

    # Three-fold channels.
    assert result.result_kind == "image"
    assert result.acp_payload() == {
        "content": "image",
        "key": result.key,
        "mime": "image/png",
    }
    assert result.llm_images() == [{"key": result.key, "mime": "image/png"}]


@pytest.mark.asyncio
async def test_image_property_returns_pil(tmp_path, images_dir):
    """Code gets a real image object, not a key: .image loads the stored
    bytes as a PIL Image (the interchange format for everything else)."""
    from PIL import Image as PILImage

    src = _make_png(tmp_path / "shot.png", w=32, h=16, color=(7, 8, 9))
    result = await vision(mode="file", path=str(src))

    img = result.image
    assert isinstance(img, PILImage.Image)
    assert img.size == (32, 16)
    # cv2 wrote BGR(7,8,9); PIL reads RGB
    assert img.getpixel((0, 0)) == (9, 8, 7)

    # and it round-trips like any PIL image
    out = tmp_path / "roundtrip.png"
    img.save(out)
    assert out.read_bytes().startswith(b"\x89PNG")


@pytest.mark.asyncio
async def test_file_mode_caps_resolution(tmp_path, images_dir):
    src = _make_png(tmp_path / "big.png", w=3000, h=2000)
    result = await vision(mode="file", path=str(src))
    # int() truncation on the scale can land a pixel under the ceiling
    assert max(result.width, result.height) <= 1568
    assert max(result.width, result.height) >= 1560


@pytest.mark.asyncio
async def test_same_bytes_dedupe_same_key(tmp_path, images_dir):
    a = _make_png(tmp_path / "a.png", color=(1, 2, 3))
    b = _make_png(tmp_path / "b.png", color=(1, 2, 3))
    ra = await vision(mode="file", path=str(a))
    rb = await vision(mode="file", path=str(b))
    assert ra.key == rb.key  # content-addressed: identical pixels, one blob
    assert len(list(images_dir.iterdir())) == 1


@pytest.mark.asyncio
async def test_dynamic_mode_recorded(tmp_path, images_dir):
    src = _make_png(tmp_path / "shot.png")
    await vision(mode="file", path=str(src))
    entries = pending()
    assert [(e.tool, e.mode, e.status, e.result_kind) for e in entries] == [
        ("vision", "file", "completed", "image")
    ]
    assert entries[0].llm_images == [{"key": entries[0].acp_payload["key"], "mime": "image/png"}]


@pytest.mark.asyncio
async def test_webcam_mode_stores_jpeg(images_dir, monkeypatch):
    """No physical camera in CI: stub the cv2 capture, keep everything real
    after it — encode, store, key, result, register entry."""
    import sys

    import numpy as np

    # `import crow_cli.tools.vision as vmod` would bind the FUNCTION: the
    # facade caches it into crow_cli.tools.__dict__, shadowing the submodule.
    vmod = sys.modules["crow_cli.tools.vision"]

    def fake_capture(device_index):
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        frame[:, :] = (9, 9, 9)
        h, w = frame.shape[:2]
        raw = vmod._encode(frame, "image/jpeg")
        return vmod._store(raw, "image/jpeg", w, h, f"webcam:{device_index}")

    monkeypatch.setattr(vmod, "_capture_webcam", fake_capture)
    result = await vmod.vision(mode="webcam", device_index=3)

    assert result.mime == "image/jpeg"
    assert result.source == "webcam:3"
    assert result.key.endswith(".jpg")
    assert (images_dir / result.key).exists()
    assert pending()[0].mode == "webcam"


@pytest.mark.asyncio
async def test_write_through_row_holds_refs(tmp_path, images_dir):
    from crow_cli.memory.models import SubtoolCall

    db_uri = f"sqlite:///{tmp_path}/crow.db"
    create_database(db_uri)
    begin_cell(
        session_id="s1",
        parent_tool_call_id="t/c",
        db_uri=db_uri,
        images_dir=str(images_dir),
    )
    src = _make_png(tmp_path / "shot.png")
    result = await vision(mode="file", path=str(src))

    engine = create_engine(db_uri)
    with sessionmaker(engine)() as session:
        rows = session.execute(select(SubtoolCall)).scalars().all()
        session.expunge_all()
    engine.dispose()
    assert len(rows) == 1
    row = rows[0]
    assert row.tool == "vision" and row.mode == "file"
    assert row.result_kind == "image"
    assert row.llm_images == [{"key": result.key, "mime": "image/png"}]
    assert row.acp_payload["key"] == result.key
    # Refs, never bytes: nothing image-sized in the row.
    assert len(str(row.acp_payload)) < 300


@pytest.mark.asyncio
async def test_file_errors_raise(tmp_path, images_dir):
    with pytest.raises(VisionError, match="not found"):
        await vision(mode="file", path=str(tmp_path / "ghost.png"))
    with pytest.raises(VisionError, match="directory"):
        await vision(mode="file", path=str(tmp_path))
    txt = tmp_path / "notes.txt"
    txt.write_text("hi")
    with pytest.raises(VisionError, match="unsupported image extension"):
        await vision(mode="file", path=str(txt))
    bad = tmp_path / "corrupt.png"
    bad.write_bytes(b"not a png at all")
    with pytest.raises(VisionError, match="failed to decode"):
        await vision(mode="file", path=str(bad))
    with pytest.raises(VisionError, match="requires path"):
        await vision(mode="file")
    # every failure recorded
    assert [e.status for e in pending()] == ["failed"] * 5


@pytest.mark.asyncio
async def test_unknown_mode_raises(tmp_path, images_dir):
    with pytest.raises(VisionError, match="unknown vision mode"):
        await vision(mode="video", path=str(tmp_path))


@pytest.mark.asyncio
async def test_no_store_raises(tmp_path):
    """begin_cell without images_dir: vision refuses rather than dropping
    bytes on the floor."""
    begin_cell(session_id="s1", parent_tool_call_id="t/c")
    src = _make_png(tmp_path / "shot.png")
    with pytest.raises(VisionError, match="no ImageStore"):
        await vision(mode="file", path=str(src))


def test_store_is_fs_by_design(tmp_path):
    begin_cell(images_dir=str(tmp_path / "img"))
    from crow_cli.tools.register import image_store

    store = image_store()
    assert isinstance(store, FsImageStore)
    store.put("k.png", b"x")
    assert store.get("k.png") == b"x"
