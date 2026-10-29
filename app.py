import streamlit as st
from dotenv import load_dotenv
from pathlib import Path

from ai_provider import generate_sql
from semantic_layer import (
    check_clarification,
    get_clarification_options,
    clarification_display_options,
    normalize_clarification_answer,
    METRIC_RULES,
    METRICS,
)
from database import (validate_sql, execute_sql, suggest_keyword)

load_dotenv()

# =========================================================
# PAGE SETUP
# =========================================================

st.set_page_config(
    page_title="Text-to-SQL AI",
    page_icon="logo.png",
    layout="wide"
)


# =========================================================
# LOAD CSS
# =========================================================

if "ui_theme" not in st.session_state:
    st.session_state.ui_theme = "Light"


def load_css():
    css_path = Path(__file__).parent / "style.css"

    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    if st.session_state.ui_theme == "Dark":
        palette = """
        --bg: #1C211D;
        --sidebar: #171B18;
        --surface: #252B26;
        --surface-hover: #2D352E;
        --border: #3A433B;
        --text: #F1F1E9;
        --muted: #A8B0A4;
        --accent: #D47A59;
        --accent-strong: #E18C6B;
        --accent-soft: #3B2C25;
        --user-bubble: #2B332C;
        --code-bg: #141815;
        --table-head: #303830;
        --shadow: rgba(0, 0, 0, .18);
        """
    else:
        palette = """
        --bg: #F4F4EF;
        --sidebar: #EBEDE5;
        --surface: #FBFBF7;
        --surface-hover: #F0F1E9;
        --border: #D9DCD1;
        --text: #292D27;
        --muted: #73786E;
        --accent: #B65335;
        --accent-strong: #98442D;
        --accent-soft: #F2E1D9;
        --user-bubble: #E8EBE1;
        --code-bg: #222922;
        --table-head: #E8EBE2;
        --shadow: rgba(35, 42, 34, .05);
        """

    st.markdown(
        f"<style>{css}\n:root {{ {palette} }}</style>",
        unsafe_allow_html=True
    )


load_css()


# =========================================================
# SESSION STATE
# =========================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "pending_confirmation" not in st.session_state:
    st.session_state.pending_confirmation = None

if "confirmed_question" not in st.session_state:
    st.session_state.confirmed_question = None


# =========================================================
# SIDEBAR
# =========================================================

with st.sidebar:

    st.markdown(
        '<div class="sidebar-title">Text-to-SQL AI</div>',
        unsafe_allow_html=True
    )

    if st.button("＋  New chat", width="stretch"):
        st.session_state.messages = []
        st.session_state.pending_confirmation = None
        st.session_state.confirmed_question = None
        st.rerun()

    st.markdown(
        '<div class="sidebar-section">Appearance</div>',
        unsafe_allow_html=True
    )

    st.radio(
        "Theme",
        ["Light", "Dark"],
        horizontal=True,
        key="ui_theme",
        label_visibility="collapsed"
    )

    st.markdown(
        '<div class="sidebar-section">Your database</div>',
        unsafe_allow_html=True
    )

    st.markdown(
        '<div class="database-card">'
        '<div class="database-dot"></div>'
        '<div><strong>Northwind SQLite</strong>'
        '<span>Read-only query workspace</span></div>'
        '</div>',
        unsafe_allow_html=True
    )


# =========================================================
# TOP BAR
# =========================================================

top_col1, top_col2 = st.columns([1, 5], vertical_alignment="center")

with top_col1:
    st.image("logo.png", width=38)

with top_col2:
    st.markdown(
        '<div class="brand-name">Text-to-SQL AI</div>'
        '<div class="brand-subtitle">Northwind Database</div>',
        unsafe_allow_html=True
    )


# =========================================================
# TYPO CONFIRMATION
# =========================================================

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


# =========================================================
# CONVERSATION HISTORY
# =========================================================

def get_conversation_history():

    conversation_history = []

    for message in st.session_state.messages[-6:]:

        if message["role"] == "user":

            conversation_history.append(
                f"User: {message['content']}"
            )

        elif message["role"] == "assistant":

            if message.get("sql"):

                conversation_history.append(
                    f"Assistant (SQL): {message['sql']}"
                )

            elif message.get("content"):

                content = message["content"]

                if isinstance(content, str):

                    conversation_history.append(
                        f"Assistant: {content}"
                    )

    return conversation_history


