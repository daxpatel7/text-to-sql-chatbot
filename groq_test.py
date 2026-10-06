import os
from dotenv import load_dotenv
from groq import Groq
from schema import get_schema

load_dotenv()

client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

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
- Only generate SELECT queries.
"""

response = client.chat.completions.create(
    model="qwen/qwen3.8-27b",
    messages=[
        {
            "role": "user",
            "content": prompt
        }
    ]
)

sql = response.choices[0].message.content.strip()

if sql.startswith("```"):
    sql = sql.replace("```sql", "").replace("```", "").strip()

print("\nGenerated SQL:")
print(sql)