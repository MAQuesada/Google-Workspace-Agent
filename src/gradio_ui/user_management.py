import gradio as gr
from typing import Tuple
import logging

logger = logging.getLogger(__name__)

def create_user_interface(api_client):
    """Create the user management interface."""

    def create_user(username: str) -> Tuple[str, str]:
        """Handle user creation with validation and API call."""
        username = username.strip()
        if not username:
            return "Please enter a username", ""

        try:
            result = api_client.create_user(username)
            if result["success"]:
                user_data = result["data"]
                user_id = user_data.get("id", "N/A")
                return result["message"], f"User ID: {user_id}"
            else:
                return f"Error: {result['message']}", ""
        except Exception as e:
            logger.error(f"Exception in create_user: {e}")
            return f"Error: {str(e)}", ""

    def refresh_user_list() -> str:
        """Fetch and format the user list from the API."""
        try:
            result = api_client.list_users()
            if result["success"]:
                users = result["data"]
                if not users:
                    return "No users found"

                user_list = []
                for user in users:
                    if isinstance(user, dict):
                        username = user.get("username", "Unknown")
                        user_id = user.get("id", "N/A")
                        user_list.append(f"• {username} (ID: {user_id})")
                    else:
                        user_list.append(f"• {user}")

                return "\n".join(user_list)
            else:
                return f"Error retrieving users: {result['message']}"
        except Exception as e:
            logger.error(f"Exception in refresh_user_list: {e}")
            return f"Error: {str(e)}"

    # UI component layout
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("## Create New User")
            username_input = gr.Textbox(
                label="Username",
                placeholder="Enter unique username",
                info="Choose a unique identifier for the user"
            )
            create_btn = gr.Button("Create User", variant="primary")

            creation_status = gr.Textbox(
                label="Status",
                interactive=False,
                show_label=True
            )
            user_id_display = gr.Textbox(
                label="User Details",
                interactive=False,
                show_label=True
            )

        with gr.Column(scale=2):
            gr.Markdown("## Existing Users")
            refresh_btn = gr.Button("Refresh User List", variant="secondary")
            user_list_display = gr.Textbox(
                label="Users",
                lines=10,
                interactive=False,
                show_label=True
            )

    # Event bindings
    create_btn.click(
        fn=create_user,
        inputs=[username_input],
        outputs=[creation_status, user_id_display]
    )

    refresh_btn.click(
        fn=refresh_user_list,
        outputs=[user_list_display]
    )

    # Auto-refresh user list on page load
    user_list_display.load(
        fn=refresh_user_list,
        outputs=[user_list_display]
    )

    return {
        "username_input": username_input,
        "create_btn": create_btn,
        "creation_status": creation_status,
        "user_id_display": user_id_display,
        "user_list_display": user_list_display
    }
