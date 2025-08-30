from typing import List

from fastapi import APIRouter

from google_service.core import get_user_service
from google_service.models import GoogleAccount, User
from utils.exceptions import CredentialsRefreshError
from utils.logger import get_logger

logger = get_logger("api.user_router")

router = APIRouter(prefix="/user", tags=["user"])


def get_dict_account(accounts: List[GoogleAccount]) -> list[dict]:
    """Get a list of dictionaries of accounts"""
    output_accounts = []
    for account in accounts:
        try:
            account.credentials.refresh()
            details = "Token refreshed successfully"
        except CredentialsRefreshError:
            details = "Token has been expired or revoked"
        output_accounts.append(
            {
                "account_email": account.account_email,
                "account_info": account.account_info,
                "details": details,
            }
        )
    return output_accounts


@router.get("/")
async def get_user(
    username: str,
):
    logger.info("Getting user.", extra={"username": username})
    user = get_user_service().load_user(username)

    if user is None:
        logger.warning("User not found.", extra={"username": username})
        return {"error": "User not found"}
    output_accounts = get_dict_account(user.accounts)
    logger.info("User found.", extra={"username": username})
    return {"accounts": output_accounts}


@router.post("/")
async def create_user(
    username: str,
):
    logger.info("Creating user.", extra={"username": username})
    user = get_user_service().load_user(username)
    if user:
        logger.warning("User already exists.", extra={"username": username})
        return {"error": "User already exists"}
    get_user_service().save_user(User(username=username))
    logger.info("User created successfully.", extra={"username": username})
    return {"username": username}


@router.post("/associate_account")
async def associate_account(
    username: str,
    refresh_token: str,
    account_info: str,
):
    logger.info(
        "Associating Google account.",
        extra={"username": username, "account_info": account_info},
    )
    get_user_service().associate_account(username, refresh_token, account_info)
    output_accounts = get_dict_account(get_user_service().load_user(username).accounts)
    logger.info(
        "Google account associated successfully.",
        extra={"username": username, "account_info": account_info},
    )
    return {"accounts": output_accounts}


@router.post("/dissociate_account")
async def dissociate_account(
    username: str,
    account_email: str,
):
    logger.info(
        "Dissociating Google account.",
        extra={"username": username, "account_email": account_email},
    )
    user = get_user_service().load_user(username)
    if user is None:
        logger.warning("Google user not found.", extra={"username": username})
        return {"error": "User not found"}
    if account_email not in [a.account_email for a in user.accounts]:
        logger.warning(
            "Google account not found.",
            extra={"username": username, "account_email": account_email},
        )
        return {"error": "Google account not found"}
    get_user_service().dissociate_account(username, account_email)
    user = get_user_service().load_user(username)
    output_accounts = get_dict_account(user.accounts)
    logger.info(
        "Google account dissociated successfully.",
        extra={"username": username, "account_email": account_email},
    )
    return {"accounts": output_accounts}
