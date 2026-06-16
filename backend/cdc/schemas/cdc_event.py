from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, model_validator


class CDCEvent(BaseModel):
    """Normalized CDC event parsed from Debezium."""

    table: str
    operation: str

    record_id: int | None = None

    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None

    timestamp: int

    source_db: str | None = None
    transaction_id: str | None = None

    # future-proofing for Kafka/Debezium offsets
    event_id: str | None = None

    @model_validator(mode="after")
    def validate_operation(self) -> "CDCEvent":
        allowed = {"c", "u", "d", "r"}

        if self.operation not in allowed:
            raise ValueError(
                f"Invalid operation: {self.operation}. " f"Must be one of {allowed}"
            )

        return self

    @model_validator(mode="after")
    def extract_record_id_if_missing(self) -> "CDCEvent":
        if self.record_id is not None:
            return self

        if self.after:
            self.record_id = self.after.get("id")

        elif self.before:
            self.record_id = self.before.get("id")

        return self

    @property
    def is_create(self) -> bool:
        return self.operation == "c"

    @property
    def is_update(self) -> bool:
        return self.operation == "u"

    @property
    def is_delete(self) -> bool:
        return self.operation == "d"

    @property
    def is_snapshot(self) -> bool:
        return self.operation == "r"

    @property
    def operation_name(self) -> str:
        return {
            "c": "CREATE",
            "u": "UPDATE",
            "d": "DELETE",
            "r": "SNAPSHOT",
        }.get(self.operation, "UNKNOWN")

    @property
    def event_datetime(self) -> datetime:
        """Convert Debezium timestamp to UTC datetime."""
        return datetime.fromtimestamp(
            self.timestamp / 1000,
            tz=timezone.utc,
        )

    def has_changes(self) -> bool:
        if not self.is_update:
            return True

        if not self.before or not self.after:
            return True

        return self.before != self.after

    def get_changed_fields(self) -> dict[str, Any]:
        if not self.before or not self.after:
            return {}

        changes = {}

        all_keys = set(self.before.keys()) | set(self.after.keys())

        for key in all_keys:
            old = self.before.get(key)
            new = self.after.get(key)

            if old != new:
                changes[key] = {
                    "from": old,
                    "to": new,
                }

        return changes

    class Config:
        json_schema_extra = {
            "example": {
                "table": "users",
                "operation": "u",
                "record_id": 123,
                "before": {
                    "id": 123,
                    "name": "John",
                },
                "after": {
                    "id": 123,
                    "name": "Jane",
                },
                "timestamp": 1700000000000,
                "source_db": "videoaudionstreaming",
            }
        }
