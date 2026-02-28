import pytest

from app.core.security import hash_password, verify_password, create_access_token, decode_token


class TestPasswordHashing:
    def test_hash_password_returns_different_from_input(self):
        password = "secure_password_123"
        hashed = hash_password(password)
        assert hashed != password

    def test_hash_password_returns_different_hash_each_time(self):
        password = "secure_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 != hash2  # bcrypt salts differ

    def test_verify_password_correct(self):
        password = "secure_password_123"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_verify_password_empty_string(self):
        hashed = hash_password("some_password")
        assert verify_password("", hashed) is False


class TestJWT:
    def test_create_access_token_returns_string(self):
        token = create_access_token(subject="user-123")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_decode_token_returns_subject(self):
        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"

    def test_decode_token_contains_exp(self):
        token = create_access_token(subject="user-123")
        payload = decode_token(token)
        assert "exp" in payload

    def test_decode_token_invalid_token_returns_none(self):
        payload = decode_token("invalid.token.here")
        assert payload is None

    def test_decode_token_with_extra_data(self):
        token = create_access_token(
            subject="user-123",
            extra={"role": "admin", "email": "test@example.com"},
        )
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "admin"
        assert payload["email"] == "test@example.com"
