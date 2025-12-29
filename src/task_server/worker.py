"""Compute worker using cl_ml_tools library for task execution.

This worker:
- Auto-discovers compute plugins from pyproject.toml entry points
- Polls for jobs from the shared database
- Executes tasks in-process using cl_ml_tools.Worker
- Broadcasts worker capabilities via MQTT for service discovery
- Handles graceful shutdown
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import signal
import sys
import time
from types import FrameType
from typing import Any

from cl_ml_tools import Worker, get_broadcaster, shutdown_broadcaster
from cl_server_shared import Config, JobStorageService
from cl_server_shared.shared_db import JobRepositoryService

from .database import SessionLocal

logger = logging.getLogger(__name__)

# Global shutdown event
shutdown_event = asyncio.Event()


def signal_handler(signum: int, _frame: FrameType | None) -> None:
    """Handle shutdown signals (SIGINT, SIGTERM)."""
    logger.info(f"Received signal {signum}, initiating graceful shutdown...")
    shutdown_event.set()


class CapabilityBroadcaster:
    """Manages MQTT broadcasting of worker capabilities for service discovery."""

    def __init__(self, worker_id: str, active_tasks: set[str]):
        """Initialize capability broadcaster.

        Args:
            worker_id: Unique identifier for this worker
            active_tasks: Set of task types this worker can execute
        """
        self.worker_id: str = worker_id
        self.active_tasks: set[str] = active_tasks
        self.is_idle: bool = True
        self.broadcaster: Any = None  # Type from cl_ml_tools (not exported)
        self.topic: str = f"{Config.CAPABILITY_TOPIC_PREFIX}/{worker_id}"

    def init(self):
        """Initialize MQTT broadcaster and set Last Will & Testament."""
        self.broadcaster = get_broadcaster(
            broadcast_type=Config.BROADCAST_TYPE,
            broker=Config.MQTT_BROKER,
            port=Config.MQTT_PORT,
        )

        # Set Last Will & Testament (LWT) - published when worker disconnects
        if self.broadcaster:
            _ = self.broadcaster.set_will(topic=self.topic, payload="", qos=1, retain=True)
            logger.info(f"MQTT broadcaster initialized for worker {self.worker_id}")

    def publish(self):
        """Publish current worker capabilities to MQTT."""
        if not self.broadcaster:
            logger.warning("MQTT broadcaster not initialized, skipping capability publish")
            return

        capabilities_msg = {
            "id": self.worker_id,
            "capabilities": list(self.active_tasks),
            "idle_count": 1 if self.is_idle else 0,
            "timestamp": int(time.time() * 1000),
        }

        payload = json.dumps(capabilities_msg)
        success = self.broadcaster.publish_retained(topic=self.topic, payload=payload, qos=1)

        if success:
            logger.debug(f"Published capabilities: {list(self.active_tasks)}, idle: {self.is_idle}")
        else:
            logger.error(f"Failed to publish capabilities to {self.topic}")

    def clear(self):
        """Clear retained worker capabilities from MQTT (on shutdown)."""
        if not self.broadcaster:
            return

        success = self.broadcaster.clear_retained(self.topic)
        if success:
            logger.info(f"Cleared retained capabilities from {self.topic}")
        else:
            logger.error(f"Failed to clear retained capabilities from {self.topic}")


class ComputeWorker:
    """Compute worker that executes jobs using cl_ml_tools."""

    def __init__(
        self,
        worker_id: str,
        supported_tasks: list[str] | None = None,
        poll_interval: int = Config.WORKER_POLL_INTERVAL,
    ):
        """Initialize compute worker.

        Args:
            worker_id: Unique identifier for this worker
            supported_tasks: List of task types to process (None = all available)
            poll_interval: Seconds to sleep when no jobs available
        """
        self.worker_id: str = worker_id
        self.poll_interval: int = poll_interval

        # Create repository and storage adapters
        self.repository: JobRepositoryService = JobRepositoryService(SessionLocal)
        self.job_storage: JobStorageService = JobStorageService(base_dir=Config.COMPUTE_STORAGE_DIR)

        # Create cl_ml_tools Worker (auto-discovers plugins)
        logger.info("Initializing cl_ml_tools Worker...")
        self.library_worker: Worker = Worker(
            repository=self.repository,
            job_storage=self.job_storage,
        )

        # Determine active task types
        available_tasks = set(self.library_worker.get_supported_task_types())
        requested_tasks = (
            set(supported_tasks)
            if supported_tasks
            else (
                set(Config.WORKER_SUPPORTED_TASKS)
                if Config.WORKER_SUPPORTED_TASKS
                else available_tasks
            )
        )

        # Active tasks = intersection of requested and available
        self.active_tasks: set[str] = available_tasks & requested_tasks

        # Log initialization details
        logger.info(f"Worker {worker_id} initialized")
        logger.info(f"  Requested tasks: {sorted(requested_tasks)}")
        logger.info(f"  Available plugins: {sorted(available_tasks)}")
        logger.info(f"  Active tasks: {sorted(self.active_tasks)}")

        # Validate we have tasks to process
        if not self.active_tasks:
            if requested_tasks and not available_tasks:
                raise RuntimeError(
                    "No compute plugins found! Ensure cl_ml_tools is installed with "
                    "task plugins registered in pyproject.toml"
                )
            elif requested_tasks and available_tasks:
                raise RuntimeError(
                    f"No matching plugins found. Requested: {sorted(requested_tasks)}, "
                    f"Available: {sorted(available_tasks)}"
                )
            else:
                raise RuntimeError("No task types specified")

        # Initialize capability broadcaster
        self.capability_broadcaster: CapabilityBroadcaster = CapabilityBroadcaster(
            worker_id=worker_id, active_tasks=self.active_tasks
        )

    async def _heartbeat_task(self):
        """Background task to periodically publish worker capabilities."""
        logger.info(f"Heartbeat task started (interval: {Config.MQTT_HEARTBEAT_INTERVAL}s)")
        try:
            while not shutdown_event.is_set():
                await asyncio.sleep(Config.MQTT_HEARTBEAT_INTERVAL)
                if not shutdown_event.is_set():
                    self.capability_broadcaster.publish()
        except asyncio.CancelledError:
            logger.debug("Heartbeat task cancelled")
        except Exception as e:
            logger.error(f"Error in heartbeat task: {e}", exc_info=True)

    async def _process_next_job(self) -> bool:
        """Process one job using cl_ml_tools Worker.

        Returns:
            True if a job was processed, False if no jobs available
        """
        # Mark as busy and publish
        self.capability_broadcaster.is_idle = False
        self.capability_broadcaster.publish()

        try:
            # Use library worker to fetch and process one job
            task_types = list(self.active_tasks)
            processed = await self.library_worker.run_once(task_types=task_types)

            if processed:
                logger.info("Job processed successfully")
                return True
            else:
                logger.debug("No jobs available")
                return False

        except Exception as e:
            logger.exception(f"Error processing job: {e}")
            return False
        finally:
            # Mark as idle and publish
            self.capability_broadcaster.is_idle = True
            self.capability_broadcaster.publish()

    async def run(self):
        """Main worker loop - poll for jobs and execute them."""
        logger.info(f"Worker {self.worker_id} starting...")

        # Initialize capability broadcaster
        self.capability_broadcaster.init()

        # Publish initial capabilities
        self.capability_broadcaster.publish()

        # Start heartbeat task
        heartbeat_task = asyncio.create_task(self._heartbeat_task())

        try:
            while not shutdown_event.is_set():
                try:
                    processed = await self._process_next_job()
                    if not processed:
                        # No job found, sleep before polling again
                        await asyncio.sleep(self.poll_interval)
                except asyncio.CancelledError:
                    logger.info("Worker cancelled")
                    break
                except Exception as e:
                    logger.exception(f"Error in worker loop: {e}")
                    await asyncio.sleep(self.poll_interval)
        finally:
            logger.info(f"Worker {self.worker_id} shutting down...")

            # Cancel heartbeat task first to prevent race conditions
            _ = heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

            # Clear retained capability message
            self.capability_broadcaster.clear()


async def run_worker(worker_id: str, tasks: list[str] | None):
    """Run worker with given configuration.

    Args:
        worker_id: Unique worker identifier
        tasks: List of task types to process (None = all available)
    """
    # Register signal handlers for graceful shutdown
    _ = signal.signal(signal.SIGINT, signal_handler)
    _ = signal.signal(signal.SIGTERM, signal_handler)

    worker = ComputeWorker(
        worker_id=worker_id,
        supported_tasks=tasks,
    )

    try:
        await worker.run()
    finally:
        # Shutdown broadcaster
        shutdown_broadcaster()


def main() -> int:
    """CLI entry point for worker."""
    parser = argparse.ArgumentParser(
        prog="task-worker",
        description="Compute worker for task execution",
    )
    _ = parser.add_argument(
        "--worker-id",
        "-w",
        default=Config.WORKER_ID,
        help=f"Unique worker identifier (default: {Config.WORKER_ID})",
    )
    _ = parser.add_argument(
        "--tasks",
        "-t",
        default=None,
        help="Comma-separated list of task types to process (default: all available)",
    )
    _ = parser.add_argument(
        "--log-level",
        "-l",
        default=Config.LOG_LEVEL,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help=f"Logging level (default: {Config.LOG_LEVEL})",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
    logger.setLevel(getattr(logging, args.log_level))

    # Parse tasks
    tasks = args.tasks.split(",") if args.tasks else None

    # Print startup info
    print(f"Starting compute worker: {args.worker_id}")
    print(f"Task filter: {tasks or 'all available'}")
    print(f"Log level: {args.log_level}")
    print("Press Ctrl+C to stop\n")

    # Run worker
    try:
        asyncio.run(run_worker(args.worker_id, tasks))
        return 0
    except KeyboardInterrupt:
        logger.info("Worker stopped by user")
        return 0
    except Exception as e:
        logger.error(f"Worker failed: {e}", exc_info=True)
        print(f"\nERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
