# SPDX-License-Identifier: Apache-2.0
"""TextDocumentConnector — emit :class:`RawRecord` instances from text files.

Reads a single text file or every text file in a directory matching a glob
pattern. Each file becomes one record, or — when ``chunk_size`` is set —
multiple records with ``chunk_index`` / ``total_chunks`` in the payload so
downstream RAG ingestion has the chunking decision visible end-to-end.

The connector handles the supply-chain pack's text-asset use cases (cached
news articles, downloaded SEC EDGAR filings) and is intentionally
encoder-agnostic — sentence-transformers and tokenizer wrappers live in
``argus.platform_core.features``, not here.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from pydantic import Field, model_validator

from argus.platform_core.ingestion.base import (
    Connector,
    ConnectorConfig,
    Modality,
    RawRecord,
    RecordStream,
)


class TextDocumentConfig(ConnectorConfig):
    """Configuration for :class:`TextDocumentConnector`."""

    root_path: Path = Field(
        ...,
        description="A single text file, or a directory containing matching files.",
    )
    file_pattern: str = Field(
        default="*.txt",
        min_length=1,
        description="Glob pattern applied when ``root_path`` is a directory.",
    )
    encoding: str = Field(default="utf-8")
    chunk_size: int | None = Field(
        default=None,
        gt=0,
        description=(
            "If set, split each file into character chunks of this size; the "
            "final chunk may be smaller. When ``None``, one record per file."
        ),
    )
    chunk_overlap: int = Field(
        default=0,
        ge=0,
        description=(
            "Characters of overlap between adjacent chunks. Must be smaller "
            "than ``chunk_size``."
        ),
    )

    @model_validator(mode="after")
    def _overlap_must_be_smaller_than_chunk_size(self) -> TextDocumentConfig:
        if self.chunk_size is not None and self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                f"chunk_overlap ({self.chunk_overlap}) must be smaller than "
                f"chunk_size ({self.chunk_size})"
            )
        return self


class TextDocumentConnector(Connector[TextDocumentConfig]):
    """Emit one :class:`RawRecord` per text file (or per chunk when chunking)."""

    @property
    def modality(self) -> Modality:
        return Modality.TEXT

    def pull(self) -> RecordStream:
        return RecordStream(self._iter_documents())

    def _iter_documents(self) -> Iterator[RawRecord]:
        for path in self._discover_paths():
            text = path.read_text(encoding=self.config.encoding)
            yield from self._records_for_file(path, text)

    def _discover_paths(self) -> list[Path]:
        root = self.config.root_path
        if not root.exists():
            raise FileNotFoundError(f"root_path does not exist: {root}")
        if root.is_file():
            return [root]
        return sorted(root.glob(self.config.file_pattern))

    def _records_for_file(self, path: Path, text: str) -> Iterator[RawRecord]:
        if self.config.chunk_size is None:
            yield self._make_record(
                record_id=path.name,
                payload=self._payload(path, text, chunk_index=0, total_chunks=1),
            )
            return

        chunks = list(_chunk_text(text, self.config.chunk_size, self.config.chunk_overlap))
        total = len(chunks)
        for index, chunk in enumerate(chunks):
            yield self._make_record(
                record_id=f"{path.name}#{index}",
                payload=self._payload(path, chunk, chunk_index=index, total_chunks=total),
            )

    @staticmethod
    def _payload(path: Path, text: str, *, chunk_index: int, total_chunks: int) -> dict[str, Any]:
        return {
            "path": str(path),
            "filename": path.name,
            "text": text,
            "chunk_index": chunk_index,
            "total_chunks": total_chunks,
        }


def _chunk_text(text: str, size: int, overlap: int) -> Iterator[str]:
    """Yield successive ``size``-character chunks with ``overlap`` characters reused.

    Chunking is strictly stride-based: a chunk is emitted at every multiple
    of ``size - overlap`` until ``start >= len(text)``. The final chunk may
    therefore be shorter than ``size``. When ``overlap`` is non-zero, this
    can also yield a short trailing chunk fully contained in the previous
    one — that's the price of deterministic stride behavior, and is
    consistent with conventional RAG chunkers.
    """
    if not text:
        return
    stride = size - overlap
    start = 0
    while start < len(text):
        yield text[start : start + size]
        start += stride


__all__ = ["TextDocumentConfig", "TextDocumentConnector"]
