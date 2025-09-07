import base64
import hashlib
import os
import urllib.parse
import requests
import re
from typing import Dict, Any, Tuple
import logging
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

def generate_pkce_pair() -> Tuple[str, str]:
    """Generate PKCE code verifier and challenge pair"""
    # Generate a cryptographically secure random string
    code_verifier = base64.urlsafe_b64encode(os.urandom(32)).rstrip(b'=').decode('ascii')
    
    # Create the SHA256 hash of the verifier
    digest = hashlib.sha256(code_verifier.encode('ascii')).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
    
    return code_verifier, code_challenge

def generate_oauth_url(config, redirect_uri: str, code_challenge: str) -> Dict[str, str]:
    """Generate OAuth authorization URL with PKCE"""
    params = {
        "client_id": config.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(config.GOOGLE_SCOPES),
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "access_type": "offline",
        "prompt": "consent"
    }
    auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    return {"auth_url": auth_url, "redirect_uri": redirect_uri}

def validate_oauth_code(code: str) -> bool:
    """
    Validate the format of an OAuth authorization code
    Google authorization codes typically follow a specific pattern
    """
    if not code or not isinstance(code, str):
        return False
    
    # Remove any whitespace
    code = code.strip()
    
    # Basic validation - Google auth codes are typically:
    # - Start with "4/"
    # - Follow with alphanumeric characters, hyphens, and underscores
    # - Are usually 50-200 characters long
    pattern = r'^4/[A-Za-z0-9_-]{40,}$'
    
    if not re.match(pattern, code):
        return False
    
    # Additional length check
    if len(code) < 45 or len(code) > 250:
        return False
    
    return True

def exchange_code_for_tokens(code: str, redirect_uri: str, code_verifier: str, config) -> Dict[str, Any]:
    """
    Exchange authorization code for access and refresh tokens
    Replicates the token exchange logic from consent_flow.py
    """
    try:
        # Prepare token exchange request
        token_data = {
            "code": code,
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
            "code_verifier": code_verifier,
        }
        
        logger.info("Exchanging authorization code for tokens...")
        
        # Make the token exchange request
        response = requests.post(
            config.GOOGLE_TOKEN_URL,
            data=token_data,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Token exchange failed: {response.status_code} - {response.text}")
            raise Exception(f"Failed to exchange code for tokens: {response.text}")
        
        tokens = response.json()
        
        # Validate that we received the required tokens
        if "access_token" not in tokens:
            raise Exception("No access token received from Google")
        
        if "refresh_token" not in tokens:
            logger.warning("No refresh token received - this may indicate the user has already authorized this app")
            raise Exception("No refresh token received. Please revoke this app's permissions in your Google Account settings and try again.")
        
        logger.info("Successfully exchanged code for tokens")
        return tokens
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during token exchange: {str(e)}")
        raise Exception(f"Network error during token exchange: {str(e)}")
    except Exception as e:
        logger.error(f"Token exchange failed: {str(e)}")
        raise

def get_user_email_from_token(access_token: str) -> str:
    """
    Get user's email address using the access token
    Replicates the email fetching logic from consent_flow.py
    """
    try:
        logger.info("Fetching user email from access token...")
        
        # Use the OpenID Connect userinfo endpoint
        response = requests.get(
            "https://openidconnect.googleapis.com/v1/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Failed to get user info: {response.status_code} - {response.text}")
            raise Exception(f"Failed to get user information: {response.text}")
        
        user_info = response.json()
        
        if "email" not in user_info:
            raise Exception("No email found in user information")
        
        email = user_info["email"]
        logger.info(f"Successfully fetched user email: {email}")
        return email
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error while fetching user email: {str(e)}")
        raise Exception(f"Network error while fetching user email: {str(e)}")
    except Exception as e:
        logger.error(f"Failed to get user email: {str(e)}")
        raise

def validate_tokens(tokens: Dict[str, Any]) -> bool:
    """
    Validate that the token response contains required fields
    """
    required_fields = ["access_token", "token_type"]
    
    for field in required_fields:
        if field not in tokens:
            logger.error(f"Missing required field in token response: {field}")
            return False
    
    # Check token type
    if tokens.get("token_type", "").lower() != "bearer":
        logger.warning(f"Unexpected token type: {tokens.get('token_type')}")
    
    return True

def refresh_access_token(refresh_token: str, config) -> Dict[str, Any]:
    """
    Refresh an access token using a refresh token
    This can be used for token renewal in the future
    """
    try:
        logger.info("Refreshing access token...")
        
        refresh_data = {
            "client_id": config.GOOGLE_CLIENT_ID,
            "client_secret": config.GOOGLE_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }
        
        response = requests.post(
            config.GOOGLE_TOKEN_URL,
            data=refresh_data,
            timeout=30
        )
        
        if response.status_code != 200:
            logger.error(f"Token refresh failed: {response.status_code} - {response.text}")
            raise Exception(f"Failed to refresh token: {response.text}")
        
        tokens = response.json()
        
        if not validate_tokens(tokens):
            raise Exception("Invalid token response received")
        
        logger.info("Successfully refreshed access token")
        return tokens
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error during token refresh: {str(e)}")
        raise Exception(f"Network error during token refresh: {str(e)}")
    except Exception as e:
        logger.error(f"Token refresh failed: {str(e)}")
        raise

def test_token_validity(access_token: str) -> bool:
    """
    Test if an access token is still valid by making a simple API call
    """
    try:
        response = requests.get(
            "https://www.googleapis.com/oauth2/v1/tokeninfo",
            params={"access_token": access_token},
            timeout=10
        )
        
        return response.status_code == 200
        
    except Exception as e:
        logger.warning(f"Token validity test failed: {str(e)}")
        return False

def extract_code_from_url(url: str) -> str:
    """
    Extract authorization code from a Google OAuth callback URL
    Useful if users paste the full callback URL instead of just the code
    """
    try:
        parsed_url = urllib.parse.urlparse(url)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if "code" in query_params:
            code = query_params["code"][0]
            return code
        
        return ""
        
    except Exception as e:
        logger.warning(f"Failed to extract code from URL: {str(e)}")
        return ""

def format_scopes_for_display(scopes: list) -> str:
    """
    Format OAuth scopes in a human-readable way for display
    """
    scope_descriptions = {
        "openid": "Basic profile identification",
        "email": "Email address",
        "profile": "Basic profile information",
        "https://www.googleapis.com/auth/userinfo.email": "Email address",
        "https://www.googleapis.com/auth/userinfo.profile": "Profile information",
        "https://www.googleapis.com/auth/drive.readonly": "Read Google Drive files",
        "https://www.googleapis.com/auth/calendar": "Manage Google Calendar",
        "https://www.googleapis.com/auth/gmail.readonly": "Read Gmail messages",
        "https://www.googleapis.com/auth/contacts.readonly": "Read contacts",
        "https://www.googleapis.com/auth/contacts.other.readonly": "Read other contacts",
    }
    
    descriptions = []
    for scope in scopes:
        desc = scope_descriptions.get(scope, scope)
        descriptions.append(f"• {desc}")
    
    return "\n".join(descriptions)