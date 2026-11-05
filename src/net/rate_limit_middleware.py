from fastapi import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from net.rate_limit import RateLimiter, RateLimitGroup, client_host
from net.utils.rest_error import handle_rest_exception, rate_limited_error


class RateLimitMiddleware:
    """A ceiling on all HTTP requests from an IP, whatever they ask for and whether or not they make it to a route"""

    def __init__(self, app: ASGIApp, limiter: RateLimiter) -> None:
        self.app = app
        self.limiter = limiter

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        retry_after_secs = self.limiter.take(RateLimitGroup.HTTP_BY_IP, client_host(request.client))
        if retry_after_secs is None:
            await self.app(scope, receive, send)
            return

        response = await handle_rest_exception(request, rate_limited_error(retry_after_secs))
        await response(scope, receive, send)
