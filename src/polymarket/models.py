from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Position(BaseModel):
    asset: str = ""
    condition_id: str = Field("", alias="conditionId")
    market_slug: str = Field("", alias="marketSlug")
    title: str = ""
    outcome: str = ""
    size: float = 0.0
    current_value: float = Field(0.0, alias="currentValue")
    initial_value: float = Field(0.0, alias="initialValue")
    price_paid_cents: float = Field(0.0, alias="pricePaidCents")
    cur_price: float = Field(0.0, alias="curPrice")
    cashout_price: float = Field(0.0, alias="cashoutPrice")
    profit_loss_cents: float = Field(0.0, alias="profitLossCents")
    token_id: str = Field("", alias="asset")
    event_slug: str = Field("", alias="eventSlug")
    event_title: str = Field("", alias="eventTitle")

    model_config = {"populate_by_name": True}


class Market(BaseModel):
    condition_id: str = Field("", alias="condition_id")
    question: str = ""
    slug: str = ""
    outcome_prices: str = Field("", alias="outcomePrices")
    tokens: list[dict] = []
    active: bool = True

    model_config = {"populate_by_name": True}


class Activity(BaseModel):
    id: str = ""
    type: str = ""
    side: str = ""
    title: str = ""
    outcome: str = ""
    slug: str = ""
    event_slug: str = Field("", alias="eventSlug")
    event_title: str = Field("", alias="eventTitle")
    tokens: float = Field(0.0, alias="size")
    cash: float = Field(0.0, alias="usdcSize")
    price: float = 0.0
    timestamp: str = ""
    transaction_hash: str = Field("", alias="transactionHash")
    condition_id: str = Field("", alias="conditionId")

    model_config = {"populate_by_name": True}

    @field_validator("timestamp", mode="before")
    @classmethod
    def coerce_timestamp(cls, v: object) -> str:
        return str(v)


class PriceInfo(BaseModel):
    price: float = 0.0
    side: str = ""
