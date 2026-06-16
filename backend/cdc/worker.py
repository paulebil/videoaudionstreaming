import asyncio
import json
import logging

from aiokafka import AIOKafkaConsumer

from cdc.consumer import CDCConsumer

logger = logging.getLogger(__name__)


class CDCWorker:
    def __init__(self):
        self.consumer = AIOKafkaConsumer(
            bootstrap_servers="localhost:29092",  
            group_id="cdc-python-consumer",
            auto_offset_reset="earliest",
            value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        )

        self.consumer.subscribe(pattern=r"fastapi_cdc\..*")

        self.cdc = CDCConsumer()

    async def start(self):
        await self.consumer.start()
        logger.info("CDC Worker started and listening to Debezium topics")

        try:
            async for message in self.consumer:
                payload = message.value

                if isinstance(payload, dict) and "payload" in payload:
                    payload = payload["payload"]

                await self.cdc.process(payload)

        except asyncio.CancelledError:
            logger.warning("CDC Worker cancelled")

        finally:
            await self.consumer.stop()
            logger.info("CDC Worker stopped")


async def main():
    worker = CDCWorker()
    await worker.start()


if __name__ == "__main__":
    asyncio.run(main())
