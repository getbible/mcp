"""Command-line entry point for stdio and direct Streamable HTTP operation."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence

import uvicorn

from getbible_mcp import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="getbible-mcp",
        description="GetBible API V2 Model Context Protocol server",
    )
    parser.add_argument(
        "--transport",
        choices=("stdio", "streamable-http"),
        default=os.getenv("GETBIBLE_MCP_TRANSPORT", "stdio"),
        help="Transport to run (default: stdio).",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    if args.transport == "stdio":
        from getbible_mcp.server import mcp

        mcp.run(transport="stdio")
        return

    from getbible_mcp.server import runtime

    uvicorn.run(
        runtime.app,
        host=runtime.settings.bind_host,
        port=runtime.settings.bind_port,
        log_level="info",
        proxy_headers=True,
        forwarded_allow_ips="127.0.0.1",
    )


if __name__ == "__main__":
    main()

