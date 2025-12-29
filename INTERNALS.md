# Compute - Developer Documentation

## Overview

Compute is a FastAPI microservice that manages compute jobs and worker capabilities. It integrates with the cl_ml_tools plugin system and uses shared infrastructure from cl_server_shared.

## Package Structure

```
compute/
├── src/compute/
│   ├── __init__.py           # Public API exports
│   ├── compute_server.py     # Server CLI entry point
│   ├── compute_worker.py     # Worker CLI entry point
│   ├── task_server.py        # FastAPI app
│   ├── routes.py             # API routes
│   ├── service.py            # Business logic
│   ├── schemas.py            # Pydantic models
│   ├── models.py             # Database models (re-exports)
│   ├── database.py           # Database configuration and migrations
│   ├── auth.py               # Authentication
│   ├── capability_manager.py # Worker capability tracking
│   ├── plugins.py            # Plugin system integration
│   ├── utils.py              # Utility functions (directory/server checks)
│   └── worker.py             # Worker implementation
├── tests/                    # Test suite
├── alembic/                  # Database migrations
│   └── versions/             # Migration scripts
├── pyproject.toml            # Package configuration
├── README.md                 # User documentation
└── INTERNALS.md              # This file
```

## Development Setup

### Prerequisites

- Python 3.12+
- uv package manager
- Running MQTT broker (for worker capabilities)
- CL Server shared packages (cl_ml_tools, cl_server_shared)

### Installation

```bash
# Install all dependencies including dev tools
uv sync --all-extras
```

### Running Tests

See [tests/README.md](tests/README.md) for detailed testing information.

```bash
# Run all tests
uv run pytest

# Run with coverage
uv run pytest --cov

# Run specific test file
uv run pytest tests/test_routes.py -v
```

### Code Quality

```bash
# Format code
uv run ruff format src/

# Lint code
uv run ruff check src/

# Type checking (if configured)
uv run basedpyright
```

## Architecture

### Service Components

1. **Routes** (`routes.py`) - FastAPI endpoint definitions
2. **Services** (`service.py`) - Business logic layer
   - `JobService` - Job management operations
   - `CapabilityService` - Worker capability queries
3. **Capability Manager** (`capability_manager.py`) - MQTT-based worker discovery
4. **Plugins** (`plugins.py`) - Integration with cl_ml_tools plugin system
5. **Database** (`database.py`) - SQLAlchemy session management with WAL mode and migrations
6. **Utils** (`utils.py`) - Utility functions for startup validation
   - `ensure_cl_server_dir()` - Creates CL_SERVER_DIR (server only)
   - `validate_cl_server_dir_exists()` - Validates CL_SERVER_DIR exists (worker only)
   - `check_server_running()` - Checks if server is accessible on a port
   - `ensure_server_running()` - Validates server is running or exits (worker only)

### Database

- Uses shared models from `cl_server_shared` (Job, QueueEntry)
- Connects to WORKER_DATABASE_URL (shared with worker service)
- SQLite with WAL mode for concurrent access
- Alembic for migrations (automatically run on server startup)

**Automatic Migrations:**
- Server runs `alembic upgrade head` automatically during startup
- Migrations are validated before execution (checks for alembic.ini and versions directory)
- Server will fail to start if migrations cannot be run
- Worker does NOT run migrations - relies on server to create tables

### Authentication

- JWT-based authentication using ES256 keys
- Shared public key from auth service
- Permission-based access control:
  - `ai_inference_support` - Required for job operations
  - `admin` - Required for admin endpoints

### Startup and Initialization

**Server Startup** (`compute_server.py`):
1. Parse command-line arguments
2. **Create CL_SERVER_DIR** - `ensure_cl_server_dir()` creates directory if needed
3. Set environment variables (AUTH_DISABLED, etc.)
4. Import and start FastAPI application
5. **Run database migrations** - Automatically runs `alembic upgrade head` in lifespan startup
6. Start uvicorn server

**Worker Startup** (`compute_worker.py`):
1. Parse command-line arguments (includes `--port` for server port)
2. **Check server is running** - `ensure_server_running()` verifies server on `localhost:PORT`
3. **Validate CL_SERVER_DIR exists** - `validate_cl_server_dir_exists()` ensures server created it
4. Import ComputeWorker class
5. Start worker main loop

