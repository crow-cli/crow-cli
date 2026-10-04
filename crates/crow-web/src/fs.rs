//! The filesystem authority: open buffers (content + dirty + mtime) and the
//! disk operations the `/fs` websocket exposes.
//!
//! The browser is a view; this module owns the state it views. A path has at
//! most one buffer no matter how many tabs or clients opened it, the buffer —
//! not the disk — is authoritative from `open` until `close`, and unsaved work
//! outlives the client that typed it: a buffer is dropped only when its last
//! holder left it clean.
use std::collections::{HashMap, HashSet};
use std::io::ErrorKind;
use std::path::{Component, Path, PathBuf};
use std::time::SystemTime;

use anyhow::{anyhow, bail, Context, Result};
use serde::Serialize;

/// Refuse to pull anything bigger than this into a code buffer. A stray log or
/// a `target/` artifact should be an error message, not a frozen editor.
pub const MAX_FILE_BYTES: u64 = 8 << 20;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "lowercase")]
pub enum EntryKind {
    Dir,
    File,
}

/// One row of a lazy directory listing.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Entry {
    pub name: String,
    /// Root-relative path a client sends back to ask for more.
    pub path: String,
    #[serde(rename = "type")]
    pub kind: EntryKind,
    /// `None` for directories and for entries whose metadata could not be read.
    pub size: Option<u64>,
    pub mtime: Option<i64>,
    /// True when the server holds unsaved work for exactly this path.
    pub dirty: bool,
}

/// One level of the tree — the explorer expands lazily, so the server never
/// walks a whole repository.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct Tree {
    /// `""` for the root.
    pub path: String,
    pub entries: Vec<Entry>,
}

/// What a client sees: the whole truth about one path.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct FileView {
    /// Normalized root-relative path, `/`-separated — the buffer key.
    pub path: String,
    pub content: String,
    pub dirty: bool,
    /// Unix millis of the last disk state this buffer agrees with. `None` means
    /// the file does not exist on disk yet (a commit creates it).
    pub mtime: Option<i64>,
}

#[derive(Debug, Clone)]
struct Buffer {
    content: String,
    dirty: bool,
    mtime: Option<SystemTime>,
}

/// What a `close` did, which is what the other tabs need to know.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize)]
#[serde(rename_all = "snake_case", tag = "state")]
pub enum Close {
    /// Another client still holds the path, or it has unsaved work: the buffer
    /// stays exactly as it was.
    Kept { dirty: bool },
    /// The last holder left with nothing unsaved: the buffer is gone and the
    /// next read comes off the disk again.
    Dropped,
}

/// The registry. One per served root, shared by every connection.
///
/// Clients are identified by a u64 handed out by the connection handler. A
/// buffer lives while any client holds its path open, and past the last one
/// only if it is dirty — so a tab closing never yanks the buffer out from
/// under another tab, and a browser crashing never takes unsaved work with it.
#[derive(Debug)]
pub struct Buffers {
    root: PathBuf,
    map: HashMap<PathBuf, Buffer>,
    holders: HashMap<PathBuf, HashSet<u64>>,
}

/// Rejects anything that is not a plain root-relative path: absolute paths,
/// `..` that climbs out, and the root itself. Symlinks *inside* the root are
/// followed — the server binds loopback and serves one user's own tree.
pub fn normalize(rel: &str) -> Result<PathBuf> {
    let mut out = PathBuf::new();
    for component in Path::new(rel).components() {
        match component {
            Component::CurDir => {}
            Component::Normal(name) => out.push(name),
            Component::ParentDir => {
                if !out.pop() {
                    bail!("path escapes the root: {rel:?}");
                }
            }
            other => bail!("path escapes the root: {rel:?} ({other:?})"),
        }
    }
    if out.as_os_str().is_empty() {
        bail!("path is the root itself: {rel:?}");
    }
    Ok(out)
}

/// Like [`normalize`], but `""` and `"."` mean the served root — the shape a
/// lazy tree request arrives in.
pub fn normalize_dir(rel: &str) -> Result<PathBuf> {
    if rel.is_empty() || rel == "." {
        return Ok(PathBuf::new());
    }
    normalize(rel)
}

