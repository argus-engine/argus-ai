# SPDX-License-Identifier: Apache-2.0
"""Pluggable verticals built on `platform_core`.

A domain pack is a self-contained Python sub-package under `argus.domain_packs`
that composes `platform_core` for a specific industry. Each pack ships with:

- Normalized Pydantic schemas (`data/schemas.py`)
- Loaders that compose `platform_core.ingestion` connectors (`data/loaders.py`)
- Pack-specific prompt assets (`prompts/`)
- Pack-tuned predictive heads (`models/`)
- Pack-level benchmarks and a model card (`evaluation/`)

A pack declares its extra dependencies under
``[project.optional-dependencies].<pack>`` in ``pyproject.toml``; installing
``pip install argus-risk[supply-chain]`` pulls them in (decision B).

The reference pack is `supply_chain`. Read it before writing a second one.
"""
