//! crow-web — the rust state server behind the crow web client.
//!
//! The browser is a view; this process owns the state it views: the fs tree,
//! open buffers (content + dirty + mtime) and, later, pty sessions. Ctrl+S in
//! the editor is a commit message to this server, not a browser-side write.
use std::net::SocketAddr;
use std::path::PathBuf;

use axum::routing::get;
use axum::Router;

mod fs;
mod pty;
mod ws;

struct Args {
    port: u16,
    root: PathBuf,
    shell: Option<String>,
}

fn parse_args(argv: impl IntoIterator<Item = String>) -> anyhow::Result<Args> {
    let mut port = 2770u16;
    let mut root: Option<PathBuf> = None;
    let mut shell: Option<String> = None;
    let mut it = argv.into_iter().skip(1);
    while let Some(arg) = it.next() {
        match arg.as_str() {
            "--port" => {
                let value = it.next().unwrap_or_else(|| panic!("--port needs a value"));
                port = value.parse()?;
            }
            "--root" => {
                let value = it.next().unwrap_or_else(|| panic!("--root needs a value"));
                root = Some(PathBuf::from(value));
            }
            "--shell" => {
                let value = it.next().unwrap_or_else(|| panic!("--shell needs a value"));
                shell = Some(value);
            }
            other => panic!("unknown argument: {other}"),
        }
    }
    Ok(Args {
        port,
        root: root.unwrap_or_else(|| std::env::current_dir().expect("cwd")),
        shell,
    })
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    let args = parse_args(std::env::args())?;
    let root = args.root.canonicalize()?;
    let fs = ws::Fs::new(root.clone())?;
    let pty = pty::Config::new(root, args.shell);
    let app = Router::new()
        .route("/healthz", get(|| async { "ok" }))
        .merge(ws::router(fs.clone()))
        .merge(pty::router(pty.clone()));
    let listener =
        tokio::net::TcpListener::bind(SocketAddr::from(([127, 0, 0, 1], args.port))).await?;
    // The bound address, not the requested one: `--port 0` asks the kernel to
    // pick, and this line is how a launcher (or a test) learns which.
    let addr = listener.local_addr()?;
    println!(
        "crow-web serving {} on http://{addr} ({} for terminals)",
        fs.root(),
        pty.shell()
    );
    axum::serve(listener, app).await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::parse_args;

    #[test]
    fn defaults_port_and_root() {
        let args = parse_args(["crow-web".to_string()]).unwrap();
        assert_eq!(args.port, 2770);
        assert_eq!(args.root, std::env::current_dir().unwrap());
    }

    #[test]
    fn parses_port_and_root() {
        let args = parse_args(
            ["crow-web", "--port", "3001", "--root", "/tmp"]
                .map(str::to_string)
                .to_vec(),
        )
        .unwrap();
        assert_eq!(args.port, 3001);
        assert_eq!(args.root, std::path::PathBuf::from("/tmp"));
    }
}
