"""Tests for Graph."""

import pytest

from orchestrator.core.context import Context
from orchestrator.core.graph import CycleError, Graph
from orchestrator.core.node import Node, NodeResult, NodeStatus


class StubNode(Node):
    async def run(self, ctx: Context) -> NodeResult:
        return NodeResult(status=NodeStatus.SUCCESS)


class TestGraphAddNode:
    def test_add_single_node(self):
        g = Graph()
        g.add_node(StubNode("a"))
        assert len(g) == 1
        assert g.node_ids == ["a"]

    def test_add_multiple_nodes(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b"))
        assert len(g) == 2

    def test_get_node(self):
        n = StubNode("x")
        g = Graph()
        g.add_node(n)
        assert g.get_node("x") is n

    def test_get_missing_node_raises(self):
        g = Graph()
        with pytest.raises(KeyError):
            g.get_node("missing")


class TestGraphAddEdge:
    def test_add_edge(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b"))
        g.add_edge("a", "b")
        assert "a" in g.predecessors("b")

    def test_edge_unknown_source_raises(self):
        g = Graph()
        g.add_node(StubNode("b"))
        with pytest.raises(ValueError, match="Unknown source"):
            g.add_edge("missing", "b")

    def test_edge_unknown_target_raises(self):
        g = Graph()
        g.add_node(StubNode("a"))
        with pytest.raises(ValueError, match="Unknown target"):
            g.add_edge("a", "missing")

    def test_chaining(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b"))
        result = g.add_edge("a", "b")
        assert result is g


class TestGraphLevels:
    def test_single_node(self):
        g = Graph()
        g.add_node(StubNode("a"))
        assert g.levels == [["a"]]

    def test_no_edges_single_level(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b")).add_node(StubNode("c"))
        levels = g.levels
        assert len(levels) == 1
        assert set(levels[0]) == {"a", "b", "c"}

    def test_linear_chain(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b")).add_node(StubNode("c"))
        g.add_edge("a", "b").add_edge("b", "c")
        levels = g.levels
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert levels[1] == ["b"]
        assert levels[2] == ["c"]

    def test_diamond_graph(self):
        g = Graph()
        for nid in ["a", "b", "c", "d"]:
            g.add_node(StubNode(nid))
        g.add_edge("a", "b").add_edge("a", "c")
        g.add_edge("b", "d").add_edge("c", "d")
        levels = g.levels
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]

    def test_cycle_raises(self):
        g = Graph()
        g.add_node(StubNode("a")).add_node(StubNode("b"))
        g.add_edge("a", "b").add_edge("b", "a")
        with pytest.raises(CycleError):
            _ = g.levels

    def test_three_node_cycle(self):
        g = Graph()
        for nid in ["a", "b", "c"]:
            g.add_node(StubNode(nid))
        g.add_edge("a", "b").add_edge("b", "c").add_edge("c", "a")
        with pytest.raises(CycleError):
            _ = g.levels

    def test_empty_graph(self):
        g = Graph()
        assert g.levels == []