**Separation of Responsibilities:**
- **Server owns**: Directory creation, database migrations, table creation
- **Worker owns**: Reading/writing database records, processing jobs
- **Worker requires**: Server must be running before worker can start

### Worker Capability Discovery

- Uses cl_ml_tools broadcaster (MQTT)
- Subscribes to worker capability topics
- Caches worker capabilities and idle counts
- Provides aggregated capability information

### Worker Execution (`worker.py`)

The worker is a standalone process that executes compute jobs:

**Prerequisites:**
- Compute server must be running on localhost
- CL_SERVER_DIR must exist (created by server)
- Database tables must exist (created by server migrations)

1. **Plugin Discovery**
   - Auto-discovers plugins from `pyproject.toml` entry points
   - Uses `cl_ml_tools.worker.get_task_registry()`
   - Filters tasks based on `--tasks` CLI argument or Config

2. **Job Processing**
   - Polls job repository for available jobs
   - Uses `cl_ml_tools.Worker.run_once()` for atomic job claiming
   - Executes tasks in-process using registered plugins
   - Updates job status and progress via repository

3. **Capability Broadcasting**
   - Publishes worker capabilities to MQTT periodically
   - Includes list of supported tasks and idle state
   - Sets MQTT Last Will & Testament (LWT) for clean disconnection
   - Heartbeat interval: `Config.MQTT_HEARTBEAT_INTERVAL`

4. **Graceful Shutdown**
   - Handles SIGINT/SIGTERM signals
   - Completes current job before shutting down
   - Clears retained MQTT capability messages
   - Closes broadcaster connection

## Plugin System

Task Server integrates with cl_ml_tools plugin system:

1. **Plugin Registration**
   - Plugins register via `pyproject.toml` entry points
   - Entry point group: `cl_ml_tools.tasks`
   - Built-in plugins provided by cl_ml_tools package

   Example custom plugin registration:
   ```toml
   [project.entry-points."cl_ml_tools.tasks"]
   my_custom_task = "my_package.tasks:MyCustomTask"
   ```

2. **API Routes**
   - `create_master_router()` creates plugin routes
   - Routes are mounted on the FastAPI app
   - Plugins use shared JobRepository and FileStorage

3. **Worker Discovery**
   - Worker auto-discovers all registered plugins
   - Uses `get_task_registry()` from cl_ml_tools
   - Filters tasks based on configuration or CLI args

4. **Available Built-in Plugins**
   - clip_embedding - CLIP image embeddings
   - dino_embedding - DINO image embeddings
   - exif - EXIF metadata extraction
   - face_detection - Face detection in images
   - face_embedding - Face recognition embeddings
   - hash - Perceptual image hashing
   - hls_streaming - HLS video streaming
   - image_conversion - Image format conversion
   - media_thumbnail - Media thumbnail generation

## Development Workflow

### Adding New Endpoints

1. Add route function to `routes.py`
2. Add service method to `service.py`
3. Add response schema to `schemas.py`
4. Write tests in `tests/`

### Database Migrations

**Automatic Migrations:**
- Migrations are automatically applied when the server starts
- Server validates that `alembic/versions` directory exists and contains at least one migration
- Server will fail to start if migrations cannot be run

**Manual Migration Tasks (for development):**

**Important:** The `alembic/versions` directory must exist before creating new migrations:

```bash
# Create versions directory if needed
mkdir -p alembic/versions

# Create a new migration after schema changes
uv run alembic revision --autogenerate -m "description"

# Manually apply migrations (not needed - server does this automatically)
uv run alembic upgrade head

# Rollback one migration (development only)
uv run alembic downgrade -1

# Check current migration version
uv run alembic current

# View migration history
uv run alembic history
```

**Note:**
- Users do NOT need to run migrations manually - the server does this automatically
- Developers only need to create new migrations when changing the schema
- The `alembic/versions` directory must exist and contain at least one migration file

## Configuration

All configuration is managed through `cl_server_shared.Config` class:
- Environment variables loaded at startup
- Shared across all CL Server services
- See cl_server_shared documentation for full config options

## Future Enhancements

- Job pagination endpoints
- Job filtering and search
- Job priority management
- Worker health monitoring
- Metrics and monitoring integration
- Rate limiting for job creation

## Contributing

1. Follow existing code patterns
2. Maintain test coverage ≥90%
3. Use type hints for all public APIs
4. Format code with ruff before committing
5. Update documentation for new features
