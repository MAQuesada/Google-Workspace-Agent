# main.py

import streamlit as st
import requests
from threading import Thread
import time

# Import the consent_flow script
from . import consent

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
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")

    if not st.session_state.is_authenticated:
        return

    st.markdown("---")
    st.subheader("Google Account Management")

    if st.session_state.oauth_in_progress:
        try:
            auth_code, redirect_uri, verifier = consent_flow.handle_oauth_flow(st.session_state.username)
            st.session_state.auth_code = auth_code
            st.session_state.redirect_uri = redirect_uri
            st.session_state.code_verifier = verifier
            st.session_state.oauth_in_progress = False
            st.rerun()
        except Exception as e:
            st.error(f"Error during OAuth flow: {e}")
            st.session_state.oauth_in_progress = False

    elif st.session_state.auth_code:
        try:
            tokens = consent_flow.exchange_code_for_tokens(
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
                if account_label.strip():
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
                else:
                    st.warning("Please provide a label for the account.")

        except Exception as e:
            st.error(f"Error during token exchange or association: {e}")
            st.session_state.oauth_in_progress = False
            st.session_state.auth_code = None
    
    elif st.session_state.accounts:
        account = st.session_state.accounts[0]
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
            st.session_state.oauth_in_progress = True
            st.rerun()

if __name__ == "__main__":
    main()