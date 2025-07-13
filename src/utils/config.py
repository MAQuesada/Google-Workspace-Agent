from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings

import pytz
from pytz import BaseTzInfo


class Config(BaseSettings):
    OPENAI_API_KEY: str = ""
    MAIN_MODEL: str = "gpt-4o-2024-08-06"
    MINI_MODEL: str = "gpt-4o-mini"

    LANGSMITH_TRACING: bool = True
    LANGSMITH_ENDPOINT: str = "https://api.smith.langchain.com"
    LANGSMITH_API_KEY: str = ""
    LANGSMITH_PROJECT: str = ""

    POSTGRES_DB_URI: str = (
        "postgresql://postgres:postgres@localhost:5432/"
        "checkpoint_lgraph?sslmode=disable"
    )
    DB_PATH: str = "data.sb"
    TIMEZONE: BaseTzInfo = pytz.timezone("Europe/Paris")
    MAX_NUM_DISPLAY_ITEMS: int = 10

    GOOGLE_PROJECT_CREDENTIALS_PATH: str = "google_credentials.json"
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    GOOGLE_TOKEN_URL: str = "https://oauth2.googleapis.com/token"
    GOOGLE_SCOPES: List[str] = [
        "https://www.googleapis.com/auth/contacts",
        "https://www.googleapis.com/auth/contacts.other.readonly",
        "https://www.googleapis.com/auth/calendar",
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://mail.google.com/",
    ]

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache
def get_config() -> Config:
    """Returns a cached instance of the Config class."""
    return Config()
