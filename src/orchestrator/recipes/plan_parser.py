"""Plan parser — extract steps and metadata from markdown plan files.

Extracted and adapted from ``scripts/tdd-loop.py``.
"""

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class StepMetadata:
    """Parsed metadata from step HTML comments."""

    context: list[str] = field(default_factory=list)
    creates: list[str] = field(default_factory=list)
    modifies: list[str] = field(default_factory=list)
    test_file: str | None = None
    depends_on: list[str] = field(default_factory=list)
    skip_tests: bool = False
    skip: bool = False
    verify_cmd: str | None = None


@dataclass
class Step:
    """A single step from the plan."""

    number: str
    title: str
    content: str
    metadata: StepMetadata


def parse_step_metadata(content: str) -> StepMetadata:
    """Parse YAML metadata from HTML comment in step content."""
    match = re.search(r"<!--\s*(.*?)\s*-->", content, re.DOTALL)
    if not match:
        return StepMetadata()

    yaml_content = match.group(1).strip()

    if yaml_content.startswith("METADATA FORMAT:"):
        return StepMetadata()

    try:
        data = yaml.safe_load(yaml_content)
        if not isinstance(data, dict):
            return StepMetadata()

        return StepMetadata(
            context=data.get("context", []) or [],
            creates=data.get("creates", []) or [],
            modifies=data.get("modifies", []) or [],
            test_file=data.get("test_file"),
            depends_on=[str(d) for d in (data.get("depends_on", []) or [])],
            skip_tests=bool(data.get("skip_tests", False)),
            skip=bool(data.get("skip", False)),
            verify_cmd=data.get("verify_cmd"),
        )
    except yaml.YAMLError:
        return StepMetadata()


def parse_plan(plan_path: str) -> tuple[list[Step], str]:
    """Parse a plan markdown file and extract implementation steps.

    Returns ``(steps, full_plan_content)``.
    """
    content = Path(plan_path).read_text()

    steps_match = re.search(
        r"## Implementation Steps\s*\n(.*?)(?=\n## |\Z)",
        content,
        re.DOTALL,
    )
    if not steps_match:
        raise ValueError("Could not find '## Implementation Steps' section in plan")

    steps_content = steps_match.group(1)

    step_pattern = r"### (Step \d+[a-z]?): ([^\n]+)\n(.*?)(?=\n### Step |\Z)"
    matches = re.findall(step_pattern, steps_content, re.DOTALL)

    steps = []
    for match in matches:
        step_num = match[0].replace("Step ", "")
        title = match[1].strip()
        step_content = match[2].strip()
        metadata = parse_step_metadata(step_content)
        steps.append(
            Step(
                number=step_num,
                title=title,
                content=step_content,
                metadata=metadata,
            )
        )

    return steps, content


def extract_verify_cmd(step: Step, default_cmd: str | None = None) -> str | None:
    """Extract the verification command for a step.

    Priority: step metadata ``verify_cmd`` > ``Verification:`` line in content > default.
    """
    if step.metadata.verify_cmd:
        return step.metadata.verify_cmd

    match = re.search(r"\*\*Verification\*\*:\s*`([^`]+)`", step.content)
    if match:
        return match.group(1)

    return default_cmd
