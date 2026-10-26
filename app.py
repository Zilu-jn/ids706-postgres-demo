"""Streamlit application for the Bakery Sales SQL Quiz."""

from __future__ import annotations

import os
import json

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from supabase import Client, create_client
from supabase.client import ClientOptions

from database import QueryValidationError, execute_read_only_query
from rag import build_knowledge_collection, generate_sql, retrieve_context

# Streamlit reruns this file after source changes. ``override=True`` ensures a
# newly rotated local database role is picked up without exposing its value.
load_dotenv(override=True)


def get_setting(name: str) -> str:
    """Read local .env values or deployment secrets without exposing them."""
    value = os.getenv(name)
    if value:
        return value
    try:
        return str(st.secrets[name])
    except (KeyError, FileNotFoundError):
        return ""


SUPABASE_URL = get_setting("SUPABASE_URL")
SUPABASE_KEY = get_setting("SUPABASE_PUBLISHABLE_KEY")
DATABASE_URL = get_setting("DATABASE_URL")
OPENAI_API_KEY = get_setting("OPENAI_API_KEY")
OPENAI_MODEL = get_setting("OPENAI_MODEL") or "gpt-5.5"


@st.cache_resource
def get_knowledge_collection(questions_json: str):
    """Build the in-memory Chroma vector database once per app process."""
    return build_knowledge_collection(json.loads(questions_json))


def build_supabase_client() -> Client:
    client = create_client(
        SUPABASE_URL,
        SUPABASE_KEY,
        options=ClientOptions(auto_refresh_token=False, persist_session=False),
    )
    access_token = st.session_state.get("access_token")
    refresh_token = st.session_state.get("refresh_token")
    if access_token and refresh_token:
        response = client.auth.set_session(access_token, refresh_token)
        if response.session:
            st.session_state.access_token = response.session.access_token
            st.session_state.refresh_token = response.session.refresh_token
    return client


def store_session(auth_response) -> None:
    if not auth_response.session or not auth_response.user:
        raise ValueError(
            "No active session was returned. Confirm your email, then sign in."
        )
    st.session_state.access_token = auth_response.session.access_token
    st.session_state.refresh_token = auth_response.session.refresh_token
    st.session_state.user_id = str(auth_response.user.id)
    st.session_state.user_email = auth_response.user.email


def clear_session() -> None:
    for key in ("access_token", "refresh_token", "user_id", "user_email"):
        st.session_state.pop(key, None)


st.set_page_config(
    page_title="Bakery Sales SQL Quiz",
    page_icon="🥐",
    layout="wide",
)

st.title("🥐 Bakery Sales SQL Quiz")
st.caption("Practice PostgreSQL against a live hosted bakery-sales database.")

missing_settings = [
    name
    for name, value in {
        "SUPABASE_URL": SUPABASE_URL,
        "SUPABASE_PUBLISHABLE_KEY": SUPABASE_KEY,
        "DATABASE_URL": DATABASE_URL,
        "OPENAI_API_KEY": OPENAI_API_KEY,
    }.items()
    if not value
]
if missing_settings:
    st.error("Missing configuration: " + ", ".join(missing_settings))
    st.stop()

try:
    supabase = build_supabase_client()
except Exception:
    clear_session()
    st.error("Your saved login session expired. Please sign in again.")
    st.stop()


if "user_id" not in st.session_state:
    st.info("Sign in to open the quiz, run SQL, and save answers.")
    sign_in_tab, register_tab = st.tabs(["Sign in", "Create account"])

    with sign_in_tab:
        with st.form("sign_in_form"):
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Sign in", type="primary")
        if submitted:
            try:
                response = supabase.auth.sign_in_with_password(
                    {"email": email.strip(), "password": password}
                )
                store_session(response)
                st.rerun()
            except Exception as error:
                st.error(f"Sign-in failed: {error}")

    with register_tab:
        with st.form("register_form"):
            new_email = st.text_input("Email", key="register_email")
            new_password = st.text_input(
                "Password (at least 6 characters)",
                type="password",
                key="register_password",
            )
            registered = st.form_submit_button("Create account")
        if registered:
            try:
                response = supabase.auth.sign_up(
                    {"email": new_email.strip(), "password": new_password}
                )
                if response.session:
                    store_session(response)
                    st.rerun()
                st.success(
                    "Account created. Check your email for the confirmation link, then sign in."
                )
            except Exception as error:
                st.error(f"Account creation failed: {error}")
    st.stop()


