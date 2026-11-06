"""Public, database-only waitlist. Never expose signup identity or membership."""

import re

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from xleuth_api.db import Database
from xleuth_api.dependencies import get_db

router = APIRouter(prefix="/waitlist", tags=["waitlist"])
EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
SUCCESS = {"message": "Thanks for your interest in Xleuth."}


class WaitlistRequest(BaseModel):
    name: str = Field(max_length=120)
    email: str = Field(max_length=255)
    consent: bool
    website: str = Field(default="", max_length=255)  # Honeypot; hidden from people.

    @field_validator("name", mode="before")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        if not isinstance(value, str):
            raise ValueError("Enter a valid name")
        value = " ".join(value.split())
        if not value or len(value) > 120 or "<" in value or ">" in value:
            raise ValueError("Enter a name (up to 120 characters, without markup)")
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


@router.post("", responses={429: {"description": "Rate limited"}, 503: {"description": "Database unavailable"}})
async def join_waitlist(body: WaitlistRequest, db: Database = Depends(get_db)) -> dict[str, str]:
    if not body.consent:
        raise HTTPException(status_code=422, detail="Consent is required")
    if body.website:
        return SUCCESS
    if not db.pool:
        raise HTTPException(status_code=503, detail="Waitlist is temporarily unavailable")
    await db.add_waitlist_entry(body.email, body.name)
    return SUCCESS
