use super::*;

fn t(session: &str) -> Transcript {
    Transcript::new(session.to_string())
}

#[test]
fn cancel_open_work_stops_running_tools() {
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "bash".into(),
        arguments: "{}".into(),
        diff: None,
    });
    tr.cancel_open_work();
    match &tr.cells[0].kind {
        CellKind::Tool { ok, error, .. } => {
            assert_eq!(*ok, Some(false));
            assert_eq!(error.as_deref(), Some("cancelled"));
        }
        other => panic!("expected tool, got {other:?}"),
    }
    assert_eq!(tr.last_finish.as_deref(), Some("cancelled"));
}

#[test]
fn streaming_text_appends_and_finalizes() {
    let mut tr = t("s");
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "Hello ".into(),
    });
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "world".into(),
    });
    assert!(tr.streaming());
    tr.apply(UiEvent::AssistantFinal {
        session: "s".into(),
        text: "Hello world!".into(),
        model: Some("m".into()),
    });
    assert!(!tr.streaming());
    match &tr.cells[0].kind {
        CellKind::Assistant { text, done, .. } => {
            assert_eq!(text, "Hello world!");
            assert!(done);
        }
        other => panic!("unexpected cell {other:?}"),
    }
}

#[test]
fn structured_session_warning_renders_as_notice_not_assistant_copy() {
    let mut tr = t("s");
    tr.apply(UiEvent::SessionNotice {
        session: "s".into(),
        severity: "warning".into(),
        title: "Skill descriptions were shortened".into(),
        details: Some("Disable unused skills or plugins.".into()),
    });

    assert!(matches!(
        &tr.cells[0].kind,
        CellKind::Notice {
            level: NoticeLevel::Warn,
            text,
        } if text == "Skill descriptions were shortened — Disable unused skills or plugins."
    ));
    assert!(!matches!(&tr.cells[0].kind, CellKind::Assistant { .. }));
}

#[test]
fn streaming_assistant_keeps_its_cursor_without_a_fallback_loading_icon() {
    let mut tr = t("s");
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "starting subagents".into(),
    });

    let mut rendered = |spinner| {
        tr.lines(&Theme::dark(), crate::markdown::ToneMode::Single, 80, spinner)
            .iter()
            .flat_map(|line| line.spans.iter().map(|span| span.content.as_ref()))
            .collect::<String>()
    };
    let first = rendered('⠋');
    let second = rendered('⠙');

    assert!(first.contains("starting subagents▍"), "{first}");
    assert!(second.contains("starting subagents▍"), "{second}");
    assert!(
        !first.contains('⠋'),
        "fallback loading icon leaked: {first}"
    );
    assert!(
        !second.contains('⠙'),
        "fallback loading icon leaked: {second}"
    );
}

#[test]
fn tool_call_pairs_with_result() {
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "bash".into(),
        arguments: r#"{"command":"ls"}"#.into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: "a\nb".into(),
        error: None,
    });
    match &tr.cells[0].kind {
        CellKind::Tool {
            name, title, ok, ..
        } => {
            assert_eq!(name, "bash");
            assert_eq!(title, "ls");
            assert_eq!(*ok, Some(true));
        }
        other => panic!("unexpected cell {other:?}"),
    }
}

#[test]
fn streamed_tool_request_updates_one_existing_cell() {
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "Subagent".into(),
        arguments: r#"{"arguments":"{\"task\":"}"#.into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "Subagent: inspect renderer".into(),
        arguments: r#"{"task":"inspect renderer"}"#.into(),
        diff: None,
    });

    assert_eq!(
        tr.cells.len(),
        1,
        "a tool update must not append another request"
    );
    match &tr.cells[0].kind {
        CellKind::Tool {
            name, request, ok, ..
        } => {
            assert_eq!(name, "Subagent: inspect renderer");
            assert_eq!(request, r#"{"task":"inspect renderer"}"#);
            assert_eq!(*ok, None);
        }
        other => panic!("unexpected cell {other:?}"),
    }
}

#[test]
fn turn_end_settles_an_orphaned_tool_in_the_client_presentation() {
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "Subagent".into(),
        arguments: "{}".into(),
        diff: None,
    });
    tr.apply(UiEvent::TurnEnd {
        session: "s".into(),
        kind: "interrupted".into(),
    });

    match &tr.cells[0].kind {
        CellKind::Tool { ok, error, .. } => {
            assert_eq!(*ok, Some(false));
            assert_eq!(error.as_deref(), Some("interrupted"));
        }
        other => panic!("unexpected cell {other:?}"),
    }
    assert!(
        !tr.streaming(),
        "the stopped turn owns all open presentation state"
    );
}

#[test]
fn reasoning_closes_when_text_starts() {
    let mut tr = t("s");
    tr.apply(UiEvent::ReasoningDelta {
        session: "s".into(),
        text: "plan".into(),
    });
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "answer".into(),
    });
    match &tr.cells[0].kind {
        CellKind::Reasoning { done, .. } => assert!(done),
        other => panic!("unexpected cell {other:?}"),
    }
}

#[test]
fn usage_accumulates() {
    let mut tr = t("s");
    for _ in 0..2 {
        tr.apply(UiEvent::Usage {
            session: "s".into(),
            input: 10,
            output: 5,
            cached: 3,
            reasoning: 1,
        });
    }
    assert_eq!(tr.usage.input, 20);
    assert_eq!(tr.usage.output, 10);
    assert_eq!(tr.usage.cached, 6);
}

#[test]
fn context_usage_overwrites_and_stays_out_of_the_totals() {
    let mut tr = t("s");
    assert_eq!(tr.context, None);

    tr.apply(UiEvent::ContextUsage {
        session: "s".into(),
        used: 100,
        size: 1000,
    });
    tr.apply(UiEvent::ContextUsage {
        session: "s".into(),
        used: 250,
        size: 1000,
    });

    // Absolute readings: the second replaces the first, it does not add to it.
    assert_eq!(
        tr.context,
        Some(ContextUsage {
            used: 250,
            size: 1000
        })
    );
    assert_eq!(tr.usage.input, 0);
    assert_eq!(tr.usage.output, 0);
}

