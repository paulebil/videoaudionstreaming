import logging
from typing import Any, Optional
from datetime import datetime

from cdc.schemas.cdc_event import CDCEvent

logger = logging.getLogger(__name__)


def extract_record_id(
    before: Optional[dict[str, Any]],
    after: Optional[dict[str, Any]],
    primary_key_field: str = "id",
) -> Optional[int]:
    """
    Extract record ID from before/after states.

    Args:
        before: State before the operation
        after: State after the operation
        primary_key_field: Name of the primary key field (default "id")

    Returns:
        Record ID if found, None otherwise
    """
    if after and primary_key_field in after:
        value = after.get(primary_key_field)
        if value is not None:
            return int(value) if isinstance(value, (int, str)) else None

    if before and primary_key_field in before:
        value = before.get(primary_key_field)
        if value is not None:
            return int(value) if isinstance(value, (int, str)) else None

    return None


def extract_table_name(payload: dict) -> str:
    """Extract table name from Debezium payload with fallbacks"""
    if "source" in payload and "table" in payload["source"]:
        return payload["source"]["table"]

    if "table" in payload:
        return payload["table"]

    raise ValueError("Cannot extract table name from payload")


def extract_operation(payload: dict) -> str:
    """Extract and validate operation type"""
    op = payload.get("op", "").lower()

    operation_map = {
        "c": "c",  
        "u": "u",  
        "d": "d", 
        "r": "r",  
        "create": "c",
        "update": "u",
        "delete": "d",
        "read": "r",
    }

    if op not in operation_map:
        logger.warning(f"Unknown operation type: {op}, defaulting to 'u'")
        return "u"

    return operation_map[op]


def extract_timestamp(payload: dict) -> int:
    """Extract timestamp in milliseconds"""
    if "ts_ms" in payload and payload["ts_ms"] is not None:
        return payload["ts_ms"]

    if "timestamp" in payload and payload["timestamp"] is not None:
        return payload["timestamp"]

    logger.warning("No timestamp found in payload, using current time")
    return int(datetime.now().timestamp() * 1000)


def extract_source_db(payload: dict) -> Optional[str]:
    """Extract source database name if available"""
    if "source" in payload:
        return payload["source"].get("db")
    return None


def extract_transaction_id(payload: dict) -> Optional[str]:
    """Extract transaction ID for correlation"""
    if "source" in payload:
        tx_id = payload["source"].get("txId")

        if tx_id is None:
            return None

        return str(tx_id)  

    return None


def validate_payload(payload: dict) -> bool:
    """Validate that payload has required fields"""
    required_fields = ["op"]
    for field in required_fields:
        if field not in payload:
            logger.error(f"Missing required field in payload: {field}")
            return False

    if "source" not in payload or "table" not in payload.get("source", {}):
        if "table" not in payload:
            logger.error(
                "Payload missing table information (source.table or table field)"
            )
            return False

    return True


def parse_message(payload: dict) -> CDCEvent:
    """
    Parse a raw Debezium message into a CDCEvent.

    Args:
        payload: Raw Debezium message payload

    Returns:
        CDCEvent object

    Raises:
        ValueError: If payload is invalid or missing required fields
    """
    if not validate_payload(payload):
        raise ValueError("Invalid Debezium payload structure")

    try:
        before = payload.get("before")
        after = payload.get("after")

        before = before if before not in (None, "null") else None
        after = after if after not in (None, "null") else None

        table = extract_table_name(payload)
        operation = extract_operation(payload)
        record_id = extract_record_id(before, after)
        timestamp = extract_timestamp(payload)
        source_db = extract_source_db(payload)
        transaction_id = extract_transaction_id(payload)

        logger.debug(
            f"Parsed CDC event: {operation} on {table}[id={record_id}] "
            f"at {datetime.fromtimestamp(timestamp/1000)}"
        )

        return CDCEvent(
            table=table,
            operation=operation,
            record_id=record_id,
            before=before,
            after=after,
            timestamp=timestamp,
            source_db=source_db,
            transaction_id=transaction_id,
        )

    except KeyError as e:
        logger.error(f"Missing expected field in payload: {e}")
        raise ValueError(f"Invalid payload structure: missing {e}")
    except Exception as e:
        logger.exception(f"Unexpected error parsing message: {e}")
        raise


def parse_messages(payloads: list[dict]) -> list[CDCEvent]:
    """Parse multiple messages in batch"""
    events = []
    for payload in payloads:
        try:
            event = parse_message(payload)
            events.append(event)
        except Exception as e:
            logger.error(f"Failed to parse message: {e}")
            continue
    return events


def parse_debezium_envelope(envelope: dict) -> CDCEvent:
    """
    Parse a full Debezium envelope (including schema info).

    Debezium often sends messages with schema and payload:
    {
        "schema": {...},
        "payload": {...}
    }
    """
    if "payload" in envelope:
        return parse_message(envelope["payload"])
    return parse_message(envelope)
