import time
import webbrowser
import urllib.parse
import requests
import hashlib
import base64
import os
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Optional, Tuple

from dotenv import load_dotenv
from utils.config import get_config
from google_service.core import UserService

load_dotenv()

# We'll use a loopback redirect URI with a random free port, as recommended by Google for installed/CLI apps.
# Example: http://127.0.0.1:PORT/callback


def pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def generate_pkce_pair() -> Tuple[str, str]:
    # RFC 7636 S256 PKCE
    verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b"=").decode("ascii")
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


class AuthCodeHandler(BaseHTTPRequestHandler):
    """Minimal handler to capture the authorization code from the querystring."""

    # This will be set externally before starting the server
    on_code_received = None

    def do_GET(self):  # Allow mixedCase per BaseHTTPRequestHandler
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if code and not error:
            self.wfile.write(
                b"<html><body><h1>Authentication complete</h1>You can close this window.</body></html>"
            )
            if AuthCodeHandler.on_code_received:
                AuthCodeHandler.on_code_received(code)
        else:
            self.wfile.write(
                f"<html><body><h1>Authentication failed</h1>Error: {error}</body></html>".encode()
            )


def start_local_server(port: int, on_code_received):
    AuthCodeHandler.on_code_received = on_code_received
    server = HTTPServer(("127.0.0.1", port), AuthCodeHandler)

    def run():
        server.handle_request()  # handle a single request then exit

    thread = Thread(target=run, daemon=True)
    thread.start()
    return server


def ensure_oidc_scopes(scopes):
    required = {"openid", "email", "profile"}
    current = set(scopes)
    if not required.issubset(current):
        return list(current.union(required))
    return scopes


def build_auth_url(
    redirect_uri: str, code_challenge: str, login_hint: Optional[str] = None
):
    scopes = ensure_oidc_scopes(get_config().GOOGLE_SCOPES)
    params = {
        "client_id": get_config().GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "scope": " ".join(scopes),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    if login_hint:
        params["login_hint"] = login_hint
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    )


def exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str):
    data = {
        "code": code,
        "client_id": get_config().GOOGLE_CLIENT_ID,
        "client_secret": get_config().GOOGLE_CLIENT_SECRET,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }

    response = requests.post(get_config().GOOGLE_TOKEN_URL, data=data)
    if response.status_code != 200:
        raise Exception(f"Failed to exchange code: {response.text}")
    return response.json()


def get_email_from_access_token(access_token: str):
    response = requests.get(
        "https://openidconnect.googleapis.com/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"},
    )
    if response.status_code != 200:
        raise Exception(f"Failed to get user info: {response.text}")
    return response.json()["email"]


def main(login_hint: Optional[str] = None):
    print("🔐 Starting Google OAuth2 consent flow...\n")
    port = pick_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    code_verifier, code_challenge = generate_pkce_pair()

    # Prepare a place to store the code received by the local server
    auth_code_container: dict[str, str | None] = {"code": None}

    def on_code(code: str):
        auth_code_container["code"] = code

    start_local_server(port, on_code)

    auth_url = build_auth_url(
        redirect_uri=redirect_uri, code_challenge=code_challenge, login_hint=login_hint
    )
    print("👉 Opening browser for authorization...")
    webbrowser.open(auth_url)

    print("🔁 Waiting for the authorization to complete in your browser...")
    # Block until we get the code (the server handles a single request)
    while auth_code_container["code"] is None:
        pass

    code = auth_code_container["code"]
    print("\n🔄 Exchanging code for tokens...")
    token_data = exchange_code_for_tokens(
        code, redirect_uri=redirect_uri, code_verifier=code_verifier
    )

    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")

    if not refresh_token:
        print(
            "❌ No refresh_token obtained. If this account was previously authorized, try again with 'prompt=consent' or remove the existing grant."
        )
        return

    print("✅ Tokens obtained successfully.")
    print("📧 Querying account email...")
    email = get_email_from_access_token(access_token)
    print(f"✅ Google Account: {email}")

    username = input(
        "🧑‍💻 Enter the local username to associate with this account: "
    ).strip()

    account_info = input("📝 Enter additional account information (optional): ").strip()

    print("refresh_token:", refresh_token)
    print("💾 Saving account to the system...")
    service = UserService()
    account = service.associate_account(
        username=username, refresh_token=refresh_token, account_info=account_info
    )

    print(f"\n🎉 Account successfully saved for user '{username}'!")
    print(f"📧 Email: {account.account_email}")
    print("🔁 You can use `UserService().list_accounts(...)` to view it later.\n")


def reauthenticate_account(username: str, login_hint: Optional[str] = None):
    """Convenience helper to re-run the consent flow and associate/refresh a user's account.

    If an existing account for the same email exists, UserService.associate_account will replace it.
    """
    print(f"🔁 Re-authenticating account for local user '{username}'...")
    port = pick_free_port()
    redirect_uri = f"http://127.0.0.1:{port}/callback"
    code_verifier, code_challenge = generate_pkce_pair()

    auth_code_container: dict[str, str | None] = {"code": None}

    def on_code(code: str):
        auth_code_container["code"] = code

    start_local_server(port, on_code)
    auth_url = build_auth_url(
        redirect_uri=redirect_uri, code_challenge=code_challenge, login_hint=login_hint
    )
    webbrowser.open(auth_url)
    print("Waiting for authorization in the browser...")
    while auth_code_container["code"] is None:
        time.sleep(5)

    token_data = exchange_code_for_tokens(
        auth_code_container["code"],
        redirect_uri=redirect_uri,
        code_verifier=code_verifier,
    )
    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")
    if not refresh_token:
        raise RuntimeError("No refresh_token returned during re-authentication.")

    email = get_email_from_access_token(access_token)
    service = UserService()
    return service.associate_account(
        username=username,
        refresh_token=refresh_token,
        account_info=f"Reauthed: {email}",
    )


if __name__ == "__main__":
    main()
