use super::*;

/// Every run of a highlighted block, flattened.
fn flat(runs: Vec<Vec<(String, Style)>>) -> Vec<(String, Style)> {
    runs.into_iter().flatten().collect()
}

fn run_with<'a>(runs: &'a [(String, Style)], needle: &str) -> Option<&'a (String, Style)> {
    runs.iter().find(|(text, _)| text.contains(needle))
}

#[test]
fn python_keywords_strings_and_comments_land_in_different_palette_colors() {
    let theme = Theme::dark();
    let runs = flat(code_block(
        "def greet():\n    return 'hi'  # warm",
        "python",
        &theme,
    ));

    let keyword = run_with(&runs, "def").expect("the keyword is its own run");
    assert_eq!(
        keyword.1.fg,
        Some(theme.brand_soft),
        "keywords take the brand blue: {runs:?}"
    );
    let string = run_with(&runs, "hi").expect("the string body is a run");
    assert_eq!(
        string.1.fg,
        Some(theme.ok),
        "strings take the green: {runs:?}"
    );
    let comment = run_with(&runs, "warm").expect("the comment is a run");
    assert_eq!(
        comment.1.fg,
        Some(theme.caption),
        "comments take the muted gray: {runs:?}"
    );
    assert!(
        comment.1.add_modifier.contains(Modifier::ITALIC),
        "and they stay italic: {runs:?}"
    );
}

#[test]
fn numbers_are_amber_and_the_panel_background_survives_every_token() {
    let theme = Theme::dark();
    let runs = flat(code_block("total = 42", "python", &theme));
    let number = run_with(&runs, "42").expect("the literal is a run");
    assert_eq!(
        number.1.fg,
        Some(theme.warn),
        "constants take the amber: {runs:?}"
    );
    assert!(
        runs.iter().all(|(_, style)| style.bg == Some(theme.panel)),
        "every token keeps the code panel behind it: {runs:?}"
    );
}

#[test]
fn one_entry_per_source_line_even_for_blank_and_unknown_languages() {
    let theme = Theme::dark();
    let runs = code_block("a\n\nb", "python", &theme);
    assert_eq!(runs.len(), 3, "blank lines keep their row");
    assert!(runs[1][0].0.is_empty(), "the blank row is empty: {runs:?}");

    // No grammar for this label: plain code style, still one row per line.
    let runs = code_block("x = 1\ny = 2", "not-a-language", &theme);
    assert_eq!(runs.len(), 2);
    assert_eq!(runs[0].len(), 1, "unhighlighted lines are a single run");
    assert_eq!(
        runs[0][0].1.fg,
        Some(theme.fg),
        "and they use the default code foreground: {runs:?}"
    );
}

#[test]
fn a_fenced_block_in_assistant_markdown_reaches_the_frame_highlighted() {
    let theme = Theme::dark();
    let lines = crate::markdown::render(
        "```python\ntotal = 42\n```",
        &theme,
        crate::markdown::ToneMode::Single,
        60,
    );
    let spans: Vec<_> = lines.iter().flat_map(|l| l.spans.iter()).collect();
    assert!(
        spans.iter().any(|s| s.content.contains("python")),
        "the frame keeps its language label: {lines:?}"
    );
    assert!(
        spans
            .iter()
            .any(|s| s.content.contains("42") && s.style.fg == Some(theme.warn)),
        "the token color survives the frame pass: {lines:?}"
    );
}

#[test]
fn every_language_the_transcript_names_has_a_grammar_unless_it_is_plain() {
    // `lang_token` labels the frame; this holds those labels to syntect's
    // default set so a rename cannot silently drop the colors. TOML and plain
    // text have no grammar to load and stay framed-only.
    const UNCOLORED: [&str; 2] = ["toml", "text"];
    for token in crate::transcript::LANG_TOKENS {
        if UNCOLORED.contains(token) {
            assert!(
                syntax_for(token).is_none(),
                "{token} has a grammar now; drop it from UNCOLORED"
            );
            continue;
        }
        assert!(
            syntax_for(token).is_some(),
            "no grammar behind the label {token}"
        );
    }
    // TypeScript is the alias case: labelled typescript, tokenized as
    // JavaScript, because the default set ships no TS grammar.
    assert_eq!(
        syntax_for("typescript").expect("aliased").name,
        "JavaScript"
    );
}
