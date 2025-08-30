import os
import tempfile

import pytest

from google_service.storage import KeyValueStore

import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch


from google_service.core import UserService
from utils.config import get_config


@pytest.fixture(autouse=True)
def setup_test_environment():
    """
    Set TESTING env var and reset cached config so tests always see TESTING=true.
    """
    os.environ["TESTING"] = "true"
    os.environ["PYTEST"] = "true"

    # invalidate cache before any test
    from agents.orchestrator.core import get_agent
    from utils.config import get_config

    get_agent.cache_clear()
    get_config.cache_clear()
    yield

    # clean up after test
    if "TESTING" in os.environ:
        del os.environ["TESTING"]
    if "PYTEST" in os.environ:
        del os.environ["PYTEST"]
    get_config.cache_clear()
    get_agent.cache_clear()


@pytest.fixture
def orchestrator_graph():
    from agents.orchestrator.core import get_agent

    return get_agent()

@pytest.fixture()
def memory_checkpointer():
    """
    Fixture that provides a MemorySaver checkpointer for tests.
    This avoids any database connections during testing.
    """
    from langgraph.checkpoint.memory import MemorySaver

    return MemorySaver()


@pytest.fixture()
def tmp_db_path():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name
    try:
        yield db_path
    finally:
        if os.path.exists(db_path):
            os.unlink(db_path)


@pytest.fixture()
def store(tmp_db_path):
    s = KeyValueStore(tmp_db_path)
    try:
        yield s
    finally:
        try:
            s.conn.close()
        except Exception:
            pass


@pytest.fixture()
def config_json(tmp_path: Path) -> Path:
    """
    Create a temp Google client secrets JSON file with the structure expected by associate_account().
    """
    data = {
        "installed": {
            "client_id": "cid-123",
            "client_secret": "csecret-xyz",
            "token_uri": "https://oauth2.googleapis.com/token",
        }
    }
    p = tmp_path / "client_secrets.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


@pytest.fixture()
def patched_config(config_json):
    """
    Patch the module-level config object inside user_service to point to our temp file + dummy scopes.
    """
    with patch("google_service.core.config") as mock_conf:
        mock_conf.GOOGLE_PROJECT_CREDENTIALS_PATH = str(config_json)
        mock_conf.GOOGLE_SCOPES = ["email", "profile"]
        yield mock_conf


@pytest.fixture()
def user_service(store, patched_config):
    # patched_config is applied via fixture use; no direct reference needed here.
    return UserService(store=store)


@pytest.fixture()
def fake_google_credentials_class():
    """
    Patch google.oauth2.credentials.Credentials with a lightweight fake that captures init args
    and simulates refresh() by setting a token/expiry.
    """

    class FakeCreds:
        def __init__(
            self, token, refresh_token, token_uri, client_id, client_secret, scopes
        ):
            self.token = token
            self.refresh_token = refresh_token
            self.token_uri = token_uri
            self.client_id = client_id
            self.client_secret = client_secret
            self.scopes = scopes
            self.expiry = None

        def refresh(self, request):
            # simulate getting a fresh access token and expiry
            self.token = "new-access-token"
            self.expiry = datetime.utcnow() + timedelta(hours=1)

    with patch("google_service.core.Credentials", FakeCreds):
        yield FakeCreds


@pytest.fixture()
def mock_requests_get_success():
    """
    Mock requests.get to return a successful userinfo response with an email.
    """
    with patch("google_service.core.requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"email": "user@example.com"}
        mock_get.return_value = resp
        yield mock_get


@pytest.fixture()
def mock_requests_get_failure():
    with patch("google_service.core.requests.get") as mock_get:
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"error": "unauthorized"}
        mock_get.return_value = resp
        yield mock_get
