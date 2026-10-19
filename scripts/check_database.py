"""Small database smoke test used locally and by GitHub Actions."""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv


load_dotenv()
database_url = os.getenv("DATABASE_URL", "")
if not database_url:
    raise SystemExit("DATABASE_URL is not configured")

with psycopg.connect(database_url) as connection:
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT
                (SELECT COUNT(*) FROM bakery_sales),
                (SELECT COUNT(*) FROM quiz_questions),
                (SELECT COALESCE(SUM(points), 0) FROM quiz_questions)
            """
        )
        row_count, question_count, point_total = cursor.fetchone()

assert row_count == 19321, f"Expected 19321 bakery rows, found {row_count}"
assert question_count == 5, f"Expected 5 questions, found {question_count}"
assert point_total == 20, f"Expected 20 total points, found {point_total}"

print("Database check passed: 19,321 rows, 5 questions, 20 points.")
