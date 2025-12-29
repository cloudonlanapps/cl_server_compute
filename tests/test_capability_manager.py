"""Tests for worker capability manager."""

import json
from unittest.mock import MagicMock, patch

from compute.capability_manager import (
    CapabilityManager,
    CapabilityMessage,
    close_capability_manager,
    get_capability_manager,
)


class TestCapabilityMessage:
    """Tests for CapabilityMessage model."""

    def test_capability_message_valid(self):
        """Test CapabilityMessage with valid data."""
        msg = CapabilityMessage(
            id="worker-1",
            capabilities=["image_resize", "image_conversion"],
            idle_count=1,
            timestamp=1234567890000,
        )

        assert msg.id == "worker-1"
        assert msg.capabilities == ["image_resize", "image_conversion"]
        assert msg.idle_count == 1
        assert msg.timestamp == 1234567890000

    def test_capability_message_from_json(self):
        """Test parsing CapabilityMessage from JSON."""
        json_data = json.dumps(
            {
                "id": "worker-2",
                "capabilities": ["face_detection"],
                "idle_count": 0,
                "timestamp": 1234567890000,
            }
        )

        msg = CapabilityMessage.model_validate_json(json_data)

        assert msg.id == "worker-2"
        assert msg.capabilities == ["face_detection"]
        assert msg.idle_count == 0


