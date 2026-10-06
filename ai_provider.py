import os
import requests
from dotenv import load_dotenv
from groq import Groq
from google import genai
from schema import get_schema
from database import get_database_keywords , suggest_keyword

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
        sql = sql.replace("```sql", "").replace("```", "").strip()

    return sql

def check_clarification(question, conversation_history=None):

    schema = get_schema()

    if conversation_history:
        conversation = "\n".join(conversation_history)
    else:
        conversation = "no previous conversation"

    prompt = f"""
    You are a Query Clarification Engine for a Text-to-SQL chatbot.

    Database schema:
    {schema}

    Previous conversation:
    {conversation}

    User question:
    {question}

    Your job is NOT to generate SQL.

    Decide whether the user's question is clear enough to generate a correct SQL query.

    Rules:
    - If the question has a clear intent and required information is available, return exactly:
    CLEAR

    - If the question is ambiguous and guessing could produce a wrong result, return exactly:
    CLARIFY

    - If the requested information does not exist in the database, return exactly:
    UNKNOWN

    Important:
    - Never guess the user's intended meaning.
    - Words such as "best", "top", "good", "popular", "successful", etc. may be ambiguous when the ranking metric is not specified.
    - If multiple reasonable interpretations exist, return CLARIFY.
    - Consider the previous conversation when deciding whether the current question is clear.
    - Understand English, Hindi, Hinglish, Gujarati, French, and other languages.
    - Return only CLEAR, CLARIFY, or UNKNOWN.
    """

    # OpenRouter
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
        result = data["choices"][0]["message"]["content"].strip().upper()
        print("Clarification Engine: OpenRouter")
        return result
    
    except Exception as openrouter_error:
        print("Clarification OpenRouter failed:", openrouter_error)

    # Groq
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

        result = response.choices[0].message.content.strip().upper()

        print("Clarification Engine: Groq")
        return result

    except Exception as groq_error:
        print("Clarification Groq failed:", groq_error)

    return "CLEAR"

def generate_clarification(question, conversation_history=None):

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

The user's question is ambiguous.

Your task:
- Ask the user one clear clarification question.
- Identify what part of the request is ambiguous.
- Give 2 to 4 useful options based on the actual database schema.
- Options must be meaningful and possible to calculate from the database.
- Do not generate SQL.
- Do not answer the original question.
- Respond in the same language/style used by the user.
- If the user uses Hinglish, respond in natural Hinglish.
- If the user uses Gujarati, respond in Gujarati.
- If the user uses English, respond in English.
- Keep the response short and conversational.
- Do not mention that you are an AI model.

Example:

User:
show me 10 best customers

Response:
I'm not sure what you mean by "best customers". How should I rank them?

💰 Total spending
🛒 Number of orders
📦 Total quantity purchased
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

        clarification = data["choices"][0]["message"]["content"].strip()

        print("Clarification Generator: OpenRouter")

        return clarification

    except Exception as error:
        print("Clarification Generator failed:", error)

        return "Could you please clarify what you mean?"

def generate_sql(question, conversation_history=None):

    schema = get_schema()
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
    
    database_keywords = get_database_keywords()

    if conversation_history:
        conversation = "\n".join(conversation_history)
    else:
        conversation = "no previous conversation"

    prompt = f"""
    You are a Text-to-SQL assistant.

    Database schema:
    {schema}

    Database keywords:
    {database_keywords}

    previous conversation:
    {conversation}

    User question:
    {corrected_question}

    Instructions:
    - Generate only a valid SQLite SQL query.
    - Do not use Markdown.
    - Do not wrap the query in ```sql or ``` blocks.
    - Do not provide explanations.
    - Only generate SELECT queries for data retrieval requests.
    - If the user asks to INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, TRUNCATE, or perform any other data-changing/schema-changing operation, do not convert it into a SELECT query. Return exactly: UNSAFE_QUERY
    - For text comparisons, use case-insensitive matching when appropriate (e.g. LOWER(column) = LOWER('value')).
    - Never guess or invent a table or column when the user's request does not match the database schema.
    - If the user's request refers to a table, column, or database entity that cannot be found or reasonably matched in the database schema, return exactly: UNKNOWN_QUERY
    - If a table or column name contains spaces or special characters, always wrap it in double quotes.
    
    - Understand the user's question regardless of whether it is written in English, Hindi, Hinglish, or mixed language.
    - Use the previous conversation to understand follow-up questions and references.
    - Resolve contextual references such as "it", "they", "their", "those", "unki", "unke", "unka", "isme", etc. using the most relevant previous context.
    - If the user mentions a new table or entity, treat it as a new context and do not incorrectly carry over the previous entity.
    - When the user continues the same topic, preserve relevant filters and conditions from the previous conversation.
    
    """

    # 1. Gemini
    try:
        response = gemini_client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt
        )

        sql = clean_sql(response.text)

        print("Using: Gemini")
        return sql

    except Exception as gemini_error:
        print("Gemini failed:", gemini_error)

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

        sql = clean_sql(response.choices[0].message.content)

        print("Using: Groq")
        print("Groq SQL:", repr(sql))
        return sql

    except Exception as groq_error:
        print("Groq failed:", groq_error)

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
            }
        )

        response.raise_for_status()

        data = response.json()

        sql = clean_sql(data["choices"][0]["message"]["content"])

        print("Using: Cloudflare")
        return sql

    except Exception as cloudflare_error:
        print("Cloudflare failed:", cloudflare_error)

    # 4. OpenRouter
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

        sql = clean_sql(data["choices"][0]["message"]["content"])

        print("Using: OpenRouter")
        return sql

    except Exception as openrouter_error:
        print("OpenRouter failed:", openrouter_error)

    raise Exception("All AI providers failed.")