import pytest

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient

from api.chat_router import router as chat_router
from api.depends import check_access

import api.chat_router as chat_module


@pytest.fixture()
def fast_api_app() -> FastAPI:
    """
    Minimal app for tests. Include the chat router (others can include their routers too).
    We attach real security dependency here; we'll override it per-test.
    """
    app = FastAPI()
    app.include_router(chat_router, dependencies=[Depends(check_access)])
    return app


@pytest.fixture()
def api_client(fast_api_app: FastAPI) -> TestClient:
    return TestClient(fast_api_app)


@pytest.fixture()
def allow_all_api_keys(fast_api_app: FastAPI):
    """
    Override 'check_access' globally for a test so no API key is needed.
    """

    def _noop():
        return None

    fast_api_app.dependency_overrides[check_access] = _noop
    yield _noop
    fast_api_app.dependency_overrides.pop(check_access, None)


@pytest.fixture()
def mock_user_service(monkeypatch, request):
    """
    Parametrizable fixture to control the result of get_user_service().list_accounts(username).
    Usage:
        @pytest.mark.parametrize("mock_user_service", [[/* accounts */]], indirect=True)
    If not parametrized, defaults to ["acc-1"].
    """
    accounts = getattr(request, "param", ["acc-1"])

    class DummyUserService:
        def list_accounts(self, username: str):
            return accounts

    def fake_get_user_service():
        return DummyUserService()

    # Patch the symbol used by api.chat_router
    monkeypatch.setattr(
        chat_module, "get_user_service", fake_get_user_service, raising=True
    )
    return fake_get_user_service
