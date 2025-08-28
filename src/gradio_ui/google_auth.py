import gradio as gr
import hashlib
import base64
import os
import urllib.parse
import requests
from typing import Tuple, Dict, Any
import logging

logger = logging.getLogger(__name__)

class GoogleAuthHandler:
    """Handles Google OAuth flow for Gradio UI."""

    def __init__(self):
        # Load securely from environment variables
        self.client_id = os.getenv("GOOGLE_CLIENT_ID")
        self.client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        self.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"  # For installed apps
        self.scopes = [
            "https://www.googleapis.com/auth/calendar",
            "https://www.googleapis.com/auth/contacts",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/drive.readonly",
            "openid", "email", "profile"
        ]

    def generate_pkce_pair(self) -> Tuple[str, str]:
        """Generate PKCE code verifier and challenge."""
        verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        return verifier, challenge

    def build_auth_url(self, code_challenge: str, login_hint: str = "") -> str:
        """Build the Google OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
            "scope": " ".join(self.scopes),
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        if login_hint:
            params["login_hint"] = login_hint

        return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"

    def exchange_code_for_tokens(self, code: str, code_verifier: str) -> Dict[str, Any]:
        """Exchange authorization code for tokens."""
        data = {
            "code": code,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "redirect_uri": self.redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }

        response = requests.post("https://oauth2.googleapis.com/token", data=data)

        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.text}")
            raise Exception("Failed to exchange authorization code for tokens. Please retry.")

        return response.json()

    def get_user_email(self, access_token: str) -> str:
        """Get user email from access token."""
        response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            logger.error(f"Failed getting user info: {response.text}")
            raise Exception("Failed to fetch user info. Please retry.")

        return response.json()["email"]


def create_auth_interface(api_client):
    """Create the Google authentication interface."""

    auth_handler = GoogleAuthHandler()

    # Use a per-user dictionary to store PKCE verifiers for better state management
    auth_state: Dict[str, str] = {}

    def start_auth_flow(user_id: str, login_hint: str = "") -> Tuple[str, str, str]:
        """Start the Google OAuth flow."""
        if not user_id.strip():
            return "Please enter a User ID", "", ""

        try:
            code_verifier, code_challenge = auth_handler.generate_pkce_pair()
            auth_state[user_id.strip()] = code_verifier

            auth_url = auth_handler.build_auth_url(code_challenge, login_hint)

            instructions = """
## Step-by-Step Instructions:

1. **Click the authorization URL** below (it will open in a new tab)
2. **Sign in** to your Google account
3. **Grant permissions** when prompted
4. **Copy the authorization code** that appears on the final page
5. **Paste the code** in the field below and click 'Complete Authentication'
            """

            return instructions, auth_url, ""

        except Exception as e:
            logger.error(f"Error starting auth flow: {e}")
            return f"Error: {str(e)}", "", ""

    def complete_auth_flow(user_id: str, auth_code: str, account_info: str = "") -> Tuple[str, str]:
        """Complete the Google OAuth flow and add account to user."""
        if not user_id.strip() or not auth_code.strip():
            return "Please provide both User ID and Authorization Code", ""

        code_verifier = auth_state.get(user_id.strip())
        if not code_verifier:
            return "Please start the authentication flow first", ""

        try:
            # Exchange code for tokens
            token_data = auth_handler.exchange_code_for_tokens(auth_code.strip(), code_verifier)

            refresh_token = token_data.get("refresh_token")
            access_token = token_data.get("access_token")

            if not refresh_token:
                return "No refresh token received. Please try again with a new authorization.", ""

            # Get user email
            email = auth_handler.get_user_email(access_token)

            # Add account via API
            result = api_client.add_google_account(
                user_id=user_id.strip(),
                refresh_token=refresh_token,
                account_info=account_info or f"Google account: {email}"
            )

            if result["success"]:
                account_details = f"Email: {email}\nAccount Info: {account_info or 'N/A'}"
                return result["message"], account_details
            else:
                return f"API Error: {result['message']}", ""

        except Exception as e:
            logger.error(f"Error completing auth flow: {e}")
            return f"Error: {str(e)}", ""

        finally:
            # Clear auth state for user
            auth_state.pop(user_id.strip(), None)

    def get_user_accounts(user_id: str) -> str:
        """Get and display user's Google accounts."""
        if not user_id.strip():
            return "Please enter a User ID"

        result = api_client.get_user_accounts(user_id.strip())

        if result["success"]:
            accounts = result["data"]
            if not accounts:
                return "No Google accounts found for this user"

            account_list = []
            for account in accounts:
                email = account.get("account_email", "Unknown")
                info = account.get("account_info", "N/A")
                account_list.append(f"• {email}\n  Info: {info}")

            return "\n\n".join(account_list)
        else:
            return f"Error: {result['message']}"

    # UI Components
    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## Google Account Authentication")

            user_id_input = gr.Textbox(
                label="User ID",
                placeholder="Enter the user ID from User Management tab",
                info="The user must exist before adding Google accounts"
            )

            login_hint_input = gr.Textbox(
                label="Email Hint (Optional)",
                placeholder="user@gmail.com",
                info="Pre-fill the Google login with this email"
            )

            start_auth_btn = gr.Button("Start Google Authentication", variant="primary")

            gr.Markdown("---")

            auth_code_input = gr.Textbox(
                label="Authorization Code",
                placeholder="Paste the code from Google here",
                info="Complete the authentication in your browser first"
            )

            account_info_input = gr.Textbox(
                label="Account Description (Optional)",
                placeholder="e.g., Work account, Personal account",
                info="Optional description for this Google account"
            )

            complete_auth_btn = gr.Button("Complete Authentication", variant="secondary")

        with gr.Column(scale=1):
            gr.Markdown("## Authentication Instructions")

            instructions_display = gr.Markdown("")

            auth_url_display = gr.Textbox(
                label="Authorization URL",
                interactive=False,
                info="Click this URL to start authentication"
            )

            gr.Markdown("## Account Management")

            check_accounts_btn = gr.Button("View User's Google Accounts")

            account_status = gr.Textbox(
                label="Status",
                lines=3,
                interactive=False
            )

            account_details = gr.Textbox(
                label="Account Details",
                lines=3,
                interactive=False
            )

            accounts_display = gr.Textbox(
                label="User's Google Accounts",
                lines=8,
                interactive=False
            )

    # Event handlers
    start_auth_btn.click(
        fn=start_auth_flow,
        inputs=[user_id_input, login_hint_input],
        outputs=[instructions_display, auth_url_display, account_status]
    )

    complete_auth_btn.click(
        fn=complete_auth_flow,
        inputs=[user_id_input, auth_code_input, account_info_input],
        outputs=[account_status, account_details]
    )

    check_accounts_btn.click(
        fn=get_user_accounts,
        inputs=[user_id_input],
        outputs=[accounts_display]
    )

    return {
        "user_id_input": user_id_input,
        "auth_url_display": auth_url_display,
        "account_status": account_status
    }
