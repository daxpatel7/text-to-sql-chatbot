import os
from click import prompt
import requests
import json

from dotenv import load_dotenv
from groq import Groq
from google import genai

from schema import get_schema
from database import get_database_keywords, suggest_keyword
from semantic_layer import get_sql_generator_context


load_dotenv()


groq_client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

gemini_client = genai.Client(
    api_key=os.getenv("GEMINI_API_KEY")
)


CLOUDFLARE_ACCOUNT_ID = os.getenv("CLOUDFLARE_ACCOUNT_ID")
CLOUDFLARE_API_TOKEN = os.getenv("CLOUDFLARE_API_TOKEN")

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


def clean_sql(sql):

    sql = sql.strip()

    if sql.startswith("```"):
        sql = (
            sql
            .replace("```sql", "")
            .replace("```", "")
            .strip()
        )

    return sql


# --------------------------------------------------
# Clarification Check
# --------------------------------------------------

def check_clarification(question, conversation_history=None):

    schema = get_schema()

    if conversation_history:
        conversation = "\n".join(conversation_history)
    else:
        conversation = "no previous conversation"

    prompt = f"""
You are the Query Confidence and Clarification Engine of a Text-to-SQL system.

Your main goal is to prevent confidently wrong SQL queries.

Database schema:
{schema}

Previous conversation:
{conversation}

Current user question:
{question}

You must decide whether the question can be converted into a correct SQL query
WITHOUT making an assumption that could change the meaning of the result.

Return ONLY one of these:
CLEAR
CLARIFY
UNKNOWN

CLEAR

Return CLEAR when the user's intent is sufficiently clear.

Do NOT ask for clarification just because:
- The wording is informal.
- The user uses Hindi, Hinglish, Gujarati, French, or another language.
- The question is short.
- The user uses synonyms or natural language.
- The user does not mention the exact database column name.
- A reasonable SQL interpretation is obvious from the database schema.
- A ranking/filtering operation has an obvious meaning from the available schema.

Examples:

"show me customers from Germany"
→ CLEAR

"give me the 10 most expensive products"
→ CLEAR

"show products costing more than 20"
→ CLEAR

"how many customers are there?"
→ CLEAR

"show orders from 1997"
→ CLEAR

"show me all order details"
→ CLEAR

CLARIFY

Return CLARIFY ONLY when there are multiple reasonable interpretations
and choosing one would require guessing the user's intention.

Examples:

"show me 10 best customers"
→ CLARIFY

Because "best" could reasonably mean:
- highest total spending
- most orders
- highest quantity purchased

Another example:

"show me the most popular products"
→ CLARIFY

if popularity could reasonably mean different measurable things
in the available database.

Important:
Do NOT decide the clarification options here.
Only decide whether clarification is required.

UNKNOWN

Return UNKNOWN when the user's request cannot reasonably be answered
using the available database schema.

Examples:

"show me employee salaries"
when salary information does not exist.

"what is today's weather?"
when weather data does not exist.

IMPORTANT RULES

1. Never guess when the ambiguity could change the result.

2. Do not over-clarify.
If a reasonable and unambiguous interpretation exists, return CLEAR.

3. Use the database schema to understand what information is actually available.

4. Use previous conversation context.
A question that looks ambiguous by itself may be clear from previous messages.

5. If the user has already specified a metric or condition in the conversation,
do not ask for it again.

6. Do not generate SQL.

7. Do not generate a clarification message.

8. Return ONLY:
CLEAR
CLARIFY
or
UNKNOWN
"""

    # 1. OpenRouter
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
            }
        )

        response.raise_for_status()

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
            .upper()
        )

        print("Clarification Engine: OpenRouter")

        if result in ["CLEAR", "CLARIFY", "UNKNOWN"]:
            return result

        return "CLEAR"

    except Exception as openrouter_error:

        print(
            "Clarification OpenRouter failed:",
            openrouter_error
        )


    # 2. Groq fallback
    try:

        response = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        result = (
            response.choices[0]
            .message.content
            .strip()
            .upper()
        )

        print("Clarification Engine: Groq")

        if result in ["CLEAR", "CLARIFY", "UNKNOWN"]:
            return result

        return "CLEAR"

    except Exception as groq_error:

        print(
            "Clarification Groq failed:",
            groq_error
        )

    return "CLEAR"


