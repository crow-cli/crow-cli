# crow-vision-mcp

Vision capabilities for crow-cli via MCP.

## Tools

### `capture_webcam(device_index: int = 6) -> Image`
Capture a single frame from a webcam device.

**Args:**
- `device_index`: Webcam device index (default: 6)

### `read_image_file(file_path: str) -> Image`
Read an image from a file path for vision analysis.

**Args:**
- `file_path`: Absolute path to the image file (jpg, jpeg, png, bmp, etc.)

## Usage

```bash
# Run the server
uv --project /home/thomas/src/crow-cli/crow-vision-mcp run python main.py

# Or with MCP client
uv run mcp-stdio -- server.py
```

## Example

```python
# From a crow-cli agent
result = await mcp_client.call_tool("read_image_file", {"file_path": "/path/to/screenshot.png"})
# Returns image data that can be sent to vision-capable LLM
```

## Supported Formats

- JPEG/JPG
- PNG
- BMP (converted to JPEG for transmission)
- Any format OpenCV can read
