//! settings_io: extracted verbatim from src/app.rs (Phase 1 split).

use super::*;

/// The settings document to patch: the parsed file when it is an object,
/// otherwise `{}`.
///
/// The same file carries compositor-owned keys (`uiPreset`, the harness recipes)
/// alongside the painter's own, so every writer patches the parsed document
/// rather than serializing a schema — an unknown key survives a theme change.
/// A file that exists but does not parse is quarantined for recovery instead of
/// being silently replaced.
pub(crate) fn settings_document(path: &std::path::Path) -> serde_json::Value {
    let existing = std::fs::read_to_string(path).ok();
    match existing
        .as_deref()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(text).ok())
        .filter(serde_json::Value::is_object)
    {
        Some(value) => value,
        None => {
            if existing
                .as_deref()
                .is_some_and(|text| !text.trim().is_empty())
            {
                let _ = std::fs::rename(path, quarantined_settings_path(path));
            }
            serde_json::json!({})
        }
    }
}

/// Point `defaultHarness` at `id`, preserving every other key.
///
/// Written before the switch is requested, not after: a respawn that succeeds
/// while the file still names the old recipe would come back as the old harness
/// on the next launch, and the npm host would disagree with the running pane.
pub(crate) fn persist_default_harness(path: &std::path::Path, id: &str) -> std::io::Result<()> {
    let mut settings = settings_document(path);
    settings["defaultHarness"] = serde_json::json!(id);
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let text = serde_json::to_string_pretty(&settings)
        .map_err(|err| std::io::Error::new(std::io::ErrorKind::InvalidData, err))?;
    write_settings_atomic(path, &text)
}

/// `settings.json` → `settings.json.corrupt-<timestamp>`, preserving a file
/// that exists but cannot be parsed for manual recovery.
pub(crate) fn quarantined_settings_path(path: &std::path::Path) -> std::path::PathBuf {
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    path.with_file_name(format!("{name}.corrupt-{}", timestamp()))
}

/// Write `text` to `path` through a same-directory temporary file plus a
/// rename: a crash or full disk can never leave a truncated settings.json
/// (the painter and the compositor both write this file).
pub(crate) fn write_settings_atomic(path: &std::path::Path, text: &str) -> std::io::Result<()> {
    let name = path.file_name().unwrap_or_default().to_string_lossy();
    let tmp = path.with_file_name(format!(
        "{name}.{}.{}.tmp",
        std::process::id(),
        timestamp()
    ));
    if let Err(err) = std::fs::write(&tmp, text) {
        let _ = std::fs::remove_file(&tmp);
        return Err(err);
    }
    if let Err(err) = std::fs::rename(&tmp, path) {
        let _ = std::fs::remove_file(&tmp);
        return Err(err);
    }
    Ok(())
}