#[test]
fn context_usage_fraction_and_reset() {
    let mut tr = t("s");
    tr.apply(UiEvent::ContextUsage {
        session: "s".into(),
        used: 250,
        size: 1000,
    });
    let ctx = tr.context.expect("reading recorded");
    assert!((ctx.fraction() - 0.25).abs() < f64::EPSILON);

    // No ceiling reported -> no divide-by-zero, reads as empty.
    assert_eq!(ContextUsage { used: 9, size: 0 }.fraction(), 0.0);
    // Over-full context clamps rather than exceeding the window.
    assert_eq!(ContextUsage { used: 2000, size: 1000 }.fraction(), 1.0);

    tr.set_root_session("other".into());
    assert_eq!(tr.context, None, "a new session starts with no meter");
}

fn line_width(line: &Line) -> usize {
    line.spans
        .iter()
        .map(|s| unicode_width::UnicodeWidthStr::width(s.content.as_ref()))
        .sum()
}

#[test]
fn wrap_handles_cjk() {
    let lines = wrap("深度求索深度求索", 8);
    assert_eq!(lines.len(), 2);
}

#[test]
fn user_bubble_stays_within_the_pane_width() {
    // The bubble line is "❯ " (2 cells) + " {l} " (text + 2 cells); the wrap
    // budget must pay for all 4 chrome cells or packed CJK lines clip.
    let mut tr = t("s");
    tr.push_user("深度求索深度求索深度求索深度求索深度求索".into(), false);
    let theme = Theme::dark();
    for width in [20u16, 40, 80] {
        for (i, line) in tr.lines(&theme, crate::markdown::ToneMode::Single, width, '⠋').iter().enumerate() {
            assert!(
                line_width(line) <= width as usize,
                "line {i} at pane width {width} paints {} cells: {line:?}",
                line_width(line),
            );
        }
    }
}

#[test]
fn wrap_expands_tabs_and_never_exceeds_width() {
    use unicode_width::UnicodeWidthStr;
    let cases = [
        format!("\t{}", "x".repeat(120)),
        format!("{}\t{}", "x".repeat(10), "y".repeat(110)),
        "\t".repeat(20) + &"code();".repeat(15),
        "a".repeat(200),
        "深度求索".repeat(40),
    ];
    for text in cases {
        for width in [40usize, 80, 120] {
            for line in wrap(&text, width) {
                let w = UnicodeWidthStr::width(line.as_str());
                assert!(
                    w <= width,
                    "wrapped line {line:?} is {w} cols, budget {width}"
                );
                assert!(
                    !line.contains('\t'),
                    "tabs must expand to spaces so display width matches: {line:?}"
                );
            }
        }
    }
}

#[test]
fn write_tool_tab_indented_body_fits_terminal_width() {
    // GitHub issue #5: writing a file whose lines contain tabs rendered
    // at 128 cols in a 120-col terminal (tab counted as 0, displayed as 8,
    // plus the "│ " gutter).
    let mut tr = t("s");
    let body = format!("\t{}", "x".repeat(120));
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "str_replace_editor".into(),
        arguments: r#"{"command":"create","path":"src/lib.rs"}"#.into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: body,
        error: Some("x".repeat(140)),
    });
    let theme = Theme::dark();
    let width = 120u16;
    let layout = tr.layout(&theme, crate::markdown::ToneMode::Single, width, ' ', false);
    for (i, line) in layout.lines.iter().enumerate() {
        let w = line_width(line);
        let text: String = line.spans.iter().map(|s| s.content.as_ref()).collect();
        assert!(
            w <= width as usize,
            "line {i} width {w} > {width}: {text:?}"
        );
        assert!(!text.contains('\t'), "tab leaked into layout line {i}");
    }
}

#[test]
fn assistant_body_rerenders_when_the_tone_changes() {
    let mut tr = t("s");
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "你好 world".into(),
    });
    tr.apply(UiEvent::AssistantFinal {
        session: "s".into(),
        text: "你好 world".into(),
        model: Some("m".into()),
    });
    let theme = Theme::dark();
    let mut fg_of = |tone: ToneMode| -> (Option<ratatui::style::Color>, Option<ratatui::style::Color>) {
        let lines = tr.lines(&theme, tone, 60, ' ');
        let segs: Vec<&ratatui::text::Span> =
            lines.iter().flat_map(|l| l.spans.iter()).collect();
        let cjk = segs
            .iter()
            .find(|s| s.content.contains("你好"))
            .expect("cjk run");
        let latin = segs
            .iter()
            .find(|s| s.content.contains("world"))
            .expect("latin run");
        (cjk.style.fg, latin.style.fg)
    };
    let (cjk_single, latin_single) = fg_of(ToneMode::Single);
    assert_eq!(cjk_single, Some(theme.fg), "single tone colors CJK with fg");
    assert_eq!(latin_single, Some(theme.fg), "single tone colors Latin with fg");
    let (cjk_two, latin_two) = fg_of(ToneMode::Two);
    assert_eq!(cjk_two, Some(theme.fg_secondary), "two-tone dims CJK");
    assert_eq!(latin_two, Some(theme.fg), "two-tone keeps Latin bright");
    assert_ne!(cjk_single, cjk_two, "tone change invalidates the render cache");
}

#[test]
fn render_smoke() {
    let mut tr = t("s");
    tr.push_user("hi".into(), false);
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "yo".into(),
    });
    let theme = Theme::dark();
    let lines = tr.lines(&theme, crate::markdown::ToneMode::Single, 40, '⠋');
    assert!(lines.len() >= 3);
}

