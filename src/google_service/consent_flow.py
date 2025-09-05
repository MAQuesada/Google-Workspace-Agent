import streamlit as st
import webbrowser
import requests
import urllib.parse
import base64
import hashlib
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from dotenv import load_dotenv
load_dotenv()

from utils.config import get_config


# Thread-safe global container for OAuth code shared between threads
oauth_code_container = {"code": None}


def pick_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate_pkce_pair():
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def start_local_server(port, on_code_received):
    class AuthCodeHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = params.get("code", [None])[0]
            error = params.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if code and not error:
                self.wfile.write(b"<html><body><h1>Authentication complete</h1>You can close this window.</body></html>")
                on_code_received(code)
            else:
                self.wfile.write(f"<html><body><h1>Authentication failed</h1>Error: {error}</body></html>".encode())

    server = HTTPServer(("127.0.0.1", port), AuthCodeHandler)

    def run():
        server.handle_request()

    thread = Thread(target=run, daemon=True)
    thread.start()
    return server


def build_auth_url(redirect_uri, code_challenge, login_hint=None):
    client_id = get_config().GOOGLE_CLIENT_ID
    scopes = ["openid", "email", "profile", "https://www.googleapis.com/auth/calendar.readonly"] # Example scope
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"


def exchange_code_for_tokens(code, redirect_uri, code_verifier):
    client_id = get_config().GOOGLE_CLIENT_ID
    client_secret = get_config().GOOGLE_CLIENT_SECRET
    token_url = get_config().GOOGLE_TOKEN_URL
    data = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    resp = requests.post(token_url, data=data)
    resp.raise_for_status()
    return resp.json()


class APIClient:
    def __init__(self, base_url, api_key):
        self.base_url = base_url.rstrip("/")
        self.headers = {"X-API-Key": api_key}

    def login(self, username):
        url = f"{self.base_url}/user/"
        resp = requests.get(url, params={"username": username}, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def associate_account(self, username, refresh_token, account_info):
        url = f"{self.base_url}/user/associate_account"
        params = {"username": username, "refresh_token": refresh_token, "account_info": account_info}
        resp = requests.post(url, params=params, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def dissociate_account(self, username, account_email):
        url = f"{self.base_url}/user/dissociate_account"
        params = {"username": username, "account_email": account_email}
        resp = requests.post(url, params=params, headers=self.headers)
        resp.raise_for_status()
        return resp.json()


API_BASE_URL = "http://localhost:8000"


def main():
    st.title("Google Workspace Multi-Agent Interface")

    for key, default in [
        ("api_client", None),
        ("is_authenticated", False),
        ("username", None),
        ("accounts", []),
        ("oauth_in_progress", False),
        ("auth_code", None),
        ("code_verifier", None),
        ("redirect_uri", None),
        ("account_label", ""),
        ("api_key", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default
            
    # Always process the auth code check at the beginning of the script execution
    # This is crucial for Streamlit to react to the local server callback
    if oauth_code_container.get("code") is not None:
        st.session_state.auth_code = oauth_code_container["code"]
        oauth_code_container["code"] = None
        st.info("Authentication code received. Exchanging for tokens...")
        st.rerun()

    api_key_input = st.text_input("API Key", type="password", value=st.session_state.api_key)
    username_input = st.text_input("Username", value=st.session_state.username if st.session_state.username else "")

    if st.button("Login"):
        if not api_key_input or not username_input.strip():
            st.warning("Please enter both API Key and Username.")
        else:
            try:
                client = APIClient(API_BASE_URL, api_key_input)
                data = client.login(username_input.strip())
                if "error" in data and "not found" in data["error"].lower():
                    st.info(f"User '{username_input}' not found. Creating new user...")
                    resp = requests.post(
                        f"{API_BASE_URL}/user/",
                        params={"username": username_input.strip()},
                        headers={"X-API-Key": api_key_input},
                    )
                    resp.raise_for_status()
                    data = resp.json()
                if "error" in data:
                    raise Exception(data["error"])
                st.success(f"Logged in as {username_input.strip()}")
                st.session_state.api_client = client
                st.session_state.is_authenticated = True
                st.session_state.username = username_input.strip()
                st.session_state.accounts = data.get("accounts", [])
                st.session_state.api_key = api_key_input
                st.session_state.oauth_in_progress = False
                st.session_state.auth_code = None
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    if not st.session_state.is_authenticated:
        return

    st.markdown("---")
    st.subheader("Google Account Management")

    if st.session_state.oauth_in_progress:
        st.info("Waiting for Google authentication...")
        # A simple st.empty() placeholder can be used to reserve space
        # while waiting, but the main logic is handled by the top-level
        # check that forces a rerun.

    elif st.session_state.auth_code:
        try:
            tokens = exchange_code_for_tokens(
                st.session_state.auth_code, 
                st.session_state.redirect_uri, 
                st.session_state.code_verifier
            )
            refresh_token = tokens.get("refresh_token")
            access_token = tokens.get("access_token")

            if not refresh_token:
                st.error("No refresh token received. Please revoke prior consent and try again.")
                st.session_state.oauth_in_progress = False
                st.session_state.auth_code = None
                return

            userinfo_resp = requests.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {access_token}"}
            )
            userinfo_resp.raise_for_status()
            email = userinfo_resp.json().get("email")

            account_label = st.text_input("Label for this Google account (work/personal):", value=st.session_state.account_label)
            st.session_state.account_label = account_label

            if st.button("Associate Account"):
                resp = st.session_state.api_client.associate_account(
                    st.session_state.username, refresh_token, account_label
                )
                if "error" in resp:
                    st.error(f"Failed to associate account: {resp.get('error')}")
                else:
                    st.success(f"Account {email} associated successfully!")
                    st.session_state.accounts = resp.get("accounts", [])
                    st.session_state.oauth_in_progress = False
                    st.session_state.auth_code = None
                    st.session_state.account_label = ""
                    st.rerun()
        except Exception as e:
            st.error(f"Error during token exchange or association: {e}")
            st.session_state.oauth_in_progress = False
            st.session_state.auth_code = None
    
    elif accounts:
        account = accounts[0]
        st.success(f"Associated Google Account: {account.get('account_email')}")
        st.write(f"Label: {account.get('account_info', '[No label]')}")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Dissociate Account"):
                try:
                    st.session_state.api_client.dissociate_account(st.session_state.username, account["account_email"])
                    st.success("Account dissociated.")
                    st.session_state.accounts = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to dissociate account: {e}")
        with col2:
            if st.button("Go to Chat"):
                st.query_params(page="chat")
                st.rerun()
    else:
        st.warning("No associated accounts found.")
        if st.button("Associate Google Account"):
            port = pick_free_port()
            redirect_uri = f"http://127.0.0.1:{port}/callback"
            verifier, challenge = generate_pkce_pair()

            st.session_state.oauth_in_progress = True
            st.session_state.auth_code = None
            st.session_state.code_verifier = verifier
            st.session_state.redirect_uri = redirect_uri

            def on_code_received(code):
                global oauth_code_container
                oauth_code_container["code"] = code

            start_local_server(port, on_code_received)

            auth_url = build_auth_url(redirect_uri, challenge, login_hint=st.session_state.username)
            st.info("Opening Google OAuth consent screen in your browser...")
            webbrowser.open(auth_url)
            st.rerun()

if __name__ == "__main__":
    main()