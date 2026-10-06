from ai_provider import generate_sql
import sqlglot
from sqlalchemy import create_engine, text
import pandas as pd

engine = create_engine("sqlite:///database.db")

questions = [
    "customers ka data de",
    "Vadodara ke customers dikha",
    "sabse zyada amount wali sale dikha",
    "laptop ki sales dikha",
    "total sales amount bata",
    "last 5 sales dikha",
    "2026 ke sales dikha",
]


def validate_sql(sql):
    try:
        parsed = sqlglot.parse_one(sql)

        if parsed.key != "select":
            return False

        return True

    except Exception:
        return False


def execute_sql(sql):
    with engine.connect() as connection:
        result = connection.execute(text(sql))

        return pd.DataFrame(
            result.fetchall(),
            columns=result.keys()
        )


print("Starting Text-to-SQL tests...\n")

for i, question in enumerate(questions, start=1):

    print(f"Test {i}")
    print("Question:", question)

    try:
        sql = generate_sql(question)

        print("SQL:", sql)

        if not validate_sql(sql):
            print("Status: FAIL - Invalid SQL")
            print("-" * 50)
            continue

        df = execute_sql(sql)

        print("Database Result:")
        print(df.to_string(index=False))

        print("Status: PASS")

    except Exception as e:
        print("Status: FAIL")
        print("Error:", e)

    print("-" * 50)