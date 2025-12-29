"""Compute job management routes."""

from fastapi import APIRouter, Depends, Path, Query, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from .auth import UserPayload, require_admin, require_permission
from .database import get_db
from .schemas import CleanupResult, JobResponse, StorageInfo, WorkerCapabilitiesResponse
from .service import CapabilityService, JobService

router = APIRouter()


@router.get(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Get Job Status",
    description="Get job status and results.",
    operation_id="get_job",
    responses={200: {"model": JobResponse, "description": "Job found"}},
)
async def get_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
) -> JobResponse:
    """Get job status and results."""
    _ = user
    job_service = JobService(db)
    return job_service.get_job(job_id)


@router.delete(
    "/jobs/{job_id}",
    tags=["job"],
    summary="Delete Job",
    description="Delete job and all associated files.",
    operation_id="delete_job",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_job(
    job_id: str = Path(..., title="Job ID"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
):
    """Delete job and all associated files."""
    _ = user
    job_service = JobService(db)
    job_service.delete_job(job_id)
    # No return statement - FastAPI will return 204 automatically


@router.get(
    "/jobs/{job_id}/files/{file_path:path}",
    tags=["job"],
    summary="Download Job Output File",
    description="Download a file from job's output directory using relative path from task_output.",
    operation_id="get_job_file",
    response_class=FileResponse,
)
async def get_job_file(
    job_id: str = Path(..., title="Job ID"),
    file_path: str = Path(..., title="Relative file path within job directory"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_permission("ai_inference_support")),
) -> FileResponse:
    """Download file from job's output directory.

    Args:
        job_id: Job UUID
        file_path: Relative file path from task_output (e.g., "output/thumbnail.jpg")
        db: Database session
        user: Authenticated user

    Returns:
        File content with appropriate Content-Type

    Raises:
        404: Job or file not found
        403: Path traversal attempt detected
        400: Invalid file path or path is a directory
    """
    _ = user
    job_service = JobService(db)
    file_absolute_path = job_service.get_job_file(job_id, file_path)

    # Return file with FileResponse (FastAPI automatically sets Content-Type)
    return FileResponse(
        path=file_absolute_path,
        filename=file_absolute_path.name,
        media_type="application/octet-stream",  # Let browser determine type
    )


@router.get(
    "/admin/jobs/storage/size",
    tags=["admin"],
    summary="Get Storage Size",
    description="Get total storage usage (admin only).",
    operation_id="get_storage_size",
    responses={200: {"model": StorageInfo, "description": "Storage information"}},
)
async def get_storage_size(
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> StorageInfo:
    """Get total storage usage (admin only)."""
    _ = user
    job_service = JobService(db)
    return job_service.get_storage_size()


@router.delete(
    "/admin/jobs/cleanup",
    tags=["admin"],
    summary="Cleanup Old Jobs",
    description="Clean up jobs older than specified number of days (admin only).",
    operation_id="cleanup_old_jobs",
    responses={200: {"model": CleanupResult, "description": "Cleanup results"}},
)
async def cleanup_old_jobs(
    days: int = Query(7, ge=0, description="Delete jobs older than N days"),
    db: Session = Depends(get_db),
    user: UserPayload | None = Depends(require_admin),
) -> CleanupResult:
    """Clean up jobs older than specified number of days (admin only)."""
    _ = user
    job_service = JobService(db)
    return job_service.cleanup_old_jobs(days)


@router.get(
    "/capabilities",
    tags=["compute"],
    summary="Get Worker Capabilities",
    description="Returns available worker capabilities and their available counts",
    response_model=WorkerCapabilitiesResponse,
    operation_id="get_worker_capabilities",
)
async def get_worker_capabilities(
    db: Session = Depends(get_db),
) -> WorkerCapabilitiesResponse:
    """Get available worker capabilities and counts from connected workers.

    Returns a dictionary with:
    - num_workers: Total number of connected workers (0 if none available)
    - capabilities: Dictionary mapping capability names to available worker counts

    Example response:
    {
        "num_workers": 3,
        "capabilities": {
            "image_resize": 2,
            "image_conversion": 1
        }
    }
    """
    _ = db
    capability_service = CapabilityService(db)
    capabilities = capability_service.get_available_capabilities()
    num_workers = capability_service.get_worker_count()
    return WorkerCapabilitiesResponse(
        num_workers=num_workers,
        capabilities=capabilities,
    )
