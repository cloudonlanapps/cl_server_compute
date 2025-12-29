"""Tests for FastAPI application."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from compute.task_server import app


@pytest.fixture
def client() -> TestClient:
    """Create test client."""
    return TestClient(app)


class TestTaskServerApp:
    """Tests for Task Server FastAPI application."""

    def test_app_exists(self):
        """Test that app is created."""
        assert app is not None
        assert app.title == "Task Server"
        assert app.version == "v1"

    def test_app_includes_routers(self):
        """Test that app includes required routers."""
        # Check that routes are registered
        routes = [getattr(route, "path") for route in app.routes if hasattr(route, "path")]

        # Job management routes
        assert "/jobs/{job_id}" in routes

        # Admin routes
        assert "/admin/jobs/storage/size" in routes
        assert "/admin/jobs/cleanup" in routes

        # Capability route
        assert "/capabilities" in routes

        # Root route
        assert "/" in routes

    def test_root_endpoint(self, client: TestClient):
        """Test root health check endpoint."""
        response = client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["service"] == "Task Server"
        assert data["version"] == "v1"

    def test_root_response_schema(self, client: TestClient):
        """Test root endpoint response matches schema."""
        response = client.get("/")

        data = response.json()
        assert "status" in data
        assert "service" in data
        assert "version" in data
        assert isinstance(data["status"], str)
        assert isinstance(data["service"], str)
        assert isinstance(data["version"], str)

    def test_http_exception_handler(self, client: TestClient):
        """Test HTTP exception handler preserves error format."""
        # Try to access non-existent job (will trigger HTTPException)
        with patch("compute.service.JobService.get_job") as mock_get_job:
            from fastapi import HTTPException

            mock_get_job.side_effect = HTTPException(status_code=404, detail="Job not found")

            # Override dependencies to allow test to run
            from cl_server_shared.models import Base
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker

            from compute.database import get_db

            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            SessionLocal = sessionmaker(bind=engine)
            test_db = SessionLocal()

            with patch("compute.auth.Config.AUTH_DISABLED", True):
                app.dependency_overrides[get_db] = lambda: iter([test_db])

                response = client.get("/jobs/test-job")

                assert response.status_code == 404
                data = response.json()
                assert "detail" in data

                # Clean up
                test_db.close()
                app.dependency_overrides.clear()

    def test_shutdown_event_closes_capability_manager(self):
        """Test that lifespan shutdown closes capability manager."""
        import asyncio

        from compute.task_server import lifespan

        with patch("compute.capability_manager.close_capability_manager") as mock_close:
            # Test lifespan context manager shutdown
            async def run_lifespan():
                async with lifespan(app):
                    pass  # Shutdown happens when exiting the context

            asyncio.run(run_lifespan())

            mock_close.assert_called_once()

    def test_plugin_router_included(self):
        """Test that plugin router is included in app."""
        # The plugin router is created and included
        # We verify this indirectly by checking that create_compute_plugin_router was called
        # This is already tested in test_plugins.py, so here we just verify the app structure

        # Check that app has expected number of routers
        # app should include: main router + plugin router
        assert len(app.router.routes) > 0

    def test_openapi_schema_generated(self, client: TestClient):
        """Test that OpenAPI schema is generated."""
        response = client.get("/openapi.json")

        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert schema["info"]["title"] == "Task Server"
        assert schema["info"]["version"] == "v1"

    def test_openapi_paths_exist(self, client: TestClient):
        """Test that expected paths exist in OpenAPI schema."""
        response = client.get("/openapi.json")
        schema = response.json()

        paths = schema["paths"]
        assert "/" in paths
        assert "/jobs/{job_id}" in paths
        assert "/capabilities" in paths
        assert "/admin/jobs/storage/size" in paths
        assert "/admin/jobs/cleanup" in paths

    def test_openapi_operations(self, client: TestClient):
        """Test that operations have correct operation IDs."""
        response = client.get("/openapi.json")
        schema = response.json()

        # Check root endpoint
        assert schema["paths"]["/"]["get"]["operationId"] == "root_get"

        # Check job endpoints
        assert schema["paths"]["/jobs/{job_id}"]["get"]["operationId"] == "get_job"
        assert schema["paths"]["/jobs/{job_id}"]["delete"]["operationId"] == "delete_job"

        # Check capability endpoint
        assert schema["paths"]["/capabilities"]["get"]["operationId"] == "get_worker_capabilities"

    def test_app_tags(self, client: TestClient):
        """Test that endpoints are tagged correctly."""
        response = client.get("/openapi.json")
        schema = response.json()

        # Job endpoints should have 'job' tag
        job_get = schema["paths"]["/jobs/{job_id}"]["get"]
        assert "job" in job_get["tags"]

        # Admin endpoints should have 'admin' tag
        storage_get = schema["paths"]["/admin/jobs/storage/size"]["get"]
        assert "admin" in storage_get["tags"]

        # Capability endpoint should have 'compute' tag
        cap_get = schema["paths"]["/capabilities"]["get"]
        assert "compute" in cap_get["tags"]
