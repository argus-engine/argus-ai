<!-- SPDX-License-Identifier: Apache-2.0 -->
# Contributing to Argus

Thanks for considering a contribution. Argus is built to look and behave like production infrastructure — the
contribution workflow exists to keep it that way.

## Dev setup

```bash
git clone https://github.com/argus-ai/platform.git argus && cd argus

python -m venv .venv
source .venv/bin/activate          # Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

pre-commit install                 # lands in Phase 1; required before your first commit
pytest                             # green test suite before opening a PR
```

Python 3.11 and 3.12 are supported. CI runs both. Develop against 3.11 unless you have a specific reason.

## Branches and commits

- Branch from `main`. Use a short prefix: `feat/`, `fix/`, `docs/`, `chore/`, `refactor/`, `test/`, `build/`, `ci/`.
- **Commit messages follow [Conventional Commits](https://www.conventionalcommits.org/).** A pre-commit hook enforces
  this; a CI job validates PR titles.
- Keep commits small and topical. A diff that "fixes the bug and renames the helper while you're there" is two commits.
- Every source file carries an SPDX header: `# SPDX-License-Identifier: Apache-2.0`. A pre-commit check enforces this.

Examples:

```
feat(ingestion): add TextDocumentConnector with chunked PDF support
fix(rag): guard against empty retrieval results before grounding check
docs: clarify the LLMProvider interface contract
```

## Code quality bar

| | Command | Notes |
|---|---|---|
| Lint | `ruff check .` | Configured in `pyproject.toml`. Fix, don't silence. |
| Format | `ruff format .` | Run before committing. |
| Types | `mypy` | `strict = true`. Type-ignore lines need a comment explaining why. |
| Tests | `pytest` | 80%+ line coverage is the eventual target. New code needs tests. |
| Security | `bandit -c pyproject.toml -r argus` | Run before PR if you touched I/O or subprocess code. |

CI runs all of the above on every PR. A red CI is a blocker, not a suggestion.

### What "good test" means here

- **Unit tests** assert one thing about one unit. They use the fixtures in `tests/fixtures/`, not network calls.
- **Integration tests** live in `tests/integration/` and are tagged with `@pytest.mark.integration`. They may touch
  Docker services (Neo4j) but never the public internet.
- **Mocks at the boundary, not in the middle.** Mock the LLM provider, not the function under test.
- Tests that hit a real database use the docker-compose stack; mocking the database is forbidden in integration suites
  because the failure mode we care about — schema drift between mock and prod — is exactly what mocks hide.

## Architectural review checklist

Before opening a PR, sanity-check your change against the design principles in the README:

- [ ] No hardcoded paths, model names, or prompts — everything configurable lives in YAML under `configs/`.
- [ ] No new external dependency is referenced directly — it sits behind an interface in `argus.platform_core`.
- [ ] If you added a model output, it carries uncertainty.
- [ ] If you added an LLM call, the output passes the grounding check before reaching a user.
- [ ] If you added a decision surface, there is a HITL path that captures disagreements.
- [ ] No notebooks committed to `main`.
- [ ] `docs/architecture.md` reflects any boundary or interface change.

## Adding a domain pack

A domain pack is an installable extra under `argus.domain_packs.<name>`. The pack:

1. Defines normalized Pydantic schemas under `data/schemas.py`.
2. Provides loaders under `data/loaders.py` that compose `argus.platform_core.ingestion` connectors.
3. Ships prompts in `prompts/`, models in `models/`, and an evaluation harness in `evaluation/`.
4. Declares its extra dependencies under `[project.optional-dependencies].<pack-name>` in `pyproject.toml`.

The `supply_chain` pack is the reference. Read it before writing a second one.

## Reporting bugs and proposing features

Open a GitHub issue. For security concerns, please email the maintainers privately rather than filing a public issue.

## License

By contributing, you agree your work is licensed under [Apache 2.0](LICENSE).
