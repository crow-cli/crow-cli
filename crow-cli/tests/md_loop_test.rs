//! 12.6 regressions for `print_markdown` (list-command tables).
//!
//! streamdown-render 0.1.4 spun forever in `text_wrap`'s force-truncate loop
//! whenever a table cell was wider than its column budget (byte-length vs
//! display-width confusion — the string GREW one ellipsis per iteration).
//! Fixed in vendor/streamdown-render; the poison case lives here.

/// The poison shape: 3 columns at width 80 → 24-col budget, cell of 26.
/// Used to burn CPU forever; must now truncate and return.
#[test]
fn wide_table_cell_terminates() {
    crow_cli::render::print_markdown(
        "| A | B | C |\n|---|---|---|\n|  | q | alibaba/qwen-image-2.0-pro |\n",
    );
}

/// The real `crow-cli models` document shape: 20 rows, `*` default marker
/// (backticked — a bare `*` cell is eaten by the inline parser), and the
/// footer with angle brackets inside inline code.
#[test]
fn models_markdown_terminates() {
    let mut md = String::from("|   | MODEL | PROVIDER / MODEL |\n|---|---|---|\n");
    let rows = [
        ("qwen3.8-max-preview", "alibaba/qwen3.8-max-preview"),
        ("glm-5.2", "alibaba/glm-5.2"),
        ("kimi-k2.7-code", "alibaba/kimi-k2.7-code"),
        (
            "MiniMax-M2.7-local",
            "llamacpp/unsloth/MiniMax-M2.7-GGUF:UD-IQ2_XXS",
        ),
        ("deepseek-v4-flash", "alibaba/deepseek-v4-flash"),
        ("qwen-image-2.0", "alibaba/qwen-image-2.0"),
        ("qwen-image-2.0-pro", "alibaba/qwen-image-2.0-pro"),
        ("wan2.7-image-pro", "alibaba/wan2.7-image-pro"),
    ];
    for (i, (name, prov)) in rows.iter().enumerate() {
        let mark = if i == 0 { "`*`" } else { "" };
        md.push_str(&format!("| {mark} | {name} | {prov} |\n"));
    }
    md.push_str("\n`*` = default. Override per-run: `crow-cli run -m <name-or-id> \"...\"`");
    crow_cli::render::print_markdown(&md);
}

/// Footer alone — angle brackets inside inline code must not loop.
#[test]
fn footer_with_angle_brackets_terminates() {
    crow_cli::render::print_markdown(
        "`*` = default. Override per-run: `crow-cli run -m <name-or-id> \"...\"`",
    );
}
