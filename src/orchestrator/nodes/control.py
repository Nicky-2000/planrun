"""Control-flow nodes: GateNode and RetryNode."""

import logging
from collections.abc import Callable
from typing import Any

from orchestrator.core.context import Context
from orchestrator.core.node import Node, NodeResult, NodeStatus

logger = logging.getLogger(__name__)


class GateNode(Node):
    """Conditional gate — skip downstream nodes if predicate fails.

    The predicate receives the context and returns a bool.
    If it returns False, the gate produces a SKIPPED result.
    """

    def __init__(
        self,
        node_id: str,
        *,
        predicate: Callable[[Context], bool],
        reason: str = "gate predicate returned False",
    ) -> None:
        super().__init__(node_id)
        self.predicate = predicate
        self.reason = reason

    async def run(self, ctx: Context) -> NodeResult:
        if self.predicate(ctx):
            return NodeResult(status=NodeStatus.SUCCESS, outputs={"gate_open": True})
        return NodeResult(
            status=NodeStatus.SKIPPED,
            outputs={"gate_open": False},
            error=self.reason,
        )


class RetryNode(Node):
    """Composite node that runs a verify→fix loop up to N times.

    1. Run ``verify_node``
    2. If verify succeeds, return SUCCESS
    3. If verify fails, run ``fix_node`` (with verify outputs in context)
    4. Repeat up to ``max_retries`` times
    5. If all retries exhausted, return FAILURE
    """

    def __init__(
        self,
        node_id: str,
        *,
        verify_node: Node,
        fix_node: Node,
        max_retries: int = 3,
        pass_key: str = "passed",
    ) -> None:
        super().__init__(node_id)
        self.verify_node = verify_node
        self.fix_node = fix_node
        self.max_retries = max_retries
        self.pass_key = pass_key

    async def run(self, ctx: Context) -> NodeResult:
        last_verify: NodeResult | None = None
        attempts: list[dict[str, Any]] = []

        for attempt in range(1, self.max_retries + 1):
            logger.info("%s: verify attempt %d/%d", self.node_id, attempt, self.max_retries)

            last_verify = await self.verify_node.execute(ctx)
            ctx.merge(f"{self.node_id}.verify", last_verify.outputs)

            passed = last_verify.outputs.get(self.pass_key, False)
            attempts.append({"attempt": attempt, "passed": passed, "error": last_verify.error})

            if passed:
                return NodeResult(
                    status=NodeStatus.SUCCESS,
                    outputs={"passed": True, "attempts": len(attempts), **last_verify.outputs},
                    metadata={"attempts": attempts},
                )

            if attempt < self.max_retries:
                logger.info("%s: running fix (attempt %d)", self.node_id, attempt)
                fix_result = await self.fix_node.execute(ctx)
                ctx.merge(f"{self.node_id}.fix", fix_result.outputs)

                if fix_result.status == NodeStatus.FAILURE:
                    logger.warning("%s: fix node failed: %s", self.node_id, fix_result.error)

        error_msg = f"Verification failed after {len(attempts)} attempts" + (
            f": {last_verify.error}" if last_verify and last_verify.error else ""
        )
        return NodeResult(
            status=NodeStatus.FAILURE,
            outputs={"passed": False, "attempts": len(attempts)},
            error=error_msg,
            metadata={"attempts": attempts},
        )
