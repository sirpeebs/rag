import os
import openai
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# Set your OpenAI API key (ensure you have set this environment variable)
openai.api_key = os.getenv("OPENAI_API_KEY")

def get_openai_response(messages):
    """
    Sends the conversation messages to the OpenAI API and returns the generated response.
    Automatically prepends a system message if not present.
    """
    # Ensure a system message is included as context (best practice)
    if not messages or messages[0].get("role") != "system":
        system_message = {"role": "system", "content": "You are ChatGPT, a helpful assistant."}
        messages.insert(0, system_message)
    try:
        response = openai.ChatCompletion.create(
            model="gpt-3.5-turbo",  # or your preferred model
            messages=messages,
            max_tokens=150,
            n=1,
            stop=None,
            temperature=0.7,
        )
        answer = response.choices[0].message['content'].strip()
        return answer
    except Exception as e:
        return f"Error: {str(e)}"

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    # Expect a conversation array with message objects ({ role, content })
    conversation = data.get("conversation", [])
    assistant_reply = get_openai_response(conversation)
    return jsonify({"response": assistant_reply})

if __name__ == "__main__":
    app.run(debug=True)
