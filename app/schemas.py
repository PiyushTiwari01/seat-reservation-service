from typing import List

from pydantic import BaseModel, Field


class CreateShowRequest(BaseModel):
    name: str
    seats: List[str] = Field(min_length=1)
    price_paise: int = Field(gt=0)
    per_user_limit: int = Field(default=4, gt=0)


class ReserveRequest(BaseModel):
    seats: List[str] = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)


class CancelResponse(BaseModel):
    reservation_id: str
    status: str
