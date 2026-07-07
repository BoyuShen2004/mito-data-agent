"""Launch the Mito Data Agent web UI.

    python -m mito_data_agent web                 # http://127.0.0.1:7860
    python -m mito_data_agent web --port 8000
"""

from __future__ import annotations

import argparse
import socket


def _port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def _find_free_port(host: str, start: int, tries: int = 20) -> int:
    for offset in range(tries):
        port = start + offset
        if not _port_in_use(host, port):
            return port
    raise SystemExit(f"No free port in range {start}-{start + tries - 1}.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="mito_data_agent web",
        description="Serve the Mito Data Agent web UI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=7860, help="Port (default: 7860)")
    parser.add_argument(
        "--no-auto-port",
        action="store_true",
        help="Fail if the requested port is busy instead of picking the next free one",
    )
    parser.add_argument("--reload", action="store_true", help="Auto-reload on code changes (dev)")
    args = parser.parse_args(argv)

    port = args.port
    if _port_in_use(args.host, port):
        if args.no_auto_port:
            raise SystemExit(f"Port {port} is already in use.")
        port = _find_free_port(args.host, port + 1)
        print(f"Port {args.port} busy — using {port} instead.")

    import uvicorn

    print(f"Mito Data Agent UI → http://{args.host}:{port}  (Ctrl+C to stop)")
    uvicorn.run(
        "mito_data_agent.web.server:app",
        host=args.host,
        port=port,
        reload=args.reload,
        log_level="info",
    )


if __name__ == "__main__":
    main()
