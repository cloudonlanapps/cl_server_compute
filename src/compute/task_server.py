"""Task Server - Compute job and worker management service."""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .plugins import create_compute_plugin_router
from .routes import router

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan event handler for startup and shutdown."""
    _ = app
    # Startup: nothing to do currently
    yield
    # Shutdown: cleanup capability manager
    from .capability_manager import close_capability_manager

    close_capability_manager()


app = FastAPI(title="Task Server", version="v1", lifespan=lifespan)

# Include job management routes
app.include_router(router)

# Create and include plugin router for compute tasks
plugin_router, repository_adapter = create_compute_plugin_router()
app.include_router(plugin_router)


@app.exception_handler(HTTPException)
async def validation_exception_handler(_request: Request, exc: HTTPException):
    """
    Preserve the default FastAPI HTTPException handling shape so callers
    can rely on the same error response structure.
    """
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )


class RootResponse(BaseModel):
    status: str
    service: str
    version: str


@app.get(
    "/",
    summary="Health Check",
    description="Returns service health status",
    response_model=RootResponse,
    operation_id="root_get",
)
async def root():
    return RootResponse(status="healthy", service="Task Server", version="v1")
