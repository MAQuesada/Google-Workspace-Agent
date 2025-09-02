import gradio as gr
import requests
import threading
import queue

def create_chat_interface(api_client):
    chat_history = queue.Queue()

    def send_message(username: str, conversation_id: str, message: str):
        if not username.strip() or not conversation_id.strip():
            return "Please enter Username and Conversation ID."

        url = f"{api_client.base_url}/chat"
        headers = api_client.session.headers
        payload = {
            "username": username,
            "conversation_id": conversation_id,
            "message": message
        }

        # We use a list to accumulate streamed messages
        messages = []

        # SSE streaming using requests (requests does not natively support SSE so polling or a library is better)
        # For simplicity, we do a blocking request and parse chunks
        with requests.post(url, headers=headers, json=payload, stream=True) as response:
            if response.status_code != 200:
                return f"Error: {response.text}"

            for line in response.iter_lines():
                if line:
                    decoded = line.decode('utf-8')
                    if decoded.startswith("data: "):
                        data_str = decoded[6:]
                        try:
                            data_json = json.loads(data_str)
                            if data_json.get("type") == "progress":
                                messages.append(f"[Processing] {data_json.get('data')}")
                            elif data_json.get("type") == "content":
                                messages.append(data_json.get("data"))
                        except Exception:
                            continue

        return "\n".join(messages)

    def clear_chat():
        while not chat_history.empty():
            chat_history.get()
        return ""

    with gr.Column():
        gr.Markdown("## Chat Interface")

        username_input = gr.Textbox(label="Username", placeholder="User identifier")
        conv_id_input = gr.Textbox(label="Conversation ID", placeholder="Conversation ID")
        message_input = gr.Textbox(label="Message", placeholder="Enter your message")

        send_button = gr.Button("Send Message")
        clear_button = gr.Button("Clear Chat")

        output_box = gr.Textbox(label="Conversation", lines=15, interactive=False)

        send_button.click(send_message,
                          inputs=[username_input, conv_id_input, message_input],
                          outputs=output_box)
        clear_button.click(clear_chat, outputs=output_box)

    return {
        "username_input": username_input,
        "conv_id_input": conv_id_input,
        "message_input": message_input,
        "send_button": send_button,
        "clear_button": clear_button,
        "output_box": output_box,
    }
