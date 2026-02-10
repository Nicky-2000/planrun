"""Tests for Context."""

from orchestrator.core.context import Context


class TestContextGetSet:
    def test_set_and_get(self):
        ctx = Context()
        ctx.set("key", "value")
        assert ctx.get("key") == "value"

    def test_get_missing_returns_default(self):
        ctx = Context()
        assert ctx.get("missing") is None
        assert ctx.get("missing", 42) == 42

    def test_initial_data(self):
        ctx = Context({"a": 1, "b": 2})
        assert ctx.get("a") == 1
        assert ctx.get("b") == 2

    def test_overwrite(self):
        ctx = Context({"key": "old"})
        ctx.set("key", "new")
        assert ctx.get("key") == "new"

    def test_contains(self):
        ctx = Context({"present": True})
        assert "present" in ctx
        assert "absent" not in ctx


class TestContextMerge:
    def test_merge_namespaces_keys(self):
        ctx = Context()
        ctx.merge("step_1", {"output": "hello", "passed": True})
        assert ctx.get("step_1.output") == "hello"
        assert ctx.get("step_1.passed") is True

    def test_merge_does_not_overwrite_other_namespaces(self):
        ctx = Context()
        ctx.merge("a", {"x": 1})
        ctx.merge("b", {"x": 2})
        assert ctx.get("a.x") == 1
        assert ctx.get("b.x") == 2

    def test_merge_empty_dict(self):
        ctx = Context({"existing": "val"})
        ctx.merge("ns", {})
        assert ctx.get("existing") == "val"


class TestContextFormatTemplate:
    def test_basic_substitution(self):
        ctx = Context({"name": "world"})
        assert ctx.format_template("hello {name}") == "hello world"

    def test_missing_key_left_as_is(self):
        ctx = Context()
        assert ctx.format_template("hello {missing}") == "hello {missing}"

    def test_mixed_present_and_missing(self):
        ctx = Context({"a": "A"})
        result = ctx.format_template("{a} and {b}")
        assert result == "A and {b}"

    def test_namespaced_keys(self):
        ctx = Context()
        ctx.merge("step_1", {"output": "data"})
        assert ctx.format_template("got: {step_1.output}") == "got: data"


class TestContextSnapshot:
    def test_snapshot_is_copy(self):
        ctx = Context({"a": 1})
        snap = ctx.snapshot()
        snap["a"] = 999
        assert ctx.get("a") == 1

    def test_snapshot_contents(self):
        ctx = Context({"x": "y"})
        ctx.set("z", "w")
        snap = ctx.snapshot()
        assert snap == {"x": "y", "z": "w"}
