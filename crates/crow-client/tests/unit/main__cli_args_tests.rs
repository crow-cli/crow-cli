use super::*;
use std::path::{Path, PathBuf};

#[test]
fn agent_flag_and_args() {
    let args = parse_args_from([
        "--agent".into(),
        "crowterm-agent".into(),
        "--agent-arg".into(),
        "--profile".into(),
        "--agent-arg".into(),
        "acp".into(),
    ])
    .unwrap();
    assert_eq!(agent_argv(&args), vec!["crowterm-agent", "--profile", "acp"]);
}

#[test]
fn help_mentions_agent() {
    assert!(HELP.contains("--agent"));
    assert!(HELP.contains("--agent-arg"));
}

#[test]
fn crow_home_precedence_owns_the_default_session_root() {
    assert_eq!(
        crate::runtime::crow_home_from(Some("/opt/crow"), "/Users/test"),
        PathBuf::from("/opt/crow")
    );
    assert_eq!(
        crate::runtime::crow_home_from(Some(""), "/Users/test"),
        PathBuf::from("/Users/test/.agents/crow"),
        "an empty CROW_HOME is not a home"
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, "/Users/test"),
        PathBuf::from("/Users/test/.agents/crow")
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, "/Users/test").join("sessions"),
        PathBuf::from("/Users/test/.agents/crow/sessions")
    );
}

#[test]
fn a_pre_rebrand_martty_home_is_not_read() {
    // The shim took MARTTY_HOME and DSH_HOME and honoured them ahead of
    // ~/.agents/crow. Same inputs, opposite assertion: both are dead env vars
    // now, and nothing in src reads either name. Safe to set unconditionally
    // and in parallel with the rest of the suite, because no code path can
    // observe them.
    std::env::set_var("MARTTY_HOME", "/opt/martty");
    std::env::set_var("DSH_HOME", "/opt/dsh");
    let home = crate::runtime::crow_home();
    std::env::remove_var("MARTTY_HOME");
    std::env::remove_var("DSH_HOME");

    let crow = std::env::var("CROW_HOME")
        .ok()
        .filter(|value| !value.is_empty());
    let user = std::env::var("HOME").unwrap_or_else(|_| ".".into());
    assert_eq!(
        home,
        crate::runtime::crow_home_from(crow.as_deref(), &user),
        "the home is explained entirely by CROW_HOME and HOME"
    );
    assert_ne!(home, PathBuf::from("/opt/martty"), "MARTTY_HOME is not read");
    assert_ne!(
        home,
        PathBuf::from("/opt/dsh/.agents/crow"),
        "DSH_HOME is not read"
    );
}

