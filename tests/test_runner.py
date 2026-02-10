"""Tests for Runner."""

import asyncio
from typing import ClassVar

import pytest

from orchestrator.core.context import Context
from orchestrator.core.graph import Graph
from orchestrator.core.node import Node, NodeResult, NodeStatus
from orchestrator.core.runner import Runner


class SuccessNode(Node):
    def __init__(self, node_id: str, outputs: dict | None = None, delay: float = 0):
        super().__init__(node_id)
        self._outputs = outputs or {}
        self._delay = delay

    async def run(self, ctx: Context) -> NodeResult:
        if self._delay:
            await asyncio.sleep(self._delay)
        return NodeResult(status=NodeStatus.SUCCESS, outputs=self._outputs)


class FailNode(Node):
    def __init__(self, node_id: str, error: str = "fail"):
        super().__init__(node_id)
        self._error = error

    async def run(self, ctx: Context) -> NodeResult:
        return NodeResult(status=NodeStatus.FAILURE, error=self._error)


class RecordingNode(Node):
    """Records the time it ran, useful for verifying parallel execution."""

    executions: ClassVar[list[tuple[str, float]]] = []

    def __init__(self, node_id: str, delay: float = 0.05):
        super().__init__(node_id)
        self._delay = delay

    async def run(self, ctx: Context) -> NodeResult:
        start = asyncio.get_event_loop().time()
        await asyncio.sleep(self._delay)
        RecordingNode.executions.append((self.node_id, start))
        return NodeResult(status=NodeStatus.SUCCESS)


class TestRunnerBasic:
    @pytest.mark.asyncio
    async def test_single_node_success(self):
        g = Graph()
        g.add_node(SuccessNode("a", outputs={"val": 42}))
        runner = Runner()
        report = await runner.run(g, Context())
        assert report.success
        assert report.results["a"].status == NodeStatus.SUCCESS

    @pytest.mark.asyncio
    async def test_single_node_failure(self):
        g = Graph()
        g.add_node(FailNode("a", error="boom"))
        runner = Runner()
        report = await runner.run(g, Context())
        assert not report.success
        assert report.failed_nodes == ["a"]
        assert report.results["a"].error == "boom"

    @pytest.mark.asyncio
    async def test_empty_graph(self):
        g = Graph()
        runner = Runner()
        report = await runner.run(g, Context())
        assert report.success
        assert report.results == {}


class TestRunnerContextMerge:
    @pytest.mark.asyncio
    async def test_outputs_merged_into_context(self):
        g = Graph()
        g.add_node(SuccessNode("a", outputs={"x": 1}))
        g.add_node(SuccessNode("b", outputs={"y": 2}))
        g.add_edge("a", "b")
        ctx = Context()
        runner = Runner()
        await runner.run(g, ctx)
        assert ctx.get("a.x") == 1
        assert ctx.get("b.y") == 2


class TestRunnerSkipLogic:
    @pytest.mark.asyncio
    async def test_downstream_skipped_on_failure(self):
        g = Graph()
        g.add_node(FailNode("a")).add_node(SuccessNode("b"))
        g.add_edge("a", "b")
        runner = Runner()
        report = await runner.run(g, Context())
        assert report.results["a"].status == NodeStatus.FAILURE
        assert report.results["b"].status == NodeStatus.SKIPPED

    @pytest.mark.asyncio
    async def test_unrelated_node_not_skipped(self):
        g = Graph()
        g.add_node(FailNode("a")).add_node(SuccessNode("b")).add_node(SuccessNode("c"))
        g.add_edge("a", "c")
        # b has no dependency on a
        runner = Runner()
        report = await runner.run(g, Context())
        assert report.results["a"].status == NodeStatus.FAILURE
        assert report.results["b"].status == NodeStatus.SUCCESS
        assert report.results["c"].status == NodeStatus.SKIPPED


class TestRunnerFailFast:
    @pytest.mark.asyncio
    async def test_fail_fast_stops_after_failure_level(self):
        g = Graph()
        g.add_node(FailNode("a")).add_node(SuccessNode("b"))
        # b in same level as a (no edge) but we add a later level
        g.add_node(SuccessNode("c"))
        g.add_edge("a", "c")
        runner = Runner(fail_fast=True)
        report = await runner.run(g, Context())
        assert report.results["a"].status == NodeStatus.FAILURE
        # c is in a later level and should not be present (execution stopped)
        assert "c" not in report.results or report.results["c"].status == NodeStatus.SKIPPED


class TestRunnerDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_skips_all(self):
        g = Graph()
        g.add_node(SuccessNode("a")).add_node(SuccessNode("b"))
        g.add_edge("a", "b")
        runner = Runner(dry_run=True)
        report = await runner.run(g, Context())
        assert report.results["a"].status == NodeStatus.SKIPPED
        assert report.results["b"].status == NodeStatus.SKIPPED
        assert report.results["a"].metadata.get("dry_run") is True


class TestRunnerParallel:
    @pytest.mark.asyncio
    async def test_parallel_nodes_run_concurrently(self):
        RecordingNode.executions = []
        g = Graph()
        g.add_node(RecordingNode("p1", delay=0.05))
        g.add_node(RecordingNode("p2", delay=0.05))
        g.add_node(RecordingNode("p3", delay=0.05))
        runner = Runner()
        report = await runner.run(g, Context())
        assert report.success
        # All 3 should have started at roughly the same time
        starts = [t for _, t in RecordingNode.executions]
        assert max(starts) - min(starts) < 0.04  # started within 40ms of each other


class TestRunReport:
    @pytest.mark.asyncio
    async def test_summary(self):
        g = Graph()
        g.add_node(SuccessNode("a")).add_node(FailNode("b"))
        runner = Runner()
        report = await runner.run(g, Context())
        s = report.summary()
        assert s["total"] == 2
        assert s["by_status"]["success"] == 1
        assert s["by_status"]["failure"] == 1
        assert s["success"] is False
        assert s["duration_ms"] > 0
