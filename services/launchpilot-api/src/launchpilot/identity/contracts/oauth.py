from typing import Protocol


class OAuthTransaction(Protocol):
    state: str
    code_challenge: str
    cookie_value: str


class BrowserState(Protocol):
    def issue(self, purpose: str) -> OAuthTransaction: ...

    def consume(self, *, cookie_value: str | None, state: str, purpose: str) -> str: ...


class GoogleOAuthGateway(Protocol):
    def authorization_url(
        self,
        *,
        state: str,
        scopes: tuple[str, ...],
        callback_path: str,
        code_challenge: str,
    ) -> str: ...

    def exchange_code(
        self, *, code: str, callback_path: str, code_verifier: str
    ) -> dict[str, object]: ...

    def user_info(self, access_token: str) -> dict[str, object]: ...


class MetaOAuthGateway(Protocol):
    def authorization_url(
        self, *, state: str, scopes: tuple[str, ...], callback_path: str
    ) -> str: ...

    def exchange_code(self, *, code: str, callback_path: str) -> dict[str, object]: ...


class UserSession(Protocol):
    def issue(self, user_id: str) -> str: ...
    def read(self, token: str) -> str: ...
