# SPDX-License-Identifier: Apache-2.0
"""Integration tests for :class:`Neo4jBackend`.

Every test in this file is marked ``@pytest.mark.integration`` via
the module-level ``pytestmark`` so a default ``pytest`` run skips
them. The CI integration job invokes ``pytest -m integration`` to
include them, against the Neo4j 5.20-community + APOC container that
:mod:`tests.platform_core.kg.conftest` spins up once per session.

The Neo4j-specific cases here cover behaviour that the parity tests
in :mod:`tests.platform_core.kg.test_backend_parity` don't exercise:
the APOC startup check, connection-failure cleanup, Cypher-injection
safety of parameterised queries, the uniqueness constraint, and
disconnect idempotency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from argus.platform_core.kg import KGBackendConfig, KGNode, NodeType

if TYPE_CHECKING:
    from argus.platform_core.kg.base import KGBackend

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Startup checks
# ---------------------------------------------------------------------------


class TestApocAvailability:
    def test_connect_fails_when_apoc_is_missing(self, neo4j_no_apoc_container: object) -> None:
        from pydantic import SecretStr

        from argus.platform_core.kg.neo4j_backend import Neo4jBackend

        config = KGBackendConfig(
            name="apoc-missing",
            neo4j_uri=neo4j_no_apoc_container.get_connection_url(),  # type: ignore[attr-defined]
            neo4j_user="neo4j",
            neo4j_password=SecretStr("test-password"),
        )
        backend = Neo4jBackend(config)
        with pytest.raises(RuntimeError, match="APOC"):
            backend.connect()
        # Backend should have rolled back its driver state — disconnect
        # is a no-op when connect() failed cleanly.
        backend.disconnect()


# ---------------------------------------------------------------------------
# Connection failure
# ---------------------------------------------------------------------------


class TestConnectionFailure:
    def test_invalid_uri_raises_within_timeout(self) -> None:
        from pydantic import SecretStr

        from argus.platform_core.kg.neo4j_backend import Neo4jBackend

        config = KGBackendConfig(
            name="invalid-uri",
            neo4j_uri="bolt://invalid.host.local:9999",
            neo4j_user="neo4j",
            neo4j_password=SecretStr("nope"),
        )
        backend = Neo4jBackend(config)
        with pytest.raises(Exception):  # noqa: B017, PT011 — neo4j driver raises ServiceUnavailable
            backend.connect()


# ---------------------------------------------------------------------------
# Cypher safety
# ---------------------------------------------------------------------------


class TestCypherInjection:
    def test_cypher_keywords_in_property_value_are_stored_as_data(
        self, neo4j_backend: KGBackend
    ) -> None:
        # A classic injection payload — if string-interpolated, this would
        # delete every node in the graph.
        malicious = "'; MATCH (n) DETACH DELETE n; //"
        neo4j_backend.upsert_node(
            KGNode(
                id="supplier:malicious",
                type=NodeType.SUPPLIER,
                properties={"name": malicious},
            )
        )
        neo4j_backend.upsert_node(KGNode(id="supplier:safe", type=NodeType.SUPPLIER))

        # Both nodes must exist; the malicious string round-trips intact.
        stored = neo4j_backend.get_node("supplier:malicious")
        assert stored is not None
        assert stored.properties["name"] == malicious
        assert neo4j_backend.get_node("supplier:safe") is not None


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------


class TestLifecycle:
    def test_disconnect_is_idempotent(self, neo4j_backend: KGBackend) -> None:
        # Fixture already connected; double-disconnect must not raise.
        neo4j_backend.disconnect()
        neo4j_backend.disconnect()

    def test_connect_is_idempotent(self, neo4j_backend: KGBackend) -> None:
        # Calling connect on an already-connected backend is a no-op.
        neo4j_backend.connect()
        # Operations still work.
        neo4j_backend.upsert_node(KGNode(id="supplier:S1", type=NodeType.SUPPLIER))
        assert neo4j_backend.get_node("supplier:S1") is not None


# ---------------------------------------------------------------------------
# Backend-specific behaviour
# ---------------------------------------------------------------------------


class TestUniquenessConstraint:
    def test_constraint_was_created_on_connect(self, neo4j_backend: KGBackend) -> None:
        # Reach into the driver to verify the constraint exists.
        # If the schema gates were not applied, MERGE would still work
        # but writes would race; this guards against silent regression.
        driver = neo4j_backend._driver  # type: ignore[attr-defined]
        with driver.session() as session:
            result = session.run("SHOW CONSTRAINTS YIELD name RETURN collect(name) AS names")
            record = result.single()
            assert record is not None
            assert "kg_node_id" in record["names"]


class TestErrorHandling:
    def test_operations_before_connect_raise_runtime_error(self) -> None:
        from pydantic import SecretStr

        from argus.platform_core.kg.neo4j_backend import Neo4jBackend

        # Construct but do NOT connect.
        backend = Neo4jBackend(
            KGBackendConfig(
                name="not-connected",
                neo4j_uri="bolt://127.0.0.1:7687",
                neo4j_user="neo4j",
                neo4j_password=SecretStr("x"),
            )
        )
        with pytest.raises(RuntimeError, match="not connected"):
            backend.upsert_node(KGNode(id="supplier:X", type=NodeType.SUPPLIER))
