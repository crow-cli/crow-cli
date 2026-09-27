use super::*;
use std::sync::mpsc::Receiver;

fn test_app() -> (App, Receiver<AppEvent>) {
    let cfg = RuntimeConfig {
        bin: "demo".into(),
        cordis: "demo".into(),
        workspace: "/tmp".into(),
        session_root: std::env::temp_dir()
            .join(format!("dsh-tui-scroll-{}", std::process::id()))
            .to_string_lossy()
            .into_owned(),
        provider: "deepseek-official".into(),
        model: "deepseek-v4-flash".into(),
        max_tokens: None,
        base_url: None,
        api_key: None,
        startup_session: None,
    };
    let (tx, rx) = std::sync::mpsc::channel::<AppEvent>();
    let app = App::new(Some(Theme::dark()), cfg, "s1".into(), true, false, tx);
    (app, rx)
}

#[test]
fn scroll_by_after_jump_top_resolves_the_sentinel_against_the_last_frame() {
    let (mut app, _rx) = test_app();
    // Last rendered frame: 200 layout lines in a 20-row pane → max_scroll =
    // 180. The snapshot is viewport-sized; `total` carries the line count.
    app.chat_view.area = ratatui::layout::Rect::new(0, 0, 80, 20);
    app.chat_view.total = 200;
    app.chat_view.top = 180;
    app.chat_view.lines = (180..200).map(|i| format!("line {i}")).collect();

    // JumpTop leaves the usize::MAX sentinel until the next draw; a wheel
    // flick arriving in the same event burst must stay relative to the top
    // (MAX as i64 would wrap to -1 and teleport the viewport to the tail).
    app.scroll_up = usize::MAX;
    app.scroll_by(3);
    assert_eq!(app.scroll_up, 183, "wheel-up from the top clamps at the top");

    app.scroll_up = usize::MAX;
    app.scroll_by(-3);
    assert_eq!(app.scroll_up, 177, "wheel-down from the top moves 3 lines");
}

#[test]
fn scroll_by_without_the_sentinel_is_untouched() {
    let (mut app, _rx) = test_app();
    app.scroll_up = 10;
    app.scroll_by(5);
    assert_eq!(app.scroll_up, 15);
    app.scroll_by(-100);
    assert_eq!(app.scroll_up, 0, "clamps at the streaming tail");
}


/// Fill the app's transcript past the scrollback high mark with settled turns
/// and return the measured height.
fn fill_scrollback(app: &mut App, width: u16) -> usize {
    use crate::events::UiEvent;
    let theme = Theme::dark();
    let tone = crate::markdown::ToneMode::Single;
    let pad = "a row of tool output that wraps when the pane is narrow. ";
    loop {
        for _ in 0..24 {
            let i = app.transcript.cells.len();
            app.transcript.push_user(format!("prompt {i}"), false);
            app.transcript.apply(UiEvent::AssistantFinal {
                session: "s1".into(),
                text: format!("answer {i}\n"),
                model: Some("m".into()),
            });
            app.transcript.apply(UiEvent::ToolCall {
                session: "s1".into(),
                call_id: format!("c{i}"),
                name: "bash".into(),
                arguments: format!(r#"{{"command":"turn {i}"}}"#),
                diff: None,
            });
            app.transcript.apply(UiEvent::ToolResult {
                session: "s1".into(),
                call_id: format!("c{i}"),
                is_error: false,
                text: (0..40).map(|k| format!("{pad}{k}")).collect::<Vec<_>>().join("\n"),
                error: None,
            });
        }
        let rows = app.transcript.row_count(&theme, tone, width, ' ', false);
        if rows > crate::transcript::PRUNE_HIGH_ROWS {
            return rows;
        }
    }
}

/// A prune shifts every cell index the app is holding, so it has to wait for
/// the outstanding ones to land: a steer echo waiting to be hidden and a local
/// shell waiting to write into its cell both name an index by position.
#[test]
fn prune_scrollback_waits_for_outstanding_cell_indexes() {
    let (mut app, _rx) = test_app();
    let rows = fill_scrollback(&mut app, 100);
    let cells = app.transcript.cells.len();

    app.shell_pending.push((7, "s1".into(), 3, app.transcript.gen()));
    assert_eq!(app.prune_scrollback(rows), 0, "pruned with a shell write outstanding");
    assert_eq!(app.transcript.cells.len(), cells);
    app.shell_pending.clear();

    app.pending_steer_cells.insert(
        11,
        PendingSteer {
            cells: vec![5, 6],
            blocks: vec![StagedBlock::Text("steer".into())],
            requeue_front: false,
            gen: app.transcript.gen(),
        },
    );
    assert_eq!(app.prune_scrollback(rows), 0, "pruned with a steer echo outstanding");
    assert_eq!(app.transcript.cells.len(), cells);
    app.pending_steer_cells.clear();

    // Nothing outstanding: the bound fires.
    assert!(app.prune_scrollback(rows) > 0, "the prune never happened");
    assert!(app.transcript.cells.len() < cells);
}

/// Rows vanishing above the viewport have to take an absolute scroll anchor
/// with them, or the pane jumps to different content mid-session. The ↥ jump
/// cursor indexes cells, so it is dropped the way crow-cli drops its block
/// cursor on prune.
#[test]
fn prune_scrollback_shifts_the_scroll_anchor_and_drops_the_jump_cursor() {
    let (mut app, _rx) = test_app();
    let rows = fill_scrollback(&mut app, 100);
    app.chat_view.manual_top = Some(rows - 40);
    app.prompt_jump_cell = Some(4);
    app.tip = None;

    let removed = app.prune_scrollback(rows);
    assert!(removed > 0);
    assert_eq!(
        app.chat_view.manual_top,
        Some(rows - 40 - removed),
        "the anchor did not move up with the pruned rows"
    );
    assert_eq!(app.prompt_jump_cell, None, "a stale jump cursor survived the prune");
    let (tip, _) = app.tip.as_ref().expect("the prune should say so");
    assert!(tip.contains(&removed.to_string()), "tip {tip:?} lacks the row count");

    // An anchor at or above the cut clamps at the new top rather than
    // underflowing.
    let rows_again = fill_scrollback(&mut app, 100);
    app.chat_view.manual_top = Some(0);
    assert!(app.prune_scrollback(rows_again) > 0, "the second prune never happened");
    assert_eq!(app.chat_view.manual_top, Some(0));
}

/// Below the high mark the bound is inert — no cut, no tip, no churn. This is
/// the hysteresis that keeps a long session from re-pruning every frame.
#[test]
fn prune_scrollback_is_inert_below_the_high_mark() {
    let (mut app, _rx) = test_app();
    app.transcript.push_user("hello".into(), false);
    app.chat_view.manual_top = Some(12);
    app.tip = None;
    assert_eq!(app.prune_scrollback(crate::transcript::PRUNE_HIGH_ROWS), 0);
    assert_eq!(app.prune_scrollback(0), 0);
    assert_eq!(app.transcript.cells.len(), 1);
    assert_eq!(app.chat_view.manual_top, Some(12));
    assert!(app.tip.is_none(), "an inert prune announced itself");
}
