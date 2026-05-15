# SPDX-License-Identifier: Apache-2.0
"""SPDX license-identifier header check.

Run as a pre-commit local hook. Verifies that every file passed on the
command line (filtered by extension) declares an Apache-2.0 SPDX
identifier within its first ``LOOKAHEAD_LINES``.

Accepted forms (extension-dependent):

  Python / YAML / TOML / Dockerfile / shell / Makefile::
      # SPDX-License-Identifier: Apache-2.0

  Markdown / HTML::
      <!-- SPDX-License-Identifier: Apache-2.0 -->

Files that conventionally do not carry headers (``LICENSE``, ``.gitignore``,
``.python-version``, ``.gitkeep``, empty files) are skipped automatically.

Exit code: 0 if every supplied file has a valid header; 1 otherwise, with a
human-readable list of offenders printed to stderr.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SPDX_RE = re.compile(r"SPDX-License-Identifier:\s*Apache-2\.0")

LOOKAHEAD_LINES = 10
"""Number of lines from the top of the file to scan for the identifier."""

CHECKED_SUFFIXES = frozenset({".py", ".md", ".yaml", ".yml", ".toml", ".sh", ".bash"})
"""File suffixes that must carry an SPDX header."""

EXEMPT_FILENAMES = frozenset(
    {"LICENSE", ".gitignore", ".python-version", ".gitkeep", "MANIFEST.in"}
)
"""Filenames exempt from the check regardless of extension."""


def _is_under_fixtures(path: Path) -> bool:
    """True if any ancestor directory is named ``fixtures``.

    Fixture files are data assets — committed sample CSVs, text snippets,
    JSON dumps — and should look like the real upstream sources they
    represent. Mandating an SPDX header on them would be cosmetic noise.
    """
    return any(parent.name == "fixtures" for parent in path.parents)


def file_needs_header(path: Path) -> bool:
    """Decide whether a path is subject to the SPDX requirement."""
    if path.name in EXEMPT_FILENAMES:
        return False
    if path.suffix.lower() not in CHECKED_SUFFIXES:
        return False
    if _is_under_fixtures(path):
        return False
    try:
        if path.stat().st_size == 0:
            return False  # empty placeholder files are not enforced
    except OSError:
        return False
    return True


def has_spdx_header(path: Path) -> bool:
    """Scan the first ``LOOKAHEAD_LINES`` for the SPDX identifier."""
    try:
        with path.open(encoding="utf-8") as fh:
            for _ in range(LOOKAHEAD_LINES):
                line = fh.readline()
                if not line:
                    break
                if SPDX_RE.search(line):
                    return True
    except (OSError, UnicodeDecodeError):
        return False
    return False


def main(argv: list[str]) -> int:
    """Entrypoint: return ``1`` if any supplied file is missing a header."""
    offenders: list[Path] = []
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file():
            continue
        if not file_needs_header(path):
            continue
        if not has_spdx_header(path):
            offenders.append(path)

    if offenders:
        print("Missing SPDX-License-Identifier header in:", file=sys.stderr)
        for path in offenders:
            print(f"  - {path}", file=sys.stderr)
        print(
            "\nAdd the appropriate one-line marker to the top of each file. "
            "For Python/YAML/TOML: `# SPDX-License-Identifier: Apache-2.0`. "
            "For Markdown/HTML: `<!-- SPDX-License-Identifier: Apache-2.0 -->`.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
