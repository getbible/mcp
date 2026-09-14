"""Installable GetBible MCP library, with no network activity during import."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from starlette.applications import Starlette

    from getbible_mcp.client import GetBibleClient
    from getbible_mcp.config import Settings
    from getbible_mcp.server import ServerRuntime

__version__ = "2.1.1"
__all__ = ["__version__", "create_app", "create_runtime"]


def create_runtime(
    settings: Settings | None = None,
    api_client: GetBibleClient | None = None,
    *,
    streamable_http_path: str = "/mcp",
) -> ServerRuntime:
    """Build a runtime exposing the same tools over HTTP or stdio.

    The embedding host must run the returned app's ASGI lifespan. The HTTP path
    can be the root or a named endpoint; API versions are selected by each tool call.
    """
    from getbible_mcp.server import create_runtime as build_runtime

    return build_runtime(settings, api_client, streamable_http_path=streamable_http_path)


def create_app(
    settings: Settings | None = None,
    api_client: GetBibleClient | None = None,
    *,
    path: str = "/mcp",
) -> Starlette:
    """Create an embeddable ASGI application.

    When mounted in another ASGI app, enter ``app.router.lifespan_context(app)`` from the parent's
    lifespan so the protocol manager and outbound client start and stop together.
    """
    from typing import cast

    from starlette.applications import Starlette

    return cast(Starlette, create_runtime(settings, api_client, streamable_http_path=path).app)
