import os
import json
import requests
from dotenv import load_dotenv
from groq import Groq
from google import genai

from schema import get_schema
from database import get_database_keywords, suggest_keyword
from semantic_layer import (
    get_sql_generator_context,
    needs_semantic_layer,
    check_clarification,
    get_clarification_options,
    clarification_display_options,
    normalize_clarification_answer,
    resolve_semantic_intent,
    METRIC_RULES,
)

load_dotenv()

groq_client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

try:
    gemini_client = genai.Client(
        api_key=os.getenv("GEMINI_API_KEY")
    )
except Exception:
    gemini_client = None

CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def clean_sql(sql):
    sql = (sql or "").strip()
    if sql.startswith("```"):
        sql = (
            sql
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )
    # Strip any leading 'sql\n'
    if sql.lower().startswith("sql\n"):
        sql = sql[4:].strip()
    return sql


def generate_sql(
    question,
    conversation_history=None
):
    # 1. Deterministic safety & unknown check
    intent = resolve_semantic_intent(question, conversation_history)
    if intent["status"] == "unsafe":
        return "UNSAFE_QUERY"
    if intent["status"] == "unknown":
        return "UNKNOWN_QUERY"

    # 2. Context & schema
    semantic_context = get_sql_generator_context(question, conversation_history)

    # 3. Typo correction for high-confidence matches
    words = question.split()
    corrected_question = question

    for word in words:
        clean_word = word.strip(".,!?")
        suggestion = suggest_keyword(clean_word)
        if suggestion and suggestion["type"] == "direct":
            corrected_question = corrected_question.replace(
                clean_word,
                suggestion["keyword"]
            )

    if conversation_history:
        conversation = "\n".join(conversation_history)
    else:
        conversation = "no previous conversation"

    prompt = f"""You are a Text-to-SQL assistant for a Northwind SQLite database.

Semantic context:
{json.dumps(semantic_context, separators=(",", ":"), ensure_ascii=False)}

Previous conversation:
{conversation}

User question:
{corrected_question}

Rules:
- Return only one valid SQLite SELECT query.
- Return no Markdown, explanation, or code fences.
- For data modifications (INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE) or malicious requests, return exactly UNSAFE_QUERY.
- If the question asks for information not in the database (e.g. employee salaries, reviews, weather), return exactly UNKNOWN_QUERY.
- Never invent tables, columns, relationships, or metrics.
- Always use double quotes for SQLite table or column names with spaces: specifically, use "Order Details", NEVER Order Details.
- Historical Revenue MUST be: SUM("Order Details"."UnitPrice" * "Order Details"."Quantity" * (1 - "Order Details"."Discount")).
  Never use Products.UnitPrice for historical revenue calculations.
- Gross Sales: SUM("Order Details"."UnitPrice" * "Order Details"."Quantity").
- Quantity Sold: SUM("Order Details"."Quantity").
- Order Count: COUNT(DISTINCT Orders.OrderID).
- Most expensive products: Products.UnitPrice DESC.
- Most sold products: SUM("Order Details".Quantity) DESC.
- Out of stock products: Products.UnitsInStock = 0. Never use Discontinued for out of stock questions.
- Understand English, Hindi, Hinglish, and Gujarati.
- For follow-up questions referencing previous entities or filters (e.g. 'unke', 'unki', 'unka', 'their', 'them', 'those', 'inme'), you MUST preserve and apply previous filters (such as Country = 'Germany') and join with the previous entities.
- Preserve filters, grouping, sorting direction (DESC or ASC), LIMIT N, and relevant previous conversation context.
- When an alias is given to a table, use only that alias for all references to that table.
- Verify every column reference matches the schema before returning the SQL.
"""

    # --------------------------------------------------
    # 1. Groq
    # --------------------------------------------------
    try:
        response = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0,
        )

        sql = clean_sql(response.choices[0].message.content)
        return sql

    except Exception as groq_error:
        print("Groq failed:", groq_error)

    # --------------------------------------------------
    # 2. Cloudflare
    # --------------------------------------------------
    if CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN:
        try:
            url = (
                f"https://api.cloudflare.com/client/v4/accounts/"
                f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/"
                f"@cf/qwen/qwen3-30b-a3b-fp8"
            )

            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {CLOUDFLARE_API_TOKEN}",
                    "Content-Type": "application/json"
                },
                json={
                    "messages": [
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                },
                timeout=20,
            )

            response.raise_for_status()
            data = response.json()
            result = data.get("result", {})

            if "response" in result:
                sql = clean_sql(result["response"])
                return sql
            else:
                raise Exception(f"Unexpected Cloudflare response: {data}")

        except Exception as cloudflare_error:
            print("Cloudflare failed:", cloudflare_error)

    # --------------------------------------------------
    # 3. OpenRouter
    # --------------------------------------------------
    if OPENROUTER_API_KEY:
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            response = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {OPENROUTER_API_KEY}",
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
                },
                timeout=25,
            )

            response.raise_for_status()
            data = response.json()
            sql = clean_sql(data["choices"][0]["message"]["content"])
            return sql

        except Exception as openrouter_error:
            print("OpenRouter failed:", openrouter_error)

    # --------------------------------------------------
    # 4. Gemini Fallback
    # --------------------------------------------------
    if gemini_client:
        try:
            response = gemini_client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            sql = clean_sql(response.text)
            return sql
        except Exception as gemini_error:
            print("Gemini failed:", gemini_error)

    raise Exception("All AI providers failed.")