# =========================================================
# PROCESS QUESTION
# =========================================================


def process_question(question, skip_clarification=False):

    conversation_history = get_conversation_history()

    print("===== CLARIFICATION TEST =====")
    print("Question:", question)

    clarification_status = check_clarification(
        question,
        conversation_history
    )

    print("Clarification Status:", clarification_status)

    # ==================================================
    # CLARIFICATION
    # ==================================================

    if not skip_clarification:

        if clarification_status == "CLARIFY":

            allowed_metrics = get_clarification_options(
                question
            )

            display_options = clarification_display_options(
                allowed_metrics
            )

            clarification = {
                "question": "What do you want to rank by?",
                "options": display_options,
                "allowed_metrics": allowed_metrics
            }

            st.session_state.messages.append({
                "role": "assistant",
                "type": "clarification",
                "content": clarification,
                "original_question": question
            })

            return

        if clarification_status == "UNKNOWN":

            message = (
                "I couldn't find a matching table "
                "or column in the database."
            )

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": message
            })

            return

    # ==================================================
    # SQL GENERATION
    # ==================================================

    with st.chat_message("assistant"):

        thinking_placeholder = st.empty()

        thinking_placeholder.markdown(
            '<div class="thinking-dots">'
            '<span></span><span></span><span></span>'
            '</div>',
            unsafe_allow_html=True
        )

        try:

            sql = generate_sql(
                question,
                conversation_history
            )

            thinking_placeholder.empty()

            # ------------------------------------------
            # Unsafe query
            # ------------------------------------------

            if sql.strip().upper() == "UNSAFE_QUERY":

                message = (
                    "The generated query is unsafe. "
                    "Only SELECT queries are allowed."
                )

                st.markdown(message)

                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "text",
                    "content": message
                })

                return

            # ------------------------------------------
            # Unknown query
            # ------------------------------------------

            if sql.strip().upper() == "UNKNOWN_QUERY":

                message = (
                    "I couldn't find a matching table "
                    "or column in the database."
                )

                st.markdown(message)

                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "text",
                    "content": message
                })

                return

            # ------------------------------------------
            # Validate SQL
            # ------------------------------------------

            if not validate_sql(sql):

                print("===== INVALID SQL =====")
                print(sql)
                print("======================")

                message = "The generated SQL query is invalid."

                st.markdown(message)

                st.session_state.messages.append({
                    "role": "assistant",
                    "type": "text",
                    "content": message
                })

                return

            # ------------------------------------------
            # Execute SQL
            # ------------------------------------------

            df = execute_sql(sql)

            if df.empty:

                st.markdown("No data found.")

            else:

                st.markdown(
                    '<div class="tool-trace"><span>SCHEMA CONTEXT</span><i>→</i><span>SQL VALIDATION</span><i>→</i><span>SQLITE EXECUTION</span></div>'
                    '<div class="sql-label">Generated SQL</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    sql,
                    language="sql"
                )

                st.markdown(
                    '<div class="result-label">Result</div>',
                    unsafe_allow_html=True
                )

                st.dataframe(
                    df,
                    width="stretch",
                    hide_index=True
                )

            # ------------------------------------------
            # Save assistant response
            # ------------------------------------------

            st.session_state.messages.append({
                "role": "assistant",
                "type": "table",
                "content": df,
                "sql": sql
            })

        except Exception as e:

            thinking_placeholder.empty()

            message = f"Something went wrong: {e}"

            st.markdown(message)

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": message
            })
# =========================================================
# DISPLAY MESSAGES
# =========================================================

