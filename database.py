"""Safe, read-only PostgreSQL helpers for the quiz application."""

from __future__ import annotations

import re
from dataclasses import dataclass

import psycopg
import sqlparse
from psycopg.rows import dict_row
from sqlparse import tokens as T


MAX_RESULT_ROWS = 500
BLOCKED_KEYWORDS = {
    "ALTER",
    "CALL",
    "COMMENT",
    "COPY",
    "CREATE",
    "DELETE",
    "DO",
    "DROP",
    "EXECUTE",
    "GRANT",
    "INSERT",
    "MERGE",
    "REINDEX",
    "RESET",
    "REVOKE",
    "SET",
    "TRUNCATE",
    "UPDATE",
    "VACUUM",
}
BLOCKED_SCHEMAS = re.compile(
    r"\b(?:auth|extensions|information_schema|pg_catalog|storage|vault)\b",
    re.IGNORECASE,
)


class QueryValidationError(ValueError):
    """Raised when a submitted statement is not a safe read-only query."""


@dataclass(frozen=True)
class QueryResult:
    rows: list[dict]
    columns: list[str]
    truncated: bool


def validate_read_only_query(query: str) -> str:
    """Return normalized SQL after checking that it is one SELECT statement."""
    cleaned = query.strip()
    if not cleaned:
        raise QueryValidationError("Enter a SQL query before clicking Run.")

    statements = [statement for statement in sqlparse.parse(cleaned) if str(statement).strip()]
    if len(statements) != 1:
        raise QueryValidationError("Run one SQL statement at a time.")

    statement = statements[0]
    if statement.get_type() != "SELECT":
        raise QueryValidationError("Only SELECT queries and SELECT queries with CTEs are allowed.")

    for token in statement.flatten():
        if token.ttype in T.Comment or token.ttype in T.Literal.String:
            continue
        if token.normalized.upper() in BLOCKED_KEYWORDS:
            raise QueryValidationError(f"{token.normalized.upper()} is not allowed in the quiz runner.")

    without_comments = sqlparse.format(cleaned, strip_comments=True)
    if BLOCKED_SCHEMAS.search(without_comments):
        raise QueryValidationError("System and private schemas are not available in the quiz runner.")

    return cleaned


def execute_read_only_query(database_url: str, query: str) -> QueryResult:
    """Execute one validated query in a short, read-only database transaction."""
    safe_query = validate_read_only_query(query)

    with psycopg.connect(database_url, row_factory=dict_row) as connection:
        with connection.transaction():
            with connection.cursor() as cursor:
                cursor.execute("SET TRANSACTION READ ONLY")
                cursor.execute("SET LOCAL statement_timeout = '8s'")
                cursor.execute("SET LOCAL search_path = public")
                cursor.execute(safe_query)

                if cursor.description is None:
                    raise QueryValidationError("The query did not return a result table.")

                columns = [column.name for column in cursor.description]
                rows = cursor.fetchmany(MAX_RESULT_ROWS + 1)

    truncated = len(rows) > MAX_RESULT_ROWS
    return QueryResult(rows=rows[:MAX_RESULT_ROWS], columns=columns, truncated=truncated)
