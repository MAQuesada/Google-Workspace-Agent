from api.auth import APIKeyProvider
from utils.config import Config, get_config
from fastapi import Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader
from typing import Protocol


class APIKeyCheckerProtocol(Protocol):
    def check_api_key(self, api_key: str) -> bool:
        """
        Checks if api_key is valid and not expired

        Returns:
            True if api_key is valid, False otherwise
        """
        ...


def get_auth_checker(
    config: Config = Depends(get_config),
) -> APIKeyCheckerProtocol:
    return APIKeyProvider(secret=config.SECRET_KEY)


def check_access(
    provider: APIKeyCheckerProtocol = Depends(get_auth_checker),
    api_key_header: str = Security(APIKeyHeader(name="X-API-Key")),
):
    """Check if the API key is valid."""
    if not provider.check_api_key(api_key_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid API key",
        )


if __name__ == "__main__":
    # To generate a new API key, run this script.
    print(
        "Api key:",
        APIKeyProvider(secret=get_config().SECRET_KEY).get_api_key(),
    )
