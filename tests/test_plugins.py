"""Tests for plugin system integration."""

from unittest.mock import MagicMock, patch

from compute.plugins import create_compute_plugin_router


class TestCreateComputePluginRouter:
    """Tests for create_compute_plugin_router function."""

    def test_create_compute_plugin_router(self):
        """Test creating plugin router."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService") as mock_repo:
                with patch("compute.plugins.JobStorageService"):
                    mock_router = MagicMock()
                    mock_create_router.return_value = mock_router
                    mock_repository = MagicMock()
                    mock_repo.return_value = mock_repository

                    router, repository = create_compute_plugin_router()

                    assert router == mock_router
                    assert repository == mock_repository

                    # Verify create_master_router was called with correct args
                    mock_create_router.assert_called_once()
                    call_kwargs = mock_create_router.call_args[1]  # pyright: ignore[reportAny] for testing purposes
                    assert "repository" in call_kwargs
                    assert "file_storage" in call_kwargs
                    assert "get_current_user" in call_kwargs

    def test_create_compute_plugin_router_uses_session_local(self):
        """Test that plugin router uses SessionLocal."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService") as mock_repo:
                with patch("compute.plugins.JobStorageService"):
                    with patch("compute.plugins.SessionLocal") as mock_session:
                        mock_router = MagicMock()
                        mock_create_router.return_value = mock_router

                        _ = create_compute_plugin_router()

                        # Verify JobRepositoryService was initialized with SessionLocal
                        mock_repo.assert_called_once_with(mock_session)

    def test_create_compute_plugin_router_uses_compute_storage_dir(self):
        """Test that plugin router uses COMPUTE_STORAGE_DIR."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService"):
                with patch("compute.plugins.JobStorageService") as mock_storage:
                    with patch("compute.plugins.Config.COMPUTE_STORAGE_DIR", "/test/storage"):
                        mock_router = MagicMock()
                        mock_create_router.return_value = mock_router

                        _ = create_compute_plugin_router()

                        # Verify JobStorageService was initialized with correct base_dir
                        mock_storage.assert_called_once_with(base_dir="/test/storage")

    def test_create_compute_plugin_router_uses_auth_permission(self):
        """Test that plugin router requires ai_inference_support permission."""
        with patch("compute.plugins.create_master_router") as mock_create_router:
            with patch("compute.plugins.JobRepositoryService"):
                with patch("compute.plugins.JobStorageService"):
                    with patch("compute.plugins.require_permission") as mock_require_permission:
                        mock_router = MagicMock()
                        mock_create_router.return_value = mock_router
                        mock_permission_checker = MagicMock()
                        mock_require_permission.return_value = mock_permission_checker

                        _ = create_compute_plugin_router()

                        # Verify require_permission was called with correct permission
                        mock_require_permission.assert_called_once_with("ai_inference_support")

                        # Verify the permission checker was passed to create_master_router
                        call_kwargs = mock_create_router.call_args[1]  # pyright: ignore[reportAny] for testing purposes
                        assert call_kwargs["get_current_user"] == mock_permission_checker
