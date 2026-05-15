# SPDX-License-Identifier: Apache-2.0
"""Argus command-line entrypoint.

Phase 1 surface: a thin Typer application that prints the installed version
and a one-line description. Sub-commands for ingestion, training, serving,
and review are mounted in subsequent phases.
"""

from __future__ import annotations

import typer

from argus import __version__

app = typer.Typer(
    name="argus",
    help="Argus — multimodal, explainable, uncertainty-aware risk intelligence.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the installed Argus version."""
    typer.echo(__version__)


if __name__ == "__main__":  # pragma: no cover
    app()
