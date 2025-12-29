"""Task Server - Compute job and worker management service.

This module handles:
- Job lifecycle management (create, retrieve, delete)
- Worker capability discovery via MQTT
- Plugin system integration (cl_ml_tools)
- Storage management for compute jobs
- Worker execution for task processing
"""

from __future__ import annotations

from .capability_manager import close_capability_manager, get_capability_manager
from .models import Job, QueueEntry
from .plugins import create_compute_plugin_router
from .schemas import CleanupResult, JobResponse, StorageInfo
from .worker import ComputeWorker

__all__ = [
    "Job",
    "QueueEntry",
    "JobResponse",
    "StorageInfo",
    "CleanupResult",
    "create_compute_plugin_router",
    "get_capability_manager",
    "close_capability_manager",
    "ComputeWorker",
]
