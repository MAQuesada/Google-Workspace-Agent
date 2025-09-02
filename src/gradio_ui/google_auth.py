import gradio as gr
from typing import Tuple

def create_auth_interface(api_client):
    def associate_account_ui(username: str, refresh_token: str, account_info: str) -> Tuple[str, str]:
        username = username.strip()
        refresh_token = refresh_token.strip()
        if not username or not refresh_token:
            return "Please provide both Username and Refresh Token.", ""

        result = api_client.associate_account(username, refresh_token, account_info.strip())
        if result.get("success"):
            accounts = result.get("data", {}).get("accounts", [])
            accounts_text = "\n".join([f"• {acc.get('account_email')} ({acc.get('account_info', 'N/A')})" for acc in accounts])
            return "Account associated successfully!", accounts_text
        else:
            return f"Error: {result.get('message')}", ""

    def get_accounts_ui(username: str) -> str:
        username = username.strip()
        if not username:
            return "Please provide a Username."
        result = api_client.get_user_accounts(username)
        if result.get("success"):
            accounts = result.get("data", [])
            if not accounts:
                return "No Google accounts found."
            return "\n".join([f"• {acc.get('account_email')} ({acc.get('account_info', 'N/A')})" for acc in accounts])
        else:
            return f"Error: {result.get('message')}"

    with gr.Row():
        with gr.Column(scale=1):
            gr.Markdown("## Google Account Association")

            username_input = gr.Textbox(label="Username", placeholder="Existing Username")
            refresh_token_input = gr.Textbox(label="Refresh Token", placeholder="Paste refresh token here", lines=2)
            account_info_input = gr.Textbox(label="Account Info (Optional)", placeholder="E.g., Personal, Work")

            associate_button = gr.Button("Associate Google Account")

            status_output = gr.Textbox(label="Status", interactive=False)
            accounts_output = gr.Textbox(label="Linked Accounts", interactive=False, lines=6)

            associate_button.click(
                associate_account_ui,
                inputs=[username_input, refresh_token_input, account_info_input],
                outputs=[status_output, accounts_output]
            )

            check_accounts_button = gr.Button("Show Linked Accounts")
            check_accounts_button.click(
                get_accounts_ui,
                inputs=[username_input],
                outputs=[accounts_output]
            )

    return {
        "username_input": username_input,
        "refresh_token_input": refresh_token_input,
        "account_info_input": account_info_input,
        "status_output": status_output,
        "accounts_output": accounts_output,
        "associate_button": associate_button,
        "check_accounts_button": check_accounts_button,
    }
