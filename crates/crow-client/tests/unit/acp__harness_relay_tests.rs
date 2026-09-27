//! The `/harness` relay — the seam that lets one controller thread outlive the
//! connection it started with.
//!
//! `run_blocking`'s supervisor loop distinguishes a switch from a shutdown by
//! whether `switch_rx` yields, so everything load-bearing is a channel
//! behaviour of `relay_commands`: what it forwards, what it intercepts, what it
//! hands back, and what it tells the painter. Tested with channels, not with a
//! spawned agent — `tests/startup_session_e2e.rs` owns that rung.

use super::*;
use std::sync::mpsc::{self, Receiver, Sender};
use std::time::Duration;

/// Longer than a relay needs, short enough that a hung one fails the suite
/// instead of stalling it.
const WAIT: Duration = Duration::from_secs(5);

fn prompt(text: &str) -> Cmd {
    Cmd::Prompt {
        session_id: "s".into(),
        text: text.into(),
    }
}

/// Join a relay thread with a deadline. A relay that never exits is one of the
/// bugs under test — it would be holding `switch_tx`, so `run_blocking`'s
/// `switch_rx.recv()` would block the controller thread forever and crow
/// would never quit. Waiting on the join directly would turn that regression
/// into a hung suite.
fn bounded_join(join: std::thread::JoinHandle<()>) {
    let (done, joined) = mpsc::channel::<()>();
    std::thread::spawn(move || {
        let _ = join.join();
        let _ = done.send(());
    });
    assert!(
        joined.recv_timeout(WAIT).is_ok(),
        "the relay thread never exited"
    );
}

struct Relay {
    painter: Sender<Cmd>,
    stack: Receiver<Cmd>,
    switched: Receiver<(Receiver<Cmd>, AcpEndpoint)>,
    events: Receiver<AppEvent>,
    join: std::thread::JoinHandle<()>,
}

fn relay() -> Relay {
    let (painter, cmd_rx) = mpsc::channel::<Cmd>();
    let (relay_tx, stack) = mpsc::channel::<Cmd>();
    let (switch_tx, switched) = mpsc::channel();
    let (bus, events) = mpsc::channel::<AppEvent>();
    let join = std::thread::Builder::new()
        .name("relay-test".into())
        .spawn(move || relay_commands(cmd_rx, relay_tx, switch_tx, &bus))
        .expect("spawn the relay");
    Relay {
        painter,
        stack,
        switched,
        events,
        join,
    }
}

impl Relay {
    /// Everything the relay put on the bus, as `kind:payload` tags. `AppEvent`
    /// has no `Debug`, so an event this test does not know becomes `other` and
    /// fails the comparison by not being the expected tag.
    fn said(&self) -> Vec<String> {
        let mut out = Vec::new();
        while let Ok(event) = self.events.try_recv() {
            out.push(match event {
                AppEvent::Ctl(CtlEvent::Starting { runtime }) => format!("starting:{runtime}"),
                AppEvent::Ctl(CtlEvent::Error(text)) => format!("error:{text}"),
                _ => "other".into(),
            });
        }
        out
    }

    fn switched(&self) -> (Receiver<Cmd>, AcpEndpoint) {
        self.switched
            .recv_timeout(WAIT)
            .expect("the relay hands the switch to the supervisor")
    }
}

#[test]
fn the_relay_forwards_every_command_except_the_switch() {
    let r = relay();
    r.painter.send(prompt("one")).expect("painter channel open");
    r.painter
        .send(Cmd::Interrupt {
            session_id: "s".into(),
        })
        .expect("painter channel open");

    assert!(
        matches!(r.stack.recv_timeout(WAIT), Ok(Cmd::Prompt { .. })),
        "an ordinary command reaches this generation's stack"
    );
    assert!(
        matches!(r.stack.recv_timeout(WAIT), Ok(Cmd::Interrupt { .. })),
        "and so does the next one"
    );

    r.painter
        .send(Cmd::SwitchHarness {
            argv: vec!["agent".into(), "acp2".into()],
        })
        .expect("painter channel open");

    let (handed, endpoint) = r.switched();
    match endpoint {
        AcpEndpoint::Spawn(argv) => assert_eq!(argv, ["agent", "acp2"]),
        _ => panic!("a switch always respawns; an attach endpoint is not switchable"),
    }
    // `runtime: "harness"` is what makes main.rs repair raw mode and poll at
    // 10 ms instead of the frame pacer while the terminal belongs to the
    // switch. Without it the pane is left in whatever mode the dead stack set.
    assert_eq!(r.said(), ["starting:harness"]);
    assert!(
        r.stack.try_recv().is_err(),
        "the switch is intercepted, not forwarded into the stack being torn down"
    );

    drop(handed);
    bounded_join(r.join);
}

#[test]
fn the_painters_own_channel_survives_the_switch() {
    let r = relay();
    r.painter
        .send(Cmd::SwitchHarness {
            argv: vec!["b".into()],
        })
        .expect("painter channel open");
    let (handed, _endpoint) = r.switched();

    // `Controller::send` still holds the original `Sender` and is never told
    // the thread behind it was replaced, so the next generation has to read
    // the painter's own receiver — the one handed back, not a fresh channel
    // nothing is sending into.
    r.painter
        .send(prompt("after"))
        .expect("painter channel open");
    match handed.recv_timeout(WAIT) {
        Ok(Cmd::Prompt { text, .. }) => assert_eq!(text, "after"),
        other => {
            panic!("expected the post-switch prompt on the handed-back receiver, got {other:?}")
        }
    }

    drop(handed);
    bounded_join(r.join);
}

#[test]
fn a_painter_that_goes_away_is_a_shutdown_and_not_a_switch() {
    let Relay {
        painter,
        stack,
        switched,
        events,
        join,
    } = relay();
    drop(painter);
    bounded_join(join);

    // The relay is gone, so this is immediate: `switch_tx` went with it.
    // `run_blocking` respawns on `Ok` and returns on `Err`, so a shutdown that
    // arrived as `Ok` would respawn the agent forever.
    assert!(
        switched.recv().is_err(),
        "dropping the painter must not look like a harness switch"
    );
    drop(stack);
    let mut said = 0;
    while events.try_recv().is_ok() {
        said += 1;
    }
    assert_eq!(said, 0, "a shutdown says nothing about starting");
}

#[test]
fn a_stack_that_goes_away_ends_the_relay_instead_of_swallowing_commands() {
    let Relay {
        painter,
        stack,
        switched,
        events: _events,
        join,
    } = relay();
    drop(stack);
    painter
        .send(prompt("into the void"))
        .expect("painter channel open");

    // The painter is still alive and still sending, so the only thing that can
    // end the relay is the closed channel it forwards into. One that ignored
    // the send error would sit in `recv()` holding `switch_tx`.
    bounded_join(join);
    assert!(
        switched.recv().is_err(),
        "a dead generation is not a harness switch either"
    );
    drop(painter);
}
