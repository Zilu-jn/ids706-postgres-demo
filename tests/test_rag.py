"""Tests for vector retrieval and RAG prompt construction."""

import pytest

from rag import (
    RetrievedContext,
    build_generation_input,
    build_knowledge_collection,
    clean_generated_sql,
    embed_text,
    retrieve_context,
)


def test_embedding_is_normalized_and_deterministic():
    first = embed_text("revenue by product category")
    second = embed_text("revenue by product category")

    assert first == second
    assert sum(value * value for value in first) == pytest.approx(1.0)


def test_chroma_retrieves_matching_quiz_example():
    question = {
        "title": "Revenue by category",
        "prompt": "Which product categories generated the most revenue?",
        "expected_sql": (
            "SELECT category, SUM(total_bill) AS revenue "
            "FROM bakery_sales GROUP BY category ORDER BY revenue DESC;"
        ),
    }
    collection = build_knowledge_collection([question])

    results = retrieve_context(collection, question["prompt"])

    assert results[0].title == "Quiz example: Revenue by category"
    assert "SUM(total_bill)" in results[0].text


def test_generation_input_contains_retrieved_context_and_question():
    context = RetrievedContext("Schema", "Table bakery_sales", 0.1)
    prompt = build_generation_input("Show all sales", [context])

    assert "Table bakery_sales" in prompt
    assert "Show all sales" in prompt


def test_clean_generated_sql_removes_markdown_fence():
    assert clean_generated_sql("```sql\nSELECT 1;\n```") == "SELECT 1;"
