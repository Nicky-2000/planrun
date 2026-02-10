"""Graph — DAG of nodes with topological sort into parallel levels."""

from collections import deque
from typing import Self

from orchestrator.core.node import Node


class CycleError(Exception):
    """Raised when the graph contains a cycle."""


class Graph:
    """Directed acyclic graph of nodes with edge dependencies.

    Nodes are added with ``add_node``, edges with ``add_edge(source, target)``
    meaning *source must complete before target starts*.

    The ``levels`` property returns a topological ordering grouped into
    parallel levels — nodes within the same level have no mutual dependencies
    and can run concurrently.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, Node] = {}
        self._edges: dict[str, set[str]] = {}  # node_id -> set of successor ids
        self._reverse: dict[str, set[str]] = {}  # node_id -> set of predecessor ids

    def add_node(self, node: Node) -> Self:
        self._nodes[node.node_id] = node
        self._edges.setdefault(node.node_id, set())
        self._reverse.setdefault(node.node_id, set())
        return self

    def add_edge(self, source: str, target: str) -> Self:
        """Add a dependency edge: *source* must finish before *target* starts."""
        if source not in self._nodes:
            raise ValueError(f"Unknown source node: {source!r}")
        if target not in self._nodes:
            raise ValueError(f"Unknown target node: {target!r}")
        self._edges[source].add(target)
        self._reverse[target].add(source)
        return self

    def get_node(self, node_id: str) -> Node:
        return self._nodes[node_id]

    def predecessors(self, node_id: str) -> set[str]:
        return set(self._reverse.get(node_id, set()))

    @property
    def node_ids(self) -> list[str]:
        return list(self._nodes)

    @property
    def levels(self) -> list[list[str]]:
        """Kahn's algorithm producing topological levels for parallel execution.

        Each level is a list of node IDs that can be executed concurrently.
        Raises ``CycleError`` if the graph contains a cycle.
        """
        in_degree: dict[str, int] = {nid: len(self._reverse.get(nid, set())) for nid in self._nodes}
        queue: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)
        levels: list[list[str]] = []
        visited = 0

        while queue:
            level: list[str] = []
            for _ in range(len(queue)):
                nid = queue.popleft()
                level.append(nid)
                visited += 1
                for succ in self._edges.get(nid, set()):
                    in_degree[succ] -= 1
                    if in_degree[succ] == 0:
                        queue.append(succ)
            levels.append(level)

        if visited != len(self._nodes):
            raise CycleError(f"Graph contains a cycle (visited {visited}/{len(self._nodes)} nodes)")

        return levels

    def __len__(self) -> int:
        return len(self._nodes)

    def __repr__(self) -> str:
        return f"Graph(nodes={len(self._nodes)}, edges={sum(len(s) for s in self._edges.values())})"
