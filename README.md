# 🤖 Google Workspace Agent

A **LangGraph-powered agent** designed to manage and interact with Google Workspace services through natural language. This project orchestrates multiple specialized managers (date, calendar, contacts, email) that route requests to the appropriate Google account APIs based on user needs.

***

## 🧠 Architecture Overview

```ascii
User Request → Orchestrator → Specialized Managers → Google Workspace APIs
                    ↑               ↓
                    └───── Feedback Synthesizer ─────┘
```

***

## ⚙️ Tech Stack

| Component           | Tool / Service              | Purpose                              |
|---------------------|-----------------------------|--------------------------------------|
| **LLM**             | OpenAI                      | Natural language understanding       |
| **Agent Framework** | LangGraph                   | Agent orchestration & state management |
| **Model tracking**  | LangSmith                   | Model tracking & debugging           |
| **Database**        | PostgreSQL/SQLite           | Checkpointing & persistence          |
| **API Integration** | Google API Client           | Google Workspace service access      |
| **Authentication**  | Google Auth                 | OAuth & credential management        |
| **Environment**     | Poetry                      | Dependency & virtual env setup       |

***

## 🚀 Features

* 📅 **Calendar Management**: Create, update, and query calendar events
* 📧 **Email Operations**: Send, read, and organize emails
* 👥 **Contact Management**: Add, update, and search contacts
* 🗓️ **Date Intelligence**: Smart date handling and scheduling
* 🔄 **Multi-account Support**: Route operations to the correct Google account
* 🧠 **Orchestration**: Central planning and task delegation
* 📝 **Verification**: Check if there is sufficient context and valid data to proceed with calling the next manager in a multi-step process.
* 💬 **Conversational Interface**: Natural language interaction

***

## 🏗️ System Architecture

The system follows a hierarchical structure:

1. **Orchestrator**: Plans and delegates tasks based on user requests
2. **Specialized Managers**:
   * **Date Manager**: Handles date-related operations and scheduling
   * **Calendar Manager**: Manages calendar events and availability
   * **Email Manager**: Processes email-related tasks
   * **Contacts Manager**: Manages contact information
3. **Google API Integration**: Each manager routes requests to the appropriate Google account

***

## 📂 Project Structure

```plaintext
.
├── README.md                    # You're reading it :)
├── pyproject.toml               # Poetry project configuration
└── src/                         # Source code
    ├── agents/                  # Agent implementation
    │   ├── orchestrator/        # Central orchestrator
    │   ├── emails/              # Email manager
    │   ├── calendar/            # Calendar manager
    │   ├── contacts/            # Contacts manager
    │   └── date/                # Date manager
    │   └── seach/               # Search manager
    ├── google_service/          # Google API integration
    ├── prompts/                 # System prompts for agents
    └── utils/                   # Utility functions and helpers
    └── evaluation_notebooks/    # Notebooks for evaluations and safety
    └── test_notebooks/          # Playground Notebooks
```

***

## 🛠  For development

This project uses **Poetry** to manage dependencies and virtual environments efficiently.

### 1. Install Poetry

Ensure you have Poetry installed:

```bash
curl -sSL https://install.python-poetry.org | python3 -
```

Verify the installation:

```bash
poetry --version
```

### 2. Initialize Poetry in the Project (First-Time Setup Only)

If this is the first time setting up the project, navigate to the project folder and initialize Poetry:

```bash
cd google_workspace_agent
poetry init
```

If the project is already initialized, skip this step and proceed to dependency installation.

### 3. Install Dependencies

Add the new dependencies to the project, for example:

```bash
poetry add langgraph langchain
```

For development dependencies, use the following:

```bash
poetry add --dev black pytest
```

### 4. Activate the Virtual Environment

Poetry automatically creates a virtual environment. To activate it, first make sure to have installed :

```bash
poetry self add poetry-plugin-shell
```

Then, activate the virtual environment:

```bash
poetry shell
```

To run a script within the virtual environment without activating it:

```bash
poetry run python main.py
```

### 5. Store Virtual Environment in the Project (Optional)

To keep the virtual environment inside the project folder:

```bash
poetry config virtualenvs.in-project true
poetry install
```

This will create a `.venv/` directory inside the project.

### 6. Check the Environment Status

To view environment details:

```bash
poetry env info
```

To list installed dependencies:

```bash
poetry show
```

### 7. Reproducing the Environment on Another Machine

When cloning the project, run:

```bash
poetry install
```

This will install all dependencies as specified in `pyproject.toml` and `poetry.lock`.

### 8. Generating the requirements.txt using Poetry