#[test]
fn acp_load_replay_paints_user_title_and_plan() {
    let mut tr = t("s");
    tr.apply(UiEvent::UserMessage {
        session: "s".into(),
        text: "hello from load".into(),
    });
    tr.apply(UiEvent::SessionTitle {
        session: "s".into(),
        title: "fix the tests".into(),
    });
    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: "locate fn main [completed]".into(),
    });
    match &tr.cells[0].kind {
        CellKind::User { text, queued } => {
            assert_eq!(text, "hello from load");
            assert!(!*queued);
        }
        other => panic!("expected user cell, got {other:?}"),
    }
    let notices: Vec<&str> = tr
        .cells
        .iter()
        .filter_map(|c| match &c.kind {
            CellKind::Notice { text, .. } => Some(text.as_str()),
            _ => None,
        })
        .collect();
    assert!(notices.iter().any(|n| *n == "session · fix the tests"));
    let plans: Vec<&str> = tr
        .cells
        .iter()
        .filter_map(|c| match &c.kind {
            CellKind::Plan { summary } => Some(summary.as_str()),
            _ => None,
        })
        .collect();
    assert_eq!(plans, ["locate fn main [completed]"]);
}

#[test]
fn plan_snapshots_replace_the_existing_plan_in_place() {
    let mut tr = t("s");
    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: "inspect [in_progress]".into(),
    });
    let cells_after_first = tr.cells.len();

    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: "inspect [completed] · test [in_progress]".into(),
    });

    assert_eq!(
        tr.cells.len(),
        cells_after_first,
        "a full plan snapshot updates one client-side view instead of appending chat history"
    );
    let rendered = tr
        .lines(&Theme::dark(), crate::markdown::ToneMode::Single, 80, '⠋')
        .iter()
        .flat_map(|line| line.spans.iter().map(|span| span.content.as_ref()))
        .collect::<String>();
    assert!(!rendered.contains("inspect [in_progress]"));
    assert!(rendered.contains("inspect [completed] · test [in_progress]"));
}

#[test]
fn empty_plan_snapshot_hides_the_existing_plan() {
    let mut tr = t("s");
    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: "inspect [in_progress]".into(),
    });
    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: String::new(),
    });

    let rendered = tr
        .lines(&Theme::dark(), crate::markdown::ToneMode::Single, 80, '⠋')
        .iter()
        .flat_map(|line| line.spans.iter().map(|span| span.content.as_ref()))
        .collect::<String>();
    assert!(!rendered.contains("plan ·"));
    assert!(!rendered.contains("inspect"));
}

#[test]
fn tool_output_is_open_by_default_and_collapse_all_takes_it_back() {
    let text = "l1\nl2\nl3\nl4\nl5\nl6\nl7\nl8";
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "bash".into(),
        arguments: "{}".into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: text.into(),
        error: None,
    });
    let theme = Theme::dark();
    let plain = |lines: &[Line]| -> String {
        lines
            .iter()
            .flat_map(|l| l.spans.iter().map(|s| s.content.to_string()))
            .collect()
    };

    // Open by default: the whole body, no tail footer, no click required.
    let p = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 40, ' '));
    assert!(p.contains("l1"), "the first line is visible on arrival: {p}");
    assert!(p.contains("l8"), "and so is the last: {p}");
    assert!(!p.contains("click to expand"), "an open body has no footer: {p}");
    assert!(!p.contains("wheel"), "tool bodies have no inner scroll: {p}");

    // ctrl+o is the transcript-wide override: it closes every cell at once.
    tr.collapse_all = true;
    let p = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 40, ' '));
    assert!(!p.contains("l4"), "collapsed keeps only the tail: {p}");
    assert!(p.contains("l8"), "the tail stays: {p}");
    assert!(
        p.contains("last 4/8 lines"),
        "footer describes the fixed tail preview: {p}"
    );
}

/// A write/edit call's diff block is its own artifact: the card replaces both
/// the raw-input preview and the plain-text result tail (they would say the
/// same thing twice), and collapsed it is the card's own title row -- the file
/// and its counts, the whole change in one line.
#[test]
fn a_diff_card_replaces_the_request_preview_and_collapses_to_its_title() {
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "edit".into(),
        arguments: r#"{"file_path":"/tmp/x.py","old_string":"a","new_string":"b"}"#.into(),
        diff: Some(ToolDiff {
            path: "/tmp/x.py".into(),
            patch: Some("--- a/tmp/x.py\n+++ b/tmp/x.py\n@@ -1 +1 @@\n-a\n+b\n".into()),
            old_text: None,
            new_text: None,
        }),
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: String::new(),
        error: None,
    });
    let theme = Theme::dark();
    let plain = |lines: &[Line]| -> String {
        lines
            .iter()
            .map(|l| {
                l.spans
                    .iter()
                    .map(|s| s.content.as_ref())
                    .collect::<String>()
            })
            .collect::<Vec<_>>()
            .join("\n")
    };

    let open = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 60, ' '));
    println!("--- open ---\n{open}");
    assert!(
        open.contains("📄 /tmp/x.py (+1, -1)"),
        "the card titles itself: {open}"
    );
    assert!(
        !open.contains("old_string"),
        "the raw input is the card's job now: {open}"
    );

    tr.collapse_all = true;
    let closed = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 60, ' '));
    println!("--- closed ---\n{closed}");
    assert!(
        closed.contains("📄 /tmp/x.py (+1, -1)"),
        "collapsed keeps the title: {closed}"
    );
    assert!(
        closed.lines().count() < open.lines().count(),
        "and drops the body: {} vs {}",
        closed.lines().count(),
        open.lines().count()
    );
}

