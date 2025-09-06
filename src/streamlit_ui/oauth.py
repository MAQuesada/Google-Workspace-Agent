import http.server
import socketserver
import threading
from urllib.parse import urlparse, parse_qs
import requests
import json
import logging
import time
import base64
import hashlib
import os
import socket

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Shared container for the OAuth code
class OAuthCodeContainer:
    def __init__(self):
        self._code = None
        self._lock = threading.Lock()

    def set_code(self, code):
        with self._lock:
            self._code = code
            logger.info(f"Received authorization code: {code[:10]}...")

    def get_code(self):
        with self._lock:
            return self._code

    def clear_code(self):
        with self._lock:
            self._code = None
            logger.info("Cleared authorization code.")

oauth_code_container = OAuthCodeContainer()

# Use a specific port for the server
PORT = 6173

class AuthServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """
    HTTP server that handles OAuth redirect callbacks.
    """
    def __init__(self, server_address, RequestHandlerClass, code_container):
        self.code_container = code_container
        self.server_thread = threading.current_thread()
        super().__init__(server_address, RequestHandlerClass)
        logger.info(f"Starting OAuth callback server on port {PORT}...")

    def shutdown(self):
        """Shutdown the server gracefully."""
        super().shutdown()
        logger.info("OAuth callback server shutting down.")

class RequestHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        query_params = parse_qs(urlparse(self.path).query)
        code = query_params.get("code", [None])[0]

        if code:
            self.server.code_container.set_code(code)
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><head><title>Authentication complete</title></head><body><h1>Authentication complete</h1><p>You can close this window.</p></body></html>")
        else:
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(b"<html><body><h1>Error</h1><p>No authorization code received.</p></body></html>")

def initiate_oauth_flow(username: str, config):
    """
    Initiates the Google OAuth 2.0 flow.
    Starts a local server in a separate thread to listen for the callback.
    Returns the authorization URL and state.
    """
    redirect_uri = f"http://127.0.0.1:{PORT}/callback"
    scopes = [
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
        "https://www.googleapis.com/auth/drive.readonly",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/gmail.readonly"
    ]

    # Generate PKCE code verifier and challenge
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('utf-8')
    code_challenge = base64.urlsafe_b64encode(hashlib.sha256(code_verifier.encode('utf-8')).digest()).rstrip(b'=').decode('utf-8')

    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id={config.GOOGLE_CLIENT_ID}&redirect_uri={redirect_uri}&scope={' '.join(scopes)}&access_type=offline&prompt=consent&code_challenge={code_challenge}&code_challenge_method=S256"

    logger.info(f"Generated OAuth URL for {username}")

    try:
        # Check if the port is in use and pick a free one if needed
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.bind(("127.0.0.1", PORT))
        except socket.error as e:
            logger.warning(f"Port {PORT} is in use. Skipping server start for this flow.")
        finally:
            s.close()
            
        # Start the local server in a separate thread
        server = AuthServer(('127.0.0.1', PORT), RequestHandler, oauth_code_container)
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.server = server # Crucial: store the server object on the thread
        server_thread.start()

        logger.info("OAuth server thread started.")

        return {
            "auth_url": auth_url,
            "code_verifier": code_verifier,
            "redirect_uri": redirect_uri,
            "server_thread": server_thread # Crucial: return the thread object
        }
    except Exception as e:
        logger.error(f"Failed to start local server: {str(e)}")
        raise RuntimeError("Failed to start local server for OAuth callback.")

def process_oauth_callback(code: str, redirect_uri: str, code_verifier: str, username: str, account_info: str, api_client, config):
    """
    Exchanges the authorization code for an access and refresh token.
    Associates the account with the user via the backend API.
    """
    token_params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "client_secret": config.GOOGLE_CLIENT_SECRET,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier
    }

    try:
        # Step 1: Exchange auth code for tokens
        token_resp = requests.post(config.GOOGLE_TOKEN_URL, data=token_params)
        token_resp.raise_for_status()
        tokens = token_resp.json()

        if "refresh_token" not in tokens:
            return {"success": False, "error": "No refresh token received. Check that 'access_type=offline' and 'prompt=consent' were used and that you are not re-authenticating with the same token."}

        refresh_token = tokens["refresh_token"]

        # Step 2: Get user's email to associate with the account
        profile_resp = requests.get("https://www.googleapis.com/oauth2/v1/userinfo",
                                    headers={"Authorization": f"Bearer {tokens['access_token']}"})
        profile_resp.raise_for_status()
        user_info = profile_resp.json()
        account_email = user_info["email"]

        # Step 3: Call backend API to associate the account
        api_result = api_client.associate_account(
            username=username,
            refresh_token=refresh_token,
            account_info=f"{account_info} ({account_email})"
        )

        if api_result and not api_result.get("error"):
            # Add fetched email and label to the result
            api_result["account_details"] = {
                "account_email": account_email,
                "account_info": f"{account_info} ({account_email})",
                "details": "Associated"
            }
            api_result["email"] = account_email
            api_result["success"] = True
            return api_result
        else:
            return {"success": False, "error": api_result.get("error", "API association failed.")}

    except requests.exceptions.RequestException as e:
        return {"success": False, "error": f"Token exchange failed: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"An unexpected error occurred during association: {str(e)}"}

def get_oauth_code():
    return oauth_code_container.get_code()

def clear_oauth_code():
    oauth_code_container.clear_code()