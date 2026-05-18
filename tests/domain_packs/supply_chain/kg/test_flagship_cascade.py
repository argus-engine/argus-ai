# SPDX-License-Identifier: Apache-2.0
"""Flagship cascading-risk test against the deterministic fixture topology.

Parametrised over both backends via the shared ``backend`` fixture in
:mod:`tests.conftest`. The neo4j parameter carries the ``integration``
marker, so a default ``pytest`` run exercises the NetworkX backend
only; ``pytest -m integration`` flips it.

The fixture topology was designed by hand to produce specific,
hand-traceable cascade results. The assertions reference
``EXPECTED_CASCADE_FROM_SUP_A_MAX_HOPS_2`` and
``CASCADE_EXCLUDED_AT_MAX_HOPS_2`` from
:mod:`tests.domain_packs.supply_chain.kg.fixtures`, never magic
numbers — see that module's docstring for the topology diagram and
the rationale (SUP-B as isolated control).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from argus.domain_packs.supply_chain.kg_adapter import SupplyChainKGAdapter
from argus.platform_core.kg.builder import KGBuilder
from tests.domain_packs.supply_chain.kg.fixtures import (
    CASCADE_EXCLUDED_AT_MAX_HOPS_2,
    EXPECTED_CASCADE_FROM_SUP_A_MAX_HOPS_2,
    build_entity_stream,
)

if TYPE_CHECKING:
    from argus.platform_core.kg.base import KGBackend


def _ingest_canonical(backend: KGBackend) -> None:
    """Drive the canonical entity stream through the adapter onto ``backend``."""
    adapter = SupplyChainKGAdapter()
    builder = KGBuilder(backend, adapter)
    builder.ingest(build_entity_stream())


class TestCascadingRiskFromSupA:
    def test_returns_exact_targets_in_documented_order(self, backend: KGBackend) -> None:
        _ingest_canonical(backend)

        paths = backend.cascading_risk("supplier:SUP-A", max_hops=2)

        target_ids = tuple(p.target_id for p in paths)
        assert target_ids == EXPECTED_CASCADE_FROM_SUP_A_MAX_HOPS_2

    def test_excludes_control_set_supp_b_side(self, backend: KGBackend) -> None:
        # Negative-assertion control: with SUP-B as a separate connected
        # component bridged only via region:NA, the SUP-B side is reachable
        # earliest at hop 3 (NA -LOCATED_IN- SUP-B; NA <-SHIPS_TO- O5),
        # deepest at hop 4 (SH-O5 / P3 / E2). max_hops=2 must therefore
        # NOT include any of CASCADE_EXCLUDED_AT_MAX_HOPS_2 — see the
        # fixture module docstring for the full hop-by-hop justification.
        # Asserting this proves the BFS hop limit is enforced, not just
        # that the BFS runs.
        _ingest_canonical(backend)

        paths = backend.cascading_risk("supplier:SUP-A", max_hops=2)

        reached = {p.target_id for p in paths}
        assert reached.isdisjoint(CASCADE_EXCLUDED_AT_MAX_HOPS_2), (
            f"BFS bled past max_hops=2; should not have reached "
            f"{reached & CASCADE_EXCLUDED_AT_MAX_HOPS_2}"
        )

    def test_paths_are_sorted_by_hops_then_target_id(self, backend: KGBackend) -> None:
        # The Protocol docstring guarantees this ordering; both backends
        # must deliver it. Pin it here so a regression on either side
        # surfaces from the supply-chain flagship rather than only from
        # the platform-core parity test.
        _ingest_canonical(backend)

        paths = backend.cascading_risk("supplier:SUP-A", max_hops=2)

        sort_keys = [(p.hops, p.target_id) for p in paths]
        assert sort_keys == sorted(sort_keys)

    def test_hops_attribute_matches_path_length(self, backend: KGBackend) -> None:
        # RiskPath.hops is documented as ``len(path)`` — pin it on real
        # data so the invariant is exercised end-to-end.
        _ingest_canonical(backend)

        paths = backend.cascading_risk("supplier:SUP-A", max_hops=2)

        for risk_path in paths:
            assert risk_path.hops == len(risk_path.path)

    def test_max_hops_four_reaches_full_excluded_control_set(self, backend: KGBackend) -> None:
        # Confirms the control set IS reachable at sufficient depth —
        # without this, the exclusion test could pass against a buggy
        # implementation that fails to reach SUP-B at any depth.
        # max_hops=4 because the deepest SUP-B-side nodes (event_signal:E2,
        # product:P3, shipment:SH-O5) are at hop 4 — Shipments do not emit
        # SHIPS_TO edges, so SH-O5 is only reachable via O5 (hop 3) or
        # SUP-B (hop 3), placing it at hop 4.
        _ingest_canonical(backend)

        paths = backend.cascading_risk("supplier:SUP-A", max_hops=4)

        reached = {p.target_id for p in paths}
        assert CASCADE_EXCLUDED_AT_MAX_HOPS_2.issubset(reached), (
            f"Excluded-at-hop-2 set should be reachable at max_hops=4; missing: "
            f"{CASCADE_EXCLUDED_AT_MAX_HOPS_2 - reached}"
        )
