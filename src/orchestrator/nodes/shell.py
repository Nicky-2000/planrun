"""ShellNode — run shell commands via asyncio subprocess."""

import asyncio

from orchestrator.core.context import Context
from orchestrator.core.node import Node, NodeResult, NodeStatus

DEFAULT_TIMEOUT = 120


class ShellNode(Node):
    """Execute a shell command and capture its output.

    Outputs: ``stdout``, ``stderr``, ``returncode``, ``passed``, ``output``.
    ``passed`` is True when the return code is 0.
    ``output`` is stdout + stderr combined.
    """

    def __init__(
        self,
        node_id: str,
        *,
        command: str,
        timeout: int = DEFAULT_TIMEOUT,
        cwd: str | None = None,
    ) -> None:
        super().__init__(node_id)
        self.command = command
        self.timeout = timeout
        self.cwd = cwd

    async def run(self, ctx: Context) -> NodeResult:
        command = ctx.format_template(self.command)

        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=self.cwd,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(),
                timeout=self.timeout,
            )
        except TimeoutError:
            proc.kill()  # type: ignore[union-attr]
            return NodeResult(
                status=NodeStatus.FAILURE,
                error=f"Command timed out after {self.timeout}s",
                outputs={"passed": False, "returncode": -1},
            )

        stdout_text = stdout.decode()
        stderr_text = stderr.decode()
        returncode = proc.returncode or 0
        passed = returncode == 0

        return NodeResult(
            status=NodeStatus.SUCCESS if passed else NodeStatus.FAILURE,
            outputs={
                "stdout": stdout_text,
                "stderr": stderr_text,
                "returncode": returncode,
                "passed": passed,
                "output": (stdout_text + "\n" + stderr_text).strip(),
            },
            error=None if passed else f"Command exited with code {returncode}",
        )
