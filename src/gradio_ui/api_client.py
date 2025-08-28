import requests
import json
from typing import Dict, Any, Optional
import logging
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

class APIClient:
    """Client for communicating with the Google Workspace Agent API."""
    
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()

        # Setup retries for reliability
        retries = Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

        self.session.headers.update({
            'Content-Type': 'application/json'
            # 'Authorization': 'Bearer <token>'  # Add if API requires authorization
        })
    
    def create_user(self, username: str) -> Dict[str, Any]:
        """Create a new user via API."""
        try:
            response = self.session.post(
                f"{self.base_url}/users",
                json={"username": username},
                timeout=10
            )
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "message": f"User '{username}' created successfully"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error creating user: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": f"Failed to create user '{username}'"
            }
    
    def add_google_account(self, user_id: str, refresh_token: str, account_info: str = "") -> Dict[str, Any]:
        """Add/update Google account for a user via API."""
        try:
            response = self.session.post(
                f"{self.base_url}/users/{user_id}/accounts",
                json={
                    "refresh_token": refresh_token,
                    "account_info": account_info
                },
                timeout=10
            )
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "message": "Google account added successfully"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error adding Google account: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to add Google account"
            }
    
    def chat(self, user_id: str, user_request: str) -> Dict[str, Any]:
        """Send chat request to the orchestrator via API."""
        try:
            response = self.session.post(
                f"{self.base_url}/users/{user_id}/chat",
                json={
                    "user_request": user_request
                },
                timeout=20
            )
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "message": "Chat processed successfully"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error in chat: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to process chat request"
            }
    
    def list_users(self) -> Dict[str, Any]:
        """Get list of all users via API."""
        try:
            response = self.session.get(f"{self.base_url}/users", timeout=10)
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "message": "Users retrieved successfully"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error listing users: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve users"
            }
    
    def get_user_accounts(self, user_id: str) -> Dict[str, Any]:
        """Get Google accounts for a user via API."""
        try:
            response = self.session.get(f"{self.base_url}/users/{user_id}/accounts", timeout=10)
            response.raise_for_status()
            return {
                "success": True,
                "data": response.json(),
                "message": "User accounts retrieved successfully"
            }
        except requests.exceptions.RequestException as e:
            logger.error(f"Error getting user accounts: {e}")
            return {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve user accounts"
            }
