import logging
from time import perf_counter
from uuid import uuid4

from starlette.datastructures import MutableHeaders

logger = logging.getLogger("taskhub.requests")


class RequestLoggingMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        request_id = uuid4().hex
        started = perf_counter()
        status = 500

        async def send_response(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                MutableHeaders(scope=message)["X-Request-ID"] = request_id
            await send(message)

        def fields():
            return {
                "request_id": request_id,
                "method": scope["method"],
                "route": getattr(scope.get("route"), "path", "<unmatched>"),
                "status": status,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
            }

        try:
            await self.app(scope, receive, send_response)
        except Exception:
            logger.exception("Request failed", extra=fields())
            raise
        else:
            logger.log(logging.ERROR if status >= 500 else logging.INFO,
                       "Request completed", extra=fields())
