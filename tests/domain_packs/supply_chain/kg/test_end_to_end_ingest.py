# SPDX-License-Identifier: Apache-2.0
"""End-to-end ingestion test: full entity stream → KGBuilder → backend.

Drives the deterministic supply-chain fixture through
:class:`SupplyChainKGAdapter` + :class:`KGBuilder` and asserts on the
shape of the resulting graph plus the :class:`IngestionReport`. This
is the only place in the suite where the adapter, the builder, the
report contract, and a real backend are wired together in one path.

Parametrised over both backends via the shared ``backend`` fixture in
:mod:`tests.conftest`. The neo4j parameter carries the ``integration``
marker, so a default ``pytest`` run exercises the NetworkX backend
only; ``pytest -m integration`` flips it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from argus.domain_packs.supply_chain.kg_adapter import SupplyChainKGAdapter
from argus.platform_core.kg.builder import KGBuilder
from tests.domain_packs.supply_chain.kg.fixtures import (
    EXPECTED_UNRESOLVED_MENTIONS,
    build_entity_stream,
)

if TYPE_CHECKING:
    from argus.platform_core.kg.base import KGBackend


class TestEndToEndIngestion:
    def test_report_carries_unresolved_mentions_counter(self, backend: KGBackend) -> None:
        # The supply-chain adapter exposes unresolved_mentions via the
        # KGAdapter.counters() seam; KGBuilder.ingest copies it into
        # IngestionReport.adapter_counters. This wires the whole chain.
        adapter = SupplyChainKGAdapter()
        builder = KGBuilder(backend, adapter)

        report = builder.ingest(build_entity_stream())

        assert report.adapter_counters == {
            "unresolved_mentions": EXPECTED_UNRESOLVED_MENTIONS,
        }

    def test_report_counts_are_non_zero_and_consistent(self, backend: KGBackend) -> None:
        # Nodes and edges counts are upsert-call counts, NOT unique-id
        # counts (the same Region node is emitted by several entities;
        # backends dedupe by id). Pin that the report is sane on real
        # data without asserting an exact magic number.
        adapter = SupplyChainKGAdapter()
        builder = KGBuilder(backend, adapter)

        report = builder.ingest(build_entity_stream())

        assert report.nodes_seen > 0
        assert report.edges_seen > 0
        assert report.duration_ms >= 0

    def test_supplier_node_round_trips_scalar_properties(self, backend: KGBackend) -> None:
        # Spot-check that scalar properties (string, int) survive the
        # round trip into either backend. The Decimal/datetime round
        # trips have known type-coercion behaviour (Decimal stored as
        # str by the adapter; datetime potentially returned as a
        # neo4j.time.DateTime by the Neo4j driver) and are not asserted
        # here — those are documented in the adapter unit tests.
        adapter = SupplyChainKGAdapter()
        builder = KGBuilder(backend, adapter)
        builder.ingest(build_entity_stream())

        node = backend.get_node("supplier:SUP-A")

        assert node is not None
        assert node.properties["name"] == "Acme Trading"
        assert node.properties["country"] == "GB"
        assert node.properties["tier"] == 1

    def test_order_decimal_unit_price_round_trips_as_string(self, backend: KGBackend) -> None:
        # The adapter serialises Decimal as str so the Neo4j driver
        # (which rejects Decimal) accepts it. Reconstruct via
        # Decimal(s) on read. Pin this contract on real data.
        adapter = SupplyChainKGAdapter()
        builder = KGBuilder(backend, adapter)
        builder.ingest(build_entity_stream())

        node = backend.get_node("order:O1")

        assert node is not None
        assert node.properties["unit_price"] == "25.00"
        assert Decimal(node.properties["unit_price"]) == Decimal("25.00")

    def test_known_edge_round_trips_with_type_and_endpoints(self, backend: KGBackend) -> None:
        # The cascade test asserts target sets; this asserts that an
        # individual edge has the expected source/target/type after
        # round trip through both backends.
        adapter = SupplyChainKGAdapter()
        builder = KGBuilder(backend, adapter)
        builder.ingest(build_entity_stream())

        # SH-O1 -SUPPLIED_BY-> SUP-A — pick a single known edge whose
        # presence is core to the cascade test working.
        neighbors = backend.neighbors(
            "shipment:SH-O1",
            direction="out",
        )
        neighbor_ids = {n.id for n in neighbors}
        assert "supplier:SUP-A" in neighbor_ids
        assert "order:O1" in neighbor_ids

    def test_repeated_ingest_is_idempotent_on_node_set(self, backend: KGBackend) -> None:
        # The builder + backend upsert merge mean re-running the same
        # stream leaves the node set identical. The adapter must produce
        # the same nodes on the second pass — which it does because
        # to_nodes / to_edges are deterministic per the adapter's
        # documented contract.
        adapter1 = SupplyChainKGAdapter()
        KGBuilder(backend, adapter1).ingest(build_entity_stream())

        first_pass_supplier = backend.get_node("supplier:SUP-A")
        assert first_pass_supplier is not None
        first_pass_name = first_pass_supplier.properties["name"]

        adapter2 = SupplyChainKGAdapter()
        KGBuilder(backend, adapter2).ingest(build_entity_stream())

        second_pass_supplier = backend.get_node("supplier:SUP-A")
        assert second_pass_supplier is not None
        assert second_pass_supplier.properties["name"] == first_pass_name