fn millis(mtime: Option<SystemTime>) -> Option<i64> {
    Some(
        mtime?
            .duration_since(SystemTime::UNIX_EPOCH)
            .map_err(|e| anyhow!("mtime before the epoch: {e}"))
            .ok()?
            .as_millis() as i64,
    )
}

fn disk_mtime(abs: &Path) -> Option<SystemTime> {
    std::fs::metadata(abs).and_then(|m| m.modified()).ok()
}

impl Buffers {
    pub fn new(root: impl Into<PathBuf>) -> Result<Self> {
        let root = root
            .into()
            .canonicalize()
            .context("canonicalize the served root")?;
        if !root.is_dir() {
            bail!("{} is not a directory", root.display());
        }
        Ok(Self {
            root,
            map: HashMap::new(),
            holders: HashMap::new(),
        })
    }

    /// Reads the disk exactly once, at open. A buffer that already exists wins:
    /// that is what "the server owns the state" means for a second tab, a
    /// second client, or a reconnect. Records this client as a holder.
    pub fn open(&mut self, client: u64, rel: &str) -> Result<FileView> {
        let path = normalize(rel)?;
        if !self.map.contains_key(&path) {
            let abs = self.root.join(&path);
            let meta = match std::fs::metadata(&abs) {
                Ok(meta) => meta,
                Err(e) if e.kind() == ErrorKind::NotFound => {
                    bail!("no such file: {}", path.display())
                }
                Err(e) => return Err(e).with_context(|| format!("stat {}", abs.display())),
            };
            if meta.is_dir() {
                bail!("{} is a directory", path.display());
            }
            if meta.len() > MAX_FILE_BYTES {
                bail!(
                    "{} is {} bytes; a code buffer holds at most {MAX_FILE_BYTES}",
                    path.display(),
                    meta.len()
                );
            }
            let content = std::fs::read_to_string(&abs).with_context(|| {
                format!("read {} (a code buffer holds text only)", abs.display())
            })?;
            self.map.insert(
                path.clone(),
                Buffer {
                    content,
                    dirty: false,
                    mtime: meta.modified().ok(),
                },
            );
        }
        self.claim(client, &path);
        Ok(self.view(&path))
    }

    /// Editor keystrokes land here: content in, dirty flag up, disk untouched
    /// until a commit. Writing a path that is not on disk yet is how "new file"
    /// works — its `mtime` stays `None` until the first commit.
    pub fn write(&mut self, client: u64, rel: &str, content: String) -> Result<FileView> {
        let path = normalize(rel)?;
        let mtime = match self.map.get(&path) {
            Some(buffer) => buffer.mtime,
            None => disk_mtime(&self.root.join(&path)),
        };
        self.map.insert(
            path.clone(),
            Buffer {
                content,
                dirty: true,
                mtime,
            },
        );
        self.claim(client, &path);
        Ok(self.view(&path))
    }

    /// Ctrl+S: the only path that touches the disk. Clears dirty and adopts the
    /// mtime the write produced.
    pub fn commit(&mut self, rel: &str) -> Result<FileView> {
        let path = normalize(rel)?;
        let abs = self.root.join(&path);
        let content = self
            .map
            .get(&path)
            .map(|buffer| buffer.content.clone())
            .ok_or_else(|| anyhow!("no open buffer for {}", path.display()))?;
        std::fs::write(&abs, &content).with_context(|| format!("commit {}", abs.display()))?;
        let buffer = self.map.get_mut(&path).expect("checked above");
        buffer.dirty = false;
        buffer.mtime = disk_mtime(&abs);
        let view = self.view(&path);
        // Saving can empty the reason to keep a buffer: if nobody holds the
        // path any more, the disk is the authority again.
        self.settle(&path);
        Ok(view)
    }

    /// One client lets go of a path. The buffer survives if anyone else still
    /// holds it or if it is dirty; otherwise it is dropped and the disk becomes
    /// the authority again.
    pub fn close(&mut self, client: u64, rel: &str) -> Result<Close> {
        let path = normalize(rel)?;
        if !self.map.contains_key(&path) {
            bail!("no open buffer for {}", path.display());
        }
        self.release(client, &path);
        Ok(self.settle(&path))
    }

