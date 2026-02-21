"""
Tests for Security Functions
"""
import pytest
from datetime import timedelta
from jose import jwt, JWTError
from fastapi import HTTPException

from src.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    decode_access_token,
    ALGORITHM,
)
from src.core.config import settings


class TestSecurity:
    """Test cases for security functions"""

    def test_hash_password(self):
        """Test password hashing"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0

    def test_verify_password_correct(self):
        """Test password verification with correct password"""
        password = "test_password_123"
        hashed = get_password_hash(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        """Test password verification with incorrect password"""
        password = "test_password_123"
        wrong_password = "wrong_password"
        hashed = get_password_hash(password)

        assert verify_password(wrong_password, hashed) is False

    def test_hash_password_different_results(self):
        """Test that same password produces different hashes (salt)"""
        password = "test_password_123"
        hash1 = get_password_hash(password)
        hash2 = get_password_hash(password)

        assert hash1 != hash2
        assert verify_password(password, hash1) is True
        assert verify_password(password, hash2) is True

    def test_create_access_token(self):
        """Test access token creation"""
        data = {"sub": "user123", "username": "testuser"}
        token = create_access_token(data)

        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0

    def test_create_access_token_with_expiration(self):
        """Test access token creation with custom expiration"""
        data = {"sub": "user123"}
        expires_delta = timedelta(minutes=30)
        token = create_access_token(data, expires_delta)

        assert token is not None
        assert isinstance(token, str)

    def test_decode_access_token(self):
        """Test access token decoding"""
        data = {"sub": "user123", "username": "testuser"}
        token = create_access_token(data)

        decoded = decode_access_token(token)

        assert decoded is not None
        assert decoded["sub"] == "user123"
        assert decoded["username"] == "testuser"
        assert "exp" in decoded

    def test_decode_invalid_token(self):
        """Test decoding invalid token"""
        invalid_token = "invalid.token.here"

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(invalid_token)

        assert exc_info.value.status_code == 401

    def test_decode_expired_token(self):
        """Test decoding expired token"""
        data = {"sub": "user123"}
        # Create token that expires immediately
        expires_delta = timedelta(seconds=-1)
        token = create_access_token(data, expires_delta)

        with pytest.raises(HTTPException) as exc_info:
            decode_access_token(token)

        assert exc_info.value.status_code == 401

    def test_password_strength(self):
        """Test that different password lengths work"""
        passwords = [
            "short",
            "medium_password",
            "very_long_password_with_many_characters_123456789",
        ]

        for password in passwords:
            hashed = get_password_hash(password)
            assert verify_password(password, hashed) is True

    def test_token_contains_required_fields(self):
        """Test that token contains all required fields"""
        data = {
            "sub": "user123",
            "username": "testuser",
            "role": "admin",
        }
        token = create_access_token(data)
        decoded = decode_access_token(token)

        assert "sub" in decoded
        assert "username" in decoded
        assert "role" in decoded
        assert "exp" in decoded

    def test_multiple_tokens_independent(self):
        """Test that multiple tokens are independent"""
        token1 = create_access_token({"sub": "user1"})
        token2 = create_access_token({"sub": "user2"})

        decoded1 = decode_access_token(token1)
        decoded2 = decode_access_token(token2)

        assert decoded1["sub"] == "user1"
        assert decoded2["sub"] == "user2"
        assert token1 != token2

    def test_token_algorithm(self):
        """Test that token uses correct algorithm"""
        data = {"sub": "user123"}
        token = create_access_token(data)

        # Decode without verification to check algorithm
        unverified = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert unverified["sub"] == "user123"
