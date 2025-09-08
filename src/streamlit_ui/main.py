import streamlit as st
import requests
import time
import webbrowser
from typing import Optional
from threading import Lock, Event
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
import socket
import urllib.parse


from streamlit_ui.oauth import (
    generate_oauth_url,
    exchange_code_for_tokens,
    get_user_email_from_token,
    validate_oauth_code,
    generate_pkce_pair,
)
from utils.config import get_config
from utils.logger import get_logger

logger = get_logger()


class UIConstants:
    MIN_USERNAME_LENGTH = 3
    MAX_ACCOUNT_LABEL_LENGTH = 50
    OAUTH_TIMEOUT_SECONDS = 300
    API_TIMEOUT_SECONDS = 30


class AuthenticationError(Exception):
    pass


class APIError(Exception):
    pass


class APIClient:
    def __init__(self, base_url: str, api_key: str):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    def _make_request(self, method: str, url: str, **kwargs):
        try:
            resp = requests.request(
                method, url, timeout=UIConstants.API_TIMEOUT_SECONDS, **kwargs
            )
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.Timeout:
            raise APIError("Request timed out. Please try again.")
        except requests.exceptions.ConnectionError:
            raise APIError(
                "Cannot connect to API server. Please check if the server is running."
            )
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
        return self._make_request(
            "GET", url, params={"username": username}, headers=self.headers
        )

    def associate_account(self, username: str, refresh_token: str, account_info: str):
        url = f"{self.base_url}/user/associate_account"
        params = {
            "username": username,
            "refresh_token": refresh_token,
            "account_info": account_info,
        }
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
        json_data = {
            "username": username,
            "conversation_id": conversation_id,
            "message": message,
        }
        resp = requests.post(
            url,
            json=json_data,
            headers=self.headers,
            stream=True,
            timeout=UIConstants.API_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        return resp.iter_content(chunk_size=1024)


# Input validation functions
def validate_username(username: str) -> str:
    if not username or not username.strip():
        raise ValueError("Username cannot be empty")
    username = username.strip()
    if len(username) < UIConstants.MIN_USERNAME_LENGTH:
        raise ValueError(
            f"Username must be at least {UIConstants.MIN_USERNAME_LENGTH} characters"
        )
    return username


def validate_account_label(label: str) -> str:
    if not label or not label.strip():
        raise ValueError("Account label cannot be empty")
    label = label.strip()
    if len(label) > UIConstants.MAX_ACCOUNT_LABEL_LENGTH:
        raise ValueError(
            f"Account label must be less than {UIConstants.MAX_ACCOUNT_LABEL_LENGTH} characters"
        )
    return label


def initialize_session_state():
    defaults = {
        "api_client": None,
        "is_authenticated": False,
        "username": None,
        "accounts": [],
        "oauth_state": "idle",
        "oauth_url": None,
        "oauth_code": "",
        "oauth_flow_type": None,
        "account_label": "",
        "api_key": "",
        "config": None,
        "oauth_code_verifier": None,
        "oauth_redirect_uri": None,
        "auth_code": None,
        "start_oauth_time": None,
        "oauth_server": None,
        "state_lock": Lock(),
        "code_received_event": Event(),
        "selected_account_email": None,
    }
    for key, default in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = default


def show_error(message: str, technical_details: Optional[str] = None):
    st.error(message)
    if technical_details:
        with st.expander("Technical Details"):
            st.code(technical_details)


def render_login_form():
    st.subheader("Login")
    api_key_input = st.text_input(
        "API Key", type="password", value=st.session_state.api_key
    )
    username_input = st.text_input(
        "Username", value=st.session_state.username if st.session_state.username else ""
    )
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
                        timeout=UIConstants.API_TIMEOUT_SECONDS,
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
            logger.info("User logged in successfully", extra={"username": username})
            st.rerun()
        except ValueError as e:
            st.warning(str(e))
        except AuthenticationError as e:
            show_error("Authentication failed. Please check your API key.", str(e))
        except APIError as e:
            show_error("Login failed. Please try again.", str(e))
        except Exception as e:
            show_error("An unexpected error occurred during login.", str(e))
            logger.error(
                "Login error", extra={"username": username_input, "error": str(e)}
            )


def refresh_user_data():
    try:
        with st.spinner("Refreshing account status..."):
            data = st.session_state.api_client.login(st.session_state.username)
            st.session_state.accounts = data.get("accounts", [])
            logger.info(
                "User data refreshed successfully",
                extra={"username": st.session_state.username},
            )
    except Exception as e:
        show_error("Failed to refresh account data", str(e))
        logger.error(
            "Failed to refresh user data",
            extra={"username": st.session_state.username, "error": str(e)},
        )


class AuthCodeHandler(BaseHTTPRequestHandler):
    on_code_received = None
    state_lock = None
    code_received_event = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code and not error:
            self.wfile.write(
                b"<html><body><h1>Authentication complete</h1><p>You can close this window and return to the app.</p></body></html>"
            )
            if self.on_code_received and self.state_lock and self.code_received_event:
                with self.state_lock:
                    st.session_state.auth_code = code
                    logger.info(
                        "Received OAuth code",
                        extra={"code": code[:10]},
                    )
                    self.code_received_event.set()
        else:
            self.wfile.write(
                b"<html><body><h1>Authentication failed</h1><p>An error occurred. Please close this window and try again.</p></body></html>"
            )
            logger.error("OAuth callback error", extra={"error": error})


def start_local_server(port: int, on_code_received, state_lock, code_received_event):
    AuthCodeHandler.on_code_received = on_code_received
    AuthCodeHandler.state_lock = state_lock
    AuthCodeHandler.code_received_event = code_received_event
    server = HTTPServer(("127.0.0.1", port), AuthCodeHandler)

    def run():
        server.handle_request()

    thread = Thread(target=run, daemon=True)
    thread.start()
    return server, thread


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def render_oauth_flow():
    if st.session_state.oauth_state == "awaiting_code":
        st.info("Complete OAuth Authentication")
        flow_type = st.session_state.get("oauth_flow_type", "association")
        if flow_type == "additional-association":
            st.markdown("**Adding Additional Google Account**")
        elif flow_type == "re-authentication":
            st.markdown("**Re-authenticating Existing Account**")
        else:
            st.markdown("**Authenticating Your Google Account**")
        st.markdown("""
        **Steps:**
        1. The browser will open automatically to the Google authentication page.
        2. Complete the authentication process.
        3. Once done, return here—the app will automatically detect and process the authorization.
        """)
        if st.button("Cancel"):
            reset_oauth_state()
            st.rerun()

        # Check for received code
        if st.session_state.code_received_event.is_set() or st.session_state.auth_code:
            code_to_process = st.session_state.auth_code
            if code_to_process:
                process_oauth_code(code_to_process, st.session_state.account_label)
                return

        # Check for timeout
        if (
            st.session_state.start_oauth_time
            and time.time() - st.session_state.start_oauth_time
            > UIConstants.OAUTH_TIMEOUT_SECONDS
        ):
            st.session_state.oauth_state = "failed"
            st.rerun()
        else:
            st.spinner("Waiting for authorization completion...")
            time.sleep(1)
            st.rerun()

    elif st.session_state.oauth_state == "processing":
        st.info("Processing authentication...")
        st.spinner("Exchanging code for tokens and associating account...")
    elif st.session_state.oauth_state == "completed":
        st.success("Authentication completed successfully!")
        if st.button("Continue", type="primary"):
            reset_oauth_state()
            refresh_user_data()
            st.rerun()
    elif st.session_state.oauth_state == "failed":
        st.error("Authentication failed. Please try again.")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Try Again", type="primary"):
                flow_type = st.session_state.get("oauth_flow_type", "association")
                start_oauth_flow(flow_type)
        with col2:
            if st.button("Cancel", type="secondary"):
                reset_oauth_state()
                st.rerun()


def process_oauth_code(code: str, account_label: str):
    st.session_state.oauth_state = "processing"
    st.rerun()
    try:
        if not validate_oauth_code(code):
            raise ValueError("Invalid authorization code format")
        with st.spinner("Exchanging authorization code for tokens..."):
            tokens = exchange_code_for_tokens(
                code=code,
                redirect_uri=st.session_state.oauth_redirect_uri,
                code_verifier=st.session_state.oauth_code_verifier,
                config=st.session_state.config,
            )
        if not tokens.get("refresh_token"):
            raise ValueError(
                "No refresh token received. The account may have been previously authorized. Try revoking access in your Google Account settings and try again."
            )
        with st.spinner("Fetching account information..."):
            user_email = get_user_email_from_token(tokens["access_token"])
        with st.spinner("Associating account with your profile..."):
            validated_label = validate_account_label(account_label)
            account_info = f"{validated_label} ({user_email})"
            result = st.session_state.api_client.associate_account(
                username=st.session_state.username,
                refresh_token=tokens["refresh_token"],
                account_info=account_info,
            )
        if "error" in result:
            raise APIError(result["error"])
        st.session_state.oauth_state = "completed"
        flow_type = st.session_state.get("oauth_flow_type", "association")
        if flow_type == "additional-association":
            st.success(
                f"Additional account `{user_email}` has been added successfully!"
            )
        elif flow_type == "re-authentication":
            st.success(
                f"Account `{user_email}` has been re-authenticated successfully!"
            )
        else:
            st.success(f"Account `{user_email}` has been associated successfully!")
        logger.info(
            "OAuth association successful",
            extra={"username": st.session_state.username, "user_email": user_email},
        )
        time.sleep(2)
        reset_oauth_state()
        refresh_user_data()
        st.rerun()
    except Exception as e:
        st.session_state.oauth_state = "failed"
        show_error("Authentication failed", str(e))
        logger.error(
            "OAuth processing failed",
            extra={"username": st.session_state.username, "error": str(e)},
        )


def start_oauth_flow(flow_type: str):
    try:
        with st.spinner("Preparing authentication..."):
            port = pick_free_port()
            redirect_uri = f"http://127.0.0.1:{port}/callback"

            # Generate PKCE pair first
            code_verifier, code_challenge = generate_pkce_pair()

            # Generate OAuth URL with PKCE
            oauth_data = generate_oauth_url(
                st.session_state.config,
                redirect_uri=redirect_uri,
                code_challenge=code_challenge,
            )

            st.session_state.oauth_url = oauth_data["auth_url"]
            st.session_state.oauth_code_verifier = code_verifier
            st.session_state.oauth_redirect_uri = redirect_uri
            st.session_state.oauth_flow_type = flow_type
            st.session_state.auth_code = None
            st.session_state.start_oauth_time = time.time()
            st.session_state.code_received_event.clear()

            # Start local server
            state_lock = st.session_state.state_lock
            code_received_event = st.session_state.code_received_event

            def on_code_received(code):
                with state_lock:
                    st.session_state.auth_code = code
                    logger.info(
                        "Received OAuth code",
                        extra={"code": code[:10]},
                    )
                    code_received_event.set()

            server, thread = start_local_server(
                port, on_code_received, state_lock, code_received_event
            )
            st.session_state.oauth_server = server

            # Open browser
            webbrowser.open(st.session_state.oauth_url)

        st.session_state.oauth_state = "awaiting_code"
        logger.info(
            "OAuth flow started",
            extra={"username": st.session_state.username, "flow_type": flow_type},
        )
        st.rerun()
    except Exception as e:
        show_error("Failed to start OAuth flow", str(e))
        logger.error(
            "OAuth flow start failed",
            extra={"username": st.session_state.username, "error": str(e)},
        )


def reset_oauth_state():
    with st.session_state.state_lock:
        st.session_state.oauth_state = "idle"
        st.session_state.oauth_url = None
        st.session_state.auth_code = None
        st.session_state.oauth_flow_type = None
        st.session_state.account_label = ""
        st.session_state.oauth_code_verifier = None
        st.session_state.oauth_redirect_uri = None
        st.session_state.start_oauth_time = None
        st.session_state.oauth_server = None
        st.session_state.code_received_event.clear()


def render_account_management():
    st.subheader("Google Account Management")

    if st.session_state.accounts:
        st.write(f"**Associated Accounts: {len(st.session_state.accounts)}**")
        working_accounts = []

        for i, account in enumerate(st.session_state.accounts):
            with st.container():
                col1, col2 = st.columns([3, 1])
                with col1:
                    account_email = account.get("account_email", "Unknown email")
                    account_info = account.get("account_info", "[No label]")
                    if "(" in account_info and ")" in account_info:
                        label = account_info.split(" (")[0]
                    else:
                        label = account_info
                    account_status = account.get("details", "Unknown status")
                    is_expired = (
                        "expired" in account_status.lower()
                        or "revoked" in account_status.lower()
                    )
                    if is_expired:
                        st.warning(f"**{account_email}** ({label})")
                        st.caption(f"Status: {account_status}")
                        st.caption("⚠️ This account needs re-authentication")
                    else:
                        st.success(f"**{account_email}** ({label})")
                        st.caption(f"Status: {account_status}")
                        working_accounts.append(account)
                with col2:
                    if is_expired:
                        if st.button(
                            "Re-auth",
                            key=f"reauth_{i}",
                            help=f"Re-authenticate {account_email}",
                        ):
                            with st.form(key=f"reauth_form_{i}"):
                                account_label = st.text_input(
                                    "Account Label:", value=label
                                )
                                submit = st.form_submit_button(
                                    "Start Re-authentication"
                                )
                                if submit:
                                    try:
                                        validated_label = validate_account_label(
                                            account_label
                                        )
                                        st.session_state.account_label = validated_label
                                        start_oauth_flow("re-authentication")
                                    except ValueError as e:
                                        st.error(str(e))
                    if st.button(
                        "Remove", key=f"remove_{i}", help=f"Remove {account_email}"
                    ):
                        try:
                            with st.spinner(f"Removing {account_email}..."):
                                st.session_state.api_client.dissociate_account(
                                    st.session_state.username, account_email
                                )
                            st.success(f"Account {account_email} removed successfully.")
                            refresh_user_data()
                            st.rerun()
                        except Exception as e:
                            show_error("Failed to remove account", str(e))
                            logger.error(
                                "Account removal failed",
                                extra={"account_email": account_email, "error": str(e)},
                            )
                if i < len(st.session_state.accounts) - 1:
                    st.divider()

        st.markdown("---")

        # Account selection and chat button
        if working_accounts:
            account_emails = [acc.get("account_email") for acc in working_accounts]
            account_options = [
                f"{acc.get('account_email')} ({acc.get('account_info').split(' (')[0] if '(' in acc.get('account_info', '') else acc.get('account_info')})"
                for acc in working_accounts
            ]

            col1, col2, col3 = st.columns(3)
            with col1:
                # Account selection dropdown
                selected_idx = st.selectbox(
                    "Select active account for chat:",
                    range(len(account_options)),
                    format_func=lambda x: account_options[x],
                    index=0,
                    key="account_select",
                )
                st.session_state.selected_account_email = account_emails[selected_idx]

                # Chat button
                if st.button("💬 Go to Chat", type="primary"):
                    st.switch_page("pages/chat.py")

            with col2:
                with st.form(key="add_account_form"):
                    account_label = st.text_input(
                        "Account Label:",
                        placeholder="e.g., work, personal, project-name",
                    )
                    submit = st.form_submit_button(
                        "Associate Google Account", type="secondary"
                    )
                    if submit:
                        try:
                            validated_label = validate_account_label(account_label)
                            st.session_state.account_label = validated_label
                            start_oauth_flow("additional-association")
                        except ValueError as e:
                            st.error(str(e))

            with col3:
                if st.button("🔄 Refresh Status", help="Check account status"):
                    refresh_user_data()
                    st.rerun()

            st.info(f"✅ {len(working_accounts)} account(s) ready for chat.")
        else:
            st.warning(
                "⚠️ No accounts are currently active. Please associate or re-authenticate an account to access chat."
            )

    else:
        st.warning("No Google accounts associated with your profile.")
        st.info(
            "You need to associate at least one Google account to access workspace features and chat."
        )
        with st.form(key="associate_form"):
            account_label = st.text_input(
                "Account Label:", placeholder="e.g., work, personal, project-name"
            )
            submit = st.form_submit_button("Associate Google Account", type="primary")
            if submit:
                try:
                    validated_label = validate_account_label(account_label)
                    st.session_state.account_label = validated_label
                    start_oauth_flow("association")
                except ValueError as e:
                    st.error(str(e))


def debug_oauth_state():
    if st.sidebar.checkbox("Show Debug Info", value=False):
        st.sidebar.write("**Debug Information:**")
        st.sidebar.write(f"OAuth State: {st.session_state.oauth_state}")
        st.sidebar.write(
            f"OAuth URL Present: {'Yes' if st.session_state.oauth_url else 'No'}"
        )
        st.sidebar.write(
            f"Auth Code Present: {'Yes' if st.session_state.auth_code else 'No'}"
        )
        st.sidebar.write(f"Flow Type: {st.session_state.get('oauth_flow_type', 'N/A')}")
        st.sidebar.write(
            f"Accounts count: {len(st.session_state.accounts) if st.session_state.accounts is not None else 'Not set'}"
        )
        if st.sidebar.button("Reset OAuth State"):
            reset_oauth_state()
            st.rerun()


def render_help_section():
    with st.expander("Help & Information", expanded=False):
        st.markdown("""
        ### How to use this application:
        1. **Login**: Enter your API key and username
        2. **Associate Google Account**: Connect your Google Workspace account
        3. **Complete Authentication**: Follow the OAuth flow to authorize access
        4. **Provide Context**: Label your account (work/personal/etc.)
        5. **Chat**: Use natural language to interact with Google Workspace services

        ### Multiple Accounts:
        - You can associate multiple Google accounts
        - Each account can have different labels for easy identification
        - Re-authenticate expired accounts individually
        - Remove accounts you no longer need

        ### Troubleshooting:
        - **No refresh token**: Revoke app permissions in your Google Account settings and try again
        - **Authentication failed**: Ensure you complete the authentication in the browser
        - **Token expired**: Use the re-authenticate button to refresh your tokens
        - **API errors**: Verify your API key is valid and the backend service is running
        - **Connection issues**: Check the API server is running on the correct port
        - **UI not updating**: Try logging out and logging back in to reset session state

        ### Security Notes:
        - Your API key is stored only for this session
        - OAuth tokens are securely managed by the backend
        - Authorization codes are discarded after use
        - Close this browser tab when finished to clear session data
        """)


def main():
    st.set_page_config(
        page_title="Google Workspace Agent Interface",
        page_icon="🤖🚀",
        layout="wide",
    )
    st.title("🤖🚀 Google Workspace Agent Interface")
    initialize_session_state()
    try:
        if not st.session_state.config:
            st.session_state.config = get_config()
    except ValueError as e:
        st.error(f"Configuration error: {str(e)}")
        st.stop()
    debug_oauth_state()
    if not st.session_state.is_authenticated:
        render_login_form()
        return
    st.markdown("---")
    st.subheader(f"Welcome, {st.session_state.username}!")
    col1, col2 = st.columns([3, 1])
    with col2:
        if st.button("Logout", type="secondary"):
            try:
                for key in list(st.session_state.keys()):
                    if key in st.session_state:
                        del st.session_state[key]
                st.success("Logged out successfully!")
                logger.info("User logged out")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.error(f"Logout error: {str(e)}")
                initialize_session_state()
                st.rerun()
    if st.session_state.oauth_state != "idle":
        render_oauth_flow()
        return
    st.markdown("---")
    render_account_management()
    st.markdown("---")
    render_help_section()


if __name__ == "__main__":
    main()
