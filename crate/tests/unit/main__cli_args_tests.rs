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
        crate::runtime::crow_home_from(
            Some("/opt/crow"),
            Some("/opt/martty"),
            Some("/opt/dsh"),
            "/Users/test"
        ),
        PathBuf::from("/opt/crow")
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, Some("/opt/martty"), Some("/opt/dsh"), "/Users/test"),
        PathBuf::from("/opt/martty"),
        "a pre-rebrand MARTTY_HOME keeps its data"
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, None, Some("/opt/dsh"), "/Users/test"),
        PathBuf::from("/opt/dsh/.agents/crow")
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, None, None, "/Users/test"),
        PathBuf::from("/Users/test/.agents/crow")
    );
    assert_eq!(
        crate::runtime::crow_home_from(None, None, None, "/Users/test").join("sessions"),
        PathBuf::from("/Users/test/.agents/crow/sessions")
    );
}

#[test]
fn legacy_settings_come_from_the_martty_home_then_dsh_tui() {
    let default_root = PathBuf::from("/Users/test/.agents/crow/sessions");
    let paths = crate::runtime::legacy_settings_paths_from(
        default_root.to_str().unwrap(),
        &default_root,
        "/Users/test",
    );
    assert_eq!(
        paths,
        [
            PathBuf::from("/Users/test/.martty/settings.json"),
            PathBuf::from("/Users/test/.dsh-tui/sessions/dsh-tui-settings.json"),
        ],
        "the abandoned home is tried before the older dsh-tui file"
    );

    let custom =
        crate::runtime::legacy_settings_paths_from("/work/sessions", &default_root, "/Users/test");
    assert_eq!(
        custom,
        [PathBuf::from("/work/sessions/dsh-tui-settings.json")],
        "a custom --session-root has no ~/.martty analogue"
    );
}

#[test]
fn removed_runtime_aliases_are_rejected() {
    for flag in ["--runtime-bin", "--cordis"] {
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
