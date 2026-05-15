# SPDX-License-Identifier: Apache-2.0
"""Operational scripts for the Argus platform.

These scripts are user-facing entry points (downloads, fixture rebuilds)
that import from the ``argus`` package. The actual logic lives in the
package so it is unit-testable; the scripts in this directory are thin
Typer shells around it.
"""
