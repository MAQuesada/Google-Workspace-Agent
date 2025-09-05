import streamlit as st
import webbrowser
import time
import requests
import json
import urllib.parse
import base64
import hashlib
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Optional

from utils.config import get_config  # centralized config


def pick_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate_pkce_pair():
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


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

    def get_chat_history(self, username, conversation_id):
        url = f"{self.base_url}/chat/history"
        resp = requests.get(url, params={"username": username, "conversation_id": conversation_id}, headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def start_chat_stream(self, username, conversation_id, message):
        url = f"{self.base_url}/chat"
        payload = {"username": username, "conversation_id": conversation_id, "message": message}
        resp = requests.post(url, json=payload, headers=self.headers, stream=True)
        resp.raise_for_status()
        return resp.iter_lines()


API_BASE_URL = "http://localhost:8000"


def main():
    st.title("Google Workspace Multi-Agent Interface")

    # Check if we're returning from OAuth
    query_params = st.query_params
    oauth_code = query_params.get("code", [None])[0]
    oauth_error = query_params.get("error", [None])[0]
    
    # Handle OAuth callback
    if oauth_code and not st.session_state.get("oauth_processed", False):
        st.session_state.oauth_code = oauth_code
        st.session_state.oauth_processed = True
        st.query_params  # Clear URL parameters
        st.rerun()
    
    if oauth_error:
        st.error(f"OAuth error: {oauth_error}")
        st.query_params # Clear URL parameters

    # Initialize session state
    for key, default in [
        ("api_client", None),
        ("is_authenticated", False),
        ("username", None),
        ("accounts", []),
        ("oauth_in_progress", False),
        ("oauth_code", None),
        ("oauth_processed", False),
        ("code_verifier", None),
        ("account_label", ""),
    ]:
        if key not in st.session_state:
            st.session_state[key] = default

    # Login inputs
    api_key_input = st.text_input("API Key", type="password", value=st.session_state.get("api_key", ""))
    username_input = st.text_input("Username", value=st.session_state.get("username", ""))

    if st.button("Login"):
        if not api_key_input or not username_input.strip():
            st.warning("Please enter both API Key and Username.")
        else:
            try:
                client = APIClient(API_BASE_URL, api_key_input)
                data = client.login(username_input.strip())
                
                # Handle new user creation
                if "error" in data and "not found" in data["error"].lower():
                    st.info(f"User '{username_input}' not found. Creating new user...")
                    try:
                        resp = requests.post(
                            f"{API_BASE_URL}/user/",
                            params={"username": username_input.strip()},
                            headers={"X-API-Key": api_key_input},
                        )
                        resp.raise_for_status()
                        data = resp.json()
                    except Exception as create_error:
                        st.error(f"Failed to create user: {create_error}")
                        return
                
                if "error" in data:
                    raise Exception(data["error"])

                st.success(f"Logged in as {username_input.strip()}")
                st.session_state.api_client = client
                st.session_state.is_authenticated = True
                st.session_state.username = username_input.strip()
                st.session_state.accounts = data.get("accounts", [])
                st.session_state.api_key = api_key_input
                st.session_state.oauth_in_progress = False
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    if not st.session_state.is_authenticated:
        return

    st.info(f"Logged in as {st.session_state.username}")
    client = st.session_state.api_client
    username = st.session_state.username
    accounts = st.session_state.accounts

    st.subheader("Google Account Management")

    if accounts:
        account = accounts[0]  # Simplified: first account
        st.write(f"**Email:** {account.get('account_email')} | **Label:** {account.get('account_info')} | **Details:** {account.get('details')}")

        col1, col2 = st.columns(2)
        with col1:
            if st.button("Dissociate Account"):
                try:
                    client.dissociate_account(username, account["account_email"])
                    st.success("Account dissociated.")
                    st.session_state.accounts = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to dissociate account: {e}")

        with col2:
            if st.button("Go to Chat"):
                st.switch_page("pages/chat.py")

    else:
        st.warning("No Google account associated. Associate one to enable chat.")
        
        # Handle OAuth code if received
        if st.session_state.oauth_code and not st.session_state.oauth_in_progress:
            st.success("Authorization received! Processing...")
            try:
                # Use the current Streamlit URL as redirect URI
                redirect_uri = "http://localhost:8501"  # Your Streamlit URL
                
                tokens = exchange_code_for_tokens(
                    st.session_state.oauth_code,
                    redirect_uri,
                    st.session_state.code_verifier
                )
                
                refresh_token = tokens.get("refresh_token")
                access_token = tokens.get("access_token")

                if not refresh_token:
                    st.error("No refresh token received. Please revoke previous consent and try again.")
                    st.session_state.oauth_code = None
                    st.session_state.oauth_processed = False
                    return

                # Get user info
                userinfo_resp = requests.get(
                    "https://openidconnect.googleapis.com/v1/userinfo",
                    headers={"Authorization": f"Bearer {access_token}"}
                )
                userinfo_resp.raise_for_status()
                email = userinfo_resp.json().get("email")
                
                st.success(f"Successfully authenticated as: {email}")
                
                # Account label input
                account_label = st.text_input(
                    "Label for this Google account:",
                    value="personal",
                    help="e.g., 'work', 'personal', 'team'"
                )
                
                col1, col2 = st.columns(2)
                with col1:
                    if st.button("Associate Account", type="primary"):
                        if not account_label.strip():
                            st.warning("Please provide a label for the account.")
                        else:
                            try:
                                resp = client.associate_account(
                                    username, 
                                    refresh_token, 
                                    account_label.strip()
                                )
                                
                                if "error" in resp:
                                    st.error(f"Association failed: {resp.get('error')}")
                                else:
                                    st.success(f"Account {email} associated successfully!")
                                    st.session_state.accounts = resp.get("accounts", [])
                                    st.session_state.oauth_code = None
                                    st.session_state.oauth_processed = False
                                    st.rerun()
                            except Exception as e:
                                st.error(f"Association error: {e}")
                
                with col2:
                    if st.button("Cancel"):
                        st.session_state.oauth_code = None
                        st.session_state.oauth_processed = False
                        st.rerun()
                        
            except Exception as e:
                st.error(f"Token exchange failed: {e}")
                st.session_state.oauth_code = None
                st.session_state.oauth_processed = False
        
        elif not st.session_state.oauth_in_progress:
            if st.button("Associate Google Account"):
                # Generate PKCE pair
                verifier, challenge = generate_pkce_pair()
                st.session_state.code_verifier = verifier
                
                # Use Streamlit URL as redirect
                redirect_uri = "http://localhost:8501"
                
                # Build auth URL
                client_id = get_config().GOOGLE_CLIENT_ID
                scopes = ["openid", "email", "profile"]
                params = {
                    "client_id": client_id,
                    "redirect_uri": redirect_uri,
                    "response_type": "code",
                    "scope": " ".join(scopes),
                    "access_type": "offline",
                    "prompt": "consent",
                    "include_granted_scopes": "true",
                    "code_challenge": challenge,
                    "code_challenge_method": "S256",
                    "login_hint": username,
                }
                
                auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
                
                st.session_state.oauth_in_progress = True
                
                # Direct redirect instead of opening new window
                st.markdown(f'<meta http-equiv="refresh" content="0; url={auth_url}">', unsafe_allow_html=True)
                st.info("Redirecting to Google for authentication...")


if __name__ == "__main__":
    main()