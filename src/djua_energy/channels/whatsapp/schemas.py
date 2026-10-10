from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class Text(BaseModel):
    body: str = Field(min_length=1, max_length=4096)


class IncomingMessage(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    sender: str = Field(alias="from", pattern=r"^[0-9]{8,15}$")
    id: str = Field(min_length=1, max_length=512)
    type: str
    text: Text | None = None


class Metadata(BaseModel):
    phone_number_id: str


class Value(BaseModel):
    messaging_product: str | None = None
    metadata: Metadata | None = None
    messages: list[IncomingMessage] = Field(default_factory=list, max_length=100)


class Change(BaseModel):
    field: str
    value: Value


class Entry(BaseModel):
    changes: list[Change] = Field(default_factory=list, max_length=100)


class WebhookPayload(BaseModel):
    object: str
    entry: list[Entry] = Field(default_factory=list, max_length=100)
