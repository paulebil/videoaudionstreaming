from schemas.cdc_event import CDCEvent


def parse_message(msg: dict) -> CDCEvent:
    return CDCEvent(
        table=msg["source"]["table"],
        operation=msg["op"],
        before=msg.get("before"),
        after=msg.get("after"),
        timestamp=msg["ts_ms"],
    )
