"""Disabled Dynamic waitlist sync integration point.

Dynamic's published API does not provide a documented pre-registration
waitlist-contact endpoint. Do not create users or call a CRM service as a
substitute. Postgres remains the source of truth and entries remain pending
until a supported endpoint and backend-only credentials are approved.
"""


async def sync_pending_entries() -> int:
    """No-op until a supported Dynamic waitlist API is available."""
    return 0
