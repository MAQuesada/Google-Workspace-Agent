import datetime
from typing import List, Optional
from uuid import uuid4

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from pydantic import BaseModel, Field


class GoogleAccountCredentials(BaseModel):
    client_id: str
    client_secret: str
    token: Optional[str]
    refresh_token: str
    token_uri: str
    expiry: Optional[datetime.datetime]

    # model_config = ConfigDict(arbitrary_types_allowed=True)

    @property
    def google_credentials(self) -> Credentials:
        return Credentials(
            token=self.token,
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri=self.token_uri,
            expiry=self.expiry,
        )

    @property
    def expired(self):
        """Check if the token has expired."""
        current_datetime = datetime.datetime.now()
        return current_datetime + datetime.timedelta(minutes=5) > self.expiry

    def refresh(self) -> None:
        """Refresh the token."""
        creds = self.google_credentials
        creds.refresh(Request())
        self.token = creds.token
        self.expiry = creds.expiry


class GoogleAccount(BaseModel):
    account_email: str
    account_info: Optional[str] = None
    credentials: GoogleAccountCredentials


class User(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    username: str
    accounts: List[GoogleAccount] = []