#[test]
fn reasoning_is_open_by_default_and_collapse_all_keeps_only_the_heading() {
    let mut tr = t("s");
    // Paragraph-separated so the markdown pipeline lays them out as five
    // body rows (soft breaks would merge single newlines into one paragraph,
    // exactly like assistant text).
    tr.apply(UiEvent::ReasoningDelta {
        session: "s".into(),
        text: "r1\n\nr2\n\nr3\n\nr4\n\nr5".into(),
    });
    // Assistant text closes the reasoning stream (`done`), which is the state
    // a finished thought is read in.
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "answer".into(),
    });
    let theme = Theme::dark();
    let plain = |lines: &[Line]| -> String {
        lines
            .iter()
            .flat_map(|l| l.spans.iter().map(|s| s.content.to_string()))
            .collect()
    };

    let p = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 40, ' '));
    assert!(p.contains("r1"), "a finished thought is readable without a click: {p}");
    assert!(p.contains("r5"), "all of it, not just a preview: {p}");
    assert!(p.contains("9 lines"), "the heading still counts them: {p}");
    assert!(p.contains("▎"), "thoughts render behind the quote gutter: {p}");

    tr.collapse_all = true;
    let p = plain(&tr.lines(&theme, crate::markdown::ToneMode::Single, 40, ' '));
    assert!(!p.contains("r1"), "collapsed drops the body: {p}");
    assert!(!p.contains("r5"), "collapsed drops all of it: {p}");
    assert!(p.contains("9 lines"), "the heading survives: {p}");
}

#[test]
fn image_cell_reserves_thumbnail_or_falls_back_to_path() {
    let mut tr = t("s");
    let mut png = vec![0u8; 24];
    png[..8].copy_from_slice(b"\x89PNG\r\n\x1a\n");
    png[16..20].copy_from_slice(&100u32.to_be_bytes());
    png[20..24].copy_from_slice(&100u32.to_be_bytes());
    tr.push_image(
        "pic.png".into(),
        "look".into(),
        "/tmp/pic.png".into(),
        std::sync::Arc::from(png.clone()),
        false,
    );
    let theme = Theme::dark();

    // Thumbnails on: reserve blank lines and report the placement.
    let layout = tr.layout(&theme, crate::markdown::ToneMode::Single, 40, ' ', true);
    assert_eq!(layout.images.len(), 1, "PNG image reports one shot");
    let shot = &layout.images[0];
    assert_eq!(shot.cols, 24);
    assert!(
        (2..=12).contains(&shot.rows),
        "aspect-true rows: {}",
        shot.rows
    );
    let reserved: String = layout.lines[shot.line]
        .spans
        .iter()
        .map(|s| s.content.to_string())
        .collect();
    assert!(
        reserved.trim().is_empty(),
        "reserved line is blank: {reserved:?}"
    );

    // Thumbnails off: no reservation, path shown as the fallback.
    let layout = tr.layout(&theme, crate::markdown::ToneMode::Single, 40, ' ', false);
    assert!(layout.images.is_empty());
    let text: String = layout
        .lines
        .iter()
        .flat_map(|l| l.spans.iter().map(|s| s.content.to_string()))
        .collect();
    assert!(text.contains("/tmp/pic.png"), "fallback path shown: {text}");
}

#[test]
fn stats_accumulate_turns_steps_and_ttft() {
    let mut tr = t("s");
    tr.apply(UiEvent::TurnStart {
        session: "s".into(),
        turn: 1,
    });
    tr.apply(UiEvent::AssistantFinal {
        session: "s".into(),
        text: "hi".into(),
        model: None,
    });
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "bash".into(),
        arguments: "{}".into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: "ok".into(),
        error: None,
    });
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "first".into(),
    });
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "second".into(),
    });
    tr.apply(UiEvent::TurnEnd {
        session: "s".into(),
        kind: "completed".into(),
    });

    assert_eq!(tr.stats.turns, 1);
    assert_eq!(tr.stats.steps, 1);
    assert_eq!(tr.stats.ttft_count, 1, "only the first delta samples TTFT");
    assert!(tr.stats.tool_millis <= tr.stats.turn_millis);
}

/// ZWJ emoji clusters must be measured as one 2-cell grapheme. Summing the
/// per-`char` widths (6 for a family emoji) used to overflow the line budget
/// and split the sequence across lines.
#[test]
fn wrap_keeps_zwj_emoji_clusters_whole() {
    let lines = wrap("aaaa👨‍👩‍👧bbbb", 4);
    assert_eq!(lines.len(), 3, "cluster occupies its own row: {lines:?}");
    for line in &lines {
        assert!(
            UnicodeWidthStr::width(line.as_str()) <= 4,
            "line over budget: {line:?}",
        );
        if line.contains('👨') || line.contains('👩') || line.contains('👧') {
            assert!(
                line.contains("👨‍👩‍👧"),
                "cluster split across lines: {line:?}",
            );
        }
    }
}

/// A variation-selector cluster is 2 cells, not the 1 its chars sum to; the
/// wrapped line must stay inside the budget instead of being clipped.
#[test]
fn wrap_measures_variation_selector_clusters_as_two_cells() {
    let lines = wrap("ab❤️cd", 4);
    assert_eq!(lines.len(), 2, "{lines:?}");
    for line in &lines {
        assert!(
            UnicodeWidthStr::width(line.as_str()) <= 4,
            "line over budget: {line:?}",
        );
    }
    assert!(lines.concat().contains("❤️"), "cluster kept: {lines:?}");
}

/// `clamp_str` ellipsizes on cluster boundaries: the ZWJ sequence either fits
/// whole or moves entirely into the dropped tail.
#[test]
fn clamp_str_never_splits_an_emoji_cluster() {
    let out = clamp_str("abc👨‍👩‍👧def", 6);
    assert!(out.ends_with('…'), "{out:?}");
    assert!(UnicodeWidthStr::width(out.as_str()) <= 6, "{out:?}");
    assert!(out.contains("👨‍👩‍👧"), "cluster split: {out:?}");
}

