import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")

url = "https://openrouter.ai/api/v1/chat/completions"

prompt = """
You are a Text-to-SQL assistant.

Database schema:
customers:
- id
- name
- city

sales:
- id
- customer_id
- product
- amount
- sale_date

User question:
customers ka data de

Instructions:
- Generate only a valid SQLite SQL query.
- Do not use Markdown.
- Do not provide explanations.
- Only generate SELECT queries.
"""

response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json"
    },
    json={
        "model": "openrouter/free",
        "messages": [
            {
                "role": "user",
                "content": prompt
            }
        ]
    }
)

print(response.status_code)
print(response.json())