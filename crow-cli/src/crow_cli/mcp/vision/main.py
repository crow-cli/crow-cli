import os
from datetime import datetime

import cv2
from fastmcp import FastMCP
from fastmcp.utilities.types import Image

from crow_cli.mcp.server.app import mcp


@mcp.tool
def capture_webcam(device_index: int = 6) -> Image:
    """Capture a single frame from webcam.

    Args:
        device_index: Webcam device index (default: 6)
    """
    cap = cv2.VideoCapture(device_index, cv2.CAP_V4L2)

    if not cap.isOpened():
        raise ValueError(f"❌ Failed to open webcam at index {device_index}")

    # Some UVC cameras (e.g. the generic "USB Camera" on this machine) only
    # expose MJPG formats and will return black frames if OpenCV's default
    # pixel format is used. Force MJPG + 480p before reading.
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    cap.set(cv2.CAP_PROP_FPS, 30)

    # Warm-up: discard a few frames so auto-exposure/gain can settle.
    for _ in range(5):
        cap.read()

    ret, frame = cap.read()
    cap.release()

    if not ret or frame is None or frame.size == 0:
        raise RuntimeError("❌ Failed to capture frame from webcam")

    # 1. Encode the OpenCV matrix (NumPy array) into a JPEG buffer
    success, buffer = cv2.imencode(".jpg", frame)
    if not success:
        raise RuntimeError("❌ Failed to encode frame to JPEG")

    # 2. Convert the memory buffer to raw bytes
    image_bytes = buffer.tobytes()

    # 3. Pass the raw bytes and specify the format to FastMCP
    return Image(data=image_bytes, format="jpeg")


@mcp.tool
def read_image_file(file_path: str) -> Image:
    """Read an image from a file path and return it for vision analysis.

    Args:
        file_path: Absolute path to the image file (jpg, jpeg, png, bmp, etc.)
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"❌ Image file not found: {file_path}")

    # Read the image file
    frame = cv2.imread(file_path)

    if frame is None:
        raise RuntimeError(
            f"❌ Failed to read image file: {file_path} (invalid format or corrupted)"
        )

    # Cap resolution: full-res screenshots re-encoded here produce multi-MB
    # base64 tool results. 1568px is the standard vision-model tile ceiling,
    # so nothing is lost for analysis.
    max_dim = 1568
    h, w = frame.shape[:2]
    if max(h, w) > max_dim:
        scale = max_dim / max(h, w)
        frame = cv2.resize(
            frame,
            (int(w * scale), int(h * scale)),
            interpolation=cv2.INTER_AREA,
        )

    # Determine format from file extension
    ext = os.path.splitext(file_path)[1].lower()
    if ext in [".jpg", ".jpeg"]:
        format_type = "jpeg"
        success, buffer = cv2.imencode(".jpg", frame)
    elif ext == ".png":
        format_type = "png"
        success, buffer = cv2.imencode(".png", frame)
    else:
        # Default to JPEG for other formats
        format_type = "jpeg"
        success, buffer = cv2.imencode(".jpg", frame)

    if not success:
        raise RuntimeError(f"❌ Failed to encode image: {file_path}")

    image_bytes = buffer.tobytes()
    return Image(data=image_bytes, format=format_type)


if __name__ == "__main__":
    mcp.run()
