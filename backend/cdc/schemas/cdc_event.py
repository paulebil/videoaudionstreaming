from pydantic import BaseModel


class CDCEvent(BaseModel):
    table: str
    operation: str
    before: dict | None
    after: dict | None
    timestamp: int
