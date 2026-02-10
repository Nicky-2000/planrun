"""TDD recipe — builds a Graph from a parsed plan file."""

from orchestrator.core.graph import Graph
from orchestrator.nodes.claude_code import ClaudeCodeNode
from orchestrator.nodes.control import RetryNode
from orchestrator.nodes.file_ops import FileReaderNode
from orchestrator.nodes.shell import ShellNode
from orchestrator.recipes.plan_parser import Step, extract_verify_cmd, parse_plan

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

TEST_WRITER_PROMPT = """You are a test writer agent in a TDD loop.

## Your Task
Write tests for Step {step_number}: {step_title}

## Step Details
{step_content}

## Context Files
{read_context_output}

## Test File Location
Write tests to: `{test_file}`

## Instructions
1. Read the step requirements carefully
2. Create the test file at the specified location
3. Tests should verify the expected behavior described in the step
4. Use the existing test patterns from the context files
5. Keep tests focused and minimal

Write the tests now. Create the test file.
"""

IMPLEMENTER_PROMPT = """You are an implementer agent in a TDD loop.

## Your Task
Implement the code for Step {step_number}: {step_title}

## Step Details
{step_content}

## Context Files (READ THESE CAREFULLY)
{read_context_output}

## Files to Create
{files_to_create}

## Files to Modify
{files_to_modify}

## Instructions
1. Read the step requirements and context files carefully
2. Implement the code exactly as specified
3. Follow the patterns shown in the context files
4. Make sure type checking will pass
5. If modifying a file, preserve unrelated code

Implement the code now.
"""

FIXER_PROMPT = """You are a fixer agent in a TDD loop.

## Your Task
Fix the implementation for Step {step_number}: {step_title}

## Verification Output (errors)
```
{verify_output}
```

## Step Details
{step_content}

## Context Files
{read_context_output}

## Instructions
1. Analyze the errors carefully
2. Identify what's wrong with the implementation
3. Fix the code to make verification pass
4. Do NOT modify tests — only fix the implementation

Fix the code now.
"""


def _build_step_nodes(
    step: Step,
    verify_cmd: str,
    max_retries: int,
    cwd: str | None,
) -> tuple[list, list[tuple[str, str]]]:
    """Build nodes and edges for a single step. Returns (nodes, edges)."""
    n = step.number
    nodes = []
    edges: list[tuple[str, str]] = []

    # Context values that all nodes in this step need
    files_to_create = (
        "\n".join(f"  - {f}" for f in step.metadata.creates)
        if step.metadata.creates
        else "  (none)"
    )
    files_to_modify = (
        "\n".join(f"  - {f}" for f in step.metadata.modifies)
        if step.metadata.modifies
        else "  (none)"
    )

    # 1. FileReaderNode — load context files
    read_id = f"read_context_{n}"
    context_paths = step.metadata.context or []
    nodes.append(FileReaderNode(read_id, paths=context_paths))

    # 2. Optional: test writer
    prev_id = read_id
    if step.metadata.test_file and not step.metadata.skip_tests:
        test_id = f"write_tests_{n}"
        nodes.append(
            ClaudeCodeNode(
                test_id,
                prompt_template=TEST_WRITER_PROMPT.replace("{step_number}", n)
                .replace("{step_title}", step.title)
                .replace("{step_content}", step.content)
                .replace("{test_file}", step.metadata.test_file)
                .replace("{read_context_output}", f"{{{read_id}.output}}"),
                cwd=cwd,
            )
        )
        edges.append((read_id, test_id))
        prev_id = test_id

    # 3. Implementer
    impl_id = f"implement_{n}"
    nodes.append(
        ClaudeCodeNode(
            impl_id,
            prompt_template=IMPLEMENTER_PROMPT.replace("{step_number}", n)
            .replace("{step_title}", step.title)
            .replace("{step_content}", step.content)
            .replace("{files_to_create}", files_to_create)
            .replace("{files_to_modify}", files_to_modify)
            .replace("{read_context_output}", f"{{{read_id}.output}}"),
            cwd=cwd,
        )
    )
    edges.append((prev_id, impl_id))

    # 4. RetryNode (verify + fix)
    verify_node = ShellNode(f"_verify_{n}", command=verify_cmd, cwd=cwd)
    fix_node = ClaudeCodeNode(
        f"_fix_{n}",
        prompt_template=FIXER_PROMPT.replace("{step_number}", n)
        .replace("{step_title}", step.title)
        .replace("{step_content}", step.content)
        .replace("{read_context_output}", f"{{{read_id}.output}}")
        .replace("{verify_output}", f"{{verify_fix_{n}.verify.output}}"),
        cwd=cwd,
    )
    retry_id = f"verify_fix_{n}"
    nodes.append(
        RetryNode(
            retry_id,
            verify_node=verify_node,
            fix_node=fix_node,
            max_retries=max_retries,
        )
    )
    edges.append((impl_id, retry_id))

    return nodes, edges


def tdd_recipe(
    plan_path: str,
    *,
    verify_cmd: str | None = None,
    max_retries: int = 3,
    step_filter: str | None = None,
    start_step: str | None = None,
    cwd: str | None = None,
) -> tuple[Graph, dict]:
    """Build a TDD graph from a plan file.

    Returns ``(graph, info_dict)`` where ``info_dict`` has metadata like step count.
    """
    steps, plan_content = parse_plan(plan_path)

    if not steps:
        raise ValueError("No steps found in plan")

    # Filter steps
    if step_filter:
        steps = [s for s in steps if s.number == step_filter]
        if not steps:
            raise ValueError(f"Step {step_filter} not found in plan")
    elif start_step:
        start_idx = None
        for i, s in enumerate(steps):
            if s.number == start_step:
                start_idx = i
                break
        if start_idx is None:
            raise ValueError(f"Start step {start_step} not found in plan")
        steps = steps[start_idx:]

    # Remove skipped steps
    active_steps = [s for s in steps if not s.metadata.skip]

    graph = Graph()
    all_edges: list[tuple[str, str]] = []

    for step in active_steps:
        step_verify = extract_verify_cmd(step, verify_cmd) or "echo 'no verify command'"
        nodes, edges = _build_step_nodes(step, step_verify, max_retries, cwd)
        for node in nodes:
            graph.add_node(node)
        all_edges.extend(edges)

    # Cross-step dependencies: verify_fix_{dep} → read_context_{step}
    active_numbers = {s.number for s in active_steps}
    for step in active_steps:
        for dep in step.metadata.depends_on:
            if dep in active_numbers:
                all_edges.append((f"verify_fix_{dep}", f"read_context_{step.number}"))

    for src, tgt in all_edges:
        graph.add_edge(src, tgt)

    # Seed context with plan-level info
    initial_ctx = {
        "plan_path": plan_path,
        "plan_content": plan_content,
        "step_count": len(active_steps),
    }

    return graph, initial_ctx
