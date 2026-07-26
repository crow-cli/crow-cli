"""Tests for the vision read_image_file tool (no camera required).

capture_webcam needs real hardware and is intentionally not tested here; its
@mcp.tool registration is covered by test_server.py.
"""

import pytest

cv2 = pytest.importorskip("cv2")
np = pytest.importorskip("numpy")

from crow_mcp.vision.main import read_image_file


def _make_image(path):
    img = np.zeros((16, 16, 3), dtype=np.uint8)
    img[:] = (0, 0, 255)  # solid red
    assert cv2.imwrite(str(path), img)
    return path


class TestReadImageFile:
    def test_read_png(self, tmp_path):
        p = _make_image(tmp_path / "img.png")
        image = read_image_file(str(p))
        # Assert on the stable public surface (to_data_uri), not the private
        # _format attr — this must keep working across the fastmcp upgrade.
        assert image.to_data_uri().startswith("data:image/png;base64,")
        assert len(image.data) > 0

    def test_read_jpeg(self, tmp_path):
        p = _make_image(tmp_path / "img.jpg")
        image = read_image_file(str(p))
        assert "image/jpeg" in image.to_data_uri()
        assert len(image.data) > 0

    def test_missing_file_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_image_file(str(tmp_path / "nope.png"))


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