/// Rendered pane text of a transcript, spans concatenated.
fn pane(tr: &mut Transcript, width: u16) -> String {
    tr.lines(&Theme::dark(), crate::markdown::ToneMode::Single, width, ' ')
        .iter()
        .flat_map(|l| l.spans.iter().map(|s| s.content.to_string()))
        .collect()
}

fn tool_call(tr: &mut Transcript, name: &str, arguments: &str) {
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: name.into(),
        arguments: arguments.into(),
        diff: None,
    });
}

#[test]
fn tool_command_reads_the_language_out_of_the_raw_input() {
    // A kernel cell is python, whatever the tool is called.
    assert_eq!(
        tool_command(r#"{"code":"x = 1"}"#),
        Some(("python", "x = 1".to_string()))
    );
    // A shell call is bash, as a string or an argv array.
    assert_eq!(
        tool_command(r#"{"command":"ls -la"}"#),
        Some(("bash", "ls -la".to_string()))
    );
    assert_eq!(
        tool_command(r#"{"command":["ls","-la"]}"#),
        Some(("bash", "ls -la".to_string()))
    );
    // A file write shows its payload, language from the path.
    assert_eq!(
        tool_command(r#"{"path":"/a/b.rs","file_text":"fn main() {}"}"#),
        Some(("rust", "fn main() {}".to_string()))
    );
    // Anything else falls back to the raw input itself.
    let (lang, body) = tool_command(r#"{"mode":"read","target":"/x"}"#).expect("fallback");
    assert_eq!(lang, "json");
    assert!(body.contains("\"mode\""), "the whole input stays readable: {body}");
    assert_eq!(tool_command("not json at all"), None);
    assert_eq!(tool_command("{}"), None, "no command, no block");
}

#[test]
fn an_open_tool_shows_its_command_as_a_labelled_block_from_the_first_frame() {
    let mut tr = t("s");
    tool_call(&mut tr, "execute", r#"{"code":"print(6 * 7)"}"#);

    // Still running: the command is on screen, framed and labelled.
    let p = pane(&mut tr, 60);
    assert!(p.contains("print(6 * 7)"), "the command renders while pending: {p}");
    assert!(p.contains("python"), "the frame names the language: {p}");
    assert!(p.contains("┌"), "and it is a framed code block: {p}");

    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: "42".into(),
        error: None,
    });
    let p = pane(&mut tr, 60);
    assert!(
        p.contains("print(6 * 7)"),
        "the command stays put once the call finishes: {p}"
    );
    assert!(p.contains("42"), "and the output joins it below: {p}");
}

#[test]
fn a_collapsed_tool_trades_the_command_block_for_its_one_line_title() {
    let mut tr = t("s");
    tool_call(&mut tr, "bash", r#"{"command":"cargo test"}"#);
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: "42".into(),
        error: None,
    });

    tr.collapse_all = true;
    let p = pane(&mut tr, 60);
    assert!(!p.contains("┌"), "no framed block while collapsed: {p}");
    assert!(
        p.contains("cargo test"),
        "the header title still says what ran: {p}"
    );
}

#[test]
fn a_command_that_arrives_fenced_frames_once_and_keeps_its_output() {
    // crow-cli rides `content` instead of `rawInput`, so what reaches the cell
    // is the fence itself — and the completion repeats it ahead of the output.
    let mut tr = t("s");
    tool_call(&mut tr, "execute", "```python\nprint(6 * 7)\n```");
    let p = pane(&mut tr, 60);
    assert!(p.contains("\u{250c}\u{2500} python"), "the frame names the language: {p}");
    assert!(p.contains("print(6 * 7)"), "the code is inside it: {p}");
    assert!(!p.contains("```"), "the wire's own markers are not drawn: {p}");

    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: "```python\nprint(6 * 7)\n```\n42".into(),
        error: None,
    });
    let p = pane(&mut tr, 60);
    assert_eq!(
        p.matches("print(6 * 7)").count(),
        1,
        "the echoed command is not drawn twice: {p}"
    );
    assert!(p.contains("42"), "the output lands below it: {p}");

    tr.collapse_all = true;
    let p = pane(&mut tr, 60);
    assert!(!p.contains("\u{250c}"), "collapsed drops the frame: {p}");
    assert!(p.contains("print(6 * 7)"), "the title still says what ran: {p}");
    assert!(!p.contains("```"), "and never the markers: {p}");
}


/// A transcript covering every `CellKind`, so the measure/layout/window
/// invariants are checked against all of them rather than whichever one a
/// narrower fixture happened to build.
fn fixture() -> Transcript {
    let mut tr = t("s");
    tr.push_user("short prompt".into(), false);
    tr.apply(UiEvent::AssistantFinal {
        session: "s".into(),
        text: "## Heading\n\nProse that wraps over a couple of rows.\n\n- one\n- two\n\n```rust\nfn f() {}\n```".into(),
        model: Some("m".into()),
    });
    tr.apply(UiEvent::ReasoningDelta {
        session: "s".into(),
        text: "thinking about it\n".into(),
    });
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c1".into(),
        name: "bash".into(),
        arguments: r#"{"command":"cargo test --locked"}"#.into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c1".into(),
        is_error: false,
        text: (0..30).map(|k| format!("line {k} of tool output")).collect::<Vec<_>>().join("\n"),
        error: None,
    });
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "c2".into(),
        name: "read".into(),
        arguments: r#"{"path":"src/app.rs"}"#.into(),
        diff: None,
    });
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "c2".into(),
        is_error: true,
        text: "boom".into(),
        error: Some("permission denied".into()),
    });
    let shell = tr.push_shell("ls -la".into());
    tr.finish_shell(shell, Some(1), "ls: cannot access\n".repeat(20), tr.gen());
    tr.apply(UiEvent::UserInjected {
        session: "s".into(),
        source: "AGENTS.md".into(),
        preview: "injected context preview".into(),
    });
    tr.apply(UiEvent::Plan {
        session: "s".into(),
        summary: "step one; step two; step three".into(),
    });
    tr.apply(UiEvent::SessionNotice {
        session: "s".into(),
        severity: "warning".into(),
        title: "heads up".into(),
        details: Some("something happened".into()),
    });
    tr.push_user("a much longer prompt ".repeat(6).trim().to_string(), true);
    tr.apply(UiEvent::AssistantFinal {
        session: "s".into(),
        text: "done".into(),
        model: Some("m".into()),
    });
    tr.cancel_open_work();
    tr
}

