import json
import logging
import uuid

from fastapi import Request

logger = logging.getLogger("seat-reservation")
logging.basicConfig(level=logging.INFO)


def request_id_from(request: Request) -> str:
    return request.headers.get("X-Request-ID") or str(uuid.uuid4())


def log_event(event: str, request_id: str, **fields):
    payload = {
        "event": event,
        "request_id": request_id,
        **fields,
    }
    logger.info(json.dumps(payload, default=str))
