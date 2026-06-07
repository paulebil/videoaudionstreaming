import typer
import asyncio

from scripts.commands import db_triggers, debezium_setup
from scripts.services.debezium import DebeziumService
from scripts.commands.db_triggers import DbTriggers

app = typer.Typer(
    help="Database and system management CLI",
    no_args_is_help=True,
)


app.add_typer(
    db_triggers.trigger_app,
    name="triggers",
    help="Database trigger management",
)

app.add_typer(
    debezium_setup.debezium_app,
    name="debezium",
    help="Debezium CDC management",
)


@app.command()
def run_all(
    publication: str = "fastapi_debezium_pub",
    output: str = "debezium_config.json",
):
    """
    Run full system setup.
    """

    async def runner():
        print("Running full system bootstrap...\n")

        print("1. Installing DB triggers...")
        await DbTriggers().install()

        print("\n2. Setting up Debezium CDC...")
        service = DebeziumService()

        await service.setup(
            publication_name=publication,
            replica_identity="FULL",
            output_file=output,
        )

        print("\nSystem bootstrap complete!")

    asyncio.run(runner())


@app.command()
def hello():
    typer.echo("Hello from VideoAudioStreaming CLI!")


if __name__ == "__main__":
    app()