Make sure the poetry-plugin-export plugin is installed. If not, you can install it with the following command:
`poetry self add poetry-plugin-export`.

Then, export your project’s dependencies to a requirements.txt file using:

```bash
poetry export --without-hashes -f requirements.txt --output requirements.txt
```

### 9. Pre-commit Setup

Once you have installed the dependencies using `poetry install`, you will need to configure pre-commit hooks:

```python
pre-commit install
```

This command sets up the pre-commit hooks that automatically format your code according to the rules defined in the `.pre-commit-config.yaml` file. The hooks are executed before each commit, and if any rule fails, the commit will be blocked. You can also run the hooks manually with:

```python
pre-commit run --all
```

***

## 🔐 Setting Up Google Cloud OAuth App

To allow your application to access a user's Google account (Calendar, Contacts, Gmail, etc.), follow these steps:

### 1. Create a Google Cloud Project

1. Go to [Google Cloud Console](https://console.cloud.google.com/).
2. Create a new project or select an existing one.

### 2. Configure the OAuth Consent Screen

1. In the left sidebar, go to **APIs & Services > OAuth consent screen**.
2. Choose **User Type: External**.
3. Fill in:

   * **App name** (e.g. `Google Workspace Agent`)
   * **User support email**
   * **Developer contact info**
4. Save and continue.
5. Add yourself (and any testers) under **Test Users** if your app is in **testing mode** (required unless app is published).
6. Submit and finish.

### 3. Create OAuth Credentials

1. Go to **APIs & Services > Credentials**.
2. Click **Create Credentials > OAuth Client ID**.
3. Choose **Application type: Desktop app**.
4. Name it (e.g. `Local Agent Auth`).
5. Click **Create**.
6. Copy your:

   * **Client ID**
   * **Client Secret**
   * Download the `.json` config file

### 4. Enable Required Google APIs

Go to **APIs & Services > Library** and enable the following:

* ✅ **Google Calendar API**
* ✅ **Google People API**
* ✅ **Gmail API**
* ✅ **OAuth2 API**

### 5. Add Environment Variables

In your `.env` file, define:

```env
GOOGLE_PROJECT_CREDENTIALS_PATH=your_project_credentials_path_here
GOOGLE_CLIENT_ID=your_client_id_here
GOOGLE_CLIENT_SECRET=your_client_secret_here
GOOGLE_TOKEN_URL=https://oauth2.googleapis.com/token
```

***

## 👤 Linking a Google Account to a User

After you’ve set up the OAuth credentials, follow these steps to associate a Google account with a local user in your system:

### 1. Run the Consent Flow Script

```bash
python src/google_service/consent_flow.py
```

This script will:

* Open a browser window where the user logs in to their Google account.
* Ask the user to authorize the application.
* Request an authorization code.
* Exchange the code for a `refresh_token` and use it to:

  * Fetch the user's Google email address
  * Store the account under a local username

### 2. Follow the Prompts

You will be asked to:

* Paste the **authorization code** from the browser.
* Provide a **username** to associate the Google account with.
* Provide a **account\_info** to associate the Google account with(this information will be used to identify the account).

Once completed, the Google account will be saved and linked to the local user.

### 3. View Associated Accounts

You can use the following code snippet to list accounts for a user:

```python
from google_service.core import UserService

service = UserService()
accounts = service.list_accounts("your_username")

for acc in accounts:
    print(f"Email: {acc.account_email} - Expires: {acc.credentials.expiry}")
```

***

## 🧪 Testing

This project includes comprehensive tests to ensure the reliability and functionality of all components. The test suite covers agents, Google services, and prompt management.

### Running Tests

To execute the test suite, make sure you have the development dependencies installed:

```bash
poetry install --with dev
```

Then run the tests using pytest:

```bash
# Run all tests
poetry run pytest

# Run tests with verbose output
poetry run pytest -v

# Run tests from a specific directory
poetry run pytest test/agents/

# Run tests with coverage report
poetry run pytest --cov=src

# Run only integration test
pytest -m integration
```

### ⚠️ Important Note on Test Costs

**The `integration` tests utilize the LLM and will incur costs when executed.** These tests make actual API calls to the language model to verify agent behavior and responses.

Before running agent tests, ensure you have:

* Valid API credentials configured
* Sufficient API credits/budget
* Understanding of the associated costs

To minimize costs during development, you can:

* Run specific test files instead of the full suite

## ▶️ Run the Orchestrator

Once you have completed the previous steps, you can run the orchestrator.

Run the `test_end_to_end.ipynb` notebook. It will include create an interactive cell for chat.

***
