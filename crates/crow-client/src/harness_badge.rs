//! A session-scoped Registry icon, decoded once when its slot snapshot changes.
use std::sync::Arc;
use crate::slots::{SlotSnapshot, TuiNode};

pub struct Badge {
    pub session: String,
    pub name: String,
    pub pixels: Option<Arc<[u8]>>,
    pub image_id: u32,
}

pub fn parse(snapshot: &SlotSnapshot) -> Option<Badge> {
    let [TuiNode::Image { id, name, mime, data_base64 }] = snapshot.nodes.as_slice() else { return None };
    let session = id.split_once(':')?.1.to_owned();
    let pixels = data_base64.as_ref().filter(|data| data.len() <= 700_000)
        .filter(|_| mime == "image/png")
        .and_then(|data| crate::pet::decode_base64(data))
        .filter(|bytes| crate::pet::image_dims(bytes).is_some_and(|(w,h)| w > 0 && h > 0 && w <= 256 && h <= 256))
        .filter(|bytes| image::load_from_memory(bytes).is_ok())
        .map(Arc::<[u8]>::from);
    // Distinct images need distinct Kitty ids, including a changed Registry URL.
    use std::hash::{Hash, Hasher};
    let mut hash = std::collections::hash_map::DefaultHasher::new();
    pixels.hash(&mut hash);
    let image_id = 0x6000_0000 | (hash.finish() as u32 & 0x0fff_ffff);
    Some(Badge { session, name: name.clone(), pixels, image_id })
}
