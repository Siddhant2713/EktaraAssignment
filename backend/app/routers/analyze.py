from fastapi import APIRouter

from app.routers.sse import sse_response
from app.schemas.analyze import AnalyzeRequest
from app.services.analyzer import analyze

router = APIRouter(prefix="/api")


@router.post("/analyze")
async def analyze_site(body: AnalyzeRequest):
    return sse_response(analyze(str(body.url)))
