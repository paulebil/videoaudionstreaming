from abc import ABC
from typing import Any, Dict, List

import typer


class BaseCommand(ABC):
    """Base class for all CLI commands."""

    def print_success(self, message: str) -> None:
        typer.echo(typer.style(message, fg=typer.colors.GREEN))

    def print_error(self, message: str) -> None:
        typer.echo(typer.style(message, fg=typer.colors.RED))

    def print_warning(self, message: str) -> None:
        typer.echo(typer.style(message, fg=typer.colors.YELLOW))

    def print_info(self, message: str) -> None:
        typer.echo(typer.style(message, fg=typer.colors.CYAN))

    def print_status(self, name: str, exists: bool) -> None:
        status = "Exists" if exists else "Missing"
        color = typer.colors.GREEN if exists else typer.colors.RED

        typer.echo(
            typer.style(
                f"{name}: {status}",
                fg=color,
            )
        )

    def print_summary(self, data: Dict[str, Any]) -> None:
        typer.echo("\n" + "=" * 60)
        typer.echo(
            typer.style(
                "Summary",
                fg=typer.colors.MAGENTA,
                bold=True,
            )
        )
        typer.echo("=" * 60)

        for key, value in data.items():
            typer.echo(f"{key}: {value}")

        typer.echo("=" * 60)

    def print_next_steps(self, steps: List[str]) -> None:
        typer.echo("\nNext Steps")

        for index, step in enumerate(steps, start=1):
            typer.echo(
                typer.style(
                    f"  {index}. {step}",
                    fg=typer.colors.YELLOW,
                )
            )
