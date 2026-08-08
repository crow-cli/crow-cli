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

async fn spawn_server() -> (crow_memory_sdk::MemoryClient, std::path::PathBuf) {
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
    (
        crow_memory_sdk::MemoryClient::connect(format!("http://{addr}")),
        tmp,
    )
}

#[tokio::test]
async fn image_round_trip() {
    let (client, _tmp) = spawn_server().await;
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
    let (client, _tmp) = spawn_server().await;
    client.health().await.unwrap();
    assert!(client.get_image("ghost-image").await.unwrap().is_none());
}

// base64 of PNG_1X1, and its sha256 (content-addressed image_id).
const PNG_1X1_B64: &str = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgAAIAAAUAAXpeqz8AAAAASUVORK5CYII=";
const PNG_1X1_ID: &str =
    "sha256:43739c566e26fd7cb88f69d3864ea34740372f5ee99acac169e090beffbce5c6";

/// End-to-end image persistence: inline base64 goes in, image_ref comes out
/// of the store, the images table row is keyed sha256:<hex>, identical bytes
/// dedupe to one row, and a hydrated load hands back the exact data URL.
#[tokio::test]
async fn message_image_extract_dedupe_hydrate() {
    let (client, tmp) = spawn_server().await;
    client.health().await.unwrap();

    // OpenAI-style inline image (data URL in an image_url block).
    let msg = serde_json::json!({
        "role": "user",
        "content": [
            {"type": "text", "text": "what is this?"},
            {"type": "image_url", "image_url": {"url": format!("data:image/png;base64,{PNG_1X1_B64}")}},
        ],
    });
    client.add_message("img-agent-1", &msg, None).await.unwrap();

    // Stored `data` carries an image_ref, not the base64 blob.
    let raw = client.load_messages("img-agent-1", false).await.unwrap();
    assert_eq!(raw.len(), 1);
    let content = raw[0]["content"].as_array().expect("array content");
    assert_eq!(content[0]["type"], "text");
    assert_eq!(content[1]["type"], "image_ref");
    assert_eq!(content[1]["image_id"], PNG_1X1_ID);
    assert_eq!(content[1]["mime"], "image/png");
    assert!(
        !raw[0].to_string().contains("iVBORw0KGgo"),
        "base64 payload must not be persisted in message data"
    );

    // Images table row keyed by sha256:, bytes exact.
    let img = client
        .get_image(PNG_1X1_ID)
        .await
        .unwrap()
        .expect("image row exists");
    assert_eq!(img.mime, "image/png");
    assert_eq!(img.data, PNG_1X1, "bytes must survive exactly");

    // Same bytes again, ACP-style block this time → still ONE row.
    let msg2 = serde_json::json!({
        "role": "user",
        "content": [
            {"type": "image", "data": PNG_1X1_B64, "mimeType": "image/png"},
        ],
    });
    client.add_message("img-agent-1", &msg2, None).await.unwrap();
    let db = lancedb::connect(tmp.to_str().unwrap())
        .execute()
        .await
        .unwrap();
    let images = db.open_table("images").execute().await.unwrap();
    assert_eq!(
        images.count_rows(None).await.unwrap(),
        1,
        "identical bytes must dedupe to one images row"
    );

    // Hydrated load: image_ref → inline data URL, bytes identical.
    let hydrated = client.load_messages("img-agent-1", true).await.unwrap();
    assert_eq!(hydrated.len(), 2);
    let want_url = format!("data:image/png;base64,{PNG_1X1_B64}");
    assert_eq!(hydrated[0]["content"][1]["type"], "image_url");
    assert_eq!(hydrated[0]["content"][1]["image_url"]["url"], want_url);
    assert_eq!(hydrated[1]["content"][0]["type"], "image_url");
    assert_eq!(hydrated[1]["content"][0]["image_url"]["url"], want_url);

    // Non-hydrated load still shows the refs (read-side only).
    let raw_again = client.load_messages("img-agent-1", false).await.unwrap();
    assert_eq!(raw_again[1]["content"][0]["type"], "image_ref");
}
