from fastapi import APIRouter

from app.routers.sse import sse_response
from app.schemas.draft import DraftRequest
from app.services.draft_pipeline import draft

router = APIRouter(prefix="/api")


@router.post("/draft")
async def draft_openers(body: DraftRequest):
    return sse_response(draft(body))
