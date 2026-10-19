import pytest

from database import QueryValidationError, validate_read_only_query


@pytest.mark.parametrize(
    "query",
    [
        "SELECT * FROM bakery_sales LIMIT 5;",
        "WITH totals AS (SELECT category, SUM(total_bill) AS revenue FROM bakery_sales GROUP BY category) SELECT * FROM totals;",
    ],
)
def test_allows_read_only_queries(query):
    assert validate_read_only_query(query) == query


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM bakery_sales;",
        "DROP TABLE bakery_sales;",
        "SELECT * FROM auth.users;",
        "SELECT 1; SELECT 2;",
    ],
)
def test_blocks_unsafe_queries(query):
    with pytest.raises(QueryValidationError):
        validate_read_only_query(query)
