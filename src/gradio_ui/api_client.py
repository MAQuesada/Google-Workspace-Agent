import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

class APIClient:
    def __init__(self, base_url: str, api_key: str = None):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
        })
        if api_key:
            self.session.headers.update({'X-API-Key': api_key})

    def create_user(self, username: str) -> Dict[str, Any]:
        try:
            resp = self.session.post(f"{self.base_url}/user/", json={"username": username})
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            logger.error(f"Error creating user: {e}")
            return {"success": False, "message": str(e)}

    def get_user_accounts(self, username: str) -> Dict[str, Any]:
        try:
            resp = self.session.get(f"{self.base_url}/user/", params={"username": username})
            resp.raise_for_status()
            return {"success": True, "data": resp.json().get("accounts", [])}
        except Exception as e:
            logger.error(f"Error fetching user accounts: {e}")
            return {"success": False, "message": str(e)}

    def associate_account(self, username: str, refresh_token: str, account_info: str = "") -> Dict[str, Any]:
        try:
            payload = {
                "username": username,
                "refresh_token": refresh_token,
                "account_info": account_info,
            }
            resp = self.session.post(f"{self.base_url}/user/associate_account", json=payload)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            logger.error(f"Error associating account: {e}")
            return {"success": False, "message": str(e)}

    def dissociate_account(self, username: str, account_email: str) -> Dict[str, Any]:
        try:
            payload = {
                "username": username,
                "account_email": account_email,
            }
            resp = self.session.post(f"{self.base_url}/user/dissociate_account", json=payload)
            resp.raise_for_status()
            return {"success": True, "data": resp.json()}
        except Exception as e:
            logger.error(f"Error dissociating account: {e}")
            return {"success": False, "message": str(e)}

    # You can add chat and other API methods similarly