/// Every window `layout_window` reports must be byte-identical to the same
/// slice of a full `layout`, and `row_count` must equal the full length — the
/// measure cache and the emitter cannot be allowed to drift, because the scroll
/// window is resolved from one and painted from the other.
#[test]
fn windowed_layout_matches_the_full_layout_slice() {
    let theme = Theme::dark();
    for width in [8u16, 23, 40, 80, 100] {
        for collapse in [false, true] {
            for thumbs in [false, true] {
                let mut tr = fixture();
                tr.collapse_all = collapse;
                let full = tr.layout(&theme, crate::markdown::ToneMode::Single, width, '⠋', thumbs);
                let total = full.lines.len();
                assert_eq!(
                    tr.row_count(&theme, crate::markdown::ToneMode::Single, width, '⠋', thumbs),
                    total,
                    "row_count != layout len (width {width} collapse {collapse} thumbs {thumbs})"
                );
                let mut starts = vec![0usize, 1, total / 3, total / 2, total.saturating_sub(5), total];
                starts.extend((0..total).step_by(total.div_ceil(17).max(1)));
                for &start in &starts {
                    for &len in &[0usize, 1, 3, 7, 20] {
                        let end = (start + len).min(total);
                        let (w, w_total, base) = tr.layout_window(
                            &theme,
                            crate::markdown::ToneMode::Single,
                            width,
                            '⠋',
                            thumbs,
                            start,
                            end,
                        );
                        let ctx = format!(
                            "width {width} collapse {collapse} thumbs {thumbs} start {start} end {end}"
                        );
                        assert_eq!(w_total, total, "total {ctx}");
                        assert!(base <= start, "base {base} past start {start}: {ctx}");
                        let lo = start - base;
                        let hi = end - base;
                        assert!(hi <= w.lines.len(), "window too short: {ctx}");
                        assert_eq!(&w.lines[lo..hi], &full.lines[start..end], "lines {ctx}");
                        assert_eq!(
                            &w.owners[lo..hi],
                            &full.owners[start..end],
                            "owners {ctx}"
                        );
                        // Absolute coordinates: every reported prompt/image must
                        // be the very same entry the full layout reported.
                        for p in &w.users {
                            assert!(
                                full.users.iter().any(|f| f.cell == p.cell
                                    && f.line == p.line
                                    && f.end == p.end),
                                "user prompt {p:?} not in the full layout: {ctx}"
                            );
                        }
                        for s in &w.images {
                            assert!(
                                full.images.iter().any(|f| f.id == s.id && f.line == s.line),
                                "image {} not in the full layout: {ctx}",
                                s.id
                            );
                        }
                    }
                }
            }
        }
    }
}

/// The point of the window: a viewport-sized slice of a long session must not
/// materialize the session. Asserted structurally (rows emitted, not wall
/// clock) so it cannot flake.
#[test]
fn windowed_layout_materializes_only_the_window() {
    let theme = Theme::dark();
    let mut tr = t("s");
    for i in 0..400 {
        tr.push_user(format!("prompt {i}"), false);
        tr.apply(UiEvent::AssistantFinal {
            session: "s".into(),
            text: format!("## {i}\n\n{}\n", "answer prose that wraps over rows. ".repeat(8)),
            model: Some("m".into()),
        });
    }
    let total = tr.row_count(&theme, crate::markdown::ToneMode::Single, 100, ' ', false);
    assert!(total > 2000, "fixture should be long, got {total}");
    let (w, _, base) =
        tr.layout_window(&theme, crate::markdown::ToneMode::Single, 100, ' ', false, total - 40, total);
    // 40 rows of viewport, plus at most the one cell it starts inside.
    assert!(
        w.lines.len() <= 40 + 60,
        "window materialized {} rows for a 40-row viewport (base {base}, total {total})",
        w.lines.len()
    );
}

/// A cell's cached row count must survive being measured through the window
/// path and then read back by the full path — and vice versa — without either
/// answer changing.
#[test]
fn measure_cache_survives_mutation_and_resize() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let mut tr = fixture();
    for width in [40u16, 80, 40, 120] {
        let full = tr.layout(&theme, tone, width, ' ', false);
        assert_eq!(tr.row_count(&theme, tone, width, ' ', false), full.lines.len());
        // A window pass must not disturb the cached heights.
        let half = full.lines.len() / 2;
        let _ = tr.layout_window(&theme, tone, width, ' ', false, half, half + 10);
        assert_eq!(tr.row_count(&theme, tone, width, ' ', false), full.lines.len());
    }
    // Streaming into the tail invalidates one stamp, not the table.
    let before = tr.row_count(&theme, tone, 80, ' ', false);
    tr.apply(UiEvent::TextDelta {
        session: "s".into(),
        text: "\n\nmore\n".into(),
    });
    let after = tr.row_count(&theme, tone, 80, ' ', false);
    assert_eq!(after, tr.layout(&theme, tone, 80, ' ', false).lines.len());
    assert!(after >= before, "growing the tail shrank the transcript");
    // Collapse changes heights; the table has to follow.
    tr.collapse_all = true;
    assert_eq!(
        tr.row_count(&theme, tone, 80, ' ', false),
        tr.layout(&theme, tone, 80, ' ', false).lines.len()
    );
    // Hiding a cell drops its rows.
    let hidden = tr.row_count(&theme, tone, 80, ' ', false);
    let gen = tr.gen();
    tr.hide_cells(&[0, 1], gen);
    let after_hide = tr.row_count(&theme, tone, 80, ' ', false);
    assert!(after_hide < hidden, "hiding cells did not shrink the transcript");
    assert_eq!(after_hide, tr.layout(&theme, tone, 80, ' ', false).lines.len());
}


