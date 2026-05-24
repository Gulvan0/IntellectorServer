import logging
import traceback

from fastapi import Request
from fastapi.responses import JSONResponse, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint


class CatchExceptionsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            detail = str(exc)
            logging.critical(detail)
            logging.critical(traceback.format_exc())
            return JSONResponse(content={"detail": detail}, status_code=500)
