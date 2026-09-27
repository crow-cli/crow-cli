//! The textual_diff_view diff pipeline.
//!
//! Two stages, exactly as `_diff_view.py` does them:
//!
//!   1. one line-level `SequenceMatcher(isjunk=blank, autojunk=True)` over the
//!      two files, read through `get_grouped_opcodes(3)` -- the geometry;
//!   2. one char-level matcher *per equal-sized `replace` opcode*, over just
//!      that opcode's lines joined with "\n" -- the inline spans, carried back
//!      out through the "\n" split.

use crate::diff::sequencematcher::{Opcode, SequenceMatcher};

pub fn junk_str(c: &&str) -> bool {
    *c == " " || *c == "\t"
}

pub fn junk_char(c: &char) -> bool {
    *c == ' ' || *c == '\t'
}

/// One change cluster: the line opcodes `get_grouped_opcodes` produced.
pub struct Group {
    pub ops: Vec<Opcode>,
}

pub fn op_tuple(o: &Opcode) -> (&str, usize, usize, usize, usize) {
    (o.tag.as_str(), o.first_start, o.first_end, o.second_start, o.second_end)
}

pub fn diff(a: &[&str], b: &[&str]) -> Vec<Group> {
    let mut sm = SequenceMatcher::new(a, b);
    sm.set_is_junk(Some(junk_str));
    let grouped = sm.get_grouped_opcodes(3);

    grouped.iter().map(|ops| Group { ops: ops.clone() }).collect()
}

/// The inline character-level highlight, indexed by FILE line on each side.
///
/// An empty inner vec means "no character on this line is highlighted".
pub struct Inline {
    pub removed: Vec<Vec<bool>>,
    pub added: Vec<Vec<bool>>,
}

/// Half-open character ranges, as the matcher's opcodes produce them.
type Ranges = Vec<(usize, usize)>;

/// Map char-index ranges over a "\n"-joined buffer back to per-line marks.
fn side_marks(buf: &[char], ranges: &Ranges) -> Vec<Vec<bool>> {
    let mut flat = vec![false; buf.len()];
    for &(s, e) in ranges {
        flat.iter_mut().take(e.min(buf.len())).skip(s).for_each(|m| *m = true);
    }
    let mut out: Vec<Vec<bool>> = Vec::new();
    let mut cur: Vec<bool> = Vec::new();
    for (i, ch) in buf.iter().enumerate() {
        if *ch == '\n' {
            out.push(std::mem::take(&mut cur));
        } else {
            cur.push(flat[i]);
        }
    }
    out.push(cur);
    out
}

/// `DiffView.highlighted_code_lines`' character-level pass.
///
/// Not one diff per group: one per `replace` opcode, and only when both sides
/// have the same number of lines -- "otherwise you get noisy diffs that don't
/// make a great deal of sense". The matcher sees just that opcode's lines
/// joined with "\n", so an equal line inside the group can never attract a
/// span, and a replace whose line counts differ gets no inline highlight at
/// all. Skipped entirely when the original file is empty.
pub fn inline_marks(a: &[&str], b: &[&str], groups: &[Group]) -> Inline {
    let mut removed = vec![Vec::new(); a.len()];
    let mut added = vec![Vec::new(); b.len()];
    if a.is_empty() {
        return Inline { removed, added };
    }
    for g in groups {
        for o in &g.ops {
            let (tag, i1, i2, j1, j2) = op_tuple(o);
            if tag != "replace" || (i2 - i1) != (j2 - j1) {
                continue;
            }
            let ca: Vec<char> = a[i1..i2].join("\n").chars().collect();
            let cb: Vec<char> = b[j1..j2].join("\n").chars().collect();
            let mut sm = SequenceMatcher::new(&ca, &cb);
            sm.set_is_junk(Some(junk_char));
            let (mut ra, mut rb): (Ranges, Ranges) = (Vec::new(), Vec::new());
            for co in sm.get_opcodes() {
                let (ctag, ci1, ci2, cj1, cj2) = op_tuple(&co);
                if ctag == "delete" || ctag == "replace" {
                    ra.push((ci1, ci2));
                }
                if ctag == "insert" || ctag == "replace" {
                    rb.push((cj1, cj2));
                }
            }
            for (k, m) in side_marks(&ca, &ra).into_iter().enumerate() {
                removed[i1 + k] = m;
            }
            for (k, m) in side_marks(&cb, &rb).into_iter().enumerate() {
                added[j1 + k] = m;
            }
        }
    }
    Inline { removed, added }
}

/// additions/removals, per `DiffView.counts`.
pub fn counts(groups: &[Group]) -> (usize, usize) {
    let (mut add, mut rem) = (0usize, 0usize);
    for g in groups {
        for o in &g.ops {
            let (tag, i1, i2, j1, j2) = op_tuple(o);
            match tag {
                "delete" => rem += i2 - i1,
                "insert" => add += j2 - j1,
                "replace" => {
                    rem += i2 - i1;
                    add += j2 - j1;
                }
                _ => {}
            }
        }
    }
    (add, rem)
}
