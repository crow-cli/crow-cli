//! End-to-end: real axum server on a temp LanceDB + real HTTP + the SDK,
//! exercising the images table. No mocks — wire contract test.

use std::sync::Arc;

// Minimal valid PNGs (generated with stdlib zlib): 1x1 RGBA and 2x2 RGB.
// 68 bytes (len % 3 == 2) — exercises the '='-padded base64 path.
const PNG_1X1: &[u8] = &[
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44,
    0x52, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x00, 0x01, 0x08, 0x06, 0x00, 0x00, 0x00, 0x1f,
    0x15, 0xc4, 0x89, 0x00, 0x00, 0x00, 0x0b, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0x60,
    0x00, 0x02, 0x00, 0x00, 0x05, 0x00, 0x01, 0x7a, 0x5e, 0xab, 0x3f, 0x00, 0x00, 0x00, 0x00,
    0x49, 0x45, 0x4e, 0x44, 0xae, 0x42, 0x60, 0x82,
];
const PNG_2X2: &[u8] = &[
    0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0x00, 0x00, 0x00, 0x0d, 0x49, 0x48, 0x44,
    0x52, 0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02, 0x08, 0x02, 0x00, 0x00, 0x00, 0xfd,
    0xd4, 0x9a, 0x73, 0x00, 0x00, 0x00, 0x14, 0x49, 0x44, 0x41, 0x54, 0x78, 0x9c, 0x63, 0xf8,
    0xcf, 0xc0, 0xc0, 0x00, 0xc2, 0x0c, 0xff, 0xff, 0xff, 0x67, 0x00, 0x00, 0x1e, 0xef, 0x04,
    0xfc, 0xa3, 0xc8, 0xb4, 0xf7, 0x00, 0x00, 0x00, 0x00, 0x49, 0x45, 0x4e, 0x44, 0xae, 0x42,
    0x60, 0x82,
];

async fn spawn_server() -> crow_memory_sdk::MemoryClient {
    let tmp = std::env::temp_dir().join(format!(
        "crow-memory-test-{}-{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap()
            .as_nanos()
    ));
    let store = crow_memory::MemoryStore::open(&tmp, crow_memory::EmbedConfig::default())
        .await
        .unwrap();
    let app = crow_memory::router(Arc::new(store));
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let addr = listener.local_addr().unwrap();
    tokio::spawn(async move {
        axum::serve(listener, app).await.unwrap();
    });
    crow_memory_sdk::MemoryClient::connect(format!("http://{addr}"))
}

#[tokio::test]
async fn image_round_trip() {
    let client = spawn_server().await;
    client.health().await.unwrap();

    client
        .add_image("img-1", "image/png", PNG_1X1, 1, 1)
        .await
        .unwrap();
    let img = client.get_image("img-1").await.unwrap().expect("image exists");
    assert_eq!(img.image_id, "img-1");
    assert_eq!(img.mime, "image/png");
    assert_eq!(img.w, 1);
    assert_eq!(img.h, 1);
    assert_eq!(img.data, PNG_1X1, "bytes must survive the round trip exactly");
    assert!(!img.created_at.is_empty());

    // A second image with different dims; both coexist.
    client
        .add_image("img-2", "image/jpeg", PNG_2X2, 2, 2)
        .await
        .unwrap();
    let img2 = client.get_image("img-2").await.unwrap().expect("image exists");
    assert_eq!(img2.mime, "image/jpeg");
    assert_eq!((img2.w, img2.h), (2, 2));
    assert_eq!(img2.data, PNG_2X2);
    // First image untouched.
    let again = client.get_image("img-1").await.unwrap().expect("image exists");
    assert_eq!(again.data, PNG_1X1);
}

#[tokio::test]
async fn image_missing_is_none() {
    let client = spawn_server().await;
    client.health().await.unwrap();
    assert!(client.get_image("ghost-image").await.unwrap().is_none());
}
