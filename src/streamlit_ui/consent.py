# consent_flow.py

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
import time

from dotenv import load_dotenv
load_dotenv()

from utils.config import get_config

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
    scopes = ["openid", "email", "profile", "https://www.googleapis.com/auth/calendar.readonly"]
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

# New function to handle the entire flow
def handle_oauth_flow(username):
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
    auth_url = build_auth_url(redirect_uri, challenge, login_hint=username)
    webbrowser.open(auth_url)
    
    # Use st.status to block and show progress
    with st.status("Waiting for Google authentication...", expanded=True) as status_box:
        status_box.write("1. Opening Google consent screen in your browser...")
        
        # Wait for the background thread to set the code
        while oauth_code_container.get("code") is None:
            time.sleep(1)
        
        # Update the status box and return the code
        status_box.write("2. Authentication successful. Exchanging code for tokens...")
        auth_code = oauth_code_container["code"]
        oauth_code_container["code"] = None
        status_box.update(label="Authentication complete!", state="complete", expanded=False)
        
        return auth_code, redirect_uri, verifier