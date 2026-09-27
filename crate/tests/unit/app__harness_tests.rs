//! `/harness` on the painter side: what the picker offers, what a switch
//! refuses, and what it writes.
//!
//! The respawn itself is `tests/startup_session_e2e.rs`'s job. Everything here
//! happens before `Cmd::SwitchHarness` is sent, and every one of them is a way
//! to leave `settings.json` and the running pane disagreeing about which agent
//! the user has.

use super::*;
use serde_json::json;
use std::sync::mpsc::Receiver;

/// Unique session root per call — `settings_path` derives the file this test
/// seeds from it, so two tests sharing a root would race over one file.
fn fresh_root() -> String {
    use std::sync::atomic::{AtomicU64, Ordering};
    static N: AtomicU64 = AtomicU64::new(0);
    let dir = std::env::temp_dir().join(format!(
        "dsh-tui-harness-{}-{}",
        std::process::id(),
        N.fetch_add(1, Ordering::Relaxed),
    ));
    let _ = std::fs::create_dir_all(&dir);
    dir.to_string_lossy().into_owned()
}

/// Two recipes that differ only in the argument that selects the protocol —
/// the real shape in a crow-cli `settings.json`, and the reason a switch has
/// to respawn rather than renegotiate.
fn two() -> serde_json::Value {
    json!({
        "harnesses": [
            {"id": "crow-cli", "label": "crow-cli", "command": "crow-cli", "args": ["acp"]},
            {"id": "crow-cli-v2", "label": "crow-cli (ACP v2)",
             "command": "crow-cli", "args": ["acp2"]}
        ],
        "defaultHarness": "crow-cli-v2",
        "uiPreset": "wide",
        "theme": "iceberg"
    })
}

fn seeded_app(settings: serde_json::Value) -> (App, Controller, Receiver<AppEvent>) {
    let root = fresh_root();
    let path = crate::runtime::settings_path(&root);
    std::fs::write(&path, settings.to_string()).expect("seed settings.json");
    let cfg = RuntimeConfig {
        bin: "demo".into(),
        cordis: "demo".into(),
        workspace: "/tmp".into(),
        session_root: root,
        provider: "deepseek-official".into(),
        model: "deepseek-v4-flash".into(),
        max_tokens: None,
        base_url: None,
        api_key: None,
        startup_session: None,
    };
    let (tx, rx) = std::sync::mpsc::channel::<AppEvent>();
    let ctl = Controller::start(cfg.clone(), true, None, tx.clone());
    let app = App::new(Some(Theme::dark()), cfg, "dsh-test".into(), true, false, tx);
    (app, ctl, rx)
}

fn tip(app: &App) -> String {
    app.tip
        .as_ref()
        .map(|(text, _)| text.as_str())
        .unwrap_or("")
        .to_owned()
}

fn saved(app: &App) -> serde_json::Value {
    let path = crate::runtime::settings_path(&app.cfg.session_root);
    serde_json::from_str(&std::fs::read_to_string(path).expect("settings.json written"))
        .expect("settings.json is valid JSON")
}

fn notices(app: &App) -> Vec<(NoticeLevel, String)> {
    app.transcript
        .cells
        .iter()
        .filter_map(|cell| match &cell.kind {
            crate::transcript::CellKind::Notice { level, text } => Some((*level, text.clone())),
            _ => None,
        })
        .collect()
}

