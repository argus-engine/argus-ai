# SPDX-License-Identifier: Apache-2.0
"""Argus — multimodal, explainable, uncertainty-aware risk intelligence platform.

The top-level package exposes the version string. Public APIs live under the
sub-packages ``argus.platform_core`` (domain-agnostic primitives) and
``argus.domain_packs`` (pluggable verticals such as supply chain). See
``docs/architecture.md`` for the layering contract.
"""

from __future__ import annotations

__version__ = "0.2.0"

__all__ = ["__version__"]
