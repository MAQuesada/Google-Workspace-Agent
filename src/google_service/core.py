import json
from typing import Optional, List

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from pydantic import ValidationError
import requests

from google_service.storage import KeyValueStore
from google_service.models import User, GoogleAccount, GoogleAccountCredentials

from utils.config import get_config
from utils.exceptions import UserError, CredentialsRefreshError

config = get_config()


class UserService:
    def __init__(self, store: Optional[KeyValueStore] = None):
        self.store = store or KeyValueStore()

    def _user_key(self, username: str) -> str:
        return f"user:{username}"

    def save_user(self, user: User):
        self.store.set(self._user_key(user.username), user.model_dump())

    def load_user(self, username: str) -> Optional[User]:
        data = self.store.get(self._user_key(username))
        if data:
            try:
                return User.model_validate(data)
            except ValidationError as e:
                print(f"Error validating user data: {e}")
                return None
        return None

    def list_accounts(self, username: str) -> List[GoogleAccount]:
        user = self.load_user(username)
        return user.accounts if user else []

    def list_users(self) -> List[str]:
        """Return a list of all registered usernames."""
        keys = self.store.list_keys("user:")
        return [key.replace("user:", "") for key in keys]

    def associate_account(
        self, username: str, refresh_token: str, account_info: str = ""
    ) -> GoogleAccount:
        user = self.load_user(username)
        if not user:
            user = User(username=username)

        with open(config.GOOGLE_PROJECT_CREDENTIALS_PATH, encoding="utf-8") as f:
            client_info = json.load(f)["installed"]

        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri=client_info["token_uri"],
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=config.GOOGLE_SCOPES,
        )

        credentials.refresh(Request())
        email = self.fetch_user_email(credentials)

        cred_model = GoogleAccountCredentials(
            client_id=credentials.client_id,
            client_secret=credentials.client_secret,
            token=credentials.token,
            refresh_token=credentials.refresh_token,
            token_uri=credentials.token_uri,
            expiry=credentials.expiry,
        )

        account = GoogleAccount(
            account_email=email,
            account_info=account_info,
            credentials=cred_model,
        )

        user.accounts = [a for a in user.accounts if a.account_email != email]
        user.accounts.append(account)

        self.save_user(user)
        return account

    def fetch_user_email(self, credentials: Credentials) -> str:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if response.status_code == 200:
            return response.json()["email"]
        raise UserError("Could not fetch user email")

    def get_account(
        self, username: str, account_email: str
    ) -> Optional[GoogleAccountCredentials]:
        """Get a Google account by username and email."""
        user = self.load_user(username)
        if not user:
            return None

        account = next(
            (a for a in user.accounts if a.account_email == account_email), None
        )
        if not account:
            return None

        if account.credentials.expired:
            try:
                account.credentials.refresh()
            except CredentialsRefreshError:
                # Persist the state and signal the caller to re-authenticate
                account.credentials.token = None
                account.credentials.expiry = None
                self.save_user(user)
                raise UserError(
                    "Your session has expired or the permissions were revoked. Please re-authenticate this account."
                )
            self.save_user(user)

        return account.credentials


def get_user_service():
    return UserService()
