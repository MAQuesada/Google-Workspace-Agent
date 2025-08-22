from datetime import datetime, timedelta
from typing import Dict

import pytest

from google_service.core import UserService
from google_service.models import (
    User,
    GoogleAccount,
    GoogleAccountCredentials,
)
from utils.exceptions import UserError, CredentialsRefreshError


def test_save_and_load_user_roundtrip(user_service: UserService):
    u = User(username="alice")
    user_service.save_user(u)

    loaded = user_service.load_user("alice")
    assert isinstance(loaded, User)
    assert loaded.username == "alice"
    assert loaded.accounts == []


def test_load_user_returns_none_on_validation_error(user_service: UserService):
    # Inject invalid data into store (missing required 'username')
    bad = {"id": "123", "accounts": []}
    user_service.store.set("user:bob", bad)

    assert user_service.load_user("bob") is None


def test_list_users_returns_all_usernames(user_service: UserService):
    # Save via model to use real logic
    user_service.save_user(User(username="u1"))
    user_service.save_user(User(username="u2"))
    user_service.save_user(User(username="u3"))

    users = set(user_service.list_users())
    assert users == {"u1", "u2", "u3"}


def test_list_accounts_no_user_returns_empty(user_service: UserService):
    assert user_service.list_accounts("nope") == []


def test_list_accounts_existing_user(user_service: UserService):
    creds = GoogleAccountCredentials(
        client_id="c",
        client_secret="s",
        token="t",
        refresh_token="rt",
        token_uri="uri",
        expiry=None,
    )
    acc = GoogleAccount(account_email="a@b.com", account_info="info", credentials=creds)
    u = User(username="alice", accounts=[acc])
    user_service.save_user(u)

    out = user_service.list_accounts("alice")
    assert len(out) == 1
    assert out[0].account_email == "a@b.com"


def test_fetch_user_email_success(
    user_service: UserService, fake_google_credentials_class, mock_requests_get_success
):
    creds = fake_google_credentials_class(
        token="tok",
        refresh_token="rt",
        token_uri="uri",
        client_id="cid",
        client_secret="sec",
        scopes=[],
    )
    email = user_service.fetch_user_email(creds)
    assert email == "user@example.com"


def test_fetch_user_email_failure_raises(
    user_service: UserService, fake_google_credentials_class, mock_requests_get_failure
):
    creds = fake_google_credentials_class(
        token="tok",
        refresh_token="rt",
        token_uri="uri",
        client_id="cid",
        client_secret="sec",
        scopes=[],
    )
    with pytest.raises(UserError):
        user_service.fetch_user_email(creds)


def test_associate_account_creates_user_and_saves_account(
    user_service: UserService,
    fake_google_credentials_class,
    mock_requests_get_success,
    patched_config,
):
    acc = user_service.associate_account(
        username="alice",
        refresh_token="refresh-123",
        account_info="primary",
    )

    # Returned account has email from the mocked userinfo endpoint
    assert acc.account_email == "user@example.com"
    assert acc.account_info == "primary"
    assert acc.credentials.token == "new-access-token"
    assert acc.credentials.client_id == "cid-123"
    assert acc.credentials.client_secret == "csecret-xyz"
    assert acc.credentials.token_uri == "https://oauth2.googleapis.com/token"

    # User persisted with exactly one account
    user = user_service.load_user("alice")
    assert user is not None
    assert len(user.accounts) == 1
    assert user.accounts[0].account_email == "user@example.com"


def test_associate_account_replaces_existing_same_email(
    user_service: UserService,
    fake_google_credentials_class,
    mock_requests_get_success,
    patched_config,
):
    # Seed existing user with same email to ensure replacement (no duplicates)
    existing_creds = GoogleAccountCredentials(
        client_id="old",
        client_secret="old",
        token="old",
        refresh_token="old",
        token_uri="old",
        expiry=None,
    )
    existing = GoogleAccount(
        account_email="user@example.com",
        account_info="old-info",
        credentials=existing_creds,
    )
    user_service.save_user(User(username="alice", accounts=[existing]))

    acc = user_service.associate_account(
        username="alice",
        refresh_token="refresh-xyz",
        account_info="new-info",
    )

    user = user_service.load_user("alice")
    assert user is not None
    assert len(user.accounts) == 1  # replaced, not duplicated
    assert user.accounts[0].account_email == "user@example.com"
    assert user.accounts[0].account_info == "new-info"
    # token was refreshed by FakeCreds.refresh()
    assert user.accounts[0].credentials.token == "new-access-token"


def build_user_with_account(
    username: str, email: str, token: str, expiry, overrides: Dict = None
) -> User:
    data = {
        "client_id": "cid",
        "client_secret": "sec",
        "token": token,
        "refresh_token": "rt",
        "token_uri": "uri",
        "expiry": expiry,
    }
    if overrides:
        data.update(overrides)

    creds = GoogleAccountCredentials(**data)
    acc = GoogleAccount(account_email=email, account_info=None, credentials=creds)
    return User(username=username, accounts=[acc])


def test_get_account_user_not_found_returns_none(user_service: UserService):
    assert user_service.get_account("nouser", "x@y") is None


def test_get_account_email_not_found_returns_none(user_service: UserService):
    user_service.save_user(User(username="alice"))
    assert user_service.get_account("alice", "missing@x.com") is None


def test_get_account_not_expired_returns_credentials(user_service: UserService):
    # Not expired → expiry well in the future and token present
    future = datetime.utcnow() + timedelta(days=1)
    u = build_user_with_account("alice", "a@b.com", token="t", expiry=future)
    user_service.save_user(u)

    creds = user_service.get_account("alice", "a@b.com")
    assert isinstance(creds, GoogleAccountCredentials)
    assert creds.token == "t"
    assert creds.expiry == future


def test_get_account_expired_refreshes_and_persists(
    user_service: UserService, monkeypatch
):
    # Expired because expiry is None (or token None)
    u = build_user_with_account("alice", "a@b.com", token=None, expiry=None)
    user_service.save_user(u)

    # Patch credentials.refresh() to set new token/expiry
    def fake_refresh(self):
        self.token = "refreshed-token"
        self.expiry = datetime.utcnow() + timedelta(hours=2)

    monkeypatch.setattr(GoogleAccountCredentials, "refresh", fake_refresh, raising=True)

    creds = user_service.get_account("alice", "a@b.com")
    assert creds.token == "refreshed-token"

    # Ensure the user was persisted after refresh
    persisted = user_service.load_user("alice")
    assert persisted is not None
    acc = next(a for a in persisted.accounts if a.account_email == "a@b.com")
    assert acc.credentials.token == "refreshed-token"


def test_get_account_expired_refresh_fails_sets_token_none_and_raises_usererror(
    user_service: UserService, monkeypatch
):
    # Expired (expiry in the past or missing token)
    past = datetime.utcnow() - timedelta(days=1)
    u = build_user_with_account("alice", "a@b.com", token="old", expiry=past)
    user_service.save_user(u)

    def raising_refresh(self):
        raise CredentialsRefreshError("boom")

    monkeypatch.setattr(
        GoogleAccountCredentials, "refresh", raising_refresh, raising=True
    )

    with pytest.raises(UserError):
        user_service.get_account("alice", "a@b.com")

    # Token/expiry should have been nulled and user persisted
    persisted = user_service.load_user("alice")
    assert persisted is not None
    acc = next(a for a in persisted.accounts if a.account_email == "a@b.com")
    assert acc.credentials.token is None
    assert acc.credentials.expiry is None
