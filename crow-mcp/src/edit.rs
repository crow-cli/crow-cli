//! Edit tool — nine cascading fuzzy matchers, ported from crow-mcp Python.
//!
//! 1. Simple (exact match)
//! 2. Line-trimmed
//! 3. Block anchor (first/last line with fuzzy middle)
//! 4. Whitespace normalized
//! 5. Indentation flexible
//! 6. Escape normalized
//! 7. Trimmed boundary
//! 8. Context-aware (50% middle match)
//! 9. Multi-occurrence

use crate::CrowMcpServer;
use regex::Regex;
use rmcp::{
    ErrorData as McpError, handler::server::wrapper::Parameters, model::*, schemars, tool,
    tool_router,
};

#[derive(Debug, serde::Deserialize, schemars::JsonSchema)]
pub struct EditParams {
    /// The absolute path to the file to edit
    file_path: String,
    /// The text to replace (MUST BE UNIQUE if not using replace_all)
    old_string: String,
    /// The text to replace it with
    new_string: String,
    /// Replace all occurrences (default false)
    #[serde(default)]
    replace_all: bool,
}

#[tool_router(router = edit_router, vis = "pub")]
impl CrowMcpServer {
    /// Performs precise string replacements in files with nine cascading fuzzy matchers.
    #[tool(description = "Performs precise string replacements in files. Uses nine cascading fuzzy matchers. old_string MUST be unique unless replace_all is true.")]
    fn edit(
        &self,
        Parameters(params): Parameters<EditParams>,
    ) -> Result<CallToolResult, McpError> {
        let result = edit_file(
            &params.file_path,
            &params.old_string,
            &params.new_string,
            params.replace_all,
        );
        Ok(CallToolResult::success(vec![ContentBlock::text(result)]))
    }
}

const SINGLE_CANDIDATE_THRESHOLD: f64 = 0.0;
const MULTIPLE_CANDIDATES_THRESHOLD: f64 = 0.3;

fn levenshtein(a: &str, b: &str) -> usize {
    if a.is_empty() || b.is_empty() {
        return a.len().max(b.len());
    }
    let a_chars: Vec<char> = a.chars().collect();
    let b_chars: Vec<char> = b.chars().collect();
    let rows = a_chars.len() + 1;
    let cols = b_chars.len() + 1;
    let mut matrix = vec![vec![0usize; cols]; rows];
    for i in 0..rows {
        matrix[i][0] = i;
    }
    for j in 0..cols {
        matrix[0][j] = j;
    }
    for i in 1..rows {
        for j in 1..cols {
            let cost = if a_chars[i - 1] == b_chars[j - 1] { 0 } else { 1 };
            matrix[i][j] = (matrix[i - 1][j] + 1)
                .min(matrix[i][j - 1] + 1)
                .min(matrix[i - 1][j - 1] + cost);
        }
    }
    matrix[rows - 1][cols - 1]
}

type Replacer = fn(&str, &str) -> Vec<String>;

/// 1. Simple exact string match.
fn simple_replacer(content: &str, find: &str) -> Vec<String> {
    if content.contains(find) {
        vec![find.to_string()]
    } else {
        vec![]
    }
}

/// 2. Match lines by trimmed content.
fn line_trimmed_replacer(content: &str, find: &str) -> Vec<String> {
    let original_lines: Vec<&str> = content.split('\n').collect();
    let mut search_lines: Vec<&str> = find.split('\n').collect();
    if search_lines.last() == Some(&"") {
        search_lines.pop();
    }
    let mut results = Vec::new();
    if search_lines.len() > original_lines.len() {
        return results;
    }
    for i in 0..=(original_lines.len() - search_lines.len()) {
        let matches = search_lines
            .iter()
            .enumerate()
            .all(|(j, sl)| original_lines[i + j].trim() == sl.trim());
        if matches {
            let start_idx: usize = original_lines[..i].iter().map(|l| l.len() + 1).sum();
            let mut end_idx = start_idx;
            for k in 0..search_lines.len() {
                end_idx += original_lines[i + k].len();
                if k < search_lines.len() - 1 {
                    end_idx += 1;
                }
            }
            results.push(content[start_idx..end_idx].to_string());
        }
    }
    results
}