#[test]
fn the_harness_picker_lists_the_recipes_and_marks_the_active_one() {
    let (mut app, _ctl, _rx) = seeded_app(two());
    app.open_harness_picker();

    let picker = app.picker.as_ref().expect("two recipes → a picker");
    assert!(
        matches!(picker.kind, PickerKind::Harness),
        "the picker has to be the harness one for enter to switch"
    );
    assert!(
        picker.title.contains("harness"),
        "an untitled picker does not say what enter does: {:?}",
        picker.title
    );
    // The meta column carries the recipe, because two harnesses that differ
    // only in `acp` vs `acp2` are otherwise the same row twice.
    let rows = picker
        .items
        .iter()
        .map(|item| (item.id.as_str(), item.label.as_str(), item.meta.as_str()))
        .collect::<Vec<_>>();
    assert_eq!(
        rows,
        [
            ("crow-cli", "crow-cli", "crow-cli acp"),
            ("crow-cli-v2", "crow-cli (ACP v2)", "crow-cli acp2 · active")
        ]
    );
    // Opens on the running value the way /model and /theme do (#102), so
    // enter on a freshly opened picker is a refusal and not a surprise switch.
    assert_eq!(picker.sel, 1);
}

#[test]
fn the_harness_picker_explains_an_empty_recipe_list_instead_of_opening() {
    let (mut app, _ctl, _rx) = seeded_app(json!({"defaultHarness": "gone", "theme": "iceberg"}));
    app.open_harness_picker();

    assert!(
        app.picker.is_none(),
        "an empty picker is a dead end with nothing to read"
    );
    assert!(
        tip(&app).contains("no harnesses configured"),
        "the user is told why nothing opened: {}",
        tip(&app)
    );
}

#[test]
fn switching_to_an_unknown_harness_changes_nothing() {
    let (mut app, ctl, _rx) = seeded_app(two());
    app.open_harness_picker();
    app.switch_harness("  codex  ", &ctl);

    assert!(
        tip(&app).contains("unknown harness: codex"),
        "the id is trimmed before it is reported: {}",
        tip(&app)
    );
    assert_eq!(
        saved(&app)["defaultHarness"],
        json!("crow-cli-v2"),
        "a refused switch must not persist"
    );
    assert!(
        app.picker.is_some(),
        "the picker stays open so a real recipe is one key away"
    );
    assert_eq!(notices(&app), []);
}

#[test]
fn switching_to_the_active_harness_is_refused_by_its_label() {
    let (mut app, ctl, _rx) = seeded_app(two());
    app.switch_harness("crow-cli-v2", &ctl);

    // The label, not the id: the user typed an id but recognises a label, and
    // the refusal is the only place either of them appears.
    assert!(
        tip(&app).contains("crow-cli (ACP v2) is already the active harness"),
        "{}",
        tip(&app)
    );
    assert_eq!(
        notices(&app),
        [],
        "a no-op switch says nothing on the transcript"
    );
}

#[test]
fn a_switch_persists_the_choice_and_forgets_what_the_dead_connection_was_delivering() {
    let (mut app, ctl, _rx) = seeded_app(two());
    // Delivery state the outgoing connection owned: a queued prompt that will
    // never be sent, a turn that will never settle, and a startup bind to a
    // session that no longer exists.
    app.prompt_queue.push_back(ClientQueuedPrompt {
        id: 7,
        blocks: vec![StagedBlock::Text("queued for the old agent".into())],
    });
    app.queued = 1;
    app.queue_selection = Some(0);
    app.prompt_pending = true;
    app.startup_bound = true;
    app.state = RunState::Running;
    app.run_started = Some(std::time::Instant::now());

    app.open_harness_picker();
    app.switch_harness("crow-cli", &ctl);

    let after = saved(&app);
    assert_eq!(after["defaultHarness"], json!("crow-cli"));
    // Written before the switch is requested, and patched rather than
    // rewritten: the same file carries the compositor's keys.
    assert_eq!(
        after["uiPreset"],
        json!("wide"),
        "a harness switch owns one key"
    );
    assert_eq!(after["theme"], json!("iceberg"));
    assert_eq!(
        after["harnesses"][1]["id"],
        json!("crow-cli-v2"),
        "the recipes survive their own switch"
    );

    assert!(app.picker.is_none(), "the picker closes on a switch");
    assert!(
        app.prompt_queue.is_empty(),
        "the queue belonged to the dead connection"
    );
    assert_eq!(app.queued, 0);
    assert_eq!(app.queue_selection, None);
    assert!(
        !app.prompt_pending,
        "no turn is in flight on an agent that is gone"
    );
    assert!(
        !app.startup_bound,
        "the new connection binds its own session"
    );
    assert_eq!(app.state, RunState::Idle);
    assert_eq!(app.run_started, None);
    assert_eq!(
        notices(&app),
        vec![(NoticeLevel::Info, "⟲ harness → crow-cli".into())]
    );
}

