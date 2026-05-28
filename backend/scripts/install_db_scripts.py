import asyncio
import sys
import os
import typer
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.database import get_session_factory


app = typer.Typer(help="Install database triggers and functions")


def get_models_with_logic():
    return []


async def execute_sql_safe(session, sql_list, description):
    """
    Executes a list of SQL statements one by one to avoid
    asyncpg 'multiple commands' error.
    """
    for i, sql in enumerate(sql_list):
        try:
            await session.execute(text(sql))
        except Exception as e:
            typer.echo(f"   [ERROR] Step {i + 1} failed: {e}")
            await session.rollback()
            return False

    typer.echo(f"   [OK] {description}")
    return True


async def install_triggers_async():
    models = get_models_with_logic()

    if not models:
        typer.echo("No models with logic found.")
        return

    typer.echo(f"Installing database logic for {len(models)} model(s)...")

    session_factory = get_session_factory()

    async with session_factory() as session:
        for model in models:
            model_name = model.__name__
            typer.echo(f"\nProcessing {model_name}...")

            if hasattr(model, "get_slug_trigger_sql_parts"):
                sql_parts = model.get_slug_trigger_sql_parts()
                if sql_parts:
                    await execute_sql_safe(
                        session,
                        sql_parts,
                        "Slug trigger installed",
                    )

            if hasattr(model, "get_fts_trigger_sql_parts"):
                sql_parts = model.get_fts_trigger_sql_parts()
                if sql_parts:
                    await execute_sql_safe(
                        session,
                        sql_parts,
                        "FTS trigger installed",
                    )

        await session.commit()
        typer.echo("\nDatabase logic installation complete!")


@app.command()
def install():
    """
    Installs or updates all database triggers.
    Usage: python scripts/install_db_logic.py install
    """
    asyncio.run(install_triggers_async())


if __name__ == "__main__":
    app()
