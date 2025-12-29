"""Tests for authentication and authorization."""

import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from jose import jwt
from pydantic import ValidationError

from compute.auth import (
    UserPayload,
    get_current_user,
    get_public_key,
    require_admin,
    require_permission,
)


class TestUserPayload:
    """Tests for UserPayload model."""

    def test_user_payload_valid(self):
        """Test UserPayload with valid data."""
        user = UserPayload(
            sub="user123",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        assert user.sub == "user123"
        assert user.is_admin is False
        assert user.permissions == ["ai_inference_support"]

    def test_user_payload_admin(self):
        """Test UserPayload for admin user."""
        user = UserPayload(
            sub="admin123",
            is_admin=True,
            permissions=["admin", "ai_inference_support"],
        )

        assert user.sub == "admin123"
        assert user.is_admin is True
        assert "admin" in user.permissions

    def test_user_payload_defaults(self):
        """Test UserPayload default values."""
        user = UserPayload(sub="user456", permissions=[])

        assert user.sub == "user456"
        assert user.is_admin is False
        assert user.permissions == []

    def test_user_payload_unique_permissions(self):
        """Test that duplicate permissions are removed."""
        user = UserPayload(
            sub="user789",
            permissions=[
                "ai_inference_support",
                "admin",
                "ai_inference_support",  # duplicate
            ],
        )

        # unique_permissions validator should remove duplicates
        assert len(user.permissions) == 2
        assert "ai_inference_support" in user.permissions
        assert "admin" in user.permissions

    def test_user_payload_extra_fields_ignored(self):
        """Test that extra fields are ignored."""
        user = UserPayload(
            sub="user999",
            permissions=[],
            extra_field="ignored",  # type: ignore
        )

        assert user.sub == "user999"
        assert not hasattr(user, "extra_field")

    def test_user_payload_missing_required_field(self):
        """Test that missing required field raises ValidationError."""
        with pytest.raises(ValidationError):
            UserPayload(permissions=[])  # type: ignore


class TestGetPublicKey:
    """Tests for get_public_key function."""

    @pytest.mark.asyncio
    async def test_get_public_key_success(self):
        """Test successful public key loading."""
        test_key = "-----BEGIN PUBLIC KEY-----\ntest_key\n-----END PUBLIC KEY-----"

        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write(test_key)
            tmp_path = tmp.name

        try:
            with patch("compute.auth.Config.PUBLIC_KEY_PATH", tmp_path):
                # Clear cache
                import compute.auth

                compute.auth._public_key_cache = None

                key = await get_public_key()
                assert key == test_key

                # Test caching - should return same value without file access
                key2 = await get_public_key()
                assert key2 == test_key
        finally:
            os.unlink(tmp_path)
            # Reset cache
            import compute.auth

            compute.auth._public_key_cache = None

    @pytest.mark.asyncio
    async def test_get_public_key_file_not_found(self):
        """Test public key loading when file doesn't exist."""
        nonexistent_path = "/nonexistent/path/to/key.pem"

        with patch("compute.auth.Config.PUBLIC_KEY_PATH", nonexistent_path):
            with patch("compute.auth._max_load_attempts", 2):  # Speed up test
                # Clear cache
                import compute.auth

                compute.auth._public_key_cache = None

                with pytest.raises(HTTPException) as exc_info:
                    await get_public_key()

                assert exc_info.value.status_code == 500
                assert "Public key not found" in exc_info.value.detail

        # Reset cache
        import compute.auth

        compute.auth._public_key_cache = None

    @pytest.mark.asyncio
    async def test_get_public_key_empty_file(self):
        """Test public key loading with empty file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False) as tmp:
            tmp.write("")  # Empty file
            tmp_path = tmp.name

        try:
            with patch("compute.auth.Config.PUBLIC_KEY_PATH", tmp_path):
                with patch("compute.auth._max_load_attempts", 2):
                    # Clear cache
                    import compute.auth

                    compute.auth._public_key_cache = None

                    with pytest.raises(HTTPException) as exc_info:
                        await get_public_key()

                    assert exc_info.value.status_code == 500
        finally:
            os.unlink(tmp_path)
            # Reset cache
            import compute.auth

            compute.auth._public_key_cache = None


class TestGetCurrentUser:
    """Tests for get_current_user function."""

    @pytest.mark.asyncio
    async def test_get_current_user_auth_disabled(self):
        """Test get_current_user when auth is disabled."""
        with patch("compute.auth.Config.AUTH_DISABLED", True):
            user = await get_current_user(token="any-token")
            assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_no_token(self):
        """Test get_current_user with no token provided."""
        with patch("compute.auth.Config.AUTH_DISABLED", False):
            user = await get_current_user(token=None)
            assert user is None

    @pytest.mark.asyncio
    async def test_get_current_user_valid_token(self):
        """Test get_current_user with valid JWT token."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.backends import default_backend

        # Generate test key pair
        private_key = ec.generate_private_key(ec.SECP256R1(), default_backend())
        public_key = private_key.public_key()

        public_pem = public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()

        # Create valid JWT
        payload = {
            "sub": "test_user",
            "is_admin": False,
            "permissions": ["ai_inference_support"],
        }
        token = jwt.encode(payload, private_pem, algorithm="ES256")

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with patch("compute.auth.get_public_key", return_value=public_pem):
                user = await get_current_user(token=token)

                assert user is not None
                assert user.sub == "test_user"
                assert user.is_admin is False
                assert "ai_inference_support" in user.permissions

    @pytest.mark.asyncio
    async def test_get_current_user_invalid_token(self):
        """Test get_current_user with invalid token."""
        public_key = "-----BEGIN PUBLIC KEY-----\nfake_key\n-----END PUBLIC KEY-----"

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with patch("compute.auth.get_public_key", return_value=public_key):
                with pytest.raises(HTTPException) as exc_info:
                    await get_current_user(token="invalid.token.here")

                assert exc_info.value.status_code == 401
                assert "Could not validate credentials" in exc_info.value.detail


class TestRequirePermission:
    """Tests for require_permission function."""

    @pytest.mark.asyncio
    async def test_require_permission_auth_disabled(self):
        """Test permission check when auth is disabled."""
        checker = require_permission("ai_inference_support")

        with patch("compute.auth.Config.AUTH_DISABLED", True):
            result = await checker(current_user=None)
            assert result is None

    @pytest.mark.asyncio
    async def test_require_permission_no_user(self):
        """Test permission check when no user is authenticated."""
        checker = require_permission("ai_inference_support")

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await checker(current_user=None)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_permission_admin_user(self):
        """Test that admin users have all permissions."""
        checker = require_permission("ai_inference_support")
        admin_user = UserPayload(
            sub="admin",
            is_admin=True,
            permissions=[],
        )

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            result = await checker(current_user=admin_user)
            assert result == admin_user

    @pytest.mark.asyncio
    async def test_require_permission_user_has_permission(self):
        """Test user with required permission."""
        checker = require_permission("ai_inference_support")
        user = UserPayload(
            sub="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            result = await checker(current_user=user)
            assert result == user

    @pytest.mark.asyncio
    async def test_require_permission_user_missing_permission(self):
        """Test user without required permission."""
        checker = require_permission("admin")
        user = UserPayload(
            sub="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await checker(current_user=user)

            assert exc_info.value.status_code == 403
            assert "Insufficient permissions" in exc_info.value.detail
            assert "admin" in exc_info.value.detail


class TestRequireAdmin:
    """Tests for require_admin function."""

    @pytest.mark.asyncio
    async def test_require_admin_auth_disabled(self):
        """Test admin check when auth is disabled."""
        with patch("compute.auth.Config.AUTH_DISABLED", True):
            result = await require_admin(current_user=None)
            assert result is None

    @pytest.mark.asyncio
    async def test_require_admin_no_user(self):
        """Test admin check when no user is authenticated."""
        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(current_user=None)

            assert exc_info.value.status_code == 401
            assert "Authentication required" in exc_info.value.detail

    @pytest.mark.asyncio
    async def test_require_admin_admin_user(self):
        """Test admin check with admin user."""
        admin_user = UserPayload(
            sub="admin",
            is_admin=True,
            permissions=["admin"],
        )

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            result = await require_admin(current_user=admin_user)
            assert result == admin_user

    @pytest.mark.asyncio
    async def test_require_admin_non_admin_user(self):
        """Test admin check with non-admin user."""
        user = UserPayload(
            sub="user",
            is_admin=False,
            permissions=["ai_inference_support"],
        )

        with patch("compute.auth.Config.AUTH_DISABLED", False):
            with pytest.raises(HTTPException) as exc_info:
                await require_admin(current_user=user)

            assert exc_info.value.status_code == 403
            assert "Admin access required" in exc_info.value.detail
