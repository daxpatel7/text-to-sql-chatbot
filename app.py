import streamlit as st

from dotenv import load_dotenv
from schema import get_schema
from ai_provider import generate_sql
from database import validate_sql, execute_sql, suggest_keyword


load_dotenv()

# Page Setup
st.set_page_config(
    page_title="Text-to-SQL AI",
    page_icon="logo.png",
    layout="centered"
)


# --------------------------------------------------
# Custom UI
# --------------------------------------------------

st.markdown("""
<style>
    .block-container {
        max-width: 750px;
        padding-top: 2rem;
        padding-bottom: 5rem;
    }

    .app-header {
        text-align: center;
        margin-bottom: 2rem;
    }

    .app-title {
        font-size: 2rem;
        font-weight: 700;
        margin-bottom: 0.3rem;
    }

    .app-subtitle {
        color: #888;
        font-size: 0.95rem;
    }

    .sql-label {
        font-size: 0.85rem;
        font-weight: 600;
        color: #888;
        margin-top: 0.5rem;
        margin-bottom: 0.3rem;
    }

    .result-label {
        font-size: 0.9rem;
        font-weight: 600;
        margin-top: 0.8rem;
        margin-bottom: 0.4rem;
    }

    [data-testid="stChatMessage"] {
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)
# Header

st.markdown(
    '<div class="app-header">',
    unsafe_allow_html=True
)

st.image("logo.png", width=60)

st.markdown(
    '<div class="app-title">Text-to-SQL AI</div>',
    unsafe_allow_html=True
)

st.markdown(
    '<div class="app-subtitle">'
    'Ask questions about your database in natural language.'
    '</div>',
    unsafe_allow_html=True
)

st.markdown(
    '</div>',
    unsafe_allow_html=True
)

# Session State

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None

if "confirmed_question" not in st.session_state:
    st.session_state.confirmed_question = None

# Typo Confirmation

def find_confirmation(question):

    for word in question.split():

        clean_word = word.strip(".,!?")

        suggestion = suggest_keyword(clean_word)

        if suggestion and suggestion["type"] == "confirm":

            return {
                "original_word": clean_word,
                "suggested_word": suggestion["keyword"],
                "question": question
            }

    return None

# Conversation History

def get_conversation_history():

    conversation_history = []

    for message in st.session_state.messages:

        if message["role"] == "user":

            conversation_history.append(
                f"User: {message['content']}"
            )

        elif message["role"] == "assistant":

            if message.get("sql"):

                conversation_history.append(
                    f"Assistant (SQL): {message['sql']}"
                )

    return conversation_history

# Display Previous Messages

for message in st.session_state.messages:

    with st.chat_message(message["role"]):

        if message["type"] == "text":

            st.write(message["content"])

        else:

            if message.get("sql"):

                st.code(
                    message["sql"],
                    language="sql"
                )

            if message["content"].empty:

                st.info("No data found.")

            else:

                st.markdown(
                    '<div class="result-label">Result</div>',
                    unsafe_allow_html=True
                )

                st.dataframe(
                    message["content"],
                    width="stretch",
                    hide_index=True
                )
# Process Question

def process_question(question):

    conversation_history = get_conversation_history()

    with st.chat_message("user"):

        st.write(question)

    with st.chat_message("assistant"):

        with st.spinner("Thinking..."):

            try:

                sql = generate_sql(
                    question,
                    conversation_history
                )

                if sql.strip().upper() == "UNSAFE_QUERY":

                    st.error(
                        "The generated query is unsafe. "
                        "Only SELECT queries are allowed."
                    )

                    return

                if sql.strip().upper() == "UNKNOWN_QUERY":

                    st.error(
                        "I couldn't find a matching table "
                        "or column in the database."
                    )

                    return

                if not validate_sql(sql):

                    st.error(
                        "The generated SQL query is invalid."
                    )

                    return

                st.markdown(
                    '<div class="sql-label">'
                    'Generated SQL'
                    '</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    sql,
                    language="sql"
                )
                df = execute_sql(sql)
                if df.empty:

                    st.info("No data found.")

                else:

                    st.markdown(
                        '<div class="result-label">'
                        'Result'
                        '</div>',
                        unsafe_allow_html=True
                    )

                    st.dataframe(
                        df,
                        width="stretch",
                        hide_index=True
                    )

                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "table",
                    "content": df,
                    "sql": sql
                })


            except Exception as e:

                st.error(
                    f"Something went wrong: {e}"
                )

# Pending Confirmation

if st.session_state.pending_confirmation:

    confirmation = st.session_state.pending_confirmation

    st.warning(
        f'Did you mean "{confirmation["suggested_word"]}"?'
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button(
            "Yes",
            width="stretch"
        ):

            corrected_question = (
                confirmation["question"].replace(
                    confirmation["original_word"],
                    confirmation["suggested_word"]
                )
            )

            st.session_state.pending_confirmation = None

            st.session_state.confirmed_question = (
                corrected_question
            )

            st.rerun()

    with col2:

        if st.button(
            "No",
            width="stretch"
        ):

            st.session_state.pending_confirmation = None

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": "Okay. Please rephrase your question."
            })

            st.rerun()

# Confirmed Question

if st.session_state.confirmed_question:

    question = st.session_state.confirmed_question

    st.session_state.confirmed_question = None

    st.session_state.messages.append({
        "role": "user",
        "type": "text",
        "content": question
    })

    process_question(question)

    st.rerun()

# Chat Input
question = st.chat_input(
    "Ask anything about your database..."
)


if question:

    confirmation = find_confirmation(question)

    # Need Confirmation
    
    if confirmation:

        st.session_state.pending_confirmation = confirmation

        st.session_state.messages.append({
            "role": "user",
            "type": "text",
            "content": question
        })

        st.rerun()

    # Normal Question

    st.session_state.messages.append({
        "role": "user",
        "type": "text",
        "content": question
    })

    process_question(question)