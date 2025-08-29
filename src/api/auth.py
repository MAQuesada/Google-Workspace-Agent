from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import JWTError, jwt

from utils.logger import get_logger

logger = get_logger("api.auth")


class APIKeyProvider:
    """To generate api_key and to check api_key for validity

    Args:
        secret: used for encode and decode api_key
    """

    def __init__(self, secret: str):
        self.secret = secret

    def get_api_key(self, time_out: Optional[int] = None) -> str:
        if time_out is None:
            exp = timedelta(weeks=100)
        else:
            exp = timedelta(days=time_out)

        logger.debug(
            "Generating API key",
            extra={
                "expiration_time": f"{exp} into the future",
            },
        )
        return jwt.encode(
            {
                "sub": "DMS",
                "exp": datetime.now(timezone.utc) + exp,
            },
            self.secret,
        )

    def check_api_key(self, api_key: str) -> bool:
        """
        Checks if api_key is valid and not expired

        Returns:
            True if api_key is valid, False otherwise
        """
        logger.info("Checking API key.")
        try:
            jwt.decode(api_key, self.secret)
        except JWTError:
            logger.debug("Invalid or expired API key")
            return False

        logger.info("API key is valid")
        return True
