# src/compute/compute_server.py
from __future__ import annotations

import logging
import os
import sys
from argparse import ArgumentParser, Namespace

logger = logging.getLogger("compute")
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")


class Args(Namespace):
    host: str
    port: int
    debug: bool
    reload: bool
    log_level: str
    no_auth: bool

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8002,
        debug: bool = False,
        reload: bool = False,
        log_level: str = "info",
        no_auth: bool = False,
    ) -> None:
        super().__init__()
        self.host = host
        self.port = port
        self.debug = debug
        self.reload = reload
        self.log_level = log_level
        self.no_auth = no_auth


def main() -> int:
    parser = ArgumentParser(prog="compute-server")
    _ = parser.add_argument("--no-auth", action="store_true", help="Disable authentication")
    _ = parser.add_argument("--port", "-p", type=int, default=int(os.getenv("PORT", "8002")))
    _ = parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    _ = parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload (dev)")
    args = parser.parse_args(namespace=Args())

    # Ensure CL_SERVER_DIR exists and is writable (creates if needed)
    # This MUST happen before importing anything that uses Config
    from .utils import ensure_cl_server_dir
    _ = ensure_cl_server_dir()

    # Set env vars expected by your app
    if args.no_auth:
        os.environ["AUTH_DISABLED"] = "true"
    _ = os.environ.setdefault("CL_SERVER_DIR", os.getenv("CL_SERVER_DIR", ""))

    # Import uvicorn here after directory is set up
    import uvicorn

    # Start server (blocks)
    try:
        # Pass app as import string for reload to work
        uvicorn.run(
            "compute.task_server:app",
            host=args.host,
            port=args.port,
            reload=args.reload,
            log_level=args.log_level,
        )
    except Exception as exc:
        print(f"Error starting service: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
