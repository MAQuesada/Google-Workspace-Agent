import streamlit as st
import json
import time
import uuid

from utils.logger import get_logger

logger = get_logger()


def main():
    st.title("Google Workspace Agent Chat Interface")

    if not st.session_state.get("is_authenticated", False):
        st.warning("Please log in first.")
        st.switch_page("main.py")
        return

    # Navigation buttons
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("← Back to Main"):
            st.switch_page("main.py")
    with col2:
        if st.button("Logout", type="secondary"):
            # Clear all session state related to authentication
            for key in list(st.session_state.keys()):
                if key in st.session_state:
                    del st.session_state[key]
            st.success("Logged out successfully!")
            time.sleep(1)
            st.switch_page("main.py")

    client = st.session_state.api_client
    username = st.session_state.username
    accounts = st.session_state.accounts

    if not accounts:
        st.warning("Associate a Google account to chat.")
        if st.button("Go to Account Management"):
            st.switch_page("main.py")
        return

    # Filter working accounts (non-expired)
    working_accounts = []
    for account in accounts:
        account_status = account.get("details", "Unknown status")
        is_expired = (
            "expired" in account_status.lower() or "revoked" in account_status.lower()
        )
        if not is_expired:
            working_accounts.append(account)

    if not working_accounts:
        st.error(
            "No active Google accounts available. Please re-authenticate your accounts."
        )
        if st.button("Go to Account Management"):
            st.switch_page("main.py")
        return

    # # Account selection dropdown with better formatting
    # st.subheader("Account Selection")
    # account_emails = [acc["account_email"] for acc in working_accounts]
    # account_labels = []
    # for acc in working_accounts:
    #     account_info = acc.get("account_info", "No label")
    #     if "(" in account_info and ")" in account_info:
    #         label = account_info.split(" (")[0]
    #     else:
    #         label = account_info
    #     account_labels.append(f"{acc['account_email']} ({label})")

    # # Initialize selected account index if not set
    # if "selected_account_idx" not in st.session_state:
    #     # Check if there's a previously selected account email
    #     if st.session_state.get("selected_account_email"):
    #         try:
    #             idx = account_emails.index(st.session_state.selected_account_email)
    #             st.session_state.selected_account_idx = idx
    #         except ValueError:
    #             st.session_state.selected_account_idx = 0
    #     else:
    #         st.session_state.selected_account_idx = 0

    # selected_account_idx = st.selectbox(
    #     "Select Google Account:",
    #     range(len(working_accounts)),
    #     index=st.session_state.selected_account_idx,
    #     format_func=lambda x: account_labels[x],
    #     help="Choose which Google account to use for this chat session",
    # )

    # # Update session state if selection changed
    # if st.session_state.selected_account_idx != selected_account_idx:
    #     st.session_state.selected_account_idx = selected_account_idx
    #     st.session_state.selected_account_email = account_emails[selected_account_idx]
    #     st.rerun()

    # selected_account = working_accounts[selected_account_idx]
    # st.info(
    #     f"Using account: **{selected_account['account_email']}** ({account_labels[selected_account_idx].split('(')[1].rstrip(')')})"
    # )

    # Conversation ID input with better UX
    st.subheader("Conversation Management")
    col1, col2 = st.columns([3, 1])
    with col1:
        conversation_id = st.text_input(
            "Conversation ID",
            value=st.session_state.get("current_conversation_id", "conv-1"),
            help="Unique identifier for this conversation. Change to start a new conversation.",
        )

    with col2:
        if st.button("New Chat", help="Generate a new conversation ID"):
            new_id = f"conv-{str(uuid.uuid4())[:8]}"
            st.session_state["current_conversation_id"] = new_id
            # Clear current chat when starting new conversation
            if "chat_messages" in st.session_state:
                if conversation_id in st.session_state.chat_messages:
                    del st.session_state.chat_messages[conversation_id]
            st.rerun()

    # Check if conversation ID changed and update session state
    if (
        "current_conversation_id" not in st.session_state
        or st.session_state.current_conversation_id != conversation_id
    ):
        st.session_state.current_conversation_id = conversation_id

    # Initialize session state for chat messages per conversation
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = {}
    if conversation_id not in st.session_state.chat_messages:
        st.session_state.chat_messages[conversation_id] = []

    # Initialize other session state
    if "show_history" not in st.session_state:
        st.session_state.show_history = False
    if "current_history" not in st.session_state:
        st.session_state.current_history = {}
    if "available_conversations" not in st.session_state:
        st.session_state.available_conversations = []

    # Sidebar for chat history controls
    with st.sidebar:
        st.header("Chat Controls")

        # Show current conversation info
        st.info(f"**Current Chat:** {conversation_id}")
        st.info(
            f"**Messages:** {len(st.session_state.chat_messages.get(conversation_id, []))}"
        )

        # History management section
        st.subheader("Chat History")

        # Show/Hide history button
        if not st.session_state.show_history:
            if st.button("Show Chat History", use_container_width=True):
                st.session_state.show_history = True
                # Clear cached history to force refresh
                st.session_state.current_history = {}
                st.rerun()
        else:
            # When showing history, provide conversation selection
            if st.button("Hide Chat History", use_container_width=True):
                st.session_state.show_history = False
                st.rerun()

            # Get available conversations from backend
            try:
                # This would need to be implemented in your API - getting list of conversation IDs
                # For now, we'll use conversations from current session plus the current one
                session_conversations = list(st.session_state.chat_messages.keys())
                if conversation_id not in session_conversations:
                    session_conversations.append(conversation_id)

                if session_conversations:
                    st.write("**Select Conversation:**")
                    selected_conv_for_history = st.selectbox(
                        "Choose conversation to view history:",
                        session_conversations,
                        index=session_conversations.index(conversation_id)
                        if conversation_id in session_conversations
                        else 0,
                        key="history_conv_select",
                    )

                    # Load and show history for selected conversation
                    if st.button("Load History", use_container_width=True):
                        if (
                            selected_conv_for_history
                            not in st.session_state.current_history
                        ):
                            try:
                                with st.spinner("Loading chat history..."):
                                    history = client.get_chat_history(
                                        username, selected_conv_for_history
                                    )
                                    st.session_state.current_history[
                                        selected_conv_for_history
                                    ] = history or []
                                    st.success(f"Loaded {len(history or [])} messages")
                            except Exception as e:
                                st.error(f"Failed to load history: {str(e)}")
                                st.session_state.current_history[
                                    selected_conv_for_history
                                ] = []
                        else:
                            st.info("History already loaded")

                    # Clear history button (only show if history is loaded)
                    if selected_conv_for_history in st.session_state.current_history:
                        if st.button(
                            "Clear Loaded History",
                            use_container_width=True,
                            type="secondary",
                        ):
                            if (
                                selected_conv_for_history
                                in st.session_state.current_history
                            ):
                                del st.session_state.current_history[
                                    selected_conv_for_history
                                ]
                            st.success("History cleared from view")
                            st.rerun()

            except Exception as e:
                st.error(f"Error managing conversations: {str(e)}")

        st.divider()

        # Clear current session messages for this conversation
        if st.button("Clear Current Chat", use_container_width=True):
            st.session_state.chat_messages[conversation_id] = []
            st.rerun()

        # Clear all conversations
        if st.button("Clear All Chats", use_container_width=True, type="secondary"):
            st.session_state.chat_messages = {}
            st.session_state.current_history = {}
            st.rerun()

        st.divider()

        # Conversation history navigation
        if st.session_state.chat_messages:
            st.subheader("Session Conversations")
            for conv_id in st.session_state.chat_messages.keys():
                msg_count = len(st.session_state.chat_messages[conv_id])
                is_current = conv_id == conversation_id

                button_label = f"{'🔸' if is_current else ''} {conv_id}"
                button_help = f"Messages: {msg_count}"

                if st.button(
                    button_label,
                    use_container_width=True,
                    disabled=is_current,
                    key=f"switch_{conv_id}",
                    help=button_help,
                ):
                    st.session_state.current_conversation_id = conv_id
                    st.rerun()

    # Display chat history if enabled and loaded
    if st.session_state.show_history:
        selected_conv_for_history = st.session_state.get(
            "history_conv_select", conversation_id
        )

        if selected_conv_for_history in st.session_state.current_history:
            st.subheader(f"Chat History for {selected_conv_for_history}")

            history = st.session_state.current_history[selected_conv_for_history]

            with st.expander(
                f"Previous Messages ({len(history)} messages)", expanded=True
            ):
                if history:
                    for i, msg in enumerate(history):
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        timestamp = msg.get("timestamp", "")

                        with st.container():
                            if role == "user":
                                with st.chat_message("user"):
                                    st.write(content)
                            else:
                                with st.chat_message("assistant"):
                                    st.write(content)

                            if timestamp:
                                st.caption(f"_{timestamp}_")

                            if i < len(history) - 1:
                                st.divider()
                else:
                    st.info("No previous messages found for this conversation.")

            st.divider()

    # Current chat interface
    st.subheader(f"Current Conversation: {conversation_id}")

    # Display current session messages in chat format
    current_messages = st.session_state.chat_messages.get(conversation_id, [])

    # Create a container for messages
    chat_container = st.container()

    with chat_container:
        for message in current_messages:
            if message["role"] == "user":
                with st.chat_message("user"):
                    st.write(message["content"])
            else:
                with st.chat_message("assistant"):
                    st.write(message["content"])

    # Message input
    user_input = st.chat_input("Type your message here...")

    if user_input:
        # Add user message to session immediately for this conversation
        if conversation_id not in st.session_state.chat_messages:
            st.session_state.chat_messages[conversation_id] = []

        st.session_state.chat_messages[conversation_id].append(
            {"role": "user", "content": user_input}
        )

        # Display user message
        with st.chat_message("user"):
            st.write(user_input)

        # Create assistant response placeholder
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            progress_placeholder = st.empty()

            full_response = ""

            try:
                # Make the API call with selected account context
                response = client.start_chat_stream(
                    username, conversation_id, user_input
                )

                # Process the streaming response
                for chunk in response:
                    if not chunk:
                        continue

                    try:
                        chunk_text = chunk.decode("utf-8").strip()

                        if not chunk_text:
                            continue

                        if chunk_text.startswith("data: "):
                            json_data = chunk_text[6:]
                        else:
                            json_data = chunk_text

                        data = json.loads(json_data)

                        message_type = data.get("type", "")
                        content = data.get("data", "")

                        if message_type == "progress":
                            # Clear and replace the progress message instead of appending
                            progress_placeholder.info(
                                f"**Processing...**\n\n• {content}"
                            )

                        elif message_type == "content":
                            # Clear the progress placeholder when content starts to stream
                            if progress_placeholder:
                                progress_placeholder.empty()

                            full_response += content
                            message_placeholder.markdown(full_response + "▌")

                        elif message_type == "error":
                            progress_placeholder.empty()
                            message_placeholder.error(f"Error: {content}")
                            full_response = f"Error: {content}"
                            break

                    except json.JSONDecodeError:
                        continue
                    except Exception as e:
                        st.error(f"Error processing chunk: {str(e)}")
                        continue

                if full_response:
                    message_placeholder.markdown(full_response)
                    st.session_state.chat_messages[conversation_id].append(
                        {"role": "assistant", "content": full_response}
                    )

                # Invalidate history cache so it refreshes on next load
                if conversation_id in st.session_state.current_history:
                    del st.session_state.current_history[conversation_id]

            except Exception as e:
                if "progress_placeholder" in locals():
                    progress_placeholder.empty()
                error_msg = f"Connection error: {str(e)}"
                message_placeholder.error(f"Error: {error_msg}")
                st.session_state.chat_messages[conversation_id].append(
                    {"role": "assistant", "content": error_msg}
                )
                logger.error("Chat stream error", extra={"error": str(e)})

        st.rerun()

    # Enhanced chat tips
    with st.expander("Chat Tips & Information", expanded=False):
        st.markdown(f"""
        **Current Session:**
        - **Conversation ID**: `{conversation_id}`
        - **Session Messages**: {len(current_messages)}

        **Features:**
        - **Live Streaming**: Responses appear in real-time as they're generated
        - **Progress Tracking**: Watch the processing steps before content appears
        - **Multi-Conversation**: Each conversation ID maintains separate history
        - **Account Switching**: Use different Google accounts for different contexts
        - **History Management**: Use sidebar to manage and view chat history
        - **Multi-Agent**: The system routes requests to appropriate agents automatically

        **How to Use History:**
        1. Click "Show Chat History" in the sidebar
        2. Select a conversation from the dropdown
        3. Click "Load History" to view past messages
        4. Use "Clear Loaded History" to remove from view
        5. Click "Hide Chat History" when done

        **Tips:**
        - Change the Conversation ID to start a fresh chat
        - Use the sidebar to navigate between different conversations
        - Clear individual chats or all chats using sidebar buttons
        - Switch accounts if you have multiple Google accounts associated
        - Use descriptive conversation IDs for better organization
        - History is loaded on-demand to improve performance
        """)


if __name__ == "__main__":
    main()