for index, message in enumerate(st.session_state.messages):

    with st.chat_message(message["role"]):

        if message["type"] == "text":

            st.write(message["content"])

        elif message["type"] == "clarification":

            clarification = message["content"]

            question_text = clarification.get(
                "question",
                "Please clarify your question."
            )

            st.markdown(
                f'<div class="clarification-card">'
                f'<div class="clarification-title">{question_text}</div>'
                f'</div>',
                unsafe_allow_html=True
            )

            options = clarification.get(
                "options",
                []
            )

            if options:

                selected_option = st.radio(
                    "Choose an option",
                    options,
                    key=f"clarification_{index}",
                    label_visibility="collapsed"
                )

                if st.button(
                    "Continue",
                    key=f"continue_{index}",
                    type="primary"
                ):

                    original_question = message.get(
                        "original_question",
                        ""
                    )

                    allowed_metrics = clarification.get(
                        "allowed_metrics",
                        []
                    )

                    metric = normalize_clarification_answer(
                        selected_option,
                        allowed_metrics
                    )

                    if metric is None:

                        st.error(
                            "Please choose one of the available options."
                        )

                    else:

                        combined_question = (
                            f"{original_question} by {metric}"
                        )

                        st.session_state.messages.pop(index)

                        st.session_state.messages.append({
                            "role": "user",
                            "type": "text",
                            "content": combined_question
                        })

                        process_question(
                            combined_question,
                            skip_clarification=True
                        )

                        st.rerun()

        else:

            if message.get("sql"):

                st.markdown(
                    '<div class="tool-trace"><span>SCHEMA CONTEXT</span><i>→</i><span>SQL VALIDATION</span><i>→</i><span>SQLITE EXECUTION</span></div>'
                    '<div class="sql-label">Generated SQL</div>',
                    unsafe_allow_html=True
                )

                st.code(
                    message["sql"],
                    language="sql"
                )

            content = message.get("content")

            if content is not None:

                if hasattr(content, "empty") and content.empty:

                    st.info("No data found.")

                elif hasattr(content, "empty"):

                    st.markdown(
                        '<div class="result-label">Result</div>',
                        unsafe_allow_html=True
                    )

                    st.dataframe(
                        content,
                        width="stretch",
                        hide_index=True
                    )

# =========================================================
# PENDING TYPO CONFIRMATION
# =========================================================

if st.session_state.pending_confirmation:

    confirmation = st.session_state.pending_confirmation

    st.warning(
        f'Did you mean "{confirmation["suggested_word"]}"?'
    )

    col1, col2 = st.columns(2)

    with col1:

        if st.button("Yes", width="stretch"):

            corrected_question = confirmation["question"]

            st.session_state.pending_confirmation = None
            st.session_state.confirmed_question = corrected_question
            st.rerun()

    with col2:

        if st.button("No", width="stretch"):

            st.session_state.pending_confirmation = None

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": "Okay. Please rephrase your question."
            })

            st.rerun()


# =========================================================
# CONFIRMED QUESTION
# =========================================================

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


# =========================================================
# WELCOME SCREEN
# =========================================================

if not st.session_state.messages:

    st.markdown(
        '<div class="welcome-wrap">',
        unsafe_allow_html=True
    )

    st.image("logo.png", width=64)

    st.markdown(
        '<div class="welcome-eyebrow">NORTHWIND WORKSPACE</div>'
        '<div class="welcome-title">Ask your data a question.</div>'
        '<div class="welcome-text">'
        'Explore your Northwind database in plain English, Hinglish or Gujarati. '
        'I’ll turn your question into a validated SQL query and show the results.'
        '</div>',
        unsafe_allow_html=True
    )

    st.markdown("</div>", unsafe_allow_html=True)


# =========================================================
# CHAT INPUT
# =========================================================

question = st.chat_input(
    "Ask about customers, orders, products..."
)

if question:

    # If a clarification is currently waiting for an answer,
    # validate the typed answer before sending anything to the LLM.
    pending_clarification = None

    for message in reversed(st.session_state.messages):
        if message.get("type") == "clarification":
            pending_clarification = message
            break

    if pending_clarification:

        clarification = pending_clarification.get("content", {})
        allowed_metrics = clarification.get("allowed_metrics", [])
        metric = normalize_clarification_answer(
            question,
            allowed_metrics
        )

        if metric is None:

            st.session_state.messages.append({
                "role": "assistant",
                "type": "text",
                "content": (
                    "Invalid option. Please choose or type one of: "
                    + ", ".join(clarification.get("options", []))
                    + "."
                )
            })

            st.rerun()

        original_question = pending_clarification.get(
            "original_question",
            ""
        )

        combined_question = f"{original_question} by {metric}"

        st.session_state.messages.remove(pending_clarification)

        st.session_state.messages.append({
            "role": "user",
            "type": "text",
            "content": combined_question
        })

        process_question(
            combined_question,
            skip_clarification=True
        )

        st.rerun()

    confirmation = find_confirmation(question)

    if confirmation:

        st.session_state.pending_confirmation = confirmation

        st.session_state.messages.append({
            "role": "user",
            "type": "text",
            "content": question
        })

        st.rerun()

    st.session_state.messages.append({
        "role": "user",
        "type": "text",
        "content": question
    })

    process_question(question)

    st.rerun()
