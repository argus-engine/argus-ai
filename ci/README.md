<!-- SPDX-License-Identifier: Apache-2.0 -->
# ci/

CI-related artifacts that are not GitHub Actions workflows.

GitHub Actions discovers workflows at `.github/workflows/` at the repo root —
that is where the actual CI pipeline lives, by GitHub's requirement. This
directory holds shared helpers, configs, and documentation about the CI
pipeline that we want versioned alongside the code but separated from the
workflow files themselves.

**Phase 1 status:** stub. The actual CI workflow lands in Task #10 at
`.github/workflows/ci.yml`. This directory will accumulate:

- Shared scripts referenced from CI (e.g., release tagging, fixture refresh)
- Renovate / Dependabot configuration if it grows past a single file
- CI architecture notes — what runs when, why, and what blocks a merge
