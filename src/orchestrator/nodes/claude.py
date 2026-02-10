"""ClaudeNode — Anthropic SDK-based node for analysis and planning."""

import anthropic

from orchestrator.core.context import Context
from orchestrator.core.node import Node, NodeResult, NodeStatus


class ClaudeNode(Node):
    """Run a prompt through the Anthropic Messages API.

    Uses ``AsyncAnthropic`` with lazy client initialization.
    The prompt is formatted using ``ctx.format_template`` so it can reference
    context values like ``{step_content}`` or ``{read_context.output}``.
    """

    def __init__(
        self,
        node_id: str,
        *,
        prompt_template: str,
        model: str = "claude-sonnet-4-5-20250929",
        max_tokens: int = 4096,
        system: str | None = None,
    ) -> None:
        super().__init__(node_id)
        self.prompt_template = prompt_template
        self.model = model
        self.max_tokens = max_tokens
        self.system = system
        self._client: anthropic.AsyncAnthropic | None = None

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            self._client = anthropic.AsyncAnthropic()
        return self._client

    async def run(self, ctx: Context) -> NodeResult:
        prompt = ctx.format_template(self.prompt_template)
        client = self._get_client()

        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self.system:
            kwargs["system"] = ctx.format_template(self.system)

        response = await client.messages.create(**kwargs)
        text = response.content[0].text if response.content else ""

        return NodeResult(
            status=NodeStatus.SUCCESS,
            outputs={"response": text},
            metadata={
                "model": response.model,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            },
        )
