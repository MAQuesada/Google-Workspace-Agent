import streamlit as st
import requests
import time
import json
from dotenv import load_dotenv
import os
import webbrowser
import logging
from enum import Enum
from typing import Optional

# Import functions from the separate oauth.py script
from oauth import (
    initiate_oauth_flow,
    process_oauth_callback,
    get_oauth_code,
    clear_oauth_code
)

load_dotenv()

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Constants
class UIConstants:
    MIN_USERNAME_LENGTH = 3
    MAX_ACCOUNT_LABEL_LENGTH = 50
    OAUTH_TIMEOUT_SECONDS = 300
    API_TIMEOUT_SECONDS = 30

class OAuthState(Enum):
    IDLE = "idle"
    IN_PROGRESS = "in_progress"
    CODE_RECEIVED = "code_received"
    COMPLETED = "completed"
    FAILED = "failed"

# Configuration and API Client
class Config:
    def __init__(self):
        self.GOOGLE_CLIENT_ID = self._get_required_env("GOOGLE_CLIENT_ID")
        self.GOOGLE_CLIENT_SECRET = self._get_required_env("GOOGLE_CLIENT_SECRET")
        self.GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
        self.API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000")

    def _get_required_env(self, key: str) -> str:
        value = os.getenv(key)
        if not value:
            raise ValueError(f"Required environment variable {key} is not set")
        return value

# Custom exceptions
class AuthenticationError(Exception):
    pass

class APIError(Exception):
    pass

class APIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    def _make_request(self, method: str, url: str, **kwargs):
        """Make API request with proper error handling"""
        try:
            resp = requests.request(method, url, timeout=UIConstants.API_TIMEOUT_SECONDS, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise APIError("Request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise APIError("Cannot connect to API server. Please check if the server is running.")
        except requests.exceptions.HTTPError as e:
            if resp.status_code == 401:
                raise AuthenticationError("Invalid API key or unauthorized")
            elif resp.status_code == 404:
                raise APIError("Resource not found")
            else:
                raise APIError(f"API request failed: {str(e)}")
        except Exception as e:
            raise APIError(f"Unexpected error: {str(e)}")

    def login(self, username: str):
        url = f"{self.base_url}/user/"
        return self._make_request("GET", url, params={"username": username}, headers=self.headers)

    def associate_account(self, username: str, refresh_token: str, account_info: str):
        url = f"{self.base_url}/user/associate_account"
        params = {"username": username, "refresh_token": refresh_token, "account_info": account_info}
        return self._make_request("POST", url, params=params, headers=self.headers)

    def dissociate_account(self, username: str, account_email: str):
        url = f"{self.base_url}/user/dissociate_account"
        params = {"username": username, "account_email": account_email}
        return self._make_request("POST", url, params=params, headers=self.headers)

    def get_chat_history(self, username: str, conversation_id: str):
        url = f"{self.base_url}/chat/history"
        params = {"username": username, "conversation_id": conversation_id}
        return self._make_request("GET", url, params=params, headers=self.headers)

    def start_chat_stream(self, username: str, conversation_id: str, message: str):
        url = f"{self.base_url}/chat"
        json_data = {"username": username, "conversation_id": conversation_id, "message": message}
        resp = requests.post(url, json=json_data, headers=self.headers, stream=True, timeout=UIConstants.API_TIMEOUT_SECONDS)
        resp.raise_for_status()
        return resp.iter_content(chunk_size=1024)

# Input validation functions
def validate_username(username: str) -> str:
    """Validate and clean username input"""
    if not username or not username.strip():
        raise ValueError("Username cannot be empty")
    username = username.strip()
    if len(username) < UIConstants.MIN_USERNAME_LENGTH:
        raise ValueError(f"Username must be at least {UIConstants.MIN_USERNAME_LENGTH} characters")
    return username

def validate_account_label(label: str) -> str:
    """Validate and clean account label input"""
    if not label or not label.strip():
        raise ValueError("Account label cannot be empty")
    label = label.strip()
    if len(label) > UIConstants.MAX_ACCOUNT_LABEL_LENGTH:
        raise ValueError(f"Account label must be less than {UIConstants.MAX_ACCOUNT_LABEL_LENGTH} characters")
    return label

def initialize_session_state():
    """Initialize all session state variables with default values"""
    defaults = {
        "api_client": None,
        "is_authenticated": False,
        "username": None,
        "accounts": [],
        "oauth_state": OAuthState.IDLE,
        "account_label": "",
        "api_key": "",
        "oauth_flow_data": None,
        "config": None,
    }

    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default

def show_error(message: str, technical_details: Optional[str] = None):
    """Show user-friendly error with optional technical details"""
    st.error(message)
    if technical_details:
        with st.expander("Technical Details"):
            st.code(technical_details)

def render_login_form():
    """Render the login form"""
    st.subheader("Login")

    api_key_input = st.text_input("API Key", type="password", value=st.session_state.api_key)
    username_input = st.text_input("Username", value=st.session_state.username if st.session_state.username else "")

    if st.button("Login", type="primary"):
        if not api_key_input or not username_input.strip():
            st.warning("Please enter both API Key and Username.")
            return

        try:
            username = validate_username(username_input)

            with st.spinner("Logging in..."):
                client = APIClient(st.session_state.config.API_BASE_URL, api_key_input)
                data = client.login(username)

            if "error" in data and "not found" in data["error"].lower():
                st.info(f"User '{username}' not found. Creating new user...")
                with st.spinner("Creating user..."):
                    resp = requests.post(
                        f"{st.session_state.config.API_BASE_URL}/user/",
                        params={"username": username},
                        headers={"X-API-Key": api_key_input},
                        timeout=UIConstants.API_TIMEOUT_SECONDS
                    )
                    resp.raise_for_status()
                    data = resp.json()

            if "error" in data:
                raise APIError(data["error"])

            st.success(f"Logged in as {username}")
            st.session_state.api_client = client
            st.session_state.is_authenticated = True
            st.session_state.username = username
            st.session_state.accounts = data.get("accounts", [])
            st.session_state.api_key = api_key_input

            logger.info(f"User {username} logged in successfully")
            st.rerun()

        except ValueError as e:
            st.warning(str(e))
        except AuthenticationError as e:
            show_error("Authentication failed. Please check your API key.", str(e))
        except APIError as e:
            show_error("Login failed. Please try again.", str(e))
        except Exception as e:
            show_error("An unexpected error occurred during login.", str(e))
            logger.error(f"Login error for user {username_input}: {str(e)}")

# Added helper function to gracefully stop the OAuth server thread
def cleanup_oauth_flow():
    if "oauth_flow_data" in st.session_state and st.session_state.oauth_flow_data and "server_thread" in st.session_state.oauth_flow_data:
        server_thread = st.session_state.oauth_flow_data["server_thread"]
        if server_thread and server_thread.is_alive():
            logger.info("Attempting to shut down OAuth server...")
            server_thread.server.shutdown()
            server_thread.join()
            st.session_state.oauth_flow_data["server_thread"] = None
            logger.info("OAuth server shut down successfully.")

def render_oauth_flow():
    """Render OAuth flow UI and handle state transitions."""

    # Check for received OAuth code and transition state if necessary.
    received_code = get_oauth_code()
    if received_code and st.session_state.oauth_state == OAuthState.IN_PROGRESS:
        st.session_state.oauth_state = OAuthState.CODE_RECEIVED
        st.success("Authentication code received! You can now complete the association.")
        st.rerun()

    if st.session_state.oauth_state == OAuthState.IN_PROGRESS:
        st.info("🔄 **OAuth Authentication in Progress**")

        # Create columns for better layout
        col1, col2 = st.columns([2, 1])

        with col1:
            st.markdown("""
            **Steps to complete authentication:**
            1. ✅ Complete the authentication in the browser tab that opened
            2. 🔄 **Click 'Check for Authentication' button below after completing step 1**
            3. 📝 Provide account label when prompted

            If the browser tab didn't open, click 'Restart Authentication' below.
            """)

            # Show the current OAuth URL for manual access if needed
            if st.session_state.oauth_flow_data:
                with st.expander("Manual Authentication Link"):
                    st.write("If the browser didn't open automatically, use this link:")
                    st.code(st.session_state.oauth_flow_data["auth_url"])

        with col2:
            st.markdown("### Actions")

            # Big prominent button to check for authentication
            if st.button("🔍 Check for Authentication", type="primary", use_container_width=True):
                with st.spinner("Checking authentication status..."):
                    time.sleep(1)  # Brief pause to check
                st.rerun()

            st.markdown("---")

            # Secondary actions
            if st.button("🔄 Restart Authentication", type="secondary", use_container_width=True):
                # Clear current state and restart
                cleanup_oauth_flow() # Ensure cleanup on restart
                st.session_state.oauth_state = OAuthState.IDLE
                st.session_state.oauth_flow_data = None
                clear_oauth_code()
                time.sleep(0.5)
                start_oauth_flow("association")

            if st.button("❌ Cancel", type="secondary", use_container_width=True):
                cleanup_oauth_flow() # Ensure cleanup on cancel
                st.session_state.oauth_state = OAuthState.IDLE
                st.session_state.oauth_flow_data = None
                clear_oauth_code()
                st.rerun()

        # Add a troubleshooting section
        with st.expander("🔧 Troubleshooting"):
            st.markdown("""
            **If authentication isn't working:**

            1. **Browser didn't open?** Use the manual link above
            2. **Completed authentication but page not updating?** Click 'Check for Authentication'
            3. **Getting errors?** Try 'Restart Authentication'
            4. **Still stuck?** Try refreshing the entire page (F5)

            **Debug Info:**
            - OAuth State: `{}`
            - Code Received: `{}`
            """.format(st.session_state.oauth_state, "Yes" if received_code else "No"))

    elif st.session_state.oauth_state == OAuthState.CODE_RECEIVED:
        st.success("✅ **Authentication Successful!**")
        st.info("Now please provide a label for your Google account:")

        account_label = st.text_input(
            "Account Label (e.g., work, personal, project-name):",
            value=st.session_state.account_label,
            help="This helps you identify this Google account",
            key="account_info_input",
            placeholder="Enter a descriptive label..."
        )
        st.session_state.account_label = account_label

        col1, col2 = st.columns(2)
        with col1:
            if st.button("✅ Complete Association", type="primary", disabled=not account_label.strip()):
                if not account_label.strip():
                    st.warning("Please provide a label for the account.")
                    return

                try:
                    validated_label = validate_account_label(account_label)

                    with st.spinner("Associating account with your profile..."):
                        result = process_oauth_callback(
                            code=get_oauth_code(),
                            redirect_uri=st.session_state.oauth_flow_data["redirect_uri"],
                            code_verifier=st.session_state.oauth_flow_data["code_verifier"],
                            username=st.session_state.username,
                            account_info=validated_label,
                            api_client=st.session_state.api_client,
                            config=st.session_state.config
                        )

                    if result["success"]:
                        st.balloons()  # Celebration animation
                        st.success(f"🎉 **Success!** Account `{result['email']}` has been associated with your profile!")
                        st.session_state.accounts = [result["account_details"]]
                        st.session_state.oauth_state = OAuthState.COMPLETED
                        st.session_state.account_label = ""
                        st.session_state.oauth_flow_data = None
                        clear_oauth_code()
                        logger.info(f"OAuth association successful for user {st.session_state.username}")
                        time.sleep(3)  # Show success message for a bit
                        st.rerun()
                    else:
                        st.session_state.oauth_state = OAuthState.FAILED
                        show_error(f"❌ Association failed: {result['error']}")
                        logger.error(f"OAuth association failed for user {st.session_state.username}: {result['error']}")

                except ValueError as e:
                    st.warning(f"⚠️ Input validation error: {str(e)}")
                except Exception as e:
                    st.session_state.oauth_state = OAuthState.FAILED
                    show_error("❌ Unexpected error during association", str(e))
                    logger.error(f"OAuth association error for user {st.session_state.username}: {str(e)}")

        with col2:
            if st.button("❌ Cancel", type="secondary"):
                cleanup_oauth_flow() # Ensure cleanup on cancel
                st.session_state.oauth_state = OAuthState.IDLE
                st.session_state.account_label = ""
                st.session_state.oauth_flow_data = None
                clear_oauth_code()
                st.rerun()

    elif st.session_state.oauth_state == OAuthState.FAILED:
        st.error("❌ **Authentication Failed**")
        st.info("Please try again or check the troubleshooting guide below.")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("🔄 Try Again", type="primary"):
                cleanup_oauth_flow() # Ensure cleanup before trying again
                st.session_state.oauth_state = OAuthState.IDLE
                st.session_state.oauth_flow_data = None
                clear_oauth_code()
                time.sleep(0.5)
                start_oauth_flow("association")

        with col2:
            if st.button("🏠 Back to Main", type="secondary"):
                cleanup_oauth_flow() # Ensure cleanup before going back
                st.session_state.oauth_state = OAuthState.IDLE
                st.session_state.oauth_flow_data = None
                clear_oauth_code()
                st.rerun()

def render_account_management():
    """Render account management section"""
    st.subheader("Google Account Management")
    if st.session_state.accounts:
        account = st.session_state.accounts[0]  # Assuming single account for now
        
        # Check account status
        account_status = account.get("details", "Unknown status")
        is_expired = "expired" in account_status.lower() or "revoked" in account_status.lower()
        
        if is_expired:
            st.warning(f"Account {account.get('account_email')}: {account_status}")
            st.info("Please re-authenticate to refresh your tokens.")
        else:
            st.success(f"Associated Google Account: **{account.get('account_email')}**")
            st.write(f"Label: **{account.get('account_info', '[No label]')}**")
            st.write(f"Status: {account_status}")
            
        col1, col2, col3 = st.columns(3)
        
        with col1:
            if st.button("Go to Chat", type="primary", disabled=is_expired):
                st.switch_page("pages/chat.py")
        
        with col2:
            if st.button("Re-authenticate"):
                start_oauth_flow("re-authentication")
        
        with col3:
            if st.button("Dissociate Account", type="secondary"):
                try:
                    with st.spinner("Dissociating account..."):
                        st.session_state.api_client.dissociate_account(
                            st.session_state.username,
                            account["account_email"]
                        )
                    st.success("Account dissociated successfully.")
                    st.session_state.accounts = []
                    logger.info(f"Account dissociated for user {st.session_state.username}")
                    st.rerun()
                except Exception as e:
                    show_error("Failed to dissociate account", str(e))
                    logger.error(f"Account dissociation failed for user {st.session_state.username}: {str(e)}")
                    
    else:
        # No associated accounts - prompt to associate
        st.warning("No Google accounts associated with your profile.")
        st.info("You need to associate a Google account to access workspace features and chat.")
        
        if st.button("Associate Google Account", type="primary"):
            start_oauth_flow("association")
            
def start_oauth_flow(flow_type: str):
    """Start OAuth flow with better error handling and user feedback"""
    try:
        with st.spinner("🚀 Preparing authentication flow..."):
            oauth_data = initiate_oauth_flow(st.session_state.username, st.session_state.config)

        # Try to open browser
        try:
            webbrowser.open(oauth_data["auth_url"])
            browser_opened = True
        except Exception as e:
            logger.warning(f"Failed to open browser automatically: {str(e)}")
            browser_opened = False

        # Update session state, now storing the server thread object
        st.session_state.oauth_state = OAuthState.IN_PROGRESS
        st.session_state.oauth_flow_data = oauth_data

        # Show appropriate message based on whether browser opened
        if browser_opened:
            st.info("🌐 Browser tab opened for authentication. Please complete the process and then click 'Check for Authentication'.")
        else:
            st.warning("⚠️ Couldn't open browser automatically. Please use the manual link that will appear on the next screen.")

        logger.info(f"OAuth flow started for user {st.session_state.username} - {flow_type}")

        # CRITICAL: Force a rerun to update the UI
        st.rerun()

    except Exception as e:
        st.session_state.oauth_state = OAuthState.FAILED
        show_error(f"❌ Failed to start {flow_type} flow", str(e))
        logger.error(f"OAuth flow start failed for user {st.session_state.username}: {str(e)}")

# Add this helper function to provide better debugging info
def debug_oauth_state():
    """Debug function to show OAuth state in sidebar (for development)"""
    if st.sidebar.checkbox("Show Debug Info", value=False):
        st.sidebar.write("**Debug Information:**")
        st.sidebar.write(f"OAuth State: {st.session_state.oauth_state}")
        st.sidebar.write(f"Code Present: {'Yes' if get_oauth_code() else 'No'}")
        st.sidebar.write(f"Flow Data: {'Yes' if st.session_state.oauth_flow_data else 'No'}")
        
        if st.sidebar.button("Clear OAuth State"):
            cleanup_oauth_flow() # Ensure cleanup on manual clear
            st.session_state.oauth_state = OAuthState.IDLE
            st.session_state.oauth_flow_data = None
            clear_oauth_code()
            st.rerun()

def render_help_section():
    """Render help and information section"""
    with st.expander("Help & Information", expanded=False):
        st.markdown("""
        ### How to use this application:
        
        1. **Login**: Enter your API key and username
        2. **Associate Google Account**: Connect your Google Workspace account
        3. **Provide Context**: Label your account (work/personal/etc.)
        4. **Chat**: Use natural language to interact with Google Workspace services
        
        ### Troubleshooting:
        - **No refresh token**: Revoke app permissions in your Google Account settings and try again
        - **Authentication failed**: Make sure you're using the correct Google account
        - **Token expired**: Use the re-authenticate button to refresh your tokens
        - **API errors**: Check that your API key is valid and the backend service is running
        - **Connection issues**: Verify the API server is running on the correct port
        
        ### Security Notes:
        - Your API key is stored only for this session
        - OAuth tokens are securely managed by the backend
        - Close this browser tab when finished to clear session data
        """)

def main():
    st.title("Google Workspace Multi-Agent Interface")
    debug_oauth_state()

    # Initialize session state and config
    initialize_session_state()
    
    try:
        if not st.session_state.config:
            st.session_state.config = Config()
    except ValueError as e:
        st.error(f"Configuration error: {str(e)}")
        st.stop()
    
    # Login Section
    if not st.session_state.is_authenticated:
        render_login_form()
        return

    # User is authenticated - show main interface
    st.markdown("---")
    st.subheader(f"Welcome, {st.session_state.username}!")
    
    # Logout button
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Logout", type="secondary"):
            # Clear all session state
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            clear_oauth_code()
            st.success("Logged out successfully!")
            logger.info("User logged out")
            time.sleep(1)
            st.rerun()

    # Handle OAuth flow states
    if st.session_state.oauth_state != OAuthState.IDLE:
        render_oauth_flow()
        # Only render the oauth flow UI when it is in progress
        if st.session_state.oauth_state in [OAuthState.IN_PROGRESS, OAuthState.CODE_RECEIVED, OAuthState.FAILED]:
            return
    
    # Account management
    render_account_management()
    
    # Help section
    render_help_section()

if __name__ == "__main__":
    main()
