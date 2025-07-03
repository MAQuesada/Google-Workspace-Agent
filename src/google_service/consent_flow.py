import webbrowser
import urllib.parse
import requests

from dotenv import load_dotenv
from utils.config import get_config
from google_service.core import UserService

load_dotenv()

REDIRECT_URI = "urn:ietf:wg:oauth:2.0:oob"


def build_auth_url():
    params = {
        "client_id": get_config().GOOGLE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "scope": " ".join(get_config().GOOGLE_SCOPES),
    }
    return (
        f"https://accounts.google.com/o/oauth2/v2/auth?{urllib.parse.urlencode(params)}"
    )


def exchange_code_for_tokens(code: str):
    data = {
        "code": code,
        "client_id": get_config().GOOGLE_CLIENT_ID,
        "client_secret": get_config().GOOGLE_CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
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


def main():
    print("🔐 Starting Google OAuth2 consent flow...\n")
    auth_url = build_auth_url()
    print("👉 Opening browser for authorization...")
    webbrowser.open(auth_url)

    print("🔁 After authorizing, paste the code that appears here:")
    code = input("Authorization code: ").strip()

    print("\n🔄 Exchanging code for tokens...")
    token_data = exchange_code_for_tokens(code)

    refresh_token = token_data.get("refresh_token")
    access_token = token_data.get("access_token")

    if not refresh_token:
        print("❌ No refresh_token obtained. Have you authorized this account before?")
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


if __name__ == "__main__":
    main()