# --------------------------------------------------
# Generate Clarification
# --------------------------------------------------

def generate_clarification(
    question,
    conversation_history=None
):

    schema = get_schema()

    if conversation_history:
        conversation = "\n".join(conversation_history)
    else:
        conversation = "no previous conversation"

    prompt = f"""
You are a clarification assistant for a Text-to-SQL chatbot.

Database schema:
{schema}

Previous conversation:
{conversation}

User question:
{question}

The question is ambiguous.

Generate a short clarification question and 2 to 4 useful options.

Rules:

- Options must be based on the actual database schema.
- Options must be relevant to the user's question.
- Do not use the same options for every question.
- Infer the relevant entity from the user's question.
- For customers, use customer-related measurable metrics.
- For products, use product-related measurable metrics.
- For orders, use order-related measurable metrics.
- For employees, use employee-related measurable metrics.
- Use only metrics that can actually be calculated from the database.
- Do not invent database columns or information.
- Do not generate SQL.
- Do not answer the original question.
- Respond in the same language/style as the user.
- If the user uses Hinglish, use natural Hinglish.
- If the user uses Gujarati, use Gujarati.
- If the user uses English, use English.
- Keep the clarification short and conversational.

Return ONLY valid JSON.

Use exactly this structure:

{{
    "question": "your clarification question",
    "options": [
        "option 1",
        "option 2",
        "option 3"
    ]
}}
"""

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
            }
        )

        response.raise_for_status()

        data = response.json()

        result = (
            data["choices"][0]["message"]["content"]
            .strip()
        )

        # Remove Markdown JSON fences if model adds them
        if result.startswith("```"):

            result = (
                result
                .replace("```json", "")
                .replace("```", "")
                .strip()
            )

        clarification = json.loads(result)

        # Basic validation
        if not isinstance(clarification, dict):
            raise ValueError(
                "Invalid clarification format"
            )

        if "question" not in clarification:
            raise ValueError(
                "Clarification question missing"
            )

        if "options" not in clarification:
            raise ValueError(
                "Clarification options missing"
            )

        if not isinstance(
            clarification["options"],
            list
        ):
            raise ValueError(
                "Clarification options must be a list"
            )

        if len(clarification["options"]) < 2:
            raise ValueError(
                "At least two clarification options required"
            )

        print(
            "Clarification Generator: OpenRouter"
        )

        return clarification

    except Exception as error:

        print(
            "Clarification Generator failed:",
            error
        )

        return {
            "question": "Could you please clarify what you mean?",
            "options": [
                "Show the available information",
                "Choose a specific metric"
            ]
        }


def needs_semantic_layer(question):
    keywords = [
        "revenue",
        "sales",
        "profit",
        "discount",
        "average",
        "total",
        "highest",
        "lowest",
        "best",
        "worst",
        "most",
        "least",
        "top",
        "bottom",
        "per",
        "each",
        "between",
        "compare",
        "growth",
        "trend",
        "monthly",
        "yearly",
        "category wise",
        "country wise",
        "customer wise",
        "product wise"
    ]

    question_lower = question.lower()

    return any(
        keyword in question_lower
        for keyword in keywords
    )

# --------------------------------------------------
# Generate SQL
# --------------------------------------------------

