from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import CORS_ORIGINS, LOG_LEVEL
from database import engine
from logging_setup import configure_logging
from middleware import RequestLoggingMiddleware
from routers import auth, examples, jobs, projects, tags, tasks, users
from routers.dependencies import get_current_active_user
from services.tag_cache import close_cache

configure_logging(LOG_LEVEL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        close_cache()
        engine.dispose()


api = FastAPI(
    title="TaskHub API",
    description="Hệ thống Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# Register static /me before the existing dynamic /{user_id} route.
api.include_router(auth.router)
for data_router in (users.router, projects.router, tasks.router, tags.router, jobs.router):
    api.include_router(data_router, dependencies=[Depends(get_current_active_user)])
api.include_router(examples.router)


@api.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "Healthy",
        "message": "TaskHub is up!",
        "version": "1.0.0",
    }


# Wrap the entire API so even unhandled 500 responses carry CORS and request IDs.
# `api` remains available for route registration and dependency overrides.
app = RequestLoggingMiddleware(CORSMiddleware(
    api,
    allow_origins=CORS_ORIGINS,
    allow_credentials=False,  # Authentication uses explicit Bearer tokens, not cookies.
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
))