    /// A socket went away: give up every claim it held and report the paths
    /// whose buffers that dropped, so the remaining clients can be told.
    pub fn disconnect(&mut self, client: u64) -> Vec<String> {
        let held: Vec<PathBuf> = self
            .holders
            .iter()
            .filter(|(_, holders)| holders.contains(&client))
            .map(|(path, _)| path.clone())
            .collect();
        let mut dropped = Vec::new();
        for path in held {
            self.release(client, &path);
            if self.settle(&path) == Close::Dropped {
                dropped.push(display(&path));
            }
        }
        dropped.sort();
        dropped
    }

    fn claim(&mut self, client: u64, path: &Path) {
        self.holders
            .entry(path.to_path_buf())
            .or_default()
            .insert(client);
    }

    fn release(&mut self, client: u64, path: &Path) {
        if let Some(holders) = self.holders.get_mut(path) {
            holders.remove(&client);
            if holders.is_empty() {
                self.holders.remove(path);
            }
        }
    }

    /// The lifetime rule in one place: a buffer with no holders lives on only
    /// when it holds unsaved work.
    fn settle(&mut self, path: &Path) -> Close {
        let dirty = self.map.get(path).is_some_and(|buffer| buffer.dirty);
        if dirty || self.holders.contains_key(path) {
            Close::Kept { dirty }
        } else {
            self.map.remove(path);
            Close::Dropped
        }
    }

    /// One level of the tree, directories first. `rel` may be `""` for the
    /// root. Entries carry the buffer's dirty flag so the explorer can mark a
    /// file the server holds unsaved work for.
    pub fn list_dir(&self, rel: &str) -> Result<Tree> {
        let dir = normalize_dir(rel)?;
        let abs = self.root.join(&dir);
        let mut entries = Vec::new();
        for entry in std::fs::read_dir(&abs).with_context(|| format!("list {}", abs.display()))? {
            let entry = entry.with_context(|| format!("list {}", abs.display()))?;
            let name = entry.file_name().to_string_lossy().into_owned();
            let path = dir.join(&name);
            // metadata() follows symlinks, so a link to a directory expands;
            // a dangling one falls back to lstat and lists as a plain file.
            let meta = std::fs::metadata(entry.path())
                .or_else(|_| std::fs::symlink_metadata(entry.path()));
            let (kind, size, mtime) = match meta {
                Ok(meta) if meta.is_dir() => (EntryKind::Dir, None, millis(meta.modified().ok())),
                Ok(meta) => (
                    EntryKind::File,
                    Some(meta.len()),
                    millis(meta.modified().ok()),
                ),
                Err(_) => (EntryKind::File, None, None),
            };
            let dirty = self.map.get(&path).is_some_and(|buffer| buffer.dirty);
            entries.push(Entry {
                name,
                path: display(&path),
                kind,
                size,
                mtime,
                dirty,
            });
        }
        entries.sort_by_key(|entry| {
            (
                entry.kind == EntryKind::File,
                entry.name.to_lowercase(),
                entry.name.clone(),
            )
        });
        Ok(Tree {
            path: display(&dir),
            entries,
        })
    }

    /// Creates a directory (and any missing parents). Refuses to overwrite.
    pub fn mkdir(&self, rel: &str) -> Result<()> {
        let path = normalize(rel)?;
        let abs = self.root.join(&path);
        if abs.exists() {
            bail!("{} already exists", path.display());
        }
        std::fs::create_dir_all(&abs).with_context(|| format!("mkdir {}", abs.display()))
    }

    /// Moves a file or directory, taking every buffer underneath it along:
    /// unsaved work must not be orphaned, and a dirty buffer left on the old
    /// key would resurrect the old path at the next commit.
    pub fn rename(&mut self, from: &str, to: &str) -> Result<()> {
        let src = normalize(from)?;
        let dst = normalize(to)?;
        let src_abs = self.root.join(&src);
        let dst_abs = self.root.join(&dst);
        if dst_abs.exists() || self.map.contains_key(&dst) {
            bail!("{} already exists", dst.display());
        }
        // A new file nobody has saved yet is only a dirty buffer: renaming it
        // re-keys the registry and leaves the disk alone, because there are no
        // bytes there to move.
        if std::fs::symlink_metadata(&src_abs).is_ok() {
            std::fs::rename(&src_abs, &dst_abs).with_context(|| {
                format!("rename {} -> {}", src_abs.display(), dst_abs.display())
            })?;
        } else if !self.map.contains_key(&src) {
            bail!("no such file: {}", src.display());
        }
        let moved: Vec<(PathBuf, PathBuf)> = self
            .map
            .keys()
            .filter(|key| key.starts_with(&src))
            .filter_map(|key| Some((key.clone(), dst.join(key.strip_prefix(&src).ok()?))))
            .collect();
        for (old, new) in moved {
            if let Some(buffer) = self.map.remove(&old) {
                self.map.insert(new.clone(), buffer);
            }
            if let Some(holders) = self.holders.remove(&old) {
                self.holders.insert(new, holders);
            }
        }
        Ok(())
    }

