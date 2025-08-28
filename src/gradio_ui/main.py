import gradio as gr
import os
from dotenv import load_dotenv

from gradio_ui.user_management import create_user_interface
from gradio_ui.google_auth import create_auth_interface
from gradio_ui.chat_interface import create_chat_interface
from gradio_ui.api_client import APIClient

load_dotenv()

# Initialize the API client with base URL from environment variables (default localhost)
api_client = APIClient(base_url=os.getenv("API_BASE_URL", "http://localhost:8000"))

def create_app():
    """Create the main Gradio app with tabs for user, auth, and chat."""
    with gr.Blocks(title="Google Workspace Agent", theme=gr.themes.Soft()) as app:
        gr.Markdown("# Google Workspace Agent")
        gr.Markdown("Manage Google Workspace tasks through natural language")

        with gr.Tabs():
            with gr.Tab("User Management"):
                create_user_interface(api_client)

            with gr.Tab("Google Authentication"):
                create_auth_interface(api_client)

            with gr.Tab("Chat"):
                create_chat_interface(api_client)

    return app

if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
        debug=True
    )
