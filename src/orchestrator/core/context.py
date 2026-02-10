"""Context — shared state dict flowing through the graph."""

import re
from typing import Any

_TEMPLATE_RE = re.compile(r"\{([^{}]+)\}")


class Context:
    """Flat key-value store shared across all nodes in a graph run.

    Nodes read with ``get()`` and write with ``set()``.
    The runner merges node outputs under the ``{node_id}.{key}`` namespace.
    """

    def __init__(self, initial: dict[str, Any] | None = None) -> None:
        self._data: dict[str, Any] = dict(initial) if initial else {}

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        self._data[key] = value

    def merge(self, namespace: str, outputs: dict[str, Any]) -> None:
        """Merge a dict of outputs under ``namespace.``."""
        for k, v in outputs.items():
            self._data[f"{namespace}.{k}"] = v

    def format_template(self, template: str) -> str:
        """Format a string template using context values.

        Replaces ``{key}`` placeholders with values from the context.
        Supports dotted keys like ``{step_1.output}``.
        Missing keys are left as-is (e.g. ``{missing}`` stays ``{missing}``).
        """

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in self._data:
                return str(self._data[key])
            return match.group(0)

        return _TEMPLATE_RE.sub(_replace, template)

    def snapshot(self) -> dict[str, Any]:
        """Return a shallow copy of all context data."""
        return dict(self._data)

    def __contains__(self, key: str) -> bool:
        return key in self._data

    def __repr__(self) -> str:
        return f"Context({self._data!r})"