/// Append settled turns — user, assistant, and a tool with a fat result —
/// until the laid-out height passes `PRUNE_HIGH_ROWS`. Returns the turn count.
fn fill_past_high_mark(tr: &mut Transcript, width: u16) -> usize {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let pad = "a row of tool output that wraps when the pane is narrow. ";
    let mut turns = 0;
    // Measured in chunks, not per turn: the point is the height, and a full
    // re-sum every turn would make the fixture quadratic.
    loop {
        for _ in 0..24 {
            let i = tr.cells.len();
            tr.push_user(format!("prompt {i}"), false);
            tr.apply(UiEvent::AssistantFinal {
                session: "s".into(),
                text: format!("answer {i}\n"),
                model: Some("m".into()),
            });
            tr.apply(UiEvent::ToolCall {
                session: "s".into(),
                call_id: format!("c{i}"),
                name: "bash".into(),
                arguments: format!(r#"{{"command":"turn {i}"}}"#),
                diff: None,
            });
            tr.apply(UiEvent::ToolResult {
                session: "s".into(),
                call_id: format!("c{i}"),
                is_error: false,
                text: (0..40).map(|k| format!("{pad}{k}")).collect::<Vec<_>>().join("\n"),
                error: None,
            });
            turns += 1;
        }
        if tr.row_count(&theme, tone, width, ' ', false) > PRUNE_HIGH_ROWS {
            return turns;
        }
    }
}

fn long_transcript(width: u16) -> Transcript {
    let mut tr = t("s");
    fill_past_high_mark(&mut tr, width);
    tr
}

/// The bound itself: a prune drops the oldest rows, lands at or under the low
/// mark, and leaves the surviving tail byte-identical to the slice of the
/// pre-prune layout it came from. Nothing about the visible session changes
/// except that its beginning is gone.
#[test]
fn prune_drops_the_oldest_rows_and_keeps_the_tail_intact() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let width = 100u16;
    let mut tr = long_transcript(width);
    let before = tr.layout(&theme, tone, width, ' ', false);
    let total = before.lines.len();
    assert!(total > PRUNE_HIGH_ROWS, "fixture should be over the high mark, got {total}");
    let cells_before = tr.cells.len();

    let removed = tr.prune_oldest(total);
    assert!(removed > 0, "nothing was pruned");
    let cut = cells_before - tr.cells.len();
    assert!(cut > 0 && cut < cells_before, "cut {cut} of {cells_before} cells");

    let after_rows = tr.row_count(&theme, tone, width, ' ', false);
    assert!(after_rows <= PRUNE_LOW_ROWS, "pruned to {after_rows}, above the low mark");
    assert!(
        after_rows > PRUNE_LOW_ROWS - 400,
        "pruned to {after_rows}: the hysteresis band should be spent, not overshot"
    );
    assert_eq!(after_rows, total - removed, "removed {removed} rows of {total}");

    let after = tr.layout(&theme, tone, width, ' ', false);
    assert_eq!(after.lines.len(), after_rows);
    assert_eq!(after.lines, before.lines[removed..], "the tail changed");
    assert_eq!(after.owners.len(), after.lines.len());
    // Owners are cell indexes, so they rebase by exactly the cut.
    let rebased: Vec<Option<usize>> = before.owners[removed..].iter().map(|o| o.map(|i| i - cut)).collect();
    assert_eq!(after.owners, rebased, "owner indexes did not rebase by {cut}");
    // Prompt spans rebase on both axes and keep their order.
    let prompts: Vec<UserPromptLine> = before.users
        .iter()
        .filter(|p| p.line >= removed)
        .map(|p| UserPromptLine { cell: p.cell - cut, line: p.line - removed, end: p.end - removed })
        .collect();
    assert_eq!(after.users.len(), prompts.len(), "prompt count");
    for (got, want) in after.users.iter().zip(&prompts) {
        assert_eq!(got.cell, want.cell, "prompt cell");
        assert_eq!(got.line, want.line, "prompt line");
        assert_eq!(got.end, want.end, "prompt end");
    }
}

/// Pruning shifts every index and bumps the generation, so it must never cut
/// into work that is still in flight — an open tool has a `call_id` pointing
/// at its cell, and a streaming assistant cell is being appended to.
#[test]
fn prune_never_removes_an_unsettled_cell() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let width = 100u16;

    // An unsettled head blocks the cut entirely.
    let mut tr = t("s");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "stuck".into(),
        name: "bash".into(),
        arguments: "{}".into(),
        diff: None,
    });
    let gen = tr.gen();
    fill_past_high_mark(&mut tr, width);
    let total = tr.row_count(&theme, tone, width, ' ', false);
    let cells = tr.cells.len();
    assert_eq!(tr.prune_oldest(total), 0, "pruned past an open tool at index 0");
    assert_eq!(tr.cells.len(), cells, "cells moved");
    assert_eq!(tr.gen(), gen, "generation bumped for a no-op prune");
    assert!(matches!(&tr.cells[0].kind, CellKind::Tool { ok: None, .. }));

    // An unsettled tail survives the cut, still open.
    for unsettled in ["tool", "stream", "shell"] {
        let mut tr = long_transcript(width);
        let live = match unsettled {
            "tool" => {
                tr.apply(UiEvent::ToolCall {
                    session: "s".into(),
                    call_id: "live".into(),
                    name: "bash".into(),
                    arguments: r#"{"command":"still running"}"#.into(),
                    diff: None,
                });
                *tr.tools.get("live").expect("open tool indexed")
            }
            "stream" => {
                tr.apply(UiEvent::TextDelta { session: "s".into(), text: "partial".into() });
                tr.cells.len() - 1
            }
            _ => tr.push_shell("sleep 99".into()),
        };
        let total = tr.row_count(&theme, tone, width, ' ', false);
        let cells = tr.cells.len();
        let removed = tr.prune_oldest(total);
        assert!(removed > 0, "{unsettled}: nothing pruned");
        let cut = cells - tr.cells.len();
        assert!(cut <= live, "{unsettled}: the cut ran past the in-flight cell");
        let at = live - cut;
        match unsettled {
            "tool" => {
                assert!(matches!(&tr.cells[at].kind, CellKind::Tool { ok: None, .. }));
                assert_eq!(tr.tools.get("live").copied(), Some(at), "tool index not rebased");
            }
            "stream" => {
                assert!(matches!(&tr.cells[at].kind, CellKind::Assistant { done: false, .. }));
            }
            _ => assert!(matches!(&tr.cells[at].kind, CellKind::Shell { output: None, .. })),
        }
    }
}

