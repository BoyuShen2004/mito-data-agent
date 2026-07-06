"""Start the Mito Data Agent chat web UI."""

from __future__ import annotations

import argparse
import socket


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _find_free_port(host: str, start: int, max_tries: int = 20) -> int:
    for offset in range(max_tries):
        port = start + offset
        if not _port_in_use(host, port):
            return port
    raise RuntimeError(f"No free port found in range {start}-{start + max_tries - 1}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Mito Data Agent — chat web UI")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    parser.add_argument(
        "--clear-outputs",
        action="store_true",
        help="Delete all outputs/ artifacts and run history before starting",
    )
    parser.add_argument(
        "-y", "--yes",
        action="store_true",
        help="Skip confirmation when using --clear-outputs",
    )
    parser.add_argument(
        "--no-auto-port",
        action="store_true",
        help="Fail instead of trying the next port if the requested port is busy",
    )
    parser.add_argument(
        "--trace",
        action="store_true",
        help="Enable LangGraph step trace for all chat requests (also toggled in UI)",
    )
    args = parser.parse_args(argv)

    if args.trace:
        import os
        os.environ["MITO_AGENT_TRACE"] = "1"

    if args.clear_outputs:
        from mito_data_agent.cli.common import run_clear

        stats = run_clear(args.yes)
        if stats.get("cancelled"):
            return
        print()

    import uvicorn

    port = args.port
    if _port_in_use(args.host, port):
        if not args.no_auto_port:
            print(f"  Port {port} is already in use, trying next available port...")
            port = _find_free_port(args.host, port + 1)
        else:
            raise SystemExit(
                f"Port {port} is already in use.\n"
                f"  Stop the other process:  fuser -k {port}/tcp\n"
                f"  Or use a different port: python -m mito_data_agent web --port {port + 1}"
            )

    print("\n  Mito Data Agent chat UI")
    print(f"  Open http://{args.host}:{port} in your browser\n")

    uvicorn.run(
        "mito_data_agent.web.server:app",
        host=args.host,
        port=port,
        reload=False,
    )
