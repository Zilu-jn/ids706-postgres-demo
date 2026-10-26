"""Small RAG pipeline for generating PostgreSQL from quiz questions."""

from __future__ import annotations

import hashlib
import math
import re
import uuid
from dataclasses import dataclass

import chromadb
from openai import OpenAI


EMBEDDING_DIMENSIONS = 384

BAKERY_SCHEMA = """PostgreSQL table: public.bakery_sales
Columns:
order_id, customer_id, customer_age, customer_gender, customer_segment,
loyalty_member, sale_date, sale_year, sale_month, sale_day, day_of_week,
weekend, sale_hour, sale_time, season, festival, weather, temperature_c,
product, category, quantity, unit_price, cost_price, discount_percentage,
selling_price, total_bill, payment_method, promotion_applied, promotion_type,
shelf_life_days, storage_type, perishability, store_id, units_produced,
units_sold, unsold_units, stock_available, waste_percentage, profit,
customer_rating.
The table contains one row per bakery sale."""

BUSINESS_SEMANTICS = """Bakery sales business meanings:
sale_date is the transaction date. total_bill is the transaction revenue.
profit is the profit for the transaction. quantity is the number of items in
the transaction. customer_id identifies a customer. product and category
describe the item. loyalty_member, weekend, and promotion_applied are boolean
columns. PostgreSQL syntax is required."""


@dataclass(frozen=True)
class RetrievedContext:
    title: str
    text: str
    distance: float


def embed_text(text: str, dimensions: int = EMBEDDING_DIMENSIONS) -> list[float]:
    """Create a deterministic normalized token-hash embedding."""
    vector = [0.0] * dimensions
    tokens = re.findall(r"[a-z0-9_]+", text.lower())
    for token in tokens:
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        index = int.from_bytes(digest[:4], "big") % dimensions
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[index] += sign

    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude:
        return [value / magnitude for value in vector]
    return vector


def build_knowledge_collection(questions: list[dict]):
    """Create an in-memory Chroma collection containing SQL knowledge."""
    documents = [BAKERY_SCHEMA, BUSINESS_SEMANTICS]
    titles = ["Database schema", "Business semantics"]

    for question in questions:
        documents.append(
            "SQL quiz example:\n"
            f"Question: {question['prompt']}\n"
            f"Expected PostgreSQL: {question['expected_sql']}"
        )
        titles.append(f"Quiz example: {question['title']}")

    client = chromadb.EphemeralClient()
    collection = client.create_collection(
        name=f"bakery_sql_{uuid.uuid4().hex}",
        metadata={"hnsw:space": "cosine"},
        embedding_function=None,
    )
    collection.add(
        ids=[f"knowledge-{index}" for index in range(len(documents))],
        documents=documents,
        metadatas=[{"title": title} for title in titles],
        embeddings=[embed_text(document) for document in documents],
    )
    return collection


def retrieve_context(collection, question: str, count: int = 3) -> list[RetrievedContext]:
    """Perform vector similarity search for context relevant to a question."""
    result = collection.query(
        query_embeddings=[embed_text(question)],
        n_results=min(count, collection.count()),
        include=["documents", "metadatas", "distances"],
    )
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]
    return [
        RetrievedContext(
            title=metadata["title"],
            text=document,
            distance=float(distance),
        )
        for document, metadata, distance in zip(documents, metadatas, distances)
    ]


def build_generation_input(question: str, contexts: list[RetrievedContext]) -> str:
    """Combine the user question with only the retrieved RAG context."""
    context_text = "\n\n---\n\n".join(context.text for context in contexts)
    return f"Retrieved context:\n{context_text}\n\nUser question:\n{question}"


def clean_generated_sql(text: str) -> str:
    """Remove Markdown fences without changing the generated SQL."""
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:sql)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    return cleaned.strip()


def generate_sql(
    api_key: str,
    model: str,
    question: str,
    contexts: list[RetrievedContext],
) -> str:
    """Generate one PostgreSQL SELECT statement using retrieved context."""
    client = OpenAI(api_key=api_key)
    response = client.responses.create(
        model=model,
        instructions=(
            "You generate PostgreSQL for the bakery SQL quiz. Use the retrieved "
            "context provided by the application. Return exactly one read-only "
            "SELECT statement, or one WITH query ending in SELECT. Return SQL only "
            "with no Markdown fence and no explanation. Never modify data."
        ),
        input=build_generation_input(question, contexts),
    )
    return clean_generated_sql(response.output_text)
