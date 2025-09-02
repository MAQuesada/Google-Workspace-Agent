import gradio as gr

from api_client import APIClient
from user_management import create_user_management_interface
from google_auth import create_auth_interface
from chat_interface import create_chat_interface

def main():
    api_base_url = "http://127.0.0.1:8000"  # Adjust as needed
    api_key = None  # Insert your API key here if required
    api_client = APIClient(api_base_url, api_key)

    with gr.Blocks() as demo:
        gr.Markdown("# Google Workspace Agent")

        with gr.Tabs():
            with gr.TabItem("User Management"):
                user_mgmt_components = create_user_management_interface(api_client)

            with gr.TabItem("Google Authentication"):
                google_auth_components = create_auth_interface(api_client)

            with gr.TabItem("Chat"):
                chat_components = create_chat_interface(api_client)

    demo.launch()

if __name__ == "__main__":
    main()
