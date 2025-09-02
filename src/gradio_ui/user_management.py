import gradio as gr
from typing import Tuple, List

def create_user_management_interface(api_client):
    def create_user_ui(username: str) -> str:
        username = username.strip()
        if not username:
            return "Please enter a username."
        result = api_client.create_user(username)
        if result.get("success"):
            return f"User '{username}' created successfully."
        else:
            return f"Error: {result.get('message')}"

    def list_users_ui() -> str:
        result = api_client.list_users()
        if result.get("success"):
            users = result.get("data", [])
            if not users:
                return "No users found."
            return "\n".join(users)
        else:
            return f"Error: {result.get('message')}"

    with gr.Column():
        gr.Markdown("## User Management")

        username_input = gr.Textbox(label="New Username", placeholder="Enter username to create")
        create_button = gr.Button("Create User")
        create_status = gr.Textbox(label="Status", interactive=False)

        list_button = gr.Button("List Users")
        user_list = gr.Textbox(label="Existing Users", interactive=False, lines=8)

        create_button.click(create_user_ui, inputs=username_input, outputs=create_status)
        list_button.click(list_users_ui, inputs=None, outputs=user_list)

    return {
        "username_input": username_input,
        "create_button": create_button,
        "create_status": create_status,
        "list_button": list_button,
        "user_list": user_list,
    }
