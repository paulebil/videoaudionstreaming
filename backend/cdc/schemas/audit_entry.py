from typing import Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field, field_validator


class AuditEntry(BaseModel):
    """Internal audit record before database persistence"""

    operation: str = Field(..., min_length=1, max_length=1)
    operation_name: str

    table: str = Field(..., min_length=1, max_length=100)
    record_id: Optional[int] = None

    before_state: Optional[dict[str, Any]] = None
    after_state: Optional[dict[str, Any]] = None
    changed_fields: dict[str, Any] = Field(default_factory=dict)

    timestamp: int  

    user_id: Optional[int] = None  
    correlation_id: Optional[str] = None  
    source_ip: Optional[str] = None

    @field_validator("operation")
    def validate_operation(cls, v: str) -> str:
        """Ensure operation is valid"""
        allowed = {"c", "u", "d", "r"}
        if v not in allowed:
            raise ValueError(f"Invalid operation: {v}")
        return v

    @field_validator("operation_name")
    def validate_operation_name(cls, v: str, info) -> str:
        """Ensure operation_name matches operation code"""
        operation = info.data.get("operation")
        expected = {"c": "CREATE", "u": "UPDATE", "d": "DELETE", "r": "SNAPSHOT"}.get(
            operation, "UNKNOWN"
        )

        if v != expected:
            raise ValueError(
                f"operation_name '{v}' doesn't match operation '{operation}' (expected '{expected}')"
            )
        return v

    @field_validator("changed_fields")
    def validate_changed_fields(cls, v: dict, info) -> dict:
        """Ensure changed_fields has proper structure for updates"""
        operation = info.data.get("operation")

        if operation == "u" and not v:
            # For updates, changed_fields should be populated
            # But we'll allow empty if no actual changes
            pass

        for field, change in v.items():
            if not isinstance(change, dict):
                raise ValueError(
                    f"Changed field '{field}' must have dict value with 'from' and 'to'"
                )
            if "from" not in change and "to" not in change:
                raise ValueError(
                    f"Changed field '{field}' must have 'from' and/or 'to' keys"
                )

        return v

    @property
    def timestamp_datetime(self) -> datetime:
        """Get timestamp as datetime object"""
        return datetime.fromtimestamp(self.timestamp / 1000)

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

    def get_summary(self) -> str:
        """Get human-readable summary"""
        return f"{self.operation_name} on {self.table}[id={self.record_id}] at {self.timestamp_datetime}"

    def get_changed_fields_summary(self) -> str:
        """Get summary of what changed"""
        if not self.changed_fields:
            return "No changes"

        changed = []
        for field, change in self.changed_fields.items():
            if "from" in change and "to" in change:
                changed.append(f"{field}: {change['from']} → {change['to']}")
            elif "to" in change:
                changed.append(f"{field}: → {change['to']}")
            elif "from" in change:
                changed.append(f"{field}: {change['from']} → (deleted)")

        return ", ".join(changed)

    def to_json(self) -> dict:
        """Convert to JSON-serializable dict"""
        return self.model_dump(exclude_none=True)

    class Config:
        json_schema_extra = {
            "example": {
                "operation": "u",
                "operation_name": "UPDATE",
                "table": "users",
                "record_id": 123,
                "before_state": {
                    "id": 123,
                    "name": "John",
                    "email": "john@example.com",
                },
                "after_state": {"id": 123, "name": "Jane", "email": "john@example.com"},
                "changed_fields": {"name": {"from": "John", "to": "Jane"}},
                "timestamp": 1700000000000,
                "user_id": 456,
                "correlation_id": "req_abc123",
            }
        }
