"""Tests for plan_parser."""

import textwrap
from pathlib import Path

import pytest

from orchestrator.recipes.plan_parser import (
    Step,
    StepMetadata,
    extract_verify_cmd,
    parse_plan,
    parse_step_metadata,
)


class TestParseStepMetadata:
    def test_full_metadata(self):
        content = textwrap.dedent("""\
            <!--
            context:
              - src/a.ts
              - src/b.ts
            creates:
              - src/new.ts
            modifies:
              - src/old.ts
            test_file: src/__tests__/new.test.ts
            depends_on:
              - 1
              - 2
            skip_tests: true
            skip: false
            verify_cmd: bun run typecheck
            -->

            Some step content here.
        """)
        meta = parse_step_metadata(content)
        assert meta.context == ["src/a.ts", "src/b.ts"]
        assert meta.creates == ["src/new.ts"]
        assert meta.modifies == ["src/old.ts"]
        assert meta.test_file == "src/__tests__/new.test.ts"
        assert meta.depends_on == ["1", "2"]
        assert meta.skip_tests is True
        assert meta.skip is False
        assert meta.verify_cmd == "bun run typecheck"

    def test_no_metadata(self):
        meta = parse_step_metadata("Just some content, no HTML comment.")
        assert meta == StepMetadata()

    def test_metadata_format_comment_ignored(self):
        content = "<!-- METADATA FORMAT: this describes the format -->"
        meta = parse_step_metadata(content)
        assert meta == StepMetadata()

    def test_partial_metadata(self):
        content = textwrap.dedent("""\
            <!--
            context:
              - src/foo.ts
            skip_tests: true
            -->
        """)
        meta = parse_step_metadata(content)
        assert meta.context == ["src/foo.ts"]
        assert meta.skip_tests is True
        assert meta.test_file is None
        assert meta.creates == []

    def test_invalid_yaml_returns_default(self):
        content = "<!-- : [invalid yaml -->"
        meta = parse_step_metadata(content)
        assert meta == StepMetadata()

    def test_non_dict_yaml_returns_default(self):
        content = "<!-- just a string -->"
        meta = parse_step_metadata(content)
        assert meta == StepMetadata()

    def test_depends_on_coerced_to_strings(self):
        content = textwrap.dedent("""\
            <!--
            depends_on:
              - 1
              - 2
            -->
        """)
        meta = parse_step_metadata(content)
        assert meta.depends_on == ["1", "2"]

    def test_null_lists_become_empty(self):
        content = textwrap.dedent("""\
            <!--
            context:
            creates:
            -->
        """)
        meta = parse_step_metadata(content)
        assert meta.context == []
        assert meta.creates == []


class TestParsePlan:
    def test_parse_two_steps(self, tmp_path: Path):
        plan = textwrap.dedent("""\
            # Plan: Test

            ## Implementation Steps

            ### Step 1: First step

            <!--
            context:
              - file_a.ts
            creates:
              - file_b.ts
            -->

            Do something.

            ### Step 2: Second step

            <!--
            depends_on:
              - 1
            skip_tests: true
            -->

            Do another thing.

            ## File Summary
        """)
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan)

        steps, content = parse_plan(str(plan_file))
        assert len(steps) == 2
        assert steps[0].number == "1"
        assert steps[0].title == "First step"
        assert steps[0].metadata.context == ["file_a.ts"]
        assert steps[1].number == "2"
        assert steps[1].metadata.depends_on == ["1"]
        assert content == plan

    def test_no_implementation_section_raises(self, tmp_path: Path):
        plan_file = tmp_path / "empty.md"
        plan_file.write_text("# No steps here\n")
        with pytest.raises(ValueError, match="Implementation Steps"):
            parse_plan(str(plan_file))

    def test_step_with_letter_suffix(self, tmp_path: Path):
        plan = textwrap.dedent("""\
            ## Implementation Steps

            ### Step 4b: Sub-step

            Some content.
        """)
        plan_file = tmp_path / "plan.md"
        plan_file.write_text(plan)
        steps, _ = parse_plan(str(plan_file))
        assert len(steps) == 1
        assert steps[0].number == "4b"


class TestExtractVerifyCmd:
    def test_from_metadata(self):
        step = Step(
            number="1",
            title="Test",
            content="",
            metadata=StepMetadata(verify_cmd="make test"),
        )
        assert extract_verify_cmd(step) == "make test"

    def test_from_content(self):
        step = Step(
            number="1",
            title="Test",
            content="**Verification**: `cd apps/ui && bun run typecheck`",
            metadata=StepMetadata(),
        )
        assert extract_verify_cmd(step) == "cd apps/ui && bun run typecheck"

    def test_metadata_takes_priority(self):
        step = Step(
            number="1",
            title="Test",
            content="**Verification**: `cmd_from_content`",
            metadata=StepMetadata(verify_cmd="cmd_from_metadata"),
        )
        assert extract_verify_cmd(step) == "cmd_from_metadata"

    def test_fallback_to_default(self):
        step = Step(
            number="1",
            title="Test",
            content="No verification line.",
            metadata=StepMetadata(),
        )
        assert extract_verify_cmd(step, default_cmd="default") == "default"
        assert extract_verify_cmd(step) is None