class TestCapabilityManager:
    """Tests for CapabilityManager."""

    def test_capability_manager_init(self):
        """Test CapabilityManager initialization."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            assert manager.capabilities_cache == {}
            assert manager.broadcaster is not None
            assert manager.ready_event.is_set()
            mock_broadcaster.subscribe.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_capability_manager_init_no_broadcaster(self):
        """Test CapabilityManager when broadcaster is None."""
        with patch("compute.capability_manager.get_broadcaster", return_value=None):
            manager = CapabilityManager()

            assert manager.broadcaster is None
            assert manager.ready_event.is_set()

    def test_on_message_valid_capability(self):
        """Test processing valid capability message."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Simulate capability message
            topic = "inference/workers/worker-1"
            payload = json.dumps(
                {
                    "id": "worker-1",
                    "capabilities": ["image_resize", "image_conversion"],
                    "idle_count": 1,
                    "timestamp": 1234567890000,
                }
            )

            manager.on_message(topic, payload)

            assert "worker-1" in manager.capabilities_cache
            assert manager.capabilities_cache["worker-1"].id == "worker-1"
            assert "image_resize" in manager.capabilities_cache["worker-1"].capabilities

    def test_on_message_empty_payload(self):
        """Test processing LWT empty message (worker disconnected)."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Add worker to cache first
            topic = "inference/workers/worker-1"
            payload = json.dumps(
                {
                    "id": "worker-1",
                    "capabilities": ["image_resize"],
                    "idle_count": 1,
                    "timestamp": 1234567890000,
                }
            )
            manager.on_message(topic, payload)
            assert "worker-1" in manager.capabilities_cache

            # Now send empty payload (LWT)
            manager.on_message(topic, "")

            # Worker should be removed from cache
            assert "worker-1" not in manager.capabilities_cache

    def test_on_message_invalid_topic(self):
        """Test processing message with invalid topic format."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Topic with less than 3 parts
            manager.on_message("invalid/topic", '{"id": "test"}')

            # Should not crash, cache should remain empty
            assert len(manager.capabilities_cache) == 0

    def test_on_message_invalid_json(self):
        """Test processing message with invalid JSON."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            topic = "inference/workers/worker-1"
            manager.on_message(topic, "invalid json{")

            # Should not crash, cache should remain empty
            assert len(manager.capabilities_cache) == 0

    def test_get_cached_capabilities_empty(self):
        """Test getting capabilities when cache is empty."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            result = manager.get_cached_capabilities()

            assert result.root == {}

    def test_get_cached_capabilities_single_worker(self):
        """Test getting capabilities with single worker."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Add worker capability
            topic = "inference/workers/worker-1"
            payload = json.dumps(
                {
                    "id": "worker-1",
                    "capabilities": ["image_resize", "image_conversion"],
                    "idle_count": 1,
                    "timestamp": 1234567890000,
                }
            )
            manager.on_message(topic, payload)

            result = manager.get_cached_capabilities()

            assert result.root["image_resize"] == 1
            assert result.root["image_conversion"] == 1

    def test_get_cached_capabilities_multiple_workers(self):
        """Test aggregating capabilities from multiple workers."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Add first worker
            manager.on_message(
                "inference/workers/worker-1",
                json.dumps(
                    {
                        "id": "worker-1",
                        "capabilities": ["image_resize", "image_conversion"],
                        "idle_count": 1,
                        "timestamp": 1234567890000,
                    }
                ),
            )

            # Add second worker
            manager.on_message(
                "inference/workers/worker-2",
                json.dumps(
                    {
                        "id": "worker-2",
                        "capabilities": ["image_resize", "face_detection"],
                        "idle_count": 2,
                        "timestamp": 1234567890000,
                    }
                ),
            )

            result = manager.get_cached_capabilities()

            # image_resize: 1 + 2 = 3
            # image_conversion: 1
            # face_detection: 2
            assert result.root["image_resize"] == 3
            assert result.root["image_conversion"] == 1
            assert result.root["face_detection"] == 2

    def test_wait_for_capabilities(self):
        """Test waiting for capability manager to be ready."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Should be immediately ready
            result = manager.wait_for_capabilities(timeout=1)

            assert result is True

    def test_get_worker_count_by_capability(self):
        """Test getting worker count by capability."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()

            # Add workers
            manager.on_message(
                "inference/workers/worker-1",
                json.dumps(
                    {
                        "id": "worker-1",
                        "capabilities": ["image_resize", "image_conversion"],
                        "idle_count": 1,
                        "timestamp": 1234567890000,
                    }
                ),
            )

            manager.on_message(
                "inference/workers/worker-2",
                json.dumps(
                    {
                        "id": "worker-2",
                        "capabilities": ["image_resize"],
                        "idle_count": 0,
                        "timestamp": 1234567890000,
                    }
                ),
            )

            result = manager.get_worker_count_by_capability()

            # Both workers have image_resize
            # Only worker-1 has image_conversion
            assert result.root["image_resize"] == 2
            assert result.root["image_conversion"] == 1

    def test_disconnect(self):
        """Test disconnecting from broadcaster."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            manager = CapabilityManager()
            manager.disconnect()

            mock_broadcaster.disconnect.assert_called_once()  # pyright: ignore[reportAny] ignore mock types for testing purposes

    def test_disconnect_no_broadcaster(self):
        """Test disconnecting when broadcaster is None."""
        with patch("compute.capability_manager.get_broadcaster", return_value=None):
            manager = CapabilityManager()
            # Should not crash
            manager.disconnect()


class TestCapabilityManagerSingleton:
    """Tests for capability manager singleton functions."""

    def test_get_capability_manager_singleton(self):
        """Test that get_capability_manager returns singleton."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            # Reset singleton
            import compute.capability_manager

            compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

            manager1 = get_capability_manager()
            manager2 = get_capability_manager()

            assert manager1 is manager2

            # Clean up
            compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

    def test_close_capability_manager(self):
        """Test closing capability manager singleton."""
        with patch("compute.capability_manager.get_broadcaster") as mock_get_broadcaster:
            mock_broadcaster: MagicMock = MagicMock()
            mock_get_broadcaster.return_value = mock_broadcaster

            # Reset singleton
            import compute.capability_manager

            compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]

            manager = get_capability_manager()
            assert manager is not None

            close_capability_manager()

            # Singleton should be None after closing
            assert compute.capability_manager._capability_manager_instance is None  # pyright: ignore[reportPrivateUsage]  for testing purposes

    def test_close_capability_manager_when_none(self):
        """Test closing when manager is already None."""
        import compute.capability_manager

        compute.capability_manager._capability_manager_instance = None  # pyright: ignore[reportPrivateUsage]  for testing purposes

        # Should not crash
        close_capability_manager()

        assert compute.capability_manager._capability_manager_instance is None  # pyright: ignore[reportPrivateUsage]  for testing purposes
