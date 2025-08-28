import gradio as gr
from typing import List, Tuple
import logging

logger = logging.getLogger(__name__)

def create_chat_interface(api_client):
    """Create the chat interface for interacting with Google Workspace Agent."""

    def send_message(user_id: str, message: str, chat_history: List[List[str]]) -> Tuple[List[List[str]], str, str]:
        """
        Send a message to the orchestrator and update chat history.

        Returns updated chat history, cleared input message, and status message.
        """
        user_id = user_id.strip()
        message = message.strip()

        if not user_id:
            error_msg = "Please enter a User ID"
            chat_history.append(["System", error_msg])
            return chat_history, "", error_msg

        if not message:
            error_msg = "Please enter a message"
            chat_history.append(["System", error_msg])
            return chat_history, "", error_msg

        # Add user message to chat history
        chat_history.append(["You", message])

        try:
            # Send request to API
            result = api_client.chat(user_id=user_id, user_request=message)

            if result["success"]:
                api_response = result["data"]
                
                # Handle typical possible response structures
                if isinstance(api_response, dict):
                    if "response" in api_response:
                        ai_response = api_response["response"]
                    elif "messages" in api_response and api_response["messages"]:
                        last_message = api_response["messages"][-1]
                        ai_response = last_message.get("content", str(last_message))
                    else:
                        ai_response = str(api_response)
                else:
                    ai_response = str(api_response)

                chat_history.append(["Agent", ai_response])
                status = "Message sent successfully"

            else:
                error_response = f"API Error: {result['message']}"
                chat_history.append(["System", error_response])
                status = error_response

        except Exception as e:
            logger.error(f"Error sending message: {e}")
            error_response = f"Error: {str(e)}"
            chat_history.append(["System", error_response])
            status = error_response

        return chat_history, "", status  # Clear message input

    def clear_chat(chat_history: List[List[str]]) -> Tuple[List[List[str]], str]:
        """Clear the chat history."""
        return [], "Chat cleared"

    def get_user_info(user_id: str) -> str:
        """Get user information and linked Google accounts."""
        user_id = user_id.strip()
        if not user_id:
            return "Please enter a User ID"

        try:
            result = api_client.get_user_accounts(user_id)
            if result["success"]:
                accounts = result["data"]
                if not accounts:
                    return f"User ID: {user_id}\nGoogle Accounts: None"

                account_info = []
                for account in accounts:
                    email = account.get("account_email", "Unknown")
                    info = account.get("account_info", "N/A")
                    account_info.append(f"• {email} ({info})")

                accounts_text = "\n".join(account_info)
                return f"User ID: {user_id}\n\nGoogle Accounts:\n{accounts_text}"
            else:
                return f"Error getting user info: {result['message']}"

        except Exception as e:
            logger.error(f"Error getting user info: {e}")
            return f"Error: {str(e)}"

    def format_chat_history(chat_history: List[List[str]]) -> str:
        """Format chat history for display in readable markdown style."""
        if not chat_history:
            return "No messages yet. Start a conversation!"

        formatted = []
        for sender, message in chat_history:
            if sender == "You":
                formatted.append(f"**You:** {message}")
            elif sender == "Agent":
                formatted.append(f"**Agent:** {message}")
            elif sender == "System":
                formatted.append(f"*System:* {message}")

        return "\n\n".join(formatted)

    # UI Components Layout
    with gr.Row():
        with gr.Column(scale=2):
            gr.Markdown("## Chat with Google Workspace Agent")

            user_id_input = gr.Textbox(
                label="User ID",
                placeholder="Enter your user ID",
                info="User must exist and have Google accounts configured"
            )

            get_info_btn = gr.Button("Get User Info", variant="secondary", size="sm")

            user_info_display = gr.Textbox(
                label="User Information",
                lines=4,
                interactive=False,
                info="Shows user ID and connected Google accounts"
            )

            gr.Markdown("---")

            chat_display = gr.Chatbot(
                label="Conversation",
                height=400,
                show_label=True
            )

            with gr.Row():
                message_input = gr.Textbox(
                    label="Message",
                    placeholder="Type your request here... (e.g., 'Schedule a meeting for tomorrow at 3pm')",
                    lines=2,
                    scale=4
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)

            with gr.Row():
                clear_btn = gr.Button("Clear Chat", variant="secondary")

            status_display = gr.Textbox(
                label="Status",
                interactive=False,
                show_label=True
            )

        with gr.Column(scale=1):
            gr.Markdown("## Usage Examples")

            examples_md = gr.Markdown("""
### Email Tasks:
- "Send an email to [john@example.com](mailto:john@example.com) about the meeting"
- "Find all emails from last week about project updates"
- "Draft an email to the team about the deadline"


### Calendar Tasks:
- "Schedule a meeting with Sarah tomorrow at 2pm"
- "What meetings do I have this week?"
- "Create a recurring weekly standup meeting"
- "Find available time slots for next Monday"


### Contact Tasks:
- "Add a new contact: John Smith, john@company.com"
- "Find contacts from Google Inc"
- "Update Sarah's phone number to 555-1234"


### Search Tasks:
- "Search for documents about quarterly reports"
- "Find files modified last month"


### Date/Time Tasks:
- "What's the date next Friday?"
- "Show me dates for the last 7 days"
            """)

            tips_md = gr.Markdown("""
- Be specific about dates, times, and recipients
- The agent can work across multiple Google accounts
- Use natural language - no special commands needed  
- Check that your user has Google accounts configured
- The agent will ask for clarification if needed
            """)

    # Event handlers
    send_btn.click(
        fn=send_message,
        inputs=[user_id_input, message_input, chat_display],
        outputs=[chat_display, message_input, status_display]
    )

    message_input.submit(
        fn=send_message,
        inputs=[user_id_input, message_input, chat_display],
        outputs=[chat_display, message_input, status_display]
    )

    clear_btn.click(
        fn=clear_chat,
        inputs=[chat_display],
        outputs=[chat_display, status_display]
    )

    get_info_btn.click(
        fn=get_user_info,
        inputs=[user_id_input],
        outputs=[user_info_display]
    )

    return {
        "user_id_input": user_id_input,
        "chat_display": chat_display,
        "message_input": message_input,
        "status_display": status_display
    }