/// The maps and cursors that index cells have to move with the cut, or the
/// next event for a surviving cell lands in the wrong place — or appends an
/// orphan instead of updating in place.
#[test]
fn prune_rebases_the_indexes_that_point_into_the_tail() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let width = 100u16;
    let mut tr = long_transcript(width);
    tr.apply(UiEvent::Plan { session: "s".into(), summary: "one; two".into() });
    let plan_before = tr.plan_cell.expect("plan cell");
    tr.apply(UiEvent::ToolCall {
        session: "s".into(),
        call_id: "live".into(),
        name: "bash".into(),
        arguments: r#"{"command":"still running"}"#.into(),
        diff: None,
    });
    let live_before = *tr.tools.get("live").expect("open tool indexed");

    let total = tr.row_count(&theme, tone, width, ' ', false);
    let cells = tr.cells.len();
    assert!(tr.prune_oldest(total) > 0);
    let cut = cells - tr.cells.len();
    assert!(cut > 0 && cut < plan_before, "cut {cut} vs plan {plan_before}");
    assert_eq!(tr.plan_cell, Some(plan_before - cut), "plan cursor not rebased");
    assert_eq!(tr.tools.get("live").copied(), Some(live_before - cut), "tool index not rebased");

    // A result for the surviving tool writes into its cell rather than
    // appending an orphan.
    let len = tr.cells.len();
    tr.apply(UiEvent::ToolResult {
        session: "s".into(),
        call_id: "live".into(),
        is_error: false,
        text: "finished\n".into(),
        error: None,
    });
    assert_eq!(tr.cells.len(), len, "a result after a prune appended a cell");
    match &tr.cells[live_before - cut].kind {
        CellKind::Tool { ok, result, .. } => {
            assert_eq!(*ok, Some(true), "result landed somewhere else");
            assert!(result.contains("finished"), "got {result:?}");
        }
        other => panic!("expected the open tool, got {other:?}"),
    }
    // Same for the plan cursor: the next Plan replaces in place.
    tr.apply(UiEvent::Plan { session: "s".into(), summary: "three".into() });
    assert_eq!(tr.cells.len(), len, "a plan after a prune appended a cell");
    assert_eq!(tr.plan_cell, Some(plan_before - cut));
}

/// A prune invalidates every cell index the transcript ever handed out, which
/// is what the generation is for: handles captured before the cut must no-op
/// afterwards instead of writing into whatever cell now sits at that index.
#[test]
fn prune_bumps_the_generation_so_stale_handles_no_op() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let width = 100u16;
    let mut tr = long_transcript(width);
    let shell = tr.push_shell("ls -la".into());
    tr.finish_shell(shell, Some(0), "ok\n".into(), tr.gen());
    let gen = tr.gen();
    let total = tr.row_count(&theme, tone, width, ' ', false);
    assert!(tr.prune_oldest(total) > 0);
    assert_ne!(tr.gen(), gen, "a prune must bump the generation");

    // A local shell finishing against the pre-prune generation must not write
    // into the cell that happens to occupy its old index now.
    let late = tr.push_shell("late".into());
    tr.finish_shell(late, Some(1), "boom\n".into(), gen);
    match &tr.cells[late].kind {
        CellKind::Shell { output, .. } => assert!(output.is_none(), "stale finish_shell wrote"),
        other => panic!("expected a shell, got {other:?}"),
    }
    tr.finish_shell(late, Some(1), "boom\n".into(), tr.gen());
    assert!(matches!(&tr.cells[late].kind, CellKind::Shell { output: Some(_), .. }));

    // Nor may a stale hide handle blank a surviving cell.
    tr.hide_cells(&[0], gen);
    assert!(!tr.cells[0].hidden, "stale hide_cells took effect");
    tr.hide_cells(&[0], tr.gen());
    assert!(tr.cells[0].hidden);
}

/// Below the high mark the bound costs nothing: no cut, no generation bump, no
/// dropped measure cache. This is the hysteresis that keeps a session sitting
/// near the mark from pruning on every frame.
#[test]
fn prune_is_inert_below_the_high_mark() {
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let mut tr = fixture();
    let total = tr.row_count(&theme, tone, 100, ' ', false);
    assert!(total < PRUNE_HIGH_ROWS);
    let gen = tr.gen();
    let cells = tr.cells.len();
    assert_eq!(tr.prune_oldest(total), 0);
    assert_eq!(tr.prune_oldest(PRUNE_HIGH_ROWS), 0, "the high mark itself is not over");
    assert_eq!(tr.cells.len(), cells);
    assert_eq!(tr.gen(), gen);
    // The measure cache survived, so the next frame is still cheap.
    assert!(tr.measure.is_some(), "an inert prune dropped the measure cache");
    assert_eq!(tr.row_count(&theme, tone, 100, ' ', false), total);
}
