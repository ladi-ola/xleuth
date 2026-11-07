"""Public waitlist payloads. Never return submitted personal data."""

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


class WaitlistRequest(BaseModel):
    name: str
    email: str
    website: str = Field(default="", max_length=255)  # Hidden honeypot.

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Enter a valid name")
        value = " ".join(value.split())
        if not 1 <= len(value) <= 100 or "<" in value or ">" in value:
            raise ValueError("Enter a name of up to 100 characters without markup")
        return value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Enter a valid email address")
        value = value.strip().lower()
        if len(value) > 255 or not EMAIL_RE.fullmatch(value):
            raise ValueError("Enter a valid email address")
        return value


class WaitlistResponse(BaseModel):
    status: Literal["ok"] = "ok"
