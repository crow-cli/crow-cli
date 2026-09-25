"""vision — capture images into the session ImageStore.

Modes:
- ``file``    — read an image from disk (normalizes like the old
  read_image_file MCP tool: decode, cap at the 1568px vision-model tile
  ceiling, re-encode in the file's format).
- ``webcam``  — capture one frame (the old capture_webcam tool: V4L2,
  MJPG forced for UVC cameras, warm-up frames for auto-exposure). This
  mode is first-class — it is the door to robotics; it never gets dropped.
- ``video``   — later: the video-frames skill as a mode (frame extraction
  -> N file results).

Bytes go to the ImageStore at CALL time, keyed ``<sha256hex><ext>`` (same
scheme as messages.extract_images — dupes dedupe free, and the server's
HybridReadStore read-fallback means kernel-written blobs hydrate even when
the server stores to S3). The VisionResult, the register entry, and the
subtool_calls row all hold refs, never bytes.
"""

import asyncio
import os

from .register import image_store, subtool
from .results import VisionError, VisionResult

# The old MCP tool's ceiling: full-res screenshots re-encoded produce
# multi-MB base64 results; 1568px is the standard vision-model tile size.
_MAX_DIM = 1568

_EXT_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
}


def _encode(frame, mime: str) -> bytes:
    import cv2

    ext = ".png" if mime == "image/png" else ".jpg"
    ok, buf = cv2.imencode(ext, frame)
    if not ok:
        raise VisionError(f"failed to encode image as {ext}")
    return buf.tobytes()


def _cap_resolution(frame):
    import cv2

    h, w = frame.shape[:2]
    if max(h, w) > _MAX_DIM:
        scale = _MAX_DIM / max(h, w)
        frame = cv2.resize(
            frame,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )
    return frame


def _store(raw: bytes, mime: str, width: int, height: int, source: str) -> VisionResult:
    from crow_cli.memory.messages import image_key

    store = image_store()
    if store is None:
        raise VisionError(
            "no ImageStore configured for this kernel (begin_cell got no "
            "images_dir) — vision needs the server-injected store"
        )
    key = image_key(raw, mime)
    store.put(key, raw)
    return VisionResult(key=key, mime=mime, width=width, height=height, source=source)


def _capture_file(path: str) -> VisionResult:
    import cv2

    if not os.path.exists(path):
        raise VisionError(f"image file not found: {path}")
    if os.path.isdir(path):
        raise VisionError(f"is a directory, not an image: {path}")
    ext = os.path.splitext(path)[1].lower()
    mime = _EXT_MIME.get(ext)
    if mime is None:
        raise VisionError(
            f"unsupported image extension {ext!r} — expected one of "
            f"{', '.join(sorted(_EXT_MIME))}"
        )
    frame = cv2.imread(path)
    if frame is None:
        raise VisionError(f"failed to decode image (corrupted?): {path}")
    frame = _cap_resolution(frame)
    h, w = frame.shape[:2]
    # Re-encode even when uncapped: normalizes exotic formats and strips
    # metadata, and the key addresses the bytes the LLM will actually see.
    raw = _encode(frame, mime)
    return _store(raw, mime, w, h, path)


def _capture_webcam(device_index: int) -> VisionResult:
    import cv2

    cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2)
    if not cap.isOpened():
        raise VisionError(f"failed to open webcam at index {device_index}")
    try:
        # Generic UVC cameras often only expose MJPG and return black
        # frames at OpenCV's default pixel format — force MJPG + 480p.
        cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        cap.set(cv2.CAP_PROP_FPS, 30)
        # Discard a few frames so auto-exposure/gain settles.
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
    finally:
        cap.release()
    if not ret or frame is None or frame.size == 0:
        raise VisionError(f"failed to capture frame from webcam {device_index}")
    h, w = frame.shape[:2]
    raw = _encode(frame, "image/jpeg")
    return _store(raw, "image/jpeg", w, h, f"webcam:{device_index}")


@subtool(tool="vision")
async def vision(
    mode: str,
    path: str | None = None,
    device_index: int = 6,
) -> VisionResult:
    """Capture an image into the session ImageStore; returns a VisionResult.

    Args:
        mode: "file" (read from disk) or "webcam" (capture one frame).
        path: image path — required for mode="file" (jpg/jpeg/png/bmp/webp).
        device_index: webcam device index — mode="webcam" only (default 6).

    Returns:
        VisionResult — .key (ImageStore ref), .mime, .width, .height,
        .source. The llm_images refs on the register entry tell the
        server-side drain to prepend hydrated image blocks to execute's
        output — the only LLM-side modification that exists; the client
        sees a real image block on the sibling tool call.

    Raises:
        VisionError: bad mode/path, undecodable file, no store, dead webcam.
    """
    if mode == "file":
        if not path:
            raise VisionError("mode='file' requires path=")
        # cv2 is blocking C — keep the kernel's loop responsive.
        return await asyncio.to_thread(_capture_file, path)
    if mode == "webcam":
        return await asyncio.to_thread(_capture_webcam, int(device_index))
    raise VisionError(f"unknown vision mode {mode!r} — expected 'file' or 'webcam'")
