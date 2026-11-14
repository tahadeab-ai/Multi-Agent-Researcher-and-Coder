"""Interactive CLI entry point for Autonomous Multi-Agent Researcher & Coder."""

from __future__ import annotations

import argparse
import sys

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from src.config import settings
from src.errors import ConfigError
from src.graph import MultiAgentGraph
from src.logging_config import configure_logging

console = Console()


def display_banner() -> None:
    """Prints the application banner."""
    console.print(
        Panel.fit(
            "[bold cyan]🤖 Autonomous Multi-Agent Researcher & Coder[/bold cyan]\n"
            f"[dim]Provider: {settings.llm_provider} | Model: {settings.llm_model} | Sandbox: {settings.workspace_dir}[/dim]",
            border_style="cyan",
        )
    )


def main() -> None:
    configure_logging()
    display_banner()

    parser = argparse.ArgumentParser(
        description="Autonomous Multi-Agent Researcher & Coder CLI"
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help="Run ID to resume from existing state.json",
    )
    parser.add_argument(
        "prompt",
        nargs="*",
        help="Feature specification or prompt",
    )

    args = parser.parse_args()

    resume_state = None
    if args.resume:
        try:
            resume_state = MultiAgentGraph.load_state(args.resume)
            prompt = resume_state.user_prompt
            console.print(f"[bold green]Resuming run {args.resume}...[/bold green]")
        except ConfigError as err:
            console.print(f"[bold red]Resume Error:[/bold red] {err}")
            sys.exit(1)
    elif args.prompt:
        prompt = " ".join(args.prompt)
    else:
        console.print("[bold yellow]Enter your feature request or specification:[/bold yellow]")
        prompt = input("> ").strip()

    if not prompt:
        prompt = (
            "Build a thread-safe LRU Cache in Python with TTL expiration "
            "and full pytest test coverage."
        )
        console.print(
            f"[dim]No prompt provided. Defaulting to demonstration task: '{prompt}'[/dim]\n"
        )

    console.print(
        Panel(
            f"[bold white]{prompt}[/bold white]",
            title="🎯 Target Goal",
            border_style="green",
        )
    )

    try:
        graph = MultiAgentGraph()
        state = graph.run(user_prompt=prompt, resume_state=resume_state)
    except ConfigError as e:
        console.print(f"[bold red]Configuration Error:[/bold red] {e}")
        sys.exit(1)

    # Output Summary Table
    table = Table(title="Execution Summary", border_style="cyan")
    table.add_column("Property", style="bold yellow")
    table.add_column("Value", style="white")

    table.add_row(
        "Final Status",
        (
            f"[bold green]{state.status.upper()}[/bold green]"
            if state.status == "completed"
            else f"[bold red]{state.status.upper()}[/bold red]"
        ),
    )
    if state.run_dir:
        table.add_row("Run Workspace", state.run_dir)
    table.add_row("Healing Cycles Used", str(state.healing_cycle))
    if state.latest_test_result:
        table.add_row("Pytest Passed", "Yes" if state.latest_test_result.passed else "No")
        table.add_row("Test Summary", state.latest_test_result.summary[:80] + "...")
    table.add_row("Total Tokens", str(state.total_tokens))
    cost_str = (
        f"${state.total_cost_usd:.4f}"
        if state.total_cost_usd is not None
        else "N/A (model rate unknown)"
    )
    table.add_row("Estimated Cost", cost_str)
    if state.plan_degraded:
        table.add_row("Plan Status", "[yellow]DEGRADED[/yellow]")

    console.print(table)


if __name__ == "__main__":
    main()