    /// Deletes a file or a directory tree, dropping the buffers with it — the
    /// user asked for those bytes to go away, so keeping a dirty buffer would
    /// only resurrect them at the next commit.
    pub fn delete(&mut self, rel: &str) -> Result<()> {
        let path = normalize(rel)?;
        let abs = self.root.join(&path);
        let meta =
            std::fs::symlink_metadata(&abs).with_context(|| format!("stat {}", abs.display()))?;
        if meta.is_dir() {
            std::fs::remove_dir_all(&abs).with_context(|| format!("delete {}", abs.display()))?;
        } else {
            std::fs::remove_file(&abs).with_context(|| format!("delete {}", abs.display()))?;
        }
        self.map.retain(|key, _| !key.starts_with(&path));
        self.holders.retain(|key, _| !key.starts_with(&path));
        Ok(())
    }

    /// Every path with a live buffer, for a client that just (re)connected.
    pub fn open_paths(&self) -> Vec<String> {
        let mut paths: Vec<String> = self.map.keys().map(|p| display(p)).collect();
        paths.sort();
        paths
    }

    /// The dirty/mtime echo the server pushes after any mutation.
    pub fn view_of(&self, rel: &str) -> Result<Option<FileView>> {
        let path = normalize(rel)?;
        Ok(self.map.get(&path).map(|_| self.view(&path)))
    }

    fn view(&self, path: &Path) -> FileView {
        let buffer = self.map.get(path).expect("callers hold the key");
        FileView {
            path: display(path),
            content: buffer.content.clone(),
            dirty: buffer.dirty,
            mtime: millis(buffer.mtime),
        }
    }
}

fn display(path: &Path) -> String {
    path.components()
        .map(|c| c.as_os_str().to_string_lossy().into_owned())
        .collect::<Vec<_>>()
        .join("/")
}

#[cfg(test)]
mod tests {
    use super::*;

    // Hand-rolled temp root: the repo deliberately has no tempfile dev-dep
    // (same pattern as crow-client's tests/unit/file_ref__tests.rs).
    struct TempRoot {
        path: PathBuf,
    }

    impl TempRoot {
        fn new(name: &str) -> Self {
            use std::sync::atomic::{AtomicU64, Ordering};
            static N: AtomicU64 = AtomicU64::new(0);
            let dir = std::env::temp_dir().join(format!(
                "crow-web-fs-{name}-{}-{}",
                std::process::id(),
                N.fetch_add(1, Ordering::Relaxed),
            ));
            let _ = std::fs::remove_dir_all(&dir);
            std::fs::create_dir_all(&dir).expect("create temp root");
            Self { path: dir }
        }

        /// Puts bytes on disk behind the registry's back.
        fn put(&self, rel: &str, content: &str) {
            let abs = self.path.join(rel);
            std::fs::create_dir_all(abs.parent().unwrap()).expect("parent");
            std::fs::write(&abs, content).expect("write fixture");
        }

        fn disk(&self, rel: &str) -> Option<String> {
            std::fs::read_to_string(self.path.join(rel)).ok()
        }

        fn exists(&self, rel: &str) -> bool {
            self.path.join(rel).exists()
        }
    }

