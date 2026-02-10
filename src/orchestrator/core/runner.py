"""Runner — DAG executor using asyncio.gather per topological level."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from orchestrator.core.context import Context
from orchestrator.core.graph import Graph
from orchestrator.core.node import NodeResult, NodeStatus

logger = logging.getLogger(__name__)


@dataclass
class RunReport:
    results: dict[str, NodeResult] = field(default_factory=dict)
    duration_ms: float = 0.0

    @property
    def success(self) -> bool:
        return all(
            r.status in (NodeStatus.SUCCESS, NodeStatus.SKIPPED) for r in self.results.values()
        )

    @property
    def failed_nodes(self) -> list[str]:
        return [nid for nid, r in self.results.items() if r.status == NodeStatus.FAILURE]

    def summary(self) -> dict[str, Any]:
        by_status: dict[str, int] = {}
        for r in self.results.values():
            by_status[r.status.value] = by_status.get(r.status.value, 0) + 1
        return {
            "total": len(self.results),
            "by_status": by_status,
            "duration_ms": self.duration_ms,
            "success": self.success,
        }


class Runner:
    """Execute a graph level-by-level, running nodes within each level concurrently."""

    def __init__(self, *, fail_fast: bool = False, dry_run: bool = False) -> None:
        self.fail_fast = fail_fast
        self.dry_run = dry_run

    async def run(self, graph: Graph, ctx: Context) -> RunReport:
        report = RunReport()
        start = time.monotonic()
        levels = graph.levels

        for level_idx, level in enumerate(levels):
            logger.info("Level %d: %s", level_idx, level)

            if self.dry_run:
                for node_id in level:
                    report.results[node_id] = NodeResult(
                        status=NodeStatus.SKIPPED,
                        metadata={"dry_run": True, "level": level_idx},
                    )
                continue

            tasks = []
            for node_id in level:
                if self._should_skip(node_id, graph, report):
                    report.results[node_id] = NodeResult(
                        status=NodeStatus.SKIPPED,
                        error="upstream dependency failed",
                        metadata={"level": level_idx},
                    )
                    continue
                tasks.append(self._run_node(node_id, graph, ctx, report, level_idx))

            if tasks:
                await asyncio.gather(*tasks)

            if self.fail_fast and any(
                report.results.get(nid, NodeResult(status=NodeStatus.SUCCESS)).status
                == NodeStatus.FAILURE
                for nid in level
            ):
                logger.warning("Fail-fast triggered at level %d", level_idx)
                break

        report.duration_ms = round((time.monotonic() - start) * 1000, 1)
        return report

    def _should_skip(self, node_id: str, graph: Graph, report: RunReport) -> bool:
        """Check if any predecessor failed."""
        for pred in graph.predecessors(node_id):
            result = report.results.get(pred)
            if result and result.status == NodeStatus.FAILURE:
                return True
        return False

    async def _run_node(
        self,
        node_id: str,
        graph: Graph,
        ctx: Context,
        report: RunReport,
        level_idx: int,
    ) -> None:
        node = graph.get_node(node_id)
        logger.info("Running %s", node_id)
        result = await node.execute(ctx)
        result.metadata.setdefault("level", level_idx)

        if result.status == NodeStatus.SUCCESS:
            ctx.merge(node_id, result.outputs)

        report.results[node_id] = result
        logger.info("Finished %s: %s", node_id, result.status.value)
