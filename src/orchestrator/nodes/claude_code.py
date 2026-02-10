"""ClaudeCodeNode — CLI wrapper for file-modifying agent tasks."""

import asyncio

from orchestrator.core.context import Context
from orchestrator.core.node import Node, NodeResult, NodeStatus

CLAUDE_CMD = "claude"
DEFAULT_TIMEOUT = 300


class ClaudeCodeNode(Node):
    """Run a prompt through ``claude --print --dangerously-skip-permissions``.

    The prompt template is formatted with context values, then piped via stdin.
    Use this for tasks that modify files (implementation, fixes, test writing).
    """

    def __init__(
        self,
        node_id: str,
        *,
        prompt_template: str,
        timeout: int = DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> None:
        super().__init__(node_id)
        self.prompt_template = prompt_template
        self.timeout = timeout
        self.cwd = cwd

    async def run(self, ctx: Context) -> NodeResult:
        prompt = ctx.format_template(self.prompt_template)

        try:
            proc = await asyncio.create_subprocess_exec(
                CLAUDE_CMD,
                "--print",
                "--dangerously-skip-permissions",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=prompt.encode()),
                timeout=self.timeout,
            )
        except FileNotFoundError:
            return NodeResult(
                status=NodeStatus.FAILURE,
                error=f"'{CLAUDE_CMD}' CLI not found. Ensure it is installed and on PATH.",
            )
        except TimeoutError:
            proc.kill()
            return NodeResult(
                status=NodeStatus.FAILURE,
                error=f"Claude Code timed out after {self.timeout}s",
            )

        stdout_text = stdout.decode()
        stderr_text = stderr.decode()

        if proc.returncode != 0:
            return NodeResult(
                status=NodeStatus.FAILURE,
                outputs={"stdout": stdout_text, "stderr": stderr_text},
                error=stderr_text or f"Exit code: {proc.returncode}",
            )

        return NodeResult(
            status=NodeStatus.SUCCESS,
            outputs={"response": stdout_text, "stdout": stdout_text, "stderr": stderr_text},
        )
