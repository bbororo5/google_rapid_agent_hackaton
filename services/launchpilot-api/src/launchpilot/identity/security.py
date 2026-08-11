from __future__ import annotations

import base64
import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from typing import Any


class InvalidSignedToken(ValueError):
    pass


class SignedTokenCodec:
    def __init__(self, secret: str) -> None:
        self._secret = secret.encode()

    def encode(self, claims: dict[str, Any], *, lifetime: timedelta) -> str:
        payload = {**claims, "exp": int((datetime.now(UTC) + lifetime).timestamp())}
        encoded = base64.urlsafe_b64encode(
            json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        ).rstrip(b"=")
        signature = hmac.new(self._secret, encoded, hashlib.sha256).digest()
        return f"{encoded.decode()}.{base64.urlsafe_b64encode(signature).rstrip(b'=').decode()}"

    def decode(self, token: str) -> dict[str, Any]:
        try:
            encoded_text, signature_text = token.split(".", 1)
            encoded = encoded_text.encode()
            signature = base64.urlsafe_b64decode(
                signature_text + "=" * (-len(signature_text) % 4)
            )
            expected = hmac.new(self._secret, encoded, hashlib.sha256).digest()
            if not hmac.compare_digest(signature, expected):
                raise InvalidSignedToken("invalid signature")
            payload = json.loads(
                base64.urlsafe_b64decode(encoded_text + "=" * (-len(encoded_text) % 4))
            )
            if int(payload["exp"]) <= int(datetime.now(UTC).timestamp()):
                raise InvalidSignedToken("token expired")
            return payload
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            if isinstance(error, InvalidSignedToken):
                raise
            raise InvalidSignedToken("invalid signed token") from error


@dataclass(frozen=True, slots=True)
class OAuthBrowserState:
    state: str
    code_verifier: str
    code_challenge: str
    cookie_value: str


class BrowserStateManager:
    def __init__(self, codec: SignedTokenCodec) -> None:
        self._codec = codec

    def issue(self, purpose: str) -> OAuthBrowserState:
        state = token_urlsafe(32)
        verifier = token_urlsafe(64)
        challenge = (
            base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
            .rstrip(b"=")
            .decode()
        )
        cookie_value = self._codec.encode(
            {"purpose": purpose, "state": state, "code_verifier": verifier},
            lifetime=timedelta(minutes=10),
        )
        return OAuthBrowserState(state, verifier, challenge, cookie_value)

    def consume(self, *, cookie_value: str | None, state: str, purpose: str) -> str:
        if cookie_value is None:
            raise InvalidSignedToken("OAuth browser state is missing")
        claims = self._codec.decode(cookie_value)
        if claims.get("purpose") != purpose or not hmac.compare_digest(
            str(claims.get("state", "")), state
        ):
            raise InvalidSignedToken("OAuth browser state does not match")
        verifier = claims.get("code_verifier")
        if not isinstance(verifier, str) or not verifier:
            raise InvalidSignedToken("OAuth PKCE verifier is missing")
        return verifier


class SessionManager:
    def __init__(self, codec: SignedTokenCodec) -> None:
        self._codec = codec

    def issue(self, user_id: str) -> str:
        return self._codec.encode({"user_id": user_id}, lifetime=timedelta(hours=12))

    def read(self, token: str) -> str:
        user_id = self._codec.decode(token).get("user_id")
        if not isinstance(user_id, str) or not user_id:
            raise InvalidSignedToken("session user is missing")
        return user_id
