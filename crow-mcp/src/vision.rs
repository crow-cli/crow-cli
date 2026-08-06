//! Vision tools — webcam capture and image file reading (return MCP Image
//! content for the agent's vision path).

use crate::CrowMcpServer;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct CaptureWebcamParams {
    /// Webcam device index (default 6)
    #[serde(default = "default_device_index")]
    pub device_index: u32,
}

fn default_device_index() -> u32 { 6 }

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct ReadImageFileParams {
    /// Absolute path to the image file (jpg, jpeg, png, bmp, etc.)
    pub file_path: String,
}

#[tool_router(router = vision_router, vis = "pub")]
impl CrowMcpServer {
    /// Capture a frame from a webcam and return it as an image.
    #[tool(description = "Capture a single frame from a webcam. Returns a JPEG image. Use device_index to select which camera.")]
    async fn capture_webcam(
        &self,
        Parameters(params): Parameters<CaptureWebcamParams>,
    ) -> Result<CallToolResult, McpError> {
        let device_index = params.device_index;

        let result = tokio::task::spawn_blocking(move || {
            use nokhwa::{
                Camera,
                pixel_format::RgbFormat,
                utils::{CameraIndex, RequestedFormat, RequestedFormatType},
            };

            let index = CameraIndex::Index(device_index);
            let requested =
                RequestedFormat::new::<RgbFormat>(RequestedFormatType::AbsoluteHighestFrameRate);
            let mut camera = Camera::new(index, requested)
                .map_err(|e| format!("failed to open camera {device_index}: {e}"))?;
            camera.open_stream()
                .map_err(|e| format!("failed to start stream: {e}"))?;
            let frame = camera.frame()
                .map_err(|e| format!("failed to capture frame: {e}"))?;
            let img = frame.decode_image::<RgbFormat>()
                .map_err(|e| format!("failed to decode frame: {e}"))?;
            drop(camera);

            // Encode as JPEG
            let mut buf = std::io::Cursor::new(Vec::new());
            img.write_to(&mut buf, image::ImageFormat::Jpeg)
                .map_err(|e| format!("failed to encode JPEG: {e}"))?;
            Ok::<Vec<u8>, String>(buf.into_inner())
        })
        .await
        .map_err(|e| McpError::internal_error(format!("task join error: {e}"), None))?
        .map_err(|e| McpError::internal_error(e, None))?;

        let b64 = base64::Engine::encode(&base64::engine::general_purpose::STANDARD, &result);

        Ok(CallToolResult::success(vec![ContentBlock::Image(
            ImageContent::new(b64, "image/jpeg"),
        )]))
    }

    /// Read an image from a file path and return it for vision analysis.
    #[tool(description = "Read an image from a file path and return it for vision analysis.")]
    async fn read_image_file(
        &self,
        Parameters(params): Parameters<ReadImageFileParams>,
    ) -> Result<CallToolResult, McpError> {
        let path = std::path::Path::new(&params.file_path);
        if !path.exists() {
            return Err(McpError::invalid_params(
                format!("Image file not found: {}", params.file_path),
                None,
            ));
        }
        let img = image::open(path).map_err(|e| {
            McpError::invalid_params(
                format!(
                    "Failed to read image file: {} (invalid format or corrupted): {e}",
                    params.file_path
                ),
                None,
            )
        })?;

        let ext = path
            .extension()
            .and_then(|e| e.to_str())
            .map(|e| e.to_lowercase())
            .unwrap_or_default();
        let (format, mime) = match ext.as_str() {
            "png" => (image::ImageFormat::Png, "image/png"),
            _ => (image::ImageFormat::Jpeg, "image/jpeg"),
        };
        let mut buf = std::io::Cursor::new(Vec::new());
        img.write_to(&mut buf, format)
            .map_err(|e| McpError::internal_error(format!("Failed to encode image: {e}"), None))?;
        let b64 =
            base64::Engine::encode(&base64::engine::general_purpose::STANDARD, buf.into_inner());
        Ok(CallToolResult::success(vec![ContentBlock::Image(
            ImageContent::new(b64, mime),
        )]))
    }
}
