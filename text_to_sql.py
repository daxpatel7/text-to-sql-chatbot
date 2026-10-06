import os
import sqlglot
import pandas as pd
from dotenv import load_dotenv
from google import genai
from sqlalchemy import create_engine, text
from schema import get_schema


load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

engine = create_engine("sqlite:///database.db")

schema = get_schema()

question = input("Ask your question: ")

prompt = f"""
You are a Text-to-SQL assistant.

Database schema:
{schema}

User question:
{question}

Instructions:
- Generate only a valid SQLite SQL query.
- Do not use Markdown.
- Do not wrap the query in ```sql or ``` blocks.
- Do not provide explanations.
"""

def generate_sql(prompt):
    response = client.models.generate_content(
        model="gemini-3.7-flash",
        contents=prompt
    )
    return response.text.strip()

sql = generate_sql(prompt)
# Remove Markdown code fences if the model still returns them
if sql.startswith("```"):
    sql = sql.replace("```sql", "").replace("```", "").strip()

print("\nGenerated SQL:")
print(sql)

try:
    parsed = sqlglot.parse_one(sql)

    if parsed.key != "select":
        print("Only SELECT queries are allowed.")
        exit()

except Exception:
    print("Invalid SQL query.")
    exit()

with engine.connect() as connection:
    result = connection.execute(text(sql))
    df = pd.DataFrame(result.fetchall(), columns=result.keys())
    print("\nResult:")
    print(df.to_string(index=False))
    
