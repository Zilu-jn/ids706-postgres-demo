# Bakery Sales SQL Quiz with RAG

A small authenticated SQL-learning application built with Streamlit and a hosted
PostgreSQL database on Supabase. The application also uses ChromaDB retrieval
and the OpenAI API to generate PostgreSQL from natural-language quiz questions.

## Quiz site

- Local development: `http://localhost:8501`
- Public deployment: https://bakery-sql-quiz.streamlit.app

## Quiz topics

The five questions practice:

1. Filtering by date, sorting, and limiting rows
2. Aggregation with `SUM()` and `GROUP BY`
3. Customer aggregation with `HAVING`
4. Classification with `CASE WHEN`
5. A CTE with the `RANK()` window function

## Dataset

This project uses the [Historical Bakery Sales Dataset](https://www.kaggle.com/datasets/sdcloud/historical-bakery-sales-dataset?resource=download) from Kaggle.

The prepared dataset contains 19,321 bakery sales records and 40 columns. Before importing it into PostgreSQL, I converted the column names to `snake_case` and changed Yes/No values into PostgreSQL-compatible boolean values.

## How the system works

1. `app.py` builds the Streamlit user interface and authenticates users through
   Supabase Auth.
2. Supabase Row Level Security allows authenticated users to read the quiz data
   and access only their own saved answers.
3. `database.py` validates submitted SQL and sends it to PostgreSQL using a
   restricted `quiz_runner` role.
4. Every submitted query runs in a read-only transaction with an eight-second
   timeout. Only one `SELECT` query (or a `WITH` query ending in `SELECT`) is
   accepted, and at most 500 result rows are displayed.

## RAG architecture and AI API

The SQL generator follows the required end-to-end pipeline:

```text
Natural-language question → ChromaDB vector retrieval → OpenAI API → Generated SQL
```

1. At application startup, `rag.py` creates an in-memory ChromaDB collection.
2. The collection stores the `bakery_sales` schema, business semantics, and the
   five quiz questions with their example SQL.
3. Each knowledge document is converted to a deterministic vector embedding and
   stored in ChromaDB.
4. When a user enters a question, ChromaDB performs vector similarity search and
   returns the three most relevant knowledge documents.
5. The retrieved documents and user question are sent to the OpenAI Responses
   API, which returns one read-only PostgreSQL statement.
6. The website displays both the generated SQL and the retrieved context so the
   retrieval step can be verified.

The RAG generator does not automatically execute its generated SQL. Automatic
execution and result validation are optional extra-credit features and are not
part of this implementation.

## Run locally

### 1. Clone the repository

```bash
git clone https://github.com/Zilu-jn/ids706-postgres-demo.git
cd ids706-postgres-demo
```

### 2. Create a Python environment and install packages

```bash
conda create -n bakery-sql-quiz python=3.12
conda activate bakery-sql-quiz
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

Copy the example file:

```bash
cp .env.example .env
```

Fill in these values in `.env`:

- `SUPABASE_URL`: the Supabase project URL
- `SUPABASE_PUBLISHABLE_KEY`: the browser-safe publishable key
- `DATABASE_URL`: the restricted `quiz_runner` Session pooler connection string
  with `sslmode=require`
- `OPENAI_API_KEY`: an OpenAI API key used only on the server
- `OPENAI_MODEL`: the model used to generate SQL (defaults to `gpt-5.5`)

The real `.env` file is ignored by Git.

### 4. Start the quiz

```bash
streamlit run app.py
```

Open `http://localhost:8501` and sign in. Under **Generate SQL with RAG**, enter
a natural-language SQL quiz question and select **Generate SQL**. The page shows
the generated SQL and an expandable list of the ChromaDB context retrieved for
that question.

For the original quiz workflow, open a question, enter SQL, select **Run query**,
and select **Save answer** if you want to keep the response under your account.

## RAG demonstration

A screenshot of a natural-language question and its generated SQL will be added
here after the deployed application is configured with its server-side API key.

## Tests and CI

Run the local checks with:

```bash
pytest -q
python -m compileall -q app.py database.py rag.py scripts tests
python scripts/check_database.py
```

The GitHub Actions workflow repeats these checks on every push and pull request.
The repository must contain an Actions secret named `DATABASE_URL`; the workflow
reads the secret without placing its value in the repository.

## Project structure

```text
.
├── app.py                     # Streamlit UI and Supabase authentication
├── database.py                # SQL validation and read-only query execution
├── rag.py                     # ChromaDB retrieval and OpenAI SQL generation
├── data/bakery_sales.csv      # Normalized bakery-sales dataset
├── scripts/
│   ├── check_database.py      # CI smoke test for hosted data and quiz totals
│   ├── prepare_bakery_csv.py  # Dataset normalization helper
├── tests/
│   ├── test_database.py       # Query-safety unit tests
│   └── test_rag.py            # Vector retrieval and prompt tests
└── .github/workflows/ci.yml   # GitHub Actions workflow
```

## Security notes

- Supabase Row Level Security protects quiz and saved-answer tables.
- Anonymous users receive no table access.
- Saved answers are scoped to the authenticated user's ID.
- Student SQL uses a dedicated, read-only PostgreSQL role rather than an admin
  account.
- The OpenAI API key is read from local environment variables or Streamlit
  secrets and is never sent to the browser.
- `.env` and `.streamlit/secrets.toml` are ignored by Git. `.env.example`
  contains placeholders only and is safe to commit.
