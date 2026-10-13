# Text-to-SQL AI Assistant

> Ask questions about your Northwind database in natural language and get SQL-backed results — with multilingual input support and safety checks.

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)]()
[![Database](https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white)]()
[![Interface](https://img.shields.io/badge/UI-Streamlit-FF4B4B?logo=streamlit&logoColor=white)]()
[![Testing](https://img.shields.io/badge/Test%20cases-100-00D0A8)]()

## Overview

The Text-to-SQL AI Assistant converts natural-language questions into SQL queries, runs approved read-only queries against a Northwind SQLite database, and presents the returned data in an interface.

It is designed to make database exploration easier for people who know what they want to ask but may not know SQL syntax. It supports English and examples of Hinglish, Hindi, and Gujarati queries.

## Features

- **Natural-language SQL generation:** Translate questions into SQL.
- **Multilingual input:** Supports tested examples in English, Hinglish, Hindi, and Gujarati.
- **Database-aware queries:** Uses the project's database schema to help generate queries for existing tables and columns.
- **Provider fallback:** Uses the configured language-model provider fallback chain (Gemini → Groq → Cloudflare → OpenRouter), as implemented in the project.
- **Read-only safety intent:** Restricts query execution to `SELECT` queries and rejects tested destructive requests.
- **SQL validation:** Uses SQLGlot as part of SQL validation.
- **Query execution:** Uses SQLAlchemy to connect to SQLite.
- **Tabular results:** Uses Pandas and Streamlit to display results.
- **Error handling:** Handles rejected/unknown queries and query execution errors.
- **Test suite:** Includes 100 test cases across common queries, joins, aggregations, filtering, ranking, dates, subqueries, multilingual input, safety, ambiguity, and edge cases.

## How It Works

```text
User question
     |
     v
Streamlit interface
     |
     v
Schema/context supplied to the LLM
     |
     v
Configured LLM provider / fallback chain
     |
     v
Generated SQL or a clarification/rejection
     |
     v
SQL validation (SQLGlot + application rules)
     |
     v
Execute approved query through SQLAlchemy
     |
     v
SQLite database (northwind.db)
     |
     v
Pandas DataFrame -> Streamlit results
```

The exact request flow depends on the implementation in the project files. The diagram summarizes the intended high-level flow.

## Technology Stack

| Technology | Role |
|---|---|
| Python | Application logic and integration |
| Streamlit | Web interface |
| SQLite | Local relational database |
| SQLAlchemy | Database connection and query execution |
| SQLGlot | SQL parsing/validation |
| Pandas | Tabular result handling |
| LLM providers | Natural-language-to-SQL generation using configured providers |
| `.env` | Local configuration for API keys and secrets |

## Database

The project uses the Northwind sample database in SQLite format. The database includes business entities such as customers, orders, products, employees, suppliers, shippers, and order details.

- Database file used by the current test results: `northwind.db`
- Queries should use only tables and columns that actually exist in the database.
- Table names containing spaces (for example, `Order Details`) need appropriate quoting in SQL.

> Keep the database file in the location expected by the project's database connection configuration.

## Example Questions

| Natural-language question | Typical SQL task |
|---|---|
| `Show all customers` | Select customer rows |
| `Customers ka data dikha do` | Select customer rows |
| `Total revenue bata` | Aggregate order-line revenue |
| `Top 5 customers by revenue` | Join, aggregate, group, and rank |
| `2020 ke orders dikha` | Filter orders by year |
| `Saare customers dikhaao` | Select customer rows |
| `Ketla orders chhe` | Count orders |

Generated SQL may vary by provider and model. Always validate outputs against the actual schema and expected business meaning.

## Safety and Limitations

- The application is intended for read-only database exploration.
- The current test suite includes destructive-query prompts such as `DELETE`, `UPDATE`, `DROP`, `INSERT`, `TRUNCATE`, and `ALTER`; the supplied test results show these prompts were rejected.
- A `SELECT`-only check is an important safeguard, but it should not be treated as a complete security boundary on its own. For production use, use a read-only database account/connection, enforce query timeouts and row limits, and test for expensive or resource-intensive queries.
- Natural-language questions can be ambiguous. For example, “best customer” could mean highest revenue, most orders, or another metric; the assistant should ask for clarification.
- An SQL query can be syntactically valid and execute successfully while still answering the question incorrectly. Review query semantics and result values for important decisions.
- Large joins may be slow. In the current supplied test output, one join query returned 609,283 rows and took about 200 seconds; consider result limits, pagination, or confirmation before running very large queries.
- Model/provider availability, rate limits, output quality, and latency can vary.

## Testing

The project test suite contains **100 unique test IDs**. Based on the supplied CSV output:

- **97 unique test IDs passed**
- **3 unique test IDs failed**
- **Observed pass rate: 97%**

The three failed cases were:
- `Customers by demographic type` — rejected as unknown.
- `Repeat customers` — rejected as unknown.
- `Who is the best customer?` — rejected as unknown instead of prompting for the intended metric.

Some test IDs appear more than once in the supplied CSV, so the raw CSV row count includes duplicates. The summary above counts unique test IDs, not raw rows. A passing test status means the test harness recorded the expected outcome; it does not prove every generated query has correct business semantics.

## Installation and Usage

The exact commands and dependencies depend on the project's current files. From the project root, a typical setup is:

1. Create and activate a Python virtual environment.
2. Install the packages listed in the project's dependency file (for example, `requirements.txt`).
3. Create a `.env` file with the API keys required by the configured providers.
4. Ensure `northwind.db` is available at the configured path.
5. Start the app:

```bash
streamlit run app.py
```

Run the test suite:

```bash
python run_tests.py
```

If your project uses different filenames or commands, follow the current code and configuration rather than these typical examples.

## Configuration

Store provider credentials in environment variables or `.env`. Do not commit real API keys or secrets.

Use the variable names expected by the current `ai_provider.py` implementation. Never paste secrets into this README.

## Project Structure

The project contains or has used files such as:

```text
text-to-sql-chatbot/
├── app.py
├── ai_provider.py
├── schema.py
├── semantic_layer.py
├── database.py
├── run_tests.py
├── results.csv          # generated test results; may be local-only
├── northwind.db         # SQLite database
└── .env                 # local secrets; do not commit
```

This is a representative structure based on the project context. Keep it aligned with the actual repository before publishing.

## Model Card

### Model / System Name
Text-to-SQL AI Assistant

### System Type
LLM-powered natural-language-to-SQL application with a database execution layer.

### Intended Use
- Explore the Northwind sample database through natural-language questions.
- Support learning, demos, and database-query assistance.
- Demonstrate SQL generation, validation, and multilingual input handling.

### Out-of-Scope Use
- Executing write operations or modifying production databases.
- Making consequential business decisions without checking SQL and results.
- Treating model output as guaranteed-correct SQL.

### Inputs
Natural-language questions in English and tested examples in Hinglish, Hindi, and Gujarati.

### Outputs
Generated SQL, a rejection/clarification response, or tabular results from the database.

### Data
Northwind sample relational data stored in `northwind.db`. The model may receive schema/context to help produce SQL. Do not send sensitive or personal data to external model providers without authorization.

### Evaluation
100 unique test IDs; 97 passed and 3 failed in the supplied results (97% observed pass rate). Evaluation is based on the test harness's recorded outcomes, not a full human review of every result.

### Known Limitations
- Ambiguous requests may be rejected instead of clarified.
- Syntactic validation does not guarantee semantic correctness.
- Some complex queries can be slow or return very large result sets.
- Provider availability and generated SQL quality may vary.
- Multilingual support is demonstrated by test examples and should not be interpreted as exhaustive language coverage.

### Risks and Mitigations
- **Unsafe SQL:** Validate queries and reject write operations; prefer a read-only database connection.
- **Incorrect results:** Inspect generated SQL and compare output with expected business definitions.
- **Expensive queries:** Add execution timeouts, row limits, and safeguards for large joins.
- **Credential exposure:** Keep API keys in `.env` and exclude secrets from version control.
- **Data privacy:** Use only data that is appropriate to send to the configured model provider.

### Maintenance
Update the test suite whenever schema, prompts, providers, or query-generation logic change. Re-run tests and review failures before release.

## Roadmap

- Improve clarification handling for ambiguous questions.
- Improve detection of unsupported schema concepts.
- Add query timeouts, row limits, and pagination for large results.
- Add semantic checks for common business metrics.
- Expand multilingual and adversarial test coverage.
- Track latency and correctness across providers.

## License

Add the license that applies to this repository before distributing it.