    impl Drop for TempRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }

    fn registry(name: &str) -> (TempRoot, Buffers) {
        let root = TempRoot::new(name);
        let buffers = Buffers::new(&root.path).expect("registry");
        (root, buffers)
    }

    #[test]
    fn normalize_rejects_escapes_and_the_root() {
        for bad in ["../x", "/etc/passwd", "a/../../b", "", ".", "a/.."] {
            assert!(normalize(bad).is_err(), "{bad:?} should be rejected");
        }
        assert_eq!(normalize("a/./b.txt").unwrap(), PathBuf::from("a/b.txt"));
        assert_eq!(
            normalize("src/main.rs").unwrap(),
            PathBuf::from("src/main.rs")
        );
    }

    #[test]
    fn open_reads_disk_then_the_buffer_wins() {
        let (root, mut buffers) = registry("open");
        root.put("a.txt", "hello");
        let view = buffers.open(1, "a.txt").unwrap();
        assert_eq!(view.content, "hello");
        assert!(!view.dirty);
        assert!(view.mtime.is_some(), "an on-disk file has an mtime");
        assert_eq!(view.path, "a.txt");

        // The disk changes behind the registry's back; the open buffer is the
        // authority, so a second open returns what the server holds.
        root.put("a.txt", "changed on disk");
        assert_eq!(buffers.open(1, "a.txt").unwrap().content, "hello");
    }

    #[test]
    fn open_missing_file_is_an_error_not_an_empty_buffer() {
        let (_root, mut buffers) = registry("open-missing");
        let err = buffers.open(1, "nope.txt").unwrap_err().to_string();
        assert!(err.contains("no such file"), "{err}");
    }

    #[test]
    fn write_marks_dirty_and_leaves_the_disk_alone() {
        let (root, mut buffers) = registry("write");
        root.put("a.txt", "hello");
        buffers.open(1, "a.txt").unwrap();
        let view = buffers.write(1, "a.txt", "hello world".into()).unwrap();
        assert!(view.dirty);
        assert_eq!(view.content, "hello world");
        assert_eq!(root.disk("a.txt").unwrap(), "hello", "write must not save");
    }

    #[test]
    fn commit_saves_clears_dirty_and_refreshes_mtime() {
        let (root, mut buffers) = registry("commit");
        root.put("a.txt", "hello");
        let before = buffers.open(1, "a.txt").unwrap().mtime.unwrap();
        buffers.write(1, "a.txt", "committed".into()).unwrap();
        let view = buffers.commit("a.txt").unwrap();
        assert!(!view.dirty);
        assert_eq!(root.disk("a.txt").unwrap(), "committed");
        assert!(
            view.mtime.unwrap() >= before,
            "mtime should not go backwards"
        );
    }

    #[test]
    fn write_then_commit_creates_a_new_file() {
        let (root, mut buffers) = registry("create");
        root.put("sub/keep.txt", "");
        let view = buffers
            .write(1, "sub/new.txt", "born dirty".into())
            .unwrap();
        assert!(view.dirty);
        assert_eq!(view.mtime, None, "not on disk yet");
        assert!(!root.exists("sub/new.txt"));

        let view = buffers.commit("sub/new.txt").unwrap();
        assert!(!view.dirty);
        assert!(view.mtime.is_some());
        assert_eq!(root.disk("sub/new.txt").unwrap(), "born dirty");
    }

    #[test]
    fn commit_does_not_invent_directories() {
        let (_root, mut buffers) = registry("commit-nodir");
        buffers.write(1, "ghost/new.txt", "x".into()).unwrap();
        let err = buffers.commit("ghost/new.txt").unwrap_err().to_string();
        assert!(err.contains("commit"), "{err}");
    }

    #[test]
    fn close_drops_a_clean_buffer_so_the_disk_is_reread() {
        let (root, mut buffers) = registry("close-clean");
        root.put("a.txt", "one");
        buffers.open(1, "a.txt").unwrap();
        assert_eq!(
            buffers.close(1, "a.txt").unwrap(),
            Close::Dropped,
            "clean buffer is dropped"
        );
        assert!(buffers.view_of("a.txt").unwrap().is_none());

        root.put("a.txt", "two");
        assert_eq!(buffers.open(1, "a.txt").unwrap().content, "two");
    }

    #[test]
    fn close_keeps_a_dirty_buffer_past_the_client_that_typed_it() {
        let (root, mut buffers) = registry("close-dirty");
        root.put("a.txt", "original");
        // A client connects, types, and vanishes without a Ctrl+S.
        {
            let client = &mut buffers;
            client.open(1, "a.txt").unwrap();
            client.write(1, "a.txt", "unsaved work".into()).unwrap();
            assert_eq!(
                client.close(1, "a.txt").unwrap(),
                Close::Kept { dirty: true }
            );
        }
        assert_eq!(buffers.open_paths(), vec!["a.txt".to_string()]);
        let view = buffers.open(1, "a.txt").unwrap();
        assert_eq!(view.content, "unsaved work");
        assert!(view.dirty);
        assert_eq!(root.disk("a.txt").unwrap(), "original", "still not saved");
    }

    #[test]
    fn one_buffer_per_path_across_tabs() {
        let (root, mut buffers) = registry("tabs");
        root.put("a.txt", "hello");
        buffers.open(1, "a.txt").unwrap(); // tab one
        buffers
            .write(1, "a.txt", "typed in tab one".into())
            .unwrap();
        let tab_two = buffers.open(1, "./a.txt").unwrap(); // tab two, same path
        assert_eq!(tab_two.content, "typed in tab one");
        assert!(tab_two.dirty);
        assert_eq!(buffers.open_paths().len(), 1);
    }

    #[test]
    fn commit_and_close_need_an_open_buffer() {
        let (_root, mut buffers) = registry("no-buffer");
        assert!(buffers.commit("ghost.txt").is_err());
        assert!(buffers.close(1, "ghost.txt").is_err());
        assert!(buffers.view_of("../ghost.txt").is_err(), "still normalized");
    }

    #[test]
    fn list_dir_is_one_level_dirs_first_and_flags_dirty() {
        let (root, mut buffers) = registry("tree");
        root.put("README.md", "# hi");
        root.put("src/main.rs", "fn main() {}");
        root.put("src/fs.rs", "");
        std::fs::create_dir_all(root.path.join("empty")).unwrap();
        buffers.write(1, "src/main.rs", "edited".into()).unwrap();

        let tree = buffers.list_dir("").unwrap();
        assert_eq!(tree.path, "");
        let rows: Vec<(String, EntryKind, bool)> = tree
            .entries
            .iter()
            .map(|e| (e.name.clone(), e.kind, e.dirty))
            .collect();
        assert_eq!(
            rows,
            vec![
                ("empty".into(), EntryKind::Dir, false),
                ("src".into(), EntryKind::Dir, false),
                ("README.md".into(), EntryKind::File, false),
            ]
        );
        assert_eq!(tree.entries[2].path, "README.md");
        assert_eq!(tree.entries[2].size, Some(4));
        assert!(tree.entries[2].mtime.is_some());

        let src = buffers.list_dir("src").unwrap();
        assert_eq!(src.path, "src");
        assert_eq!(src.entries.len(), 2, "one level, not a recursive walk");
        let main = src.entries.iter().find(|e| e.name == "main.rs").unwrap();
        assert_eq!(main.path, "src/main.rs");
        assert!(main.dirty, "the explorer sees unsaved work");
        assert_eq!(
            main.size,
            Some(12),
            "size is the disk size, not the buffer's"
        );
        assert!(buffers.list_dir("README.md").is_err(), "not a directory");
        assert!(buffers.list_dir("../").is_err(), "no escaping");
    }

    #[test]
    fn mkdir_creates_parents_and_refuses_to_overwrite() {
        let (root, buffers) = registry("mkdir");
        buffers.mkdir("a/b/c").unwrap();
        assert!(root.path.join("a/b/c").is_dir());
        let err = buffers.mkdir("a/b/c").unwrap_err().to_string();
        assert!(err.contains("already exists"), "{err}");
        assert!(buffers.mkdir("../out").is_err());
    }

    #[test]
    fn rename_takes_the_buffer_with_it() {
        let (root, mut buffers) = registry("rename");
        root.put("old.txt", "old");
        buffers.open(1, "old.txt").unwrap();
        buffers.write(1, "old.txt", "unsaved".into()).unwrap();
        buffers.rename("old.txt", "new.txt").unwrap();

        assert!(!root.exists("old.txt"));
        assert_eq!(root.disk("new.txt").unwrap(), "old", "rename does not save");
        assert_eq!(buffers.open_paths(), vec!["new.txt".to_string()]);
        let view = buffers.open(1, "new.txt").unwrap();
        assert_eq!(
            view.content, "unsaved",
            "the dirty buffer followed the file"
        );
        assert!(view.dirty);
        buffers.commit("new.txt").unwrap();
        assert_eq!(root.disk("new.txt").unwrap(), "unsaved");
        assert!(
            !root.exists("old.txt"),
            "commit must not resurrect the old path"
        );
    }

    #[test]
    fn rename_of_a_directory_rekeys_every_buffer_underneath() {
        let (root, mut buffers) = registry("rename-dir");
        root.put("pkg/one.rs", "1");
        root.put("pkg/two.rs", "2");
        buffers.open(1, "pkg/one.rs").unwrap();
        buffers.write(1, "pkg/one.rs", "1!".into()).unwrap();
        buffers.open(1, "pkg/two.rs").unwrap();
        buffers.rename("pkg", "crate").unwrap();

        assert_eq!(
            buffers.open_paths(),
            vec!["crate/one.rs".to_string(), "crate/two.rs".to_string()]
        );
        assert_eq!(buffers.open(1, "crate/one.rs").unwrap().content, "1!");
        assert!(buffers.open(1, "pkg/one.rs").is_err(), "old key is gone");
        buffers.commit("crate/one.rs").unwrap();
        assert_eq!(root.disk("crate/one.rs").unwrap(), "1!");
    }

    #[test]
    fn rename_of_an_unsaved_new_file_only_rekeys_the_buffer() {
        let (root, mut buffers) = registry("rename-unsaved");
        buffers.write(1, "draft.rs", "never saved".into()).unwrap();
        buffers.rename("draft.rs", "final.rs").unwrap();
        assert!(!root.exists("draft.rs"));
        assert!(!root.exists("final.rs"), "there were no bytes to move");
        assert_eq!(buffers.open_paths(), vec!["final.rs".to_string()]);
        let view = buffers.open(1, "final.rs").unwrap();
        assert_eq!(view.content, "never saved");
        assert!(view.dirty);
        buffers.commit("final.rs").unwrap();
        assert_eq!(root.disk("final.rs").unwrap(), "never saved");
        assert!(
            buffers.rename("ghost.rs", "x.rs").is_err(),
            "nothing to rename"
        );
    }

    #[test]
    fn rename_refuses_to_clobber() {
        let (root, mut buffers) = registry("rename-onto");
        root.put("a.txt", "a");
        root.put("b.txt", "b");
        let err = buffers.rename("a.txt", "b.txt").unwrap_err().to_string();
        assert!(err.contains("already exists"), "{err}");
        assert_eq!(root.disk("b.txt").unwrap(), "b");
    }

    #[test]
    fn delete_drops_the_dirty_buffer_with_the_file() {
        let (root, mut buffers) = registry("delete");
        root.put("gone.txt", "bytes");
        buffers.open(1, "gone.txt").unwrap();
        buffers.write(1, "gone.txt", "unsaved".into()).unwrap();
        buffers.delete("gone.txt").unwrap();
        assert!(!root.exists("gone.txt"));
        assert!(buffers.open_paths().is_empty(), "no buffer to resurrect it");
        assert!(buffers.commit("gone.txt").is_err());
    }

    #[test]
    fn delete_removes_a_directory_tree_and_its_buffers() {
        let (root, mut buffers) = registry("delete-dir");
        root.put("pkg/deep/one.rs", "1");
        root.put("package.rs", "keep");
        buffers.open(1, "pkg/deep/one.rs").unwrap();
        buffers
            .write(1, "pkg/deep/one.rs", "unsaved".into())
            .unwrap();
        buffers.open(1, "package.rs").unwrap();

        buffers.delete("pkg").unwrap();
        assert!(!root.exists("pkg"));
        assert!(
            root.exists("package.rs"),
            "a sibling that merely shares a prefix"
        );
        assert_eq!(buffers.open_paths(), vec!["package.rs".to_string()]);
        assert!(buffers.delete("ghost").is_err(), "nothing to delete");
    }

    #[test]
    fn open_refuses_directories_and_huge_files() {
        let (root, mut buffers) = registry("guard");
        root.put("dir/inner.txt", "");
        let err = buffers.open(1, "dir").unwrap_err().to_string();
        assert!(err.contains("is a directory"), "{err}");

        root.put("big.log", &"x".repeat(MAX_FILE_BYTES as usize + 1));
        let err = buffers.open(1, "big.log").unwrap_err().to_string();
        assert!(err.contains("at most"), "{err}");
        // 0xff is not valid UTF-8 on its own: a code buffer holds text.
        std::fs::write(root.path.join("bin.dat"), [0xff_u8, 0xfe, b'x']).unwrap();
        let err = buffers.open(1, "bin.dat").unwrap_err().to_string();
        assert!(err.contains("text only"), "{err}");
    }

    #[test]
    fn commit_by_a_non_holder_drops_the_clean_buffer() {
        let (root, mut buffers) = registry("commit-settles");
        root.put("a.txt", "a");
        buffers.open(1, "a.txt").unwrap();
        buffers.write(1, "a.txt", "saved".into()).unwrap();
        buffers.close(1, "a.txt").unwrap(); // dirty, so kept — and unheld
        assert_eq!(buffers.open_paths(), vec!["a.txt".to_string()]);

        let view = buffers.commit("a.txt").unwrap();
        assert_eq!(view.content, "saved");
        assert!(!view.dirty);
        assert_eq!(root.disk("a.txt").unwrap(), "saved");
        assert!(
            buffers.open_paths().is_empty(),
            "clean and unheld: the disk is the authority again"
        );
    }

    #[test]
    fn close_by_one_client_keeps_a_buffer_another_still_holds() {
        let (root, mut buffers) = registry("holders");
        root.put("a.txt", "one");
        buffers.open(1, "a.txt").unwrap(); // tab one
        buffers.open(2, "a.txt").unwrap(); // tab two, same buffer
        assert_eq!(
            buffers.close(1, "a.txt").unwrap(),
            Close::Kept { dirty: false },
            "tab two is still reading it"
        );
        assert!(buffers.view_of("a.txt").unwrap().is_some());
        assert_eq!(buffers.close(2, "a.txt").unwrap(), Close::Dropped);
        assert!(buffers.view_of("a.txt").unwrap().is_none());
    }

    #[test]
    fn disconnect_drops_only_the_clean_buffers_it_alone_held() {
        let (root, mut buffers) = registry("disconnect");
        root.put("clean.txt", "c");
        root.put("dirty.txt", "d");
        root.put("shared.txt", "s");
        buffers.open(1, "clean.txt").unwrap();
        buffers.open(1, "dirty.txt").unwrap();
        buffers.write(1, "dirty.txt", "unsaved".into()).unwrap();
        buffers.open(1, "shared.txt").unwrap();
        buffers.open(2, "shared.txt").unwrap();

        // Client 1's socket dies: browser closed, laptop slept, tab crashed.
        assert_eq!(buffers.disconnect(1), vec!["clean.txt".to_string()]);
        assert_eq!(
            buffers.open_paths(),
            vec!["dirty.txt".to_string(), "shared.txt".to_string()]
        );
        assert!(buffers.view_of("dirty.txt").unwrap().unwrap().dirty);
        assert_eq!(buffers.open(2, "dirty.txt").unwrap().content, "unsaved");
        assert_eq!(buffers.disconnect(1), Vec::<String>::new(), "idempotent");
        assert_eq!(buffers.disconnect(2), vec!["shared.txt".to_string()]);
        assert_eq!(buffers.open_paths(), vec!["dirty.txt".to_string()]);
    }

    #[test]
    fn rename_moves_the_holders_too() {
        let (root, mut buffers) = registry("rename-holders");
        root.put("a.txt", "a");
        buffers.open(7, "a.txt").unwrap();
        buffers.rename("a.txt", "b.txt").unwrap();
        assert_eq!(
            buffers.close(9, "b.txt").unwrap(),
            Close::Kept { dirty: false },
            "client 7 still holds the renamed path"
        );
        assert_eq!(buffers.close(7, "b.txt").unwrap(), Close::Dropped);
    }

    #[test]
    fn the_registry_needs_a_real_directory_root() {
        let (root, _buffers) = registry("root");
        root.put("a-file.txt", "x");
        let err = Buffers::new(root.path.join("a-file.txt"))
            .unwrap_err()
            .to_string();
        assert!(err.contains("not a directory"), "{err}");
        assert!(Buffers::new(root.path.join("ghost")).is_err(), "must exist");
    }
}
