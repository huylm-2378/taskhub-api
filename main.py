from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI

from database import engine
from routers import auth, examples, projects, tags, tasks, users
from routers.dependencies import get_current_active_user
from services.tag_cache import close_cache


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        yield
    finally:
        close_cache()
        engine.dispose()


app = FastAPI(
    title="TaskHub API",
    description="Hệ thống Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# Register static /me before the existing dynamic /{user_id} route.
app.include_router(auth.router)
for data_router in (users.router, projects.router, tasks.router, tags.router):
    app.include_router(data_router, dependencies=[Depends(get_current_active_user)])
app.include_router(examples.router)


@app.get("/health", tags=["System"])
async def health_check():
    return {
        "status": "Healthy",
        "message": "TaskHub is up!",
        "version": "1.0.0",
    }