#[test]
fn settings_come_from_the_configured_root_only() {
    // `legacy_settings_paths*` is deleted, so `~/.martty/settings.json` and
    // `.dsh-tui-settings.json` are not read. This used to assert the search
    // order; it now asserts there is no search: a valid legacy file sitting
    // right where the shim looked is ignored, and the configured file is the
    // only source.
    let home = std::env::temp_dir().join(format!("crow-settings-only-{}", std::process::id()));
    let _ = std::fs::remove_dir_all(&home);
    let session_root = home.join("sessions");
    std::fs::create_dir_all(&session_root).unwrap();
    std::fs::create_dir_all(home.join(".martty")).unwrap();
    std::fs::create_dir_all(home.join(".dsh-tui/sessions")).unwrap();
    for legacy in [
        home.join(".martty/settings.json"),
        home.join(".dsh-tui/sessions/dsh-tui-settings.json"),
    ] {
        std::fs::write(&legacy, r#"{"uiPreset":"legacy-home"}"#).unwrap();
    }

    let cfg = crate::runtime::RuntimeConfig {
        bin: "/bin/agent acp".into(),
        workspace: "/tmp".into(),
        session_root: session_root.to_string_lossy().into_owned(),
        startup_session: None,
    };
    assert_eq!(
        crate::app::App::locale_settings_path(&cfg),
        session_root.join("settings.json"),
        "a custom --session-root reads its own settings.json"
    );
    let loaded = crate::app::App::load_settings(&cfg);
    assert_eq!(loaded.ui_preset, "default", "no legacy file is consulted");

    std::fs::write(
        session_root.join("settings.json"),
        r#"{"uiPreset":"configured"}"#,
    )
    .unwrap();
    assert_eq!(
        crate::app::App::load_settings(&cfg).ui_preset,
        "configured",
        "the configured file is the one source of truth"
    );
    let _ = std::fs::remove_dir_all(&home);
}

#[test]
fn removed_runtime_aliases_are_rejected() {
    // The client owns no model route and no credentials, so the flags that
    // used to carry them are gone — not hidden, rejected.
    for flag in [
        "--runtime-bin",
        "--cordis",
        "--provider",
        "--base-url",
        "--api-key",
        "--max-tokens",
    ] {
        let err = match parse_args_from([flag.into(), "legacy".into()]) {
            Ok(_) => panic!("{flag} unexpectedly remained accepted"),
            Err(err) => err,
        };
        assert!(
            err.to_string().contains("unknown argument"),
            "{flag} must not remain as a hidden legacy option: {err:#}"
        );
    }
}

#[test]
fn help_offers_no_provider_route_and_no_credentials() {
    for gone in ["--provider", "--base-url", "--api-key", "--max-tokens"] {
        assert!(!HELP.contains(gone), "help must not offer {gone}:\n{HELP}");
    }
    assert!(
        !HELP.to_ascii_uppercase().contains("DEEPSEEK"),
        "help must not name a provider brand or its env vars:\n{HELP}"
    );
    assert!(
        HELP.contains("--model"),
        "help must still offer --model, the request handed to the agent:\n{HELP}"
    );
}

#[test]
fn model_flag_becomes_the_startup_request() {
    let args = parse_args_from([
        "-w".into(),
        "/tmp".into(),
        "--model".into(),
        "gpt-5.6-sol".into(),
    ])
    .unwrap();
    assert_eq!(
        startup_model(&args).as_deref(),
        Some("gpt-5.6-sol"),
        "--model must reach the session bind, not die in Args"
    );
}

#[test]
fn no_model_flag_means_the_agent_chooses() {
    let args = parse_args_from(["-w".into(), "/tmp".into()]).unwrap();
    assert_eq!(
        startup_model(&args),
        std::env::var("CROW_MODEL").ok().filter(|value| !value.trim().is_empty()),
        "with no --model the only source is $CROW_MODEL: the client has no default model"
    );
}

#[test]
fn dump_frame_defaults_and_explicit_dims() {
    let args = parse_args_from(["--dump-frame".into()]).unwrap();
    assert_eq!(args.dump_frame, Some((100, 34)));
    let args = parse_args_from(["--dump-frame".into(), "80x24".into()]).unwrap();
    assert_eq!(args.dump_frame, Some((80, 24)));
}

#[test]
fn dump_frame_does_not_swallow_the_next_flag() {
    // `--dump-frame --theme light`: --theme is a flag, not dimensions.
    let args = parse_args_from([
        "--dump-frame".into(),
        "--theme".into(),
        "light".into(),
        "--demo".into(),
    ])
    .unwrap();
    assert_eq!(args.dump_frame, Some((100, 34)));
    assert_eq!(args.theme.as_deref(), Some("light"));
    assert!(args.demo);
}

#[test]
fn session_id_flag_becomes_the_startup_reattach_target() {
    let args = parse_args_from([
        "-w".into(),
        "/tmp".into(),
        "--session-id".into(),
        "coolname".into(),
    ])
    .unwrap();
    let cfg = build_config(&args).unwrap();
    assert_eq!(
        cfg.startup_session.as_deref(),
        Some("coolname"),
        "--session-id must reach the runtime, not die in Args"
    );
}

#[test]
fn no_session_id_flag_means_no_startup_reattach() {
    let args = parse_args_from(["-w".into(), "/tmp".into()]).unwrap();
    let cfg = build_config(&args).unwrap();
    assert_eq!(cfg.startup_session, None);
}

#[test]
fn gui_flag_defaults_off() {
    let args = parse_args_from(["-w".into(), "/tmp".into()]).unwrap();
    assert!(!args.gui, "the TUI must stay the default front end");
}

#[test]
fn gui_flag_turns_on_the_native_window() {
    let args = parse_args_from(["--gui".into(), "-w".into(), "/tmp".into()]).unwrap();
    assert!(args.gui);
    assert_eq!(args.workspace.as_deref(), Some("/tmp"), "--gui must not eat the next flag");
}

#[test]
fn gui_flag_coexists_with_demo() {
    // `--demo --gui` is the cheap way to eyeball the GPU window with no runtime.
    let args = parse_args_from(["--demo".into(), "--gui".into()]).unwrap();
    assert!(args.demo);
    assert!(args.gui);
}

#[test]
fn help_mentions_gui() {
    assert!(HELP.contains("--gui"));
}
