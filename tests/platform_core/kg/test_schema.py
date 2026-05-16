# SPDX-License-Identifier: Apache-2.0
"""Contract tests for the knowledge-graph schema module.

Covers the enum surface, the frozen Pydantic models, and the stable-ID
helpers. No backend interaction — each test exercises only the data
shapes defined in :mod:`argus.platform_core.kg.schema`.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from argus.platform_core.kg.schema import (
    EdgeType,
    KGEdge,
    KGNode,
    NodeType,
    make_edge_id,
    make_node_id,
)

# ---------------------------------------------------------------------------
# NodeType
# ---------------------------------------------------------------------------


class TestNodeType:
    def test_has_seven_values(self) -> None:
        assert {n.value for n in NodeType} == {
            "supplier",
            "product",
            "region",
            "order",
            "shipment",
            "customer",
            "event_signal",
        }

    def test_is_a_string_enum(self) -> None:
        assert NodeType.SUPPLIER == "supplier"  # type: ignore[comparison-overlap]
        assert NodeType("region") is NodeType.REGION

    @pytest.mark.parametrize(
        "value",
        ["supplier", "product", "region", "order", "shipment", "customer", "event_signal"],
    )
    def test_round_trips_through_string(self, value: str) -> None:
        assert NodeType(value).value == value


# ---------------------------------------------------------------------------
# EdgeType
# ---------------------------------------------------------------------------


class TestEdgeType:
    def test_has_ten_values(self) -> None:
        assert {e.value for e in EdgeType} == {
            "HAS_SUPPLIER",
            "PLACED_BY",
            "OF_PRODUCT",
            "FULFILS_ORDER",
            "SUPPLIED_BY",
            "SHIPS_TO",
            "LOCATED_IN",
            "DEPENDS_ON",
            "AFFECTS",
            "MENTIONS",
        }

    def test_values_are_uppercase_cypher_style(self) -> None:
        for edge in EdgeType:
            assert edge.value == edge.value.upper()
            assert " " not in edge.value

    def test_is_a_string_enum(self) -> None:
        assert EdgeType.AFFECTS == "AFFECTS"
        assert EdgeType("MENTIONS") is EdgeType.MENTIONS


# ---------------------------------------------------------------------------
# make_node_id / make_edge_id
# ---------------------------------------------------------------------------


class TestMakeNodeId:
    def test_formats_type_colon_source_key(self) -> None:
        assert make_node_id(NodeType.SUPPLIER, "SUP-001") == "supplier:SUP-001"
        assert make_node_id(NodeType.REGION, "APAC") == "region:APAC"
        assert make_node_id(NodeType.EVENT_SIGNAL, "EV-9") == "event_signal:EV-9"

    def test_is_deterministic(self) -> None:
        first = make_node_id(NodeType.ORDER, "LINE-42")
        second = make_node_id(NodeType.ORDER, "LINE-42")
        assert first == second

    def test_rejects_empty_source_key(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            make_node_id(NodeType.SUPPLIER, "")


class TestMakeEdgeId:
    def test_formats_source_dash_type_arrow_target(self) -> None:
        eid = make_edge_id("order:LINE-42", EdgeType.HAS_SUPPLIER, "supplier:SUP-001")
        assert eid == "order:LINE-42-HAS_SUPPLIER->supplier:SUP-001"

    def test_is_deterministic(self) -> None:
        a = make_edge_id("a", EdgeType.MENTIONS, "b")
        b = make_edge_id("a", EdgeType.MENTIONS, "b")
        assert a == b

    @pytest.mark.parametrize(
        ("source_id", "target_id"),
        [("", "b"), ("a", ""), ("", "")],
    )
    def test_rejects_empty_endpoint(self, source_id: str, target_id: str) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            make_edge_id(source_id, EdgeType.AFFECTS, target_id)


# ---------------------------------------------------------------------------
# KGNode
# ---------------------------------------------------------------------------


def _node(node_id: str = "supplier:SUP-001", *, node_type: NodeType = NodeType.SUPPLIER) -> KGNode:
    return KGNode(id=node_id, type=node_type)


class TestKGNode:
    def test_minimal_construction_round_trips(self) -> None:
        node = KGNode(id="region:APAC", type=NodeType.REGION)
        assert node.id == "region:APAC"
        assert node.type is NodeType.REGION
        assert node.properties == {}
        assert node.source_refs == ()

    def test_properties_and_source_refs_round_trip(self) -> None:
        node = KGNode(
            id="supplier:SUP-001",
            type=NodeType.SUPPLIER,
            properties={"name": "Acme", "country": "GB"},
            source_refs=("dataco:row-7", "edgar:CIK-12345"),
        )
        assert node.properties == {"name": "Acme", "country": "GB"}
        assert node.source_refs == ("dataco:row-7", "edgar:CIK-12345")

    def test_is_frozen(self) -> None:
        node = _node()
        with pytest.raises(ValidationError):
            node.id = "tampered"

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            KGNode(  # type: ignore[call-arg]
                id="supplier:X",
                type=NodeType.SUPPLIER,
                surprise="field",
            )

    def test_empty_id_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            KGNode(id="", type=NodeType.SUPPLIER)

    def test_type_must_be_a_valid_node_type(self) -> None:
        with pytest.raises(ValidationError):
            KGNode(id="x", type="not-a-real-type")  # type: ignore[arg-type]

    def test_id_built_from_helper_is_accepted(self) -> None:
        node = KGNode(
            id=make_node_id(NodeType.PRODUCT, "SKU-9X"),
            type=NodeType.PRODUCT,
        )
        assert node.id == "product:SKU-9X"


# ---------------------------------------------------------------------------
# KGEdge
# ---------------------------------------------------------------------------


def _edge(
    *,
    source_id: str = "order:LINE-42",
    target_id: str = "supplier:SUP-001",
    edge_type: EdgeType = EdgeType.HAS_SUPPLIER,
) -> KGEdge:
    return KGEdge(
        id=make_edge_id(source_id, edge_type, target_id),
        source_id=source_id,
        target_id=target_id,
        type=edge_type,
    )


class TestKGEdge:
    def test_minimal_construction_round_trips(self) -> None:
        edge = _edge()
        assert edge.source_id == "order:LINE-42"
        assert edge.target_id == "supplier:SUP-001"
        assert edge.type is EdgeType.HAS_SUPPLIER
        assert edge.id == "order:LINE-42-HAS_SUPPLIER->supplier:SUP-001"
        assert edge.properties == {}
        assert edge.source_refs == ()

    def test_properties_and_source_refs_round_trip(self) -> None:
        edge = KGEdge(
            id=make_edge_id("a", EdgeType.AFFECTS, "b"),
            source_id="a",
            target_id="b",
            type=EdgeType.AFFECTS,
            properties={"weight": 0.8},
            source_refs=("gdelt:row-3",),
        )
        assert edge.properties == {"weight": 0.8}
        assert edge.source_refs == ("gdelt:row-3",)

    def test_is_frozen(self) -> None:
        edge = _edge()
        with pytest.raises(ValidationError):
            edge.target_id = "supplier:OTHER"

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            KGEdge(  # type: ignore[call-arg]
                id="a-AFFECTS->b",
                source_id="a",
                target_id="b",
                type=EdgeType.AFFECTS,
                surprise="field",
            )

    @pytest.mark.parametrize("missing", ["id", "source_id", "target_id"])
    def test_string_fields_require_non_empty_value(self, missing: str) -> None:
        kwargs: dict[str, object] = {
            "id": "a-AFFECTS->b",
            "source_id": "a",
            "target_id": "b",
            "type": EdgeType.AFFECTS,
        }
        kwargs[missing] = ""
        with pytest.raises(ValidationError):
            KGEdge(**kwargs)  # type: ignore[arg-type]

    def test_type_must_be_a_valid_edge_type(self) -> None:
        with pytest.raises(ValidationError):
            KGEdge(
                id="a-X->b",
                source_id="a",
                target_id="b",
                type="NOT_REAL",  # type: ignore[arg-type]
            )
