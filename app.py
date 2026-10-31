# app.py
import streamlit as st

st.set_page_config(page_title="AI Agent", layout="centered")
st.title("🤖 AI Agent")

# 1. State: Keeps chat history across script reruns
if "messages" not in st.session_state:
    st.session_state.messages = []

# 2. Render: Display past conversation
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if "tools" in msg and msg["tools"]:
            with st.expander("🛠️ Tool Output"):
                st.write(msg["tools"])

# 3. Logic: Replace this single function with your actual agent/database logic
def run_agent_logic(user_query: str):
    # --- YOUR LOGIC / TOOL CALLING GOES HERE ---
    response = f"Answer to: {user_query}"
    tools_called = ["database_search", "calculator"]
    return response, tools_called

# 4. Input: Handle user submission
if prompt := st.chat_input("Ask a question..."):
    # Append & render user message
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # Execute logic and render assistant response
    with st.chat_message("assistant"):
        with st.spinner("Processing..."):
            answer, tools_used = run_agent_logic(prompt)
            st.markdown(answer)
            if tools_used:
                with st.expander("🛠️ Tool Output"):
                    st.write(tools_used)

    # Save assistant message to state
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "tools": tools_used
    })