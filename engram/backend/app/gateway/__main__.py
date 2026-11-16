"""`python -m engram.backend.app.gateway` — Windows 兼容启动入口。

用法：python -m engram.backend.app.gateway [--host H] [--port P] [--log-level L]
"""

from __future__ import annotations

import argparse


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="python -m engram.backend.app.gateway",
        description="Engram gateway (Windows-compatible Selector event loop)",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args()

    from engram.backend.app.gateway.entry import run_gateway

    run_gateway(host=args.host, port=args.port, log_level=args.log_level)


if __name__ == "__main__":
    main()
