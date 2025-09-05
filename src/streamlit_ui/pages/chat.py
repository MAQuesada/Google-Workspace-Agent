# Chat Page (pages/chat.py)
import streamlit as st
import json
import time
import requests

def main():
    st.title("🤖 Google Workspace Multi-Agent Chat")

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
        if st.button("🚪 Logout", type="secondary"):
            # Clear all session state related to authentication
            for key in list(st.session_state.keys()):
                del st.session_state[key]
            st.success("Logged out successfully!")
            time.sleep(1)
            st.switch_page("main.py")

    client = st.session_state.api_client
    username = st.session_state.username
    accounts = st.session_state.accounts

    if not accounts:
        st.warning("Associate a Google account to chat.")
        return

    # Conversation ID input
    conversation_id = st.text_input("Conversation ID", value="conv-1", help="Unique identifier for this conversation")

    # Initialize session state
    if "show_history" not in st.session_state:
        st.session_state.show_history = False
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Sidebar for chat history controls
    with st.sidebar:
        st.header("Chat Controls")
        
        if not st.session_state.show_history:
            if st.button("📜 Show Chat History", use_container_width=True):
                st.session_state.show_history = True
                st.rerun()
        else:
            if st.button("❌ Hide Chat History", use_container_width=True):
                st.session_state.show_history = False
                st.rerun()
        
        st.divider()
        
        # Clear current session messages
        if st.button("🗑️ Clear Current Chat", use_container_width=True):
            st.session_state.chat_messages = []
            st.rerun()

    # Display chat history if enabled
    if st.session_state.show_history:
        st.subheader("📚 Chat History")
        with st.expander("Previous Messages", expanded=False):
            try:
                history = client.get_chat_history(username, conversation_id)
                if history:
                    for msg in history:
                        role = msg.get("role", "user")
                        content = msg.get("content", "")
                        
                        if role == "user":
                            st.markdown(f"**🧑 You:** {content}")
                        else:
                            st.markdown(f"**🤖 Assistant:** {content}")
                else:
                    st.info("No previous messages found.")
            except Exception as e:
                st.error(f"Failed to load history: {str(e)}")

    st.divider()

    # Current chat interface
    st.subheader("💬 Current Conversation")
    
    # Display current session messages in chat format
    for message in st.session_state.chat_messages:
        if message["role"] == "user":
            with st.chat_message("user"):
                st.write(message["content"])
        else:
            with st.chat_message("assistant"):
                st.write(message["content"])

    # Message input
    user_input = st.chat_input("Type your message here...")
    
    if user_input:
        # Add user message to session immediately
        st.session_state.chat_messages.append({"role": "user", "content": user_input})
        
        # Display user message
        with st.chat_message("user"):
            st.write(user_input)

        # Create assistant response placeholder
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            progress_placeholder = st.empty()
            
            full_response = ""
            progress_logs = []
            
            try:
                # Make the API call
                response = client.start_chat_stream(username, conversation_id, user_input)
                
                # Process the streaming response
                for chunk in response:
                    if not chunk:
                        continue
                    
                    try:
                        # Decode the chunk
                        chunk_text = chunk.decode('utf-8').strip()
                        
                        # Skip empty lines
                        if not chunk_text:
                            continue
                        
                        # Handle Server-Sent Events format
                        if chunk_text.startswith('data: '):
                            json_data = chunk_text[6:]  # Remove 'data: ' prefix
                        else:
                            json_data = chunk_text
                        
                        # Parse JSON
                        data = json.loads(json_data)
                        
                        message_type = data.get("type", "")
                        content = data.get("data", "")
                        
                        if message_type == "progress":
                            # Add to progress logs
                            progress_logs.append(content)
                            # Display current progress
                            progress_text = "\n".join([f"• {log}" for log in progress_logs])
                            progress_placeholder.info(f"**Processing...**\n\n{progress_text}")
                            
                        elif message_type == "content":
                            # Clear progress and start streaming content
                            if progress_logs:  # First content chunk
                                progress_placeholder.empty()
                                progress_logs = []
                            
                            # Accumulate response
                            full_response += content
                            # Display accumulated response
                            message_placeholder.markdown(full_response + "▌")
                            
                        elif message_type == "error":
                            progress_placeholder.empty()
                            message_placeholder.error(f"❌ {content}")
                            full_response = f"Error: {content}"
                            break
                            
                    except json.JSONDecodeError:
                        # Skip invalid JSON
                        continue
                    except Exception as e:
                        st.error(f"Error processing chunk: {str(e)}")
                        continue
                
                # Clean up the final response (remove cursor)
                if full_response:
                    message_placeholder.markdown(full_response)
                    # Add to chat history
                    st.session_state.chat_messages.append({
                        "role": "assistant", 
                        "content": full_response
                    })
                
            except Exception as e:
                progress_placeholder.empty()
                error_msg = f"Connection error: {str(e)}"
                message_placeholder.error(f"❌ {error_msg}")
                # Add error to chat history
                st.session_state.chat_messages.append({
                    "role": "assistant", 
                    "content": error_msg
                })
        
        # Force rerun to show updated messages
        st.rerun()

    # Help information
    with st.expander("ℹ️ Chat Tips", expanded=False):
        st.markdown("""
        - **Live Streaming**: Responses appear in real-time as they're generated
        - **Progress Tracking**: Watch the processing steps before content appears
        - **History**: Toggle chat history visibility using the sidebar
        - **Multi-Agent**: The system routes requests to appropriate agents automatically
        """)

if __name__ == "__main__":
    main()