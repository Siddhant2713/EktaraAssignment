from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.schemas.analyze import AnalyzeRequest
from app.services.analyzer import Event, analyze

router = APIRouter(prefix="/api")


def to_sse(event: Event) -> str:
    return f"data: {event.model_dump_json()}\n\n"


@router.post("/analyze")
async def analyze_site(body: AnalyzeRequest):
    async def stream():
        async for event in analyze(str(body.url)):
            yield to_sse(event)

    return StreamingResponse(
        stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
