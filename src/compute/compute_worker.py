"""Compute worker CLI entry point.

This CLI:
- Parses command-line arguments
- Configures logging
- Invokes the ComputeWorker class to execute tasks
"""

from __future__ import annotations

import asyncio
import logging
import sys
from argparse import ArgumentParser, Namespace

from cl_server_shared import Config

from .worker import ComputeWorker

logger = logging.getLogger("compute")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class Args(Namespace):
    worker_id: str = Config.WORKER_ID
    tasks: str | None = None
    log_level: str = Config.LOG_LEVEL

    def __init__(
        self,
        worker_id: str = Config.WORKER_ID,
        tasks: str | None = None,
        log_level: str = Config.LOG_LEVEL,
    ) -> None:
        super().__init__()
        self.worker_id = worker_id
        self.tasks = tasks
        self.log_level = log_level


def main() -> int:
    """CLI entry point for worker."""
    parser = ArgumentParser(
        prog="compute-worker",
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

    args = parser.parse_args(namespace=Args())

    # Parse tasks
    tasks = args.tasks.split(",") if args.tasks else None

    # Print startup info
    print(f"Starting compute worker: {args.worker_id}")
    print(f"Task filter: {tasks or 'all available'}")
    print(f"Log level: {args.log_level}")
    print("Press Ctrl+C to stop\n")

    # Run worker
    try:
        asyncio.run(ComputeWorker.run_worker(args.worker_id, tasks))
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