#[test]
fn a_switch_on_a_fresh_pane_tips_as_well_as_noticing() {
    let (mut app, ctl, _rx) = seeded_app(two());
    assert!(
        app.show_banner,
        "a pane that has not sent a prompt yet is showing the welcome banner"
    );
    app.switch_harness("crow-cli", &ctl);

    // The chat pane draws the banner INSTEAD of the transcript, so the notice
    // on its own is invisible here: the user switches harness, every session
    // is dropped, and nothing on screen says so.
    assert!(
        tip(&app).contains("⟲ harness → crow-cli"),
        "the switch is visible on a fresh pane: {}",
        tip(&app)
    );
    assert_eq!(
        notices(&app),
        vec![(NoticeLevel::Info, "⟲ harness → crow-cli".into())],
        "the transcript still records where the agent changed"
    );

    let (mut app, ctl, _rx) = seeded_app(two());
    app.show_banner = false;
    app.switch_harness("crow-cli", &ctl);
    assert!(
        app.tip.is_none(),
        "a drawn transcript does not need the same sentence twice"
    );
    assert_eq!(
        notices(&app),
        vec![(NoticeLevel::Info, "⟲ harness → crow-cli".into())]
    );
}

#[test]
fn persisting_the_default_harness_keeps_the_keys_it_does_not_own() {
    let root = fresh_root();
    let path = crate::runtime::settings_path(&root);
    std::fs::write(
        &path,
        r#"{"uiPreset":"wide","harnesses":[{"id":"a","command":"a"}],"defaultHarness":"a"}"#,
    )
    .expect("seed");

    persist_default_harness(&path, "b").expect("write");

    let after: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(after["defaultHarness"], json!("b"));
    assert_eq!(after["uiPreset"], json!("wide"));
    assert_eq!(after["harnesses"][0]["id"], json!("a"));
}

#[test]
fn persisting_the_default_harness_creates_a_settings_file_that_is_not_there_yet() {
    let root = fresh_root();
    let path = crate::runtime::settings_path(&root)
        .join("nested")
        .join("settings.json");
    assert!(!path.exists());

    persist_default_harness(&path, "b").expect("write");

    let after: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(after, json!({"defaultHarness": "b"}));
}

#[test]
fn a_settings_file_that_does_not_parse_is_quarantined_not_replaced() {
    let root = fresh_root();
    let path = crate::runtime::settings_path(&root);
    std::fs::write(&path, "{ the compositor was mid-write").expect("seed");

    persist_default_harness(&path, "b").expect("write");

    let after: serde_json::Value =
        serde_json::from_str(&std::fs::read_to_string(&path).unwrap()).unwrap();
    assert_eq!(after, json!({"defaultHarness": "b"}));
    // The recipes in the broken file are the npm host's, and they are not
    // recoverable from anywhere else.
    let quarantined = std::fs::read_dir(path.parent().unwrap())
        .expect("read the settings dir")
        .filter_map(|entry| entry.ok())
        .map(|entry| entry.path())
        .find(|path| {
            path.file_name()
                .is_some_and(|name| name.to_string_lossy().starts_with("settings.json.corrupt-"))
        })
        .expect("the unparseable file is kept for recovery");
    assert_eq!(
        std::fs::read_to_string(&quarantined).unwrap(),
        "{ the compositor was mid-write"
    );
}