/// 3. Match blocks using first/last line as anchors with fuzzy middle.
fn block_anchor_replacer(content: &str, find: &str) -> Vec<String> {
    let original_lines: Vec<&str> = content.split('\n').collect();
    let mut search_lines: Vec<&str> = find.split('\n').collect();
    if search_lines.len() < 3 {
        return vec![];
    }
    if search_lines.last() == Some(&"") {
        search_lines.pop();
    }
    let first = search_lines[0].trim();
    let last = search_lines[search_lines.len() - 1].trim();

    let mut candidates: Vec<(usize, usize)> = Vec::new();
    for (i, line) in original_lines.iter().enumerate() {
        if line.trim() != first {
            continue;
        }
        for j in (i + 2)..original_lines.len() {
            if original_lines[j].trim() == last {
                candidates.push((i, j));
                break;
            }
        }
    }
    if candidates.is_empty() {
        return vec![];
    }

    let threshold = if candidates.len() == 1 {
        SINGLE_CANDIDATE_THRESHOLD
    } else {
        MULTIPLE_CANDIDATES_THRESHOLD
    };

    let mut best: Option<(usize, usize)> = None;
    let mut max_sim = -1.0f64;

    for &(start_line, end_line) in &candidates {
        let actual_size = end_line - start_line + 1;
        let lines_to_check = (search_lines.len() - 2).min(actual_size - 2);
        let similarity = if lines_to_check > 0 {
            let mut sim = 0.0f64;
            for j in 1..(search_lines.len() - 1).min(actual_size - 1) {
                let orig = original_lines[start_line + j].trim();
                let search = search_lines[j].trim();
                let max_len = orig.len().max(search.len());
                if max_len > 0 {
                    let dist = levenshtein(orig, search);
                    sim += 1.0 - dist as f64 / max_len as f64;
                }
            }
            sim / lines_to_check as f64
        } else {
            1.0
        };
        if similarity > max_sim {
            max_sim = similarity;
            best = Some((start_line, end_line));
        }
    }

    if max_sim >= threshold {
        if let Some((start_line, end_line)) = best {
            let start_idx: usize = original_lines[..start_line].iter().map(|l| l.len() + 1).sum();
            let mut end_idx = start_idx;
            for k in start_line..=end_line {
                end_idx += original_lines[k].len();
                if k < end_line {
                    end_idx += 1;
                }
            }
            return vec![content[start_idx..end_idx].to_string()];
        }
    }
    vec![]
}

/// 4. Match with normalized whitespace using regex.
fn whitespace_normalized_replacer(content: &str, find: &str) -> Vec<String> {
    let words: Vec<&str> = find.split_whitespace().collect();
    if words.is_empty() {
        return vec![];
    }
    let pattern = words
        .iter()
        .map(|w| regex::escape(w))
        .collect::<Vec<_>>()
        .join(r"\s+");
    let re = match Regex::new(&pattern) {
        Ok(r) => r,
        Err(_) => return vec![],
    };
    re.find_iter(content).map(|m| m.as_str().to_string()).collect()
}

/// 5. Match ignoring common indentation.
fn indentation_flexible_replacer(content: &str, find: &str) -> Vec<String> {
    fn remove_indentation(text: &str) -> String {
        let lines: Vec<&str> = text.split('\n').collect();
        let non_empty: Vec<&&str> = lines.iter().filter(|l| !l.trim().is_empty()).collect();
        if non_empty.is_empty() {
            return text.to_string();
        }
        let min_indent = non_empty
            .iter()
            .map(|l| l.len() - l.trim_start().len())
            .min()
            .unwrap_or(0);
        lines
            .iter()
            .map(|l| {
                if l.trim().is_empty() {
                    l.to_string()
                } else if l.len() >= min_indent {
                    l[min_indent..].to_string()
                } else {
                    l.to_string()
                }
            })
            .collect::<Vec<_>>()
            .join("\n")
    }

    let normalized_find = remove_indentation(find);
    let content_lines: Vec<&str> = content.split('\n').collect();
    let find_lines: Vec<&str> = find.split('\n').collect();
    let mut results = Vec::new();

    if find_lines.len() > content_lines.len() {
        return results;
    }
    for i in 0..=(content_lines.len() - find_lines.len()) {
        let block = content_lines[i..i + find_lines.len()].join("\n");
        if remove_indentation(&block) == normalized_find {
            results.push(block);
        }
    }
    results
}

