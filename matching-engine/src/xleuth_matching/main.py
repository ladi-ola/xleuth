"""Uvicorn entry point for the matching engine service.

Loads .env, then builds the FastAPI app (see xleuth_matching.api).
"""

import logging

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from xleuth_matching.api import _env_ready, create_app  # noqa: E402

app = create_app() if _env_ready() else None
if app is None:
    raise SystemExit("matching engine env not configured; check matching-engine/.env")
