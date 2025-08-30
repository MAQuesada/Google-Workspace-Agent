from functools import lru_cache
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
from utils.logger import get_logger

logger = get_logger("google_service.core")

config = get_config()


class UserService:
    def __init__(self, store: Optional[KeyValueStore] = None):
        self.store = store or KeyValueStore()

    def _user_key(self, username: str) -> str:
        return f"user:{username}"

    def save_user(self, user: User):
        logger.info("Saving user.", extra={"username": user.username})
        self.store.set(self._user_key(user.username), user.model_dump())
        logger.info("User saved successfully.", extra={"username": user.username})

    def load_user(self, username: str) -> Optional[User]:
        logger.info("Loading user.", extra={"username": username})
        data = self.store.get(self._user_key(username))
        if data:
            try:
                user = User.model_validate(data)
                logger.info("User loaded successfully.", extra={"username": username})
                return user
            except ValidationError:
                logger.exception("Error validating user data.")
                return None
        logger.info("User not found.", extra={"username": username})
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
        logger.info("Associating account.", extra={"username": username})
        user = self.load_user(username)
        if not user:
            user = User(username=username)

        logger.info(
            "Creating credentials.",
            extra={"path": config.GOOGLE_PROJECT_CREDENTIALS_PATH},
        )
        with open(config.GOOGLE_PROJECT_CREDENTIALS_PATH, encoding="utf-8") as f:
            client_info = json.load(f)["installed"]
        logger.info("Credentials created.", extra={"client_info": client_info})

        credentials = Credentials(
            None,
            refresh_token=refresh_token,
            token_uri=client_info["token_uri"],
            client_id=client_info["client_id"],
            client_secret=client_info["client_secret"],
            scopes=config.GOOGLE_SCOPES,
        )
        logger.info("Credentials created.")

        credentials.refresh(Request())
        logger.info("Credentials refreshed successfully.")

        email = self.fetch_user_email(credentials)
        logger.info("User email fetched successfully.", extra={"email": email})

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
        logger.info("Account created successfully.", extra={"email": email})

        user.accounts = [a for a in user.accounts if a.account_email != email]
        user.accounts.append(account)
        logger.info(
            "Account associated to user successfully.", extra={"username": username}
        )

        self.save_user(user)
        logger.info("User saved successfully.", extra={"username": username})

        return account

    def dissociate_account(self, username: str, account_email: str) -> None:
        logger.info(
            "Dissociating account.",
            extra={"username": username, "account_email": account_email},
        )
        user = self.load_user(username)
        if not user:
            logger.warning("User not found.", extra={"username": username})
            return
        user.accounts = [a for a in user.accounts if a.account_email != account_email]
        self.save_user(user)
        logger.info(
            "Account dissociated successfully.",
            extra={"username": username, "account_email": account_email},
        )

    def fetch_user_email(self, credentials: Credentials) -> str:
        logger.info("Fetching user email.")
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/userinfo",
            headers={"Authorization": f"Bearer {credentials.token}"},
        )
        if response.status_code == 200:
            email = response.json()["email"]
            logger.info("User email fetched successfully.", extra={"email": email})
            return email
        logger.error("Could not fetch user email.")
        raise UserError("Could not fetch user email")

    def get_account(
        self, username: str, account_email: str
    ) -> Optional[GoogleAccountCredentials]:
        """Get a Google account by username and email."""
        user = self.load_user(username)
        if not user:
            logger.info("User not found.", extra={"username": username})
            return None

        account = next(
            (a for a in user.accounts if a.account_email == account_email), None
        )
        if not account:
            logger.info(
                "Account not found.",
                extra={"username": username, "account_email": account_email},
            )
            return None

        if account.credentials.expired:
            try:
                account.credentials.refresh()
                logger.info(
                    "Credentials refreshed successfully.",
                    extra={"username": username, "account_email": account_email},
                )

            except CredentialsRefreshError:
                # Persist the state and signal the caller to re-authenticate
                logger.info(
                    "Credentials expired or revoked.",
                    extra={"username": username, "account_email": account_email},
                )
                account.credentials.token = None
                account.credentials.expiry = None
                self.save_user(user)
                raise UserError(
                    "Your session has expired or the permissions were revoked. Please re-authenticate this account."
                )
            self.save_user(user)

        logger.info(
            "Account found.",
            extra={"username": username, "account_email": account_email},
        )
        return account.credentials


@lru_cache(maxsize=1)
def get_user_service():
    return UserService()
