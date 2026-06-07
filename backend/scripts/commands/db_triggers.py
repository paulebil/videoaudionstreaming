import asyncio
import typer
from sqlalchemy import text

from scripts.commons.base import BaseCommand
from scripts.commons.utils import get_session

from media.models import (
    MediaAsset,
    OriginalMediaFile,
    ProcessingJob,
    MediaRepresentation,
    StreamingManifest,
    Thumbnail,
)

trigger_app = typer.Typer(help="Database trigger management")


def get_models_with_logic():
    return [
        MediaAsset,
        OriginalMediaFile,
        ProcessingJob,
        MediaRepresentation,
        StreamingManifest,
        Thumbnail,
    ]


class DbTriggers(BaseCommand):

    def __init__(self):
        self.models = get_models_with_logic()

    async def execute_sql_safe(self, session, sql_list, description: str):
        for i, sql in enumerate(sql_list, start=1):
            try:
                await session.execute(text(sql))
            except Exception as e:
                self.print_error(f"[ERROR] Step {i} failed: {e}")
                await session.rollback()
                return False

        self.print_success(f"[OK] {description}")
        return True

    async def install(self):
        if not self.models:
            self.print_warning("No models with logic found.")
            return

        self.print_info(f"Installing database logic for {len(self.models)} model(s)...")

        async with get_session() as session:
            for model in self.models:
                self.print_info(f"Processing {model.__name__}...")

                if hasattr(model, "get_slug_trigger_sql_parts"):
                    sql_parts = model.get_slug_trigger_sql_parts()
                    if sql_parts:
                        await self.execute_sql_safe(
                            session,
                            sql_parts,
                            "Slug trigger installed",
                        )

                if hasattr(model, "get_fts_trigger_sql_parts"):
                    sql_parts = model.get_fts_trigger_sql_parts()
                    if sql_parts:
                        await self.execute_sql_safe(
                            session,
                            sql_parts,
                            "FTS trigger installed",
                        )

            await session.commit()
            self.print_success("Database logic installation complete!")


@trigger_app.command("install")
def install_triggers():
    """
    Install all database triggers.
    """
    asyncio.run(DbTriggers().install())
