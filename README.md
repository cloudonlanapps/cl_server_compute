# Compute

Task and compute job management microservice for the CL Server platform.

## Overview

Compute provides REST API endpoints for:
- Job lifecycle management (retrieve, delete)
- Worker capability discovery
- Compute task execution via plugin system
- Job storage management

## Quick Start

### Installation

```bash
# Install dependencies
uv sync

# Or install with development dependencies
uv sync --all-extras
```

### Database Setup

Initialize the database with Alembic migrations:

```bash
# Create the versions directory (if it doesn't exist)
mkdir -p alembic/versions

# Apply database migrations
uv run alembic upgrade head

# Optional: Check current migration version
uv run alembic current
```

**Note:** The `alembic/versions` directory must exist before running migrations. If you need to create a new migration after schema changes:

```bash
# Generate a new migration
uv run alembic revision --autogenerate -m "description of changes"

# Apply the new migration
uv run alembic upgrade head
```

### Running the Server

```bash
# Run with default settings (port 8002)
uv run compute-server

# Run with custom port
uv run compute-server --port 8003

# Run with auto-reload for development
uv run compute-server --reload

# Disable authentication (dev/testing only)
uv run compute-server --no-auth
```

### Running the Worker

The worker executes compute tasks by polling the job queue and processing them using registered plugins.

**Important:** The worker requires the compute server to be running on localhost. It will check server connectivity before starting.

```bash
# Run worker with default settings (connects to localhost:8002)
uv run compute-worker

# Run with custom worker ID
uv run compute-worker --worker-id worker-1

# Connect to server on different port
uv run compute-worker --port 8003

# Run with specific task types
uv run compute-worker --tasks clip_embedding,face_detection

# Run with debug logging
uv run compute-worker --log-level DEBUG

# Example: Multiple workers for scalability
uv run compute-worker --worker-id worker-1 &
uv run compute-worker --worker-id worker-2 &
```

**Worker Arguments:**
- `--worker-id, -w` - Unique worker identifier (default: worker-default)
- `--port, -p` - Compute server port on localhost (default: 8002, env: COMPUTE_SERVER_PORT)
- `--tasks, -t` - Comma-separated task types to process (default: all available)
- `--log-level, -l` - Logging level: DEBUG, INFO, WARNING, ERROR (default: INFO)

## Environment Variables

Required:
- `CL_SERVER_DIR` - Base directory for all data (must exist and be writable)

Optional:
- `PORT` - Server port (default: 8002)
- `HOST` - Server host (default: 0.0.0.0)
- `WORKER_DATABASE_URL` - Database connection string
- `COMPUTE_STORAGE_DIR` - Compute workspace directory
- `MQTT_BROKER` - MQTT broker hostname (default: localhost)
- `MQTT_PORT` - MQTT broker port (default: 1883)
- `CAPABILITY_TOPIC_PREFIX` - Worker capability topic prefix
- `AUTH_DISABLED` - Disable authentication (set to "true")
- `PUBLIC_KEY_PATH` - Path to JWT public key

## API Endpoints

### Job Management

- `GET /jobs/{job_id}` - Get job status and results
- `DELETE /jobs/{job_id}` - Delete job and associated files

### Worker Capabilities

- `GET /capabilities` - Get available worker capabilities

### Admin Endpoints

- `GET /admin/jobs/storage/size` - Get total storage usage
- `DELETE /admin/jobs/cleanup?days=7` - Cleanup old jobs

### Compute Plugin Endpoints

Dynamically registered endpoints from cl_ml_tools plugins.

## Development

> **For Developers:** See [INTERNALS.md](INTERNALS.md) for development setup.

## License

See [LICENSE](LICENSE) file for details.
