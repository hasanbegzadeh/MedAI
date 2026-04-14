"""Tests for JWT authentication utilities."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import jwt
import pytest

from app.auth import (
    create_access_token,
    decode_access_token,
    validate_websocket_token,
)


class TestCreateAccessToken:
    """Tests for JWT token creation."""

    def test_create_token_contains_required_claims(self):
        """Access token includes sub, username, role, exp, type."""
        user_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
        )

        decoded = jwt.decode(token, "test-secret-key-at-least-32-chars-long!!", algorithms=["HS256"], options={"verify_exp": False})
        assert decoded["sub"] == str(user_id)
        assert decoded["username"] == "testuser"
        assert decoded["role"] == "radiologist"
        assert decoded["type"] == "access"

    def test_create_token_custom_expiry(self):
        """Custom expiry is applied correctly."""
        user_id = uuid4()
        expires_delta = timedelta(hours=2)
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
            expires_delta=expires_delta,
        )

        decoded = jwt.decode(token, "test-secret-key-at-least-32-chars-long!!", algorithms=["HS256"], options={"verify_exp": True})
        assert decoded["sub"] == str(user_id)
        assert decoded["exp"] > datetime.now(timezone.utc).timestamp()


class TestDecodeAccessToken:
    """Tests for JWT token decoding and validation."""

    def test_decode_valid_token(self):
        """Valid token decodes successfully."""
        user_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
        )

        payload = decode_access_token(token)
        assert payload["sub"] == str(user_id)
        assert payload["username"] == "testuser"

    def test_decode_expired_token_raises(self):
        """Expired token raises HTTPException."""
        from fastapi import HTTPException

        user_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
            expires_delta=timedelta(seconds=-1),  # Already expired
        )

        with pytest.raises(HTTPException, match="expired"):
            decode_access_token(token)

    def test_decode_invalid_token_raises(self):
        """Invalid token raises HTTPException."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException, match="Invalid token"):
            decode_access_token("not-a-valid-jwt-token")

    def test_decode_token_wrong_secret_raises(self):
        """Token signed with wrong secret raises HTTPException."""
        from fastapi import HTTPException
        from unittest.mock import patch, MagicMock

        user_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
        )

        wrong_settings = MagicMock()
        wrong_settings.jwt_secret = "wrong-secret-key-at-least-32-chars!!!"
        wrong_settings.jwt_algorithm = "HS256"

        with patch("app.auth.get_settings", return_value=wrong_settings):
            with pytest.raises(HTTPException):
                decode_access_token(token)


class TestValidateWebsocketToken:
    """Tests for WebSocket token validation."""

    def test_validate_websocket_token(self):
        """Valid token validates successfully."""
        user_id = uuid4()
        token = create_access_token(
            user_id=user_id,
            username="testuser",
            role="radiologist",
        )

        payload = validate_websocket_token(token)
        assert payload["sub"] == str(user_id)
