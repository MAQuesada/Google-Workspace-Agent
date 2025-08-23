import pytest
from unittest.mock import patch, MagicMock
import os 

os.environ["TESTING"] = "true"

@pytest.fixture
def mock_user_service():
    """Fixture to mock the user service and its methods."""
    mock_service = MagicMock()

    # Mock accounts
    mock_account = MagicMock()
    mock_account.account_email = "test@example.com"
    mock_account.account_info = "Test Account"

    # Mock user
    mock_user = MagicMock()
    mock_user.username = "test_user"

    # Setup the mock service methods
    mock_service.list_accounts.return_value = [mock_account]
    mock_service.load_user.return_value = mock_user

    with patch("agents.orchestrator.graph.get_user_service", return_value=mock_service):
        yield mock_service
