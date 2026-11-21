from app.schemas.events import ErrorCode


class PipelineError(Exception):
    """A failure the user should see, tagged with the pipeline step and an ErrorCode."""

    def __init__(self, step: str, code: ErrorCode, message: str):
        super().__init__(message)
        self.step = step
        self.code = code
        self.message = message