/// 6. Match with escape sequences normalized.
fn escape_normalized_replacer(content: &str, find: &str) -> Vec<String> {
    fn unescape(s: &str) -> String {
        s.replace(r"\n", "\n")
            .replace(r"\t", "\t")
            .replace(r"\r", "\r")
            .replace(r"\'", "'")
            .replace(r#"\""#, "\"")
            .replace(r"\\", "\\")
    }

    let unescaped_find = unescape(find);
    let mut results = Vec::new();
    let mut yielded = std::collections::HashSet::new();

    if content.contains(&unescaped_find) {
        results.push(unescaped_find.clone());
        yielded.insert(unescaped_find.clone());
    }

    let content_lines: Vec<&str> = content.split('\n').collect();
    let find_lines: Vec<&str> = unescaped_find.split('\n').collect();
    if find_lines.len() <= content_lines.len() {
        for i in 0..=(content_lines.len() - find_lines.len()) {
            let block = content_lines[i..i + find_lines.len()].join("\n");
            if unescape(&block) == unescaped_find && !yielded.contains(&block) {
                results.push(block.clone());
                yielded.insert(block);
            }
        }
    }
    results
}

/// 7. Match with trimmed boundaries.
fn trimmed_boundary_replacer(content: &str, find: &str) -> Vec<String> {
    let trimmed = find.trim();
    if trimmed == find {
        return vec![];
    }
    let mut results = Vec::new();
    let mut yielded = std::collections::HashSet::new();

    if content.contains(trimmed) {
        results.push(trimmed.to_string());
        yielded.insert(trimmed.to_string());
    }

    let content_lines: Vec<&str> = content.split('\n').collect();
    let find_lines: Vec<&str> = find.split('\n').collect();
    if find_lines.len() <= content_lines.len() {
        for i in 0..=(content_lines.len() - find_lines.len()) {
            let block = content_lines[i..i + find_lines.len()].join("\n");
            if block.trim() == trimmed && !yielded.contains(&block) {
                results.push(block.clone());
                yielded.insert(block);
            }
        }
    }
    results
}

/// 8. Match using first/last lines as context with 50% middle match.
fn context_aware_replacer(content: &str, find: &str) -> Vec<String> {
    let mut find_lines: Vec<&str> = find.split('\n').collect();
    if find_lines.len() < 3 {
        return vec![];
    }
    if find_lines.last() == Some(&"") {
        find_lines.pop();
    }
    let content_lines: Vec<&str> = content.split('\n').collect();
    let first = find_lines[0].trim();
    let last = find_lines[find_lines.len() - 1].trim();
    let mut results = Vec::new();

    for (i, line) in content_lines.iter().enumerate() {
        if line.trim() != first {
            continue;
        }
        let expected_end = i + find_lines.len() - 1;
        if expected_end >= content_lines.len() {
            continue;
        }
        if content_lines[expected_end].trim() != last {
            continue;
        }
        let block_lines = &content_lines[i..=expected_end];
        let mut matching = 0;
        let mut total = 0;
        for k in 1..block_lines.len().saturating_sub(1) {
            let block_ln = block_lines[k].trim();
            let find_ln = find_lines[k].trim();
            if !block_ln.is_empty() || !find_ln.is_empty() {
                total += 1;
                if block_ln == find_ln {
                    matching += 1;
                }
            }
        }
        if total == 0 || (matching as f64 / total as f64) >= 0.5 {
            results.push(block_lines.join("\n"));
        }
    }
    results
}

/// 9. Yield all exact matches.
fn multi_occurrence_replacer(content: &str, find: &str) -> Vec<String> {
    if content.contains(find) {
        vec![find.to_string()]
    } else {
        vec![]
    }
}

const REPLACERS: [Replacer; 9] = [
    simple_replacer,
    line_trimmed_replacer,
    block_anchor_replacer,
    whitespace_normalized_replacer,
    indentation_flexible_replacer,
    escape_normalized_replacer,
    trimmed_boundary_replacer,
    context_aware_replacer,
    multi_occurrence_replacer,
];

/// Replace old_string with new_string using cascading fuzzy matchers.
fn replace(
    content: &str,
    old_string: &str,
    new_string: &str,
    replace_all: bool,
) -> Result<String, String> {
    if old_string == new_string {
        return Err("old_string and new_string must be different".to_string());
    }

    let mut all_matches: Vec<(usize, usize)> = Vec::new();

    for replacer in &REPLACERS {
        let mut found: std::collections::HashSet<(usize, usize)> = std::collections::HashSet::new();
        for search_text in replacer(content, old_string) {
            let mut start = 0;
            while let Some(rel) = content[start..].find(&search_text) {
                let idx = start + rel;
                found.insert((idx, idx + search_text.len()));
                start = idx + search_text.len();
            }
        }
        if !found.is_empty() {
            all_matches = found.into_iter().collect();
            break;
        }
    }

    if all_matches.is_empty() {
        return Err("old_string not found in file".to_string());
    }

    all_matches.sort_by(|a, b| b.0.cmp(&a.0));

    if all_matches.len() > 1 && !replace_all {
        return Err(format!(
            "old_string found {} times. Provide more context to identify the correct match.",
            all_matches.len()
        ));
    }

    let mut new_content = content.to_string();
    for (start, end) in &all_matches {
        new_content = format!(
            "{}{}{}",
            &new_content[..*start],
            new_string,
            &new_content[*end..]
        );
    }

    Ok(new_content)
}

/// Perform an edit on a file. Returns a success/error message.
fn edit_file(
    file_path: &str,
    old_string: &str,
    new_string: &str,
    replace_all: bool,
) -> String {
    if old_string == new_string {
        return "Error: old_string and new_string must be different".to_string();
    }

    let path = std::path::Path::new(file_path);
    let path = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_default()
            .join(path)
    };
    let path = match path.canonicalize() {
        Ok(p) => p,
        Err(e) => return format!("Error: Cannot resolve path: {e}"),
    };

    if !path.exists() {
        return format!("Error: File does not exist: {}", path.display());
    }
    if path.is_dir() {
        return format!("Error: Path is a directory: {}", path.display());
    }

    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => return format!("Error: Failed to read file: {e}"),
    };

    let new_content = match replace(&content, old_string, new_string, replace_all) {
        Ok(c) => c,
        Err(e) => return format!("Error: {e}"),
    };

    if let Err(e) = std::fs::write(&path, &new_content) {
        return format!("Error: Failed to write file: {e}");
    }

    if replace_all {
        format!("Successfully made replacements in {}", path.display())
    } else {
        format!("Successfully edited {}", path.display())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn simple_exact() {
        let result = replace("hello world", "world", "rust", false).unwrap();
        assert_eq!(result, "hello rust");
    }

    #[test]
    fn line_trimmed() {
        let content = "fn main() {\n    println!(\"hi\");\n}\n";
        let find = "fn main() {\nprintln!(\"hi\");\n}";
        let result = replace(content, find, "fn main() {}", false).unwrap();
        assert_eq!(result, "fn main() {}\n");
    }

    #[test]
    fn whitespace_normalized() {
        let content = "let   x   =   5;";
        let find = "let x = 5;";
        let result = replace(content, find, "let y = 10;", false).unwrap();
        assert_eq!(result, "let y = 10;");
    }

    #[test]
    fn indentation_flexible() {
        let content = "    if true {\n        do_thing();\n    }\n";
        let find = "if true {\n    do_thing();\n}";
        let result = replace(content, find, "if false { other(); }", false).unwrap();
        assert_eq!(result, "if false { other(); }\n");
    }

    #[test]
    fn multi_occurrence_error() {
        let result = replace("aaa bbb aaa", "aaa", "ccc", false);
        assert!(result.is_err());
        assert!(result.unwrap_err().contains("2 times"));
    }

    #[test]
    fn multi_occurrence_replace_all() {
        let result = replace("aaa bbb aaa", "aaa", "ccc", true).unwrap();
        assert_eq!(result, "ccc bbb ccc");
    }

    #[test]
    fn not_found() {
        let result = replace("hello", "xyz", "abc", false);
        assert!(result.is_err());
    }

    #[test]
    fn same_string_error() {
        let result = replace("hello", "hello", "hello", false);
        assert!(result.is_err());
    }

    #[test]
    fn trimmed_boundary() {
        let content = "prefix hello world suffix";
        let find = "\nhello world\n";
        let result = replace(content, find, "REPLACED", false).unwrap();
        assert_eq!(result, "prefix REPLACED suffix");
    }
}
