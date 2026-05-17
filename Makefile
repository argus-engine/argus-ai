# SPDX-License-Identifier: Apache-2.0
# ---------------------------------------------------------------------------
# Argus developer Makefile.
#
# Run `make help` for the full list of targets. Common flow after cloning:
#
#     make install     # pip install -e ".[dev]"
#     make hooks       # install pre-commit + commit-msg hooks
#     make check       # lint + typecheck + test (CI-equivalent)
#
# Windows note: targets run under GNU Make. Use Git Bash, WSL, or a make
# installation on PATH. PowerShell-native equivalents can be added later if
# someone needs them.
# ---------------------------------------------------------------------------

PYTHON ?= python
PIP ?= pip
PYTEST ?= pytest

.DEFAULT_GOAL := help

.PHONY: help
help:  ## Show this help and exit
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-14s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# ---- environment ----------------------------------------------------------

.PHONY: install
install:  ## Install Argus and dev deps in editable mode
	$(PIP) install -e ".[dev]"

.PHONY: install-all
install-all:  ## Install Argus with every optional extra (ml, kg, rag, supply-chain, streamlit, dev)
	$(PIP) install -e ".[all,dev]"

.PHONY: hooks
hooks:  ## Install pre-commit and commit-msg hooks
	pre-commit install --hook-type pre-commit --hook-type commit-msg

# ---- quality gates --------------------------------------------------------

.PHONY: lint
lint:  ## Run ruff lint + format check (does not modify files)
	ruff check .
	ruff format --check .

.PHONY: format
format:  ## Auto-format with ruff and apply lint fixes
	ruff format .
	ruff check --fix .

.PHONY: typecheck
typecheck:  ## Run mypy in strict mode
	mypy

.PHONY: test
test:  ## Run pytest with coverage (unit tests only; excludes -m integration)
	$(PYTEST) --cov=argus --cov-report=term-missing

.PHONY: integration
integration:  ## Run integration tests via pytest -m integration (requires Docker)
	$(PYTEST) -m integration

.PHONY: security
security:  ## Run bandit + pip-audit
	bandit -c pyproject.toml -r argus
	pip-audit

.PHONY: check
check: lint typecheck test  ## Run lint, typecheck, and unit tests (CI-equivalent)

# ---- runtime --------------------------------------------------------------

.PHONY: up
up:  ## Bring up the local docker-compose stack (lands in Task #11)
	docker compose up --build

.PHONY: down
down:  ## Tear down the local docker-compose stack
	docker compose down --remove-orphans

# ---- housekeeping ---------------------------------------------------------

.PHONY: clean
clean:  ## Remove build artifacts and tooling caches
	rm -rf build dist *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov coverage.xml
	find . -type d -name __pycache__ -exec rm -rf {} +
