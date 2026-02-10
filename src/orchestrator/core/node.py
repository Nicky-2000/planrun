"""Node ABC, NodeResult dataclass, and NodeStatus enum."""

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from orchestrator.core.context import Context


class NodeStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass
class NodeResult:
    status: NodeStatus
    outputs: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Node(ABC):
    """Abstract base class for all graph nodes."""

    def __init__(self, node_id: str) -> None:
        self.node_id = node_id

    @abstractmethod
    async def run(self, ctx: Context) -> NodeResult: ...

    async def execute(self, ctx: Context) -> NodeResult:
        """Run the node with timing metadata."""
        start = time.monotonic()
        try:
            result = await self.run(ctx)
        except Exception as e:
            result = NodeResult(status=NodeStatus.FAILURE, error=str(e))
        elapsed_ms = (time.monotonic() - start) * 1000
        result.metadata.setdefault("duration_ms", round(elapsed_ms, 1))
        return result

    def __repr__(self) -> str:
        return f"{type(self).__name__}({self.node_id!r})"
