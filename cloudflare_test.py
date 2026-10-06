import os
import requests
from dotenv import load_dotenv

load_dotenv()

ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/ai/run/@cf/qwen/qwen3-30b-a3b-fp8"

question = input("Ask your question: ")
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
{question}

Instructions:
- Generate only a valid SQLite SQL query.
- Do not use Markdown.
- Do not provide explanations.
- Only generate SELECT queries.
"""

response = requests.post(
    url,
    headers={
        "Authorization": f"Bearer {API_TOKEN}",
        "Content-Type": "application/json"
    },
    json={
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