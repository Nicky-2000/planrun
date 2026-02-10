"""FileReaderNode — read files into formatted markdown for context injection."""

from pathlib import Path

from orchestrator.core.context import Context
from orchestrator.core.node import Node, NodeResult, NodeStatus


class FileReaderNode(Node):
    """Read one or more files and produce a formatted markdown string.

    Each file is rendered as a markdown section with its path and content.
    Missing files are noted but don't cause failure.
    """

    def __init__(self, node_id: str, *, paths: list[str]) -> None:
        super().__init__(node_id)
        self.paths = paths

    async def run(self, ctx: Context) -> NodeResult:
        sections: list[str] = []
        missing: list[str] = []

        for path_str in self.paths:
            p = Path(path_str)
            if p.exists():
                try:
                    content = p.read_text()
                    sections.append(f"### File: `{path_str}`\n```\n{content}\n```")
                except Exception as e:
                    sections.append(f"### File: `{path_str}`\n(Error reading: {e})")
                    missing.append(path_str)
            else:
                sections.append(f"### File: `{path_str}`\n(File does not exist — will be created)")
                missing.append(path_str)

        output = "\n\n".join(sections)

        return NodeResult(
            status=NodeStatus.SUCCESS,
            outputs={"output": output, "missing": missing},
            metadata={"file_count": len(self.paths), "missing_count": len(missing)},
        )
