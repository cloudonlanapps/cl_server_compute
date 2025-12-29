"""Utility functions for compute service."""

import os
import socket
import sys
from pathlib import Path


def ensure_cl_server_dir() -> Path:
    """Ensure CL_SERVER_DIR exists and is writable.

    Creates the directory if it doesn't exist.

    Returns:
        Path to CL_SERVER_DIR

    Raises:
        SystemExit: If directory cannot be created or is not writable
    """
    cl_server_dir = os.getenv("CL_SERVER_DIR")

    if not cl_server_dir:
        print(
            "ERROR: CL_SERVER_DIR environment variable is not set.\n"
            "Please set it to a valid directory path.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    dir_path = Path(cl_server_dir)

    # Try to create directory if it doesn't exist
    if not dir_path.exists():
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
            print(f"Created CL_SERVER_DIR: {dir_path}")
        except (OSError, PermissionError) as e:
            print(
                f"ERROR: Failed to create CL_SERVER_DIR: {dir_path}\n"
                f"Reason: {e}\n"
                "Please ensure the parent directory exists and you have write permissions.",
                file=sys.stderr,
            )
            raise SystemExit(1)

    # Check if directory is writable
    if not os.access(dir_path, os.W_OK):
        print(
            f"ERROR: CL_SERVER_DIR exists but is not writable: {dir_path}\n"
            "Please ensure you have write permissions.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return dir_path


def validate_cl_server_dir_exists() -> Path:
    """Validate that CL_SERVER_DIR exists and is accessible.

    This is used by worker to ensure the server has set up the directory.
    Does NOT create the directory - expects server to have created it.

    Returns:
        Path to CL_SERVER_DIR

    Raises:
        SystemExit: If directory doesn't exist or is not accessible
    """
    cl_server_dir = os.getenv("CL_SERVER_DIR")

    if not cl_server_dir:
        print(
            "ERROR: CL_SERVER_DIR environment variable is not set.\n"
            "Please set it to a valid directory path.\n"
            "Ensure the compute server is running or has been run at least once.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    dir_path = Path(cl_server_dir)

    # Check if directory exists
    if not dir_path.exists():
        print(
            f"ERROR: CL_SERVER_DIR does not exist: {dir_path}\n"
            "Please ensure:\n"
            "  1. The compute server has been started at least once, OR\n"
            "  2. The directory has been created manually\n"
            f"Run: mkdir -p {dir_path}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Check if it's a directory
    if not dir_path.is_dir():
        print(
            f"ERROR: CL_SERVER_DIR is not a directory: {dir_path}\n"
            "Please ensure CL_SERVER_DIR points to a directory, not a file.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    # Check if directory is accessible
    if not os.access(dir_path, os.R_OK | os.W_OK):
        print(
            f"ERROR: CL_SERVER_DIR exists but is not accessible: {dir_path}\n"
            "Please ensure you have read and write permissions.",
            file=sys.stderr,
        )
        raise SystemExit(1)

    return dir_path


def check_server_running(host: str, port: int, timeout: float = 2.0) -> bool:
    """Check if compute server is running on the specified host and port.

    Args:
        host: Server hostname or IP address
        port: Server port number
        timeout: Connection timeout in seconds

    Returns:
        True if server is reachable, False otherwise
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        result = sock.connect_ex((host, port))
        sock.close()
        return result == 0
    except (socket.gaierror, socket.timeout, OSError):
        return False


def ensure_server_running(host: str, port: int) -> None:
    """Ensure compute server is running, or exit with error.

    This is used by worker to ensure the server is running before starting.

    Args:
        host: Server hostname or IP address
        port: Server port number

    Raises:
        SystemExit: If server is not reachable
    """
    if not check_server_running(host, port):
        print(
            f"ERROR: Compute server is not running at {host}:{port}\n"
            f"Please ensure:\n"
            f"  1. The compute server is started, OR\n"
            f"  2. The server host/port are correct\n"
            f"Start server with: uv run compute-server --port {port}",
            file=sys.stderr,
        )
        raise SystemExit(1)
