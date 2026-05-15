# SPDX-License-Identifier: Apache-2.0
"""Argus command-line entrypoint.

Phase 1 surface: ``argus version`` and ``argus serve``. More commands land
alongside the layers that need them — ``argus ingest`` in Phase 2,
``argus predict`` in Phase 3, ``argus review`` in Phase 5.
"""

from __future__ import annotations

import typer
import uvicorn

from argus import __version__

app = typer.Typer(
    name="argus",
    help="Argus — multimodal, explainable, uncertainty-aware risk intelligence.",
    no_args_is_help=True,
    add_completion=False,
    pretty_exceptions_show_locals=False,
)


@app.command(help="Print the installed Argus version.")
def version() -> None:
    """Print the installed Argus version."""
    typer.echo(__version__)


@app.command(help="Start the FastAPI service locally via uvicorn.")
def serve(
    host: str = typer.Option(
        "127.0.0.1",
        "--host",
        help="Bind address. Defaults to localhost; pass 0.0.0.0 to expose.",
    ),
    port: int = typer.Option(
        8000,
        "--port",
        "-p",
        help="HTTP port to bind.",
    ),
    reload: bool = typer.Option(
        False,
        "--reload",
        help="Auto-reload on source changes (development use only).",
    ),
    log_level: str = typer.Option(
        "info",
        "--log-level",
        help="uvicorn log level.",
    ),
) -> None:
    """Run the FastAPI app via uvicorn. Container deployments call uvicorn directly."""
    uvicorn.run(
        "argus.platform_core.api.main:app",
        host=host,
        port=port,
        reload=reload,
        log_level=log_level,
    )


if __name__ == "__main__":  # pragma: no cover
    app()
