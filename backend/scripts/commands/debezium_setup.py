import asyncio
import typer

from scripts.services.debezium import DebeziumService
from core.settings import get_settings


settings = get_settings()

debezium_app = typer.Typer(help="Debezium CDC management")


@debezium_app.command("setup")
def setup(
    publication: str = typer.Option("fastapi_debezium_pub"),
    replica_identity: str = typer.Option("FULL"),
    output: str = typer.Option("debezium_config.json"),
):
    async def runner():
        service = DebeziumService()

        await service.setup(
            publication_name=publication,
            replica_identity=replica_identity,
            output_file=output,
            settings=settings,
        )

    asyncio.run(runner())