def generate_sql(
    question,
    conversation_history=None
):

    schema = get_schema()
    semantic_context = None

    if needs_semantic_layer(question):
        semantic_context = get_sql_generator_context(question)
    words = question.split()

    corrected_question = question

    for word in words:

        clean_word = word.strip(".,!?")

        suggestion = suggest_keyword(
            clean_word
        )

        if (
            suggestion
            and suggestion["type"] == "direct"
        ):

            corrected_question = (
                corrected_question.replace(
                    clean_word,
                    suggestion["keyword"]
                )
            )

    database_keywords = get_database_keywords()

    if conversation_history:

        conversation = "\n".join(
            conversation_history
        )

    else:

        conversation = "no previous conversation"

    prompt = f"""
You are a Text-to-SQL assistant for a Northwind SQLite database.

Semantic context:
{json.dumps(semantic_context, separators=(",", ":"), ensure_ascii=False)}

Previous conversation:
{conversation}

User question:
{corrected_question}

Rules:
- Return only one valid SQLite SELECT query.
- Return no Markdown, explanation, or code fences.
- For INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, or other data/schema changes, return exactly UNSAFE_QUERY.
- If the request cannot be matched to the supplied schema/semantic context, return exactly UNKNOWN_QUERY.
- Never invent tables, columns, relationships, or metrics.
- Follow semantic metric definitions exactly; never simplify or replace them.
- Use declared relationships for joins.
- Use DISTINCT when required by a metric.
- Avoid duplicating order-level values after line-item joins.
- Quote identifiers containing spaces or special characters with double quotes.
- Use case-insensitive text matching when appropriate.
- Understand English, Hindi, Hinglish, and Gujarati.
- Preserve filters, grouping, sorting, LIMIT, and relevant previous context.
- Resolve follow-up references such as it, they, those, unke, unki, unka, isme from previous conversation.
"""

    # 1. Gemini
    try:

        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        sql = clean_sql(
            response.text
        )

        print("Using: Gemini")

        return sql

    except Exception as gemini_error:

        print(
            "Gemini failed:",
            gemini_error
        )


    # 2. Groq
    try:

        response = groq_client.chat.completions.create(
            model="qwen/qwen3.8-27b",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )
        print("\n===== GROQ INPUT =====")
        print(prompt)
        print("===== GROQ INPUT END =====")
        print("Prompt characters:", len(prompt))

        sql = clean_sql(
            response.choices[0]
            .message.content
        )

        print("Using: Groq")
        print(
            "Groq SQL:",
            repr(sql)
        )

        return sql

    except Exception as groq_error:

        print(
            "Groq failed:",
            groq_error
        )


    # 3. Cloudflare
    try:

        url = (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{CLOUDFLARE_ACCOUNT_ID}/ai/run/"
            f"@cf/qwen/qwen3-30b-a3b-fp8"
        )

        response = requests.post(
            url,
            headers={
                "Authorization":
                    f"Bearer {CLOUDFLARE_API_TOKEN}",
                "Content-Type":
                    "application/json"
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

        response.raise_for_status()

        data = response.json()
        result = data.get("result", {})

        if "response" in result:
            sql = clean_sql(result["response"])
        else:
            raise Exception(f"Unexpected Cloudflare response: {data}")

        print("Using: Cloudflare")
        print("Cloudflare SQL:", repr(sql))

        return sql

    except Exception as cloudflare_error:

        print(
            "Cloudflare failed:",
            cloudflare_error
        )


    # 4. OpenRouter
    try:

        url = (
            "https://openrouter.ai/api/v1/chat/completions"
        )

        response = requests.post(
            url,
            headers={
                "Authorization":
                    f"Bearer {OPENROUTER_API_KEY}",
                "Content-Type":
                    "application/json"
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

        response.raise_for_status()

        data = response.json()

        sql = clean_sql(
            data["choices"][0]["message"]["content"]
        )

        print("Using: OpenRouter")

        return sql

    except Exception as openrouter_error:

        print(
            "OpenRouter failed:",
            openrouter_error
        )

    raise Exception(
        "All AI providers failed."
    )