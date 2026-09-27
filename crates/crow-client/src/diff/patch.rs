//! Unified-diff geometry: an ACP v2 `git_patch` walked back into the two
//! sides' lines and the opcode groups the renderer wants.
//!
//! A patch carries only what its hunks cover, so `a` and `b` are the hunk
//! lines in order and every hunk becomes one group -- the view folds between
//! groups, which is precisely the context the patch left out.

use super::pipeline::Group;
use super::sequencematcher::Opcode;

pub struct Patch {
    pub a: Vec<String>,
    pub b: Vec<String>,
    pub groups: Vec<Group>,
}

/// One hunk line and which side(s) of the diff it belongs to.
enum Item {
    Equal(String),
    Remove(String),
    Add(String),
}

/// The patch's hunks, as ordered line items. Everything outside a hunk --
/// `diff --git`, `--- a/x`, `+++ b/x`, `index`, mode lines, `Binary files ...
/// differ` -- is prose and skipped; a bare empty line inside one is an empty
/// context line, and `\\ No newline` is a note about the line before it.
fn hunks(text: &str) -> Vec<Vec<Item>> {
    let mut hunks: Vec<Vec<Item>> = Vec::new();
    let mut cur: Option<Vec<Item>> = None;
    for line in text.lines() {
        if line.starts_with("@@") {
            if let Some(done) = cur.take() {
                hunks.push(done);
            }
            cur = Some(Vec::new());
            continue;
        }
        // Outside a hunk everything is prose, and only a hunk header can open
        // one: `--- a/x` is a removal of `-- a/x` or it is the header, and the
        // one thing that tells them apart is which side of the `@@` it is on.
        let item = match line.as_bytes().first() {
            Some(b' ') => Some(Item::Equal(line[1..].to_string())),
            Some(b'-') => Some(Item::Remove(line[1..].to_string())),
            Some(b'+') => Some(Item::Add(line[1..].to_string())),
            Some(b'\\') => None,
            // Producers strip the leading space off a hunk's blank context
            // lines, so a bare empty line inside one is an empty line of both
            // sides rather than the end of the hunk.
            None => Some(Item::Equal(String::new())),
            // Anything else is the next file's headers: the hunk is over, and
            // it is a hunk finished, not one abandoned.
            Some(_) => {
                if let Some(done) = cur.take() {
                    hunks.push(done);
                }
                continue;
            }
        };
        if let (Some(items), Some(item)) = (cur.as_mut(), item) {
            items.push(item);
        }
    }
    if let Some(done) = cur.take() {
        hunks.push(done);
    }
    hunks
}

/// One hunk's items to opcodes over the lines appended to `a` and `b`.
///
/// A run of removals followed by a run of additions is one `replace`, the way
/// `SequenceMatcher` reads the same two sides; a lone run is a `delete` or an
/// `insert`. Indices are file-wide because both sides grow monotonically.
fn opcodes(items: &[Item], a: &mut Vec<String>, b: &mut Vec<String>) -> Vec<Opcode> {
    let mut ops: Vec<Opcode> = Vec::new();
    let (mut i, mut j) = (a.len(), b.len());
    let mut k = 0;
    while k < items.len() {
        if matches!(items[k], Item::Equal(_)) {
            let (i1, j1) = (i, j);
            while let Some(Item::Equal(t)) = items.get(k) {
                a.push(t.clone());
                b.push(t.clone());
                (i, j, k) = (i + 1, j + 1, k + 1);
            }
            ops.push(Opcode {
                tag: "equal".into(),
                first_start: i1,
                first_end: i,
                second_start: j1,
                second_end: j,
            });
            continue;
        }
        let (i1, j1) = (i, j);
        let mut removed = 0;
        while let Some(Item::Remove(t)) = items.get(k) {
            a.push(t.clone());
            (i, k) = (i + 1, k + 1);
            removed += 1;
        }
        let mut added = 0;
        while let Some(Item::Add(t)) = items.get(k) {
            b.push(t.clone());
            (j, k) = (j + 1, k + 1);
            added += 1;
        }
        let tag = match (removed > 0, added > 0) {
            (true, true) => "replace",
            (true, false) => "delete",
            _ => "insert",
        };
        ops.push(Opcode {
            tag: tag.into(),
            first_start: i1,
            first_end: i,
            second_start: j1,
            second_end: j,
        });
    }
    ops
}

pub fn parse(text: &str) -> Patch {
    let mut patch = Patch {
        a: Vec::new(),
        b: Vec::new(),
        groups: Vec::new(),
    };
    for items in hunks(text) {
        let ops = opcodes(&items, &mut patch.a, &mut patch.b);
        if !ops.is_empty() {
            patch.groups.push(Group { ops });
        }
    }
    patch
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::pipeline::op_tuple;

    const PATCH: &str = "--- a/src/x.py\n+++ b/src/x.py\n@@ -1,4 +1,4 @@\n one\n-two\n+TWO\n three\n-four\n+four!\n tail\n@@ -20,3 +20,4 @@\n keep\n+added\n keep2\n";

    #[test]
    fn hunks_become_groups_with_file_wide_indices() {
        let p = parse(PATCH);
        assert_eq!(p.a, vec!["one", "two", "three", "four", "tail", "keep", "keep2"]);
        assert_eq!(p.b, vec!["one", "TWO", "three", "four!", "tail", "keep", "added", "keep2"]);
        assert_eq!(p.groups.len(), 2);
        let tags: Vec<&str> = p.groups[0].ops.iter().map(|o| o.tag.as_str()).collect();
        assert_eq!(tags, vec!["equal", "replace", "equal", "replace", "equal"]);
        let (tag, i1, i2, j1, j2) = op_tuple(&p.groups[0].ops[1]);
        assert_eq!((tag, i1, i2, j1, j2), ("replace", 1, 2, 1, 2));
        let tags: Vec<&str> = p.groups[1].ops.iter().map(|o| o.tag.as_str()).collect();
        assert_eq!(tags, vec!["equal", "insert", "equal"]);
        let (tag, i1, i2, j1, j2) = op_tuple(&p.groups[1].ops[1]);
        assert_eq!((tag, i1, i2, j1, j2), ("insert", 6, 6, 6, 7));
    }

    #[test]
    fn headers_and_no_newline_notes_are_prose() {
        let p = parse(concat!(
            "diff --git a/x b/x\nindex 1234567..89abcde 100644\n",
            "--- a/x\n+++ b/x\n@@ -1,2 +1,2 @@\n-a\n+b\n",
            "\\ No newline at end of file\n",
        ));
        assert_eq!(p.a, vec!["a"]);
        assert_eq!(p.b, vec!["b"]);
        assert_eq!(p.groups.len(), 1);
    }

    /// A multi-file patch: `--- a/two.py` is a header, not a removal of
    /// `-- a/two.py`, and the only thing that says so is the hunk it follows
    /// having ended. Getting this wrong silently prepends both files' headers
    /// to the sides they are describing.
    #[test]
    fn a_second_file_ends_the_hunk_before_its_headers() {
        let p = parse(concat!(
            "--- a/one.py\n+++ b/one.py\n@@ -1 +1 @@\n-x\n+y\n",
            "diff --git a/two.py b/two.py\nindex 1111111..2222222 100644\n",
            "--- a/two.py\n+++ b/two.py\n@@ -1 +1,2 @@\n-p\n+q\n+r\n",
        ));
        assert_eq!(p.a, vec!["x", "p"]);
        assert_eq!(p.b, vec!["y", "q", "r"]);
        assert_eq!(p.groups.len(), 2, "one group per hunk, across files");
    }

    #[test]
    fn an_empty_patch_renders_nothing() {
        let p = parse("");
        assert!(p.a.is_empty() && p.b.is_empty() && p.groups.is_empty());
    }
}
