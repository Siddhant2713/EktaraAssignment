from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel


class ErrorCode(str, Enum):
    CONFIG_MISSING = "CONFIG_MISSING"
    INVALID_URL = "INVALID_URL"
    SITE_UNREACHABLE = "SITE_UNREACHABLE"
    SITE_BLOCKED = "SITE_BLOCKED"
    NO_CONTENT = "NO_CONTENT"
    LLM_FAILED = "LLM_FAILED"
    SEARCH_FAILED = "SEARCH_FAILED"
    TIMEOUT = "TIMEOUT"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    step: str
    message: str


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    data: dict[str, Any]


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    step: str
    code: ErrorCode
    message: str


Event = ProgressEvent | ResultEvent | ErrorEvent
