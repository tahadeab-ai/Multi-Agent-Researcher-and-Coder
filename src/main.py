"""Interactive CLI entry point for Autonomous Multi-Agent Researcher & Coder."""

import sys
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from src.config import settings
from src.graph import MultiAgentGraph

console = Console()


def display_banner():
    """Prints the application banner."""
    console.print(
        Panel.fit(
            "[bold cyan]🤖 Autonomous Multi-Agent Researcher & Coder[/bold cyan]\n"
            f"[dim]Provider: {settings.llm_provider} | Model: {settings.llm_model} | Sandbox: {settings.workspace_dir}[/dim]",
            border_style="cyan",
        )
    )


def main():
    display_banner()

    if len(sys.argv) > 1:
        prompt = " ".join(sys.argv[1:])
    else:
        console.print("[bold yellow]Enter your feature request or specification:[/bold yellow]")
        prompt = input("> ").strip()

    if not prompt:
        prompt = "Build a thread-safe LRU Cache in Python with TTL expiration and full pytest test coverage."
        console.print(f"[dim]No prompt provided. Defaulting to demonstration task: '{prompt}'[/dim]\n")

    console.print(Panel(f"[bold white]{prompt}[/bold white]", title="🎯 Target Goal", border_style="green"))

    graph = MultiAgentGraph()
    state = graph.run(user_prompt=prompt)

    # Output Summary Table
    table = Table(title="Execution Summary", border_style="cyan")
    table.add_column("Property", style="bold yellow")
    table.add_column("Value", style="white")

    table.add_row("Final Status", f"[bold green]{state.status.upper()}[/bold green]" if state.status == "completed" else f"[bold red]{state.status.upper()}[/bold red]")
    table.add_row("Healing Cycles Used", str(state.healing_cycle))
    if state.latest_test_result:
        table.add_row("Pytest Passed", "Yes" if state.latest_test_result.passed else "No")
        table.add_row("Test Summary", state.latest_test_result.summary[:80] + "...")

    console.print(table)


if __name__ == "__main__":
    main()
