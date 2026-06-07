import json
from sqlalchemy import text

from utils.database import get_session_factory
from media.models import (
    MediaAsset,
    Thumbnail,
    StreamingManifest,
    MediaRepresentation,
    ProcessingJob,
    OriginalMediaFile,
)

from core.settings import get_settings

settings = get_settings()


class DebeziumService:

    def get_all_models(self):
        return [
            MediaAsset,
            OriginalMediaFile,
            ProcessingJob,
            MediaRepresentation,
            StreamingManifest,
            Thumbnail,
        ]

    def get_table_name(self, model):
        return model.__tablename__

    def get_model_name(self, model):
        module = model.__module__.split(".")[0]
        return f"{module}.{model.__name__}"

    async def setup(
        self,
        publication_name: str,
        replica_identity: str,
        output_file: str,
    ):
        print("Setting up Debezium CDC...")

        models = self.get_all_models()

        tracked = [m for m in models if m.__tablename__ not in ["alembic_version"]]

        session_factory = get_session_factory()

        async with session_factory() as session:

            if replica_identity == "FULL":
                print("Setting REPLICA IDENTITY FULL...")

                for i, model in enumerate(tracked, 1):
                    table = model.__tablename__

                    try:
                        await session.execute(
                            text(f'ALTER TABLE "{table}" REPLICA IDENTITY FULL;')
                        )
                        print(f"  {i}/{len(tracked)} {table}")
                    except Exception as e:
                        print(f"  Failed {table}: {e}")

                await session.commit()

            print(f"Creating publication {publication_name}")

            await session.execute(
                text(f"DROP PUBLICATION IF EXISTS {publication_name};")
            )

            table_list = ", ".join([f'"{m.__tablename__}"' for m in tracked])

            await session.execute(
                text(f"CREATE PUBLICATION {publication_name} FOR TABLE {table_list};")
            )

            await session.commit()

        config = {
            "name": f"{publication_name}-connector",
            "config": {
                "connector.class": "io.debezium.connector.postgresql.PostgresConnector",
                "database.hostname": "postgres",
                "database.port": "5432",
                "database.user": settings.DB_USER,
                "database.password": settings.DB_PASSWORD,
                "database.dbname": settings.DB_NAME,
                "topic.prefix": "fastapi_cdc",
                "plugin.name": "pgoutput",
                "publication.name": publication_name,
                "slot.name": f"{publication_name}_slot",
                "snapshot.mode": "initial",
                "table.include.list": ",".join(
                    [f"public.{m.__tablename__}" for m in tracked]
                ),
                "key.converter": "org.apache.kafka.connect.json.JsonConverter",
                "value.converter": "org.apache.kafka.connect.json.JsonConverter",
                "key.converter.schemas.enable": "false",
                "value.converter.schemas.enable": "false",
                "tombstones.on.delete": "false",
            },
        }

        with open(output_file, "w") as f:
            json.dump(config, f, indent=2)

        print(f"Config saved: {output_file}")

        return config
