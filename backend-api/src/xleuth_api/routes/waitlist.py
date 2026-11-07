"""Public, database-only waitlist. Never expose signup identity or membership."""

from fastapi import APIRouter, Depends, HTTPException, status

from xleuth_api.db import Database
from xleuth_api.dependencies import get_db
from xleuth_api.models.waitlist import WaitlistRequest, WaitlistResponse

router = APIRouter(prefix="/waitlist", tags=["waitlist"])
SUCCESS = WaitlistResponse()


@router.post("", status_code=status.HTTP_201_CREATED, response_model=WaitlistResponse,
             responses={429: {"description": "Rate limited"}, 503: {"description": "Database unavailable"}})
async def join_waitlist(body: WaitlistRequest, db: Database = Depends(get_db)) -> WaitlistResponse:
    if body.website:
        return SUCCESS
    if not db.pool:
        raise HTTPException(status_code=503, detail="Waitlist is temporarily unavailable")
    try:
        await db.add_waitlist_entry(body.email, body.name)
    except Exception as exc:
        # No addresses in errors or INFO logs. A failed insert must never look
        # like a successful signup; the client can safely retry.
        raise HTTPException(status_code=503, detail="Waitlist is temporarily unavailable") from exc
    return SUCCESS