header_left, header_right = st.columns([4, 1])
with header_left:
    st.success(f"Signed in as {st.session_state.user_email}")
with header_right:
    if st.button("Sign out", use_container_width=True):
        try:
            supabase.auth.sign_out()
        finally:
            clear_session()
        st.rerun()

try:
    questions = (
        supabase.table("quiz_questions")
        .select("id,position,title,prompt,points,hint,expected_sql,expected_result")
        .order("position")
        .execute()
        .data
    )
    saved_rows = (
        supabase.table("saved_answers")
        .select("question_id,sql_text")
        .eq("user_id", st.session_state.user_id)
        .execute()
        .data
    )
except Exception as error:
    st.error(f"Could not load the quiz: {error}")
    st.stop()

saved_answers = {row["question_id"]: row["sql_text"] for row in saved_rows}
total_points = sum(question["points"] for question in questions)
metric_one, metric_two, metric_three = st.columns(3)
metric_one.metric("Questions", len(questions))
metric_two.metric("Total points", total_points)
metric_three.metric("Saved answers", len(saved_answers))

st.divider()
st.subheader("Generate SQL with RAG")
st.caption(
    "Enter a natural-language quiz question. The app retrieves relevant knowledge "
    "from ChromaDB, then asks the AI model to generate PostgreSQL."
)
rag_question = st.text_area(
    "Natural-language question",
    key="rag_question",
    height=100,
    placeholder="For example: Which product categories generated the most revenue?",
)

if st.button("Generate SQL", type="primary"):
    if not rag_question.strip():
        st.warning("Enter a question before generating SQL.")
    else:
        try:
            knowledge_collection = get_knowledge_collection(
                json.dumps(questions, sort_keys=True)
            )
            retrieved_context = retrieve_context(
                knowledge_collection, rag_question.strip()
            )
            generated_sql = generate_sql(
                OPENAI_API_KEY,
                OPENAI_MODEL,
                rag_question.strip(),
                retrieved_context,
            )
            st.session_state.rag_generated_sql = generated_sql
            st.session_state.rag_context = retrieved_context
        except Exception as error:
            st.error(f"Could not generate SQL: {error}")

if st.session_state.get("rag_generated_sql"):
    st.markdown("**AI-generated SQL**")
    st.code(st.session_state.rag_generated_sql, language="sql")
    with st.expander("Retrieved ChromaDB context"):
        for context in st.session_state.rag_context:
            st.markdown(f"**{context.title}**")
            st.text(context.text)

st.divider()
st.markdown(
    "Write one read-only `SELECT` query. CTEs and window functions are supported."
)

for question in questions:
    number = question["position"]
    question_id = question["id"]
    with st.expander(
        f"Question {number}: {question['title']} — {question['points']} points",
        expanded=number == 1,
    ):
        st.markdown(question["prompt"])
        st.info("Hint: " + question["hint"])

        answer_key = f"answer_{question_id}"
        if answer_key not in st.session_state:
            st.session_state[answer_key] = saved_answers.get(question_id, "")

        sql_text = st.text_area(
            "Your SQL",
            key=answer_key,
            height=180,
            placeholder="SELECT ...",
        )

        run_col, save_col = st.columns(2)
        if run_col.button("Run query", key=f"run_{question_id}", type="primary"):
            try:
                result = execute_read_only_query(DATABASE_URL, sql_text)
                frame = pd.DataFrame(result.rows, columns=result.columns)
                st.dataframe(frame, use_container_width=True, hide_index=True)
                st.success(f"Query returned {len(result.rows)} row(s).")
                if result.truncated:
                    st.warning("Only the first 500 rows are displayed.")
            except QueryValidationError as error:
                st.warning(str(error))
            except Exception as error:
                st.error(f"The database could not run this query: {error}")

        if save_col.button("Save answer", key=f"save_{question_id}"):
            if not sql_text.strip():
                st.warning("Enter SQL before saving.")
            else:
                try:
                    supabase.table("saved_answers").upsert(
                        {
                            "user_id": st.session_state.user_id,
                            "question_id": question_id,
                            "sql_text": sql_text,
                        },
                        on_conflict="user_id,question_id",
                    ).execute()
                    st.success("Answer saved to your account.")
                except Exception as error:
                    st.error(f"Could not save the answer: {error}")

        with st.expander("Check expected SQL and result"):
            st.code(question["expected_sql"], language="sql")
            st.markdown(question["expected_result"])

st.divider()
st.caption(
    "All submitted SQL runs in a read-only transaction with an 8-second timeout."
)
