import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from agents.orchestrator.graph import orchestrator_input_node

TEST_USER_ID = "test_user_123"


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


def _route_order_from(response):
    """
    Extracts the order of managers from the orchestrator response.
    Expects response.update['manager_list'] to be a list of OrchestratorRouter
    objects with attribute .route_manager (or dicts with key 'route_manager').
    """
    managers = response.update["manager_list"]
    order = []
    for item in managers:
        if hasattr(item, "route_manager"):
            order.append(item.route_manager)
        else:
            order.append(item.get("route_manager"))
    return order


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input,expected_order,case",
    [
        (
            "How can you help me?",
            [],
            "No managers",
        ),
        (
            "Do you know my name?",
            [],
            "No managers",
        ),
        (
            "what are my events for tomorrow?",
            ["date_manage", "calendar_manage"],
            "Events: 'tomorrow' => date first, then calendar",
        ),
        (
            "list my events from May 1 to May 5",
            ["date_manage", "calendar_manage"],
            "Events: explicit date range",
        ),
        (
            "show me emails from last month with attachments",
            ["date_manage", "email_manage"],
            "Emails: period 'last month' => date + email",
        ),
        (
            "tell me my last mail from my contact manuel?",
            ["contacts_manage", "email_manage"],
            "Emails: 'manuel' + important label => date + email",
        ),
        (
            "past emails",
            ["date_manage", "email_manage"],
            "Emails: vague temporal reference => 15-day range (date) + email",
        ),
        (
            "find John Appleseed contact",
            ["contacts_manage"],
            "Contacts: search for a contact",
        ),
        (
            "delete contact Maria Gomez",
            ["contacts_manage"],
            "Contacts: delete a contact",
        ),
        (
            "add Bob to 'Team Sync' event on Aug 30",
            ["contacts_manage", "calendar_manage"],
            "Find a contact and add to an event",
        ),
        (
            "send an email to alice@example.com saying hi",
            ["email_manage"],
            "Emails: drafting/sending without temporal info",
        ),
        (
            "check my availability for the next two days and write a draft email to alice@example.com",
            ["date_manage", "calendar_manage", "email_manage"],
            "More complex: date + calendar + email",
        ),
    ],
)
async def test_planning_route_order(
    user_input, expected_order, case, mock_user_service
):
    """
    Validates that the orchestrator schedules the correct order of managers
    according to the planning rules:
      - date_manage must always come first if the request has temporal references
        (specific day, range, or general period).
      - contacts_manage must be used when contacts are involved.
      - email_manage for emails (preceded by date_manage if temporal).
      - calendar_manage for events (preceded by date_manage if temporal).
      - If the event is identified by a full link, date_manage is not needed.
    """
    response = await orchestrator_input_node(
        {
            "user_input": user_input,
            "user_id": TEST_USER_ID,
            "messages": [],
            "supervisors_messages": [],
            "manager_response": [],
            "manager_list": [],
        }
    )

    order = _route_order_from(response)
    assert order == expected_order, f"Case failed: {case}. Got {order}"


# --- Additional invariant tests ---


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input",
    [
        "tomorrow's events",
        "events next week",
        "emails two days ago",
        "important emails last month",
        "free time from now until Friday",
    ],
)
async def test_date_manage_is_first_when_temporal(user_input, mock_user_service):
    """
    Invariant: if there are temporal references, the first manager must be date_manage.
    """
    response = await orchestrator_input_node(
        {
            "user_input": user_input,
            "user_id": TEST_USER_ID,
            "messages": [],
            "supervisors_messages": [],
            "manager_response": [],
            "manager_list": [],
        }
    )
    order = _route_order_from(response)
    assert order[0] == "date_manage", f"date_manage was not first for: {user_input}"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "user_input,expected_contains",
    [
        ("contacts of my team", "contacts_manage"),
        ("list my contacts", "contacts_manage"),
        ("remove contact Bob", "contacts_manage"),
        ("find contact Alice", "contacts_manage"),
    ],
)
async def test_contacts_requests_include_contacts_manager(
    user_input, expected_contains, mock_user_service
):
    """
    Invariant: any mention of 'contact(s)' must include contacts_manage.
    """
    response = await orchestrator_input_node(
        {
            "user_input": user_input,
            "user_id": TEST_USER_ID,
            "messages": [],
            "supervisors_messages": [],
            "manager_response": [],
            "manager_list": [],
        }
    )
    order = _route_order_from(response)
    assert expected_contains in order, (
        f"{expected_contains} not included for: {user_input}"
    )
