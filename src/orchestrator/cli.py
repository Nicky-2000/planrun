"""CLI entry point for the orchestrator."""

import argparse
import asyncio
import logging
import sys

from orchestrator.core.context import Context
from orchestrator.core.runner import Runner
from orchestrator.recipes.tdd import tdd_recipe


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="planrun",
        description="Composable DAG-based agent orchestration system",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Enable debug logging")

    sub = parser.add_subparsers(dest="command")

    tdd = sub.add_parser("tdd", help="Run TDD recipe from a plan file")
    tdd.add_argument("--plan", required=True, help="Path to the plan markdown file")
    tdd.add_argument("--step", default=None, help="Run only this specific step (e.g. '2')")
    tdd.add_argument("--start-step", default=None, help="Start from this step (e.g. '3')")
    tdd.add_argument("--dry-run", action="store_true", help="Print DAG levels without executing")
    tdd.add_argument("--fail-fast", action="store_true", help="Stop on first failure")
    tdd.add_argument("--verify-cmd", default=None, help="Override verification command")
    tdd.add_argument("--max-retries", type=int, default=3, help="Max fix attempts per step")
    tdd.add_argument("--cwd", default=None, help="Working directory for subprocesses")

    return parser


async def _run_tdd(args: argparse.Namespace) -> int:
    graph, initial_ctx = tdd_recipe(
        args.plan,
        verify_cmd=args.verify_cmd,
        max_retries=args.max_retries,
        step_filter=args.step,
        start_step=args.start_step,
        cwd=args.cwd,
    )

    ctx = Context(initial_ctx)
    runner = Runner(fail_fast=args.fail_fast, dry_run=args.dry_run)

    levels = graph.levels
    print(f"Plan: {args.plan}")
    print(f"Nodes: {len(graph)}")
    print(f"Levels: {len(levels)}")
    for i, level in enumerate(levels):
        print(f"  Level {i}: {level}")

    if args.dry_run:
        print("\nDry run — no nodes executed.")
        return 0

    print()
    report = await runner.run(graph, ctx)

    print(f"\nDone in {report.duration_ms:.0f}ms")
    summary = report.summary()
    for status, count in summary["by_status"].items():
        print(f"  {status}: {count}")

    if not report.success:
        print(f"\nFailed nodes: {report.failed_nodes}")
        return 1

    return 0


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.verbose:
        logging.basicConfig(level=logging.DEBUG, format="%(name)s %(levelname)s %(message)s")
    else:
        logging.basicConfig(level=logging.INFO, format="%(message)s")

    if args.command == "tdd":
        code = asyncio.run(_run_tdd(args))
        sys.exit(code)
    else:
        parser.print_help()
        sys.exit(1)
