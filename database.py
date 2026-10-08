import pandas as pd
import sqlglot
from functools import lru_cache
from difflib import SequenceMatcher
from sqlalchemy import create_engine, inspect, text

engine = create_engine("sqlite:///northwind.db")

FORBIDDEN_EXPRESSIONS = (
    sqlglot.exp.Drop,
    sqlglot.exp.Delete,
    sqlglot.exp.Update,
    sqlglot.exp.Insert,
    sqlglot.exp.Alter,
    sqlglot.exp.Create,
    sqlglot.exp.Command,
)

COMMON_IGNORE_WORDS = {
    "show", "list", "find", "give", "from", "with", "have", "what", "which",
    "where", "when", "many", "much", "each", "every", "more", "less", "than",
    "over", "under", "into", "then", "also", "only", "total", "some", "most",
    "best", "worst", "that", "this", "these", "those", "their", "there",
    "hain", "karo", "kare", "kaun", "kise", "kitne", "kitna", "dikha", "dikhao",
    "batao", "bata", "wala", "wali", "wale", "che", "chhe", "ketla", "sauthi",
    "saras", "unke", "unki", "unka", "inme", "isse", "iska", "sabse", "zyada",
    "jyada", "adhik", "sara", "data", "date", "year", "month", "price",
}


@lru_cache(maxsize=1)
def get_database_keywords():
    inspector = inspect(engine)
    keywords = []

    for table in inspector.get_table_names():
        if table == "sqlite_sequence":
            continue
        keywords.append(table)
        for column in inspector.get_columns(table):
            keywords.append(column['name'])

    return keywords


def find_similar_keywords(word, keywords):
    matches = []
    word = word.lower()

    for keyword in keywords:
        keyword_lower = keyword.lower()
        similarity = SequenceMatcher(
            None,
            word,
            keyword_lower
        ).ratio()

        if similarity >= 0.75:
            matches.append((keyword, similarity))

    matches.sort(
        key=lambda x: x[1],
        reverse=True
    )
    return matches


def suggest_keyword(word):
    clean = word.strip().lower()

    # Very short words, numbers, or common words should not trigger typo correction
    if len(clean) <= 3 or clean.isdigit() or clean in COMMON_IGNORE_WORDS:
        return None

    keywords = get_database_keywords()
    matches = find_similar_keywords(clean, keywords)

    if not matches:
        return None

    best_match, best_score = matches[0]

    # Exact match already
    if best_score >= 0.99 or clean == best_match.lower():
        return None

    # Very high confidence → automatically correct
    if best_score >= 0.90:
        return {
            "type": "direct",
            "keyword": best_match,
            "score": best_score
        }

    # Medium confidence → ask user
    if best_score >= 0.75:
        return {
            "type": "confirm",
            "keyword": best_match,
            "score": best_score
        }

    return None


def validate_sql(sql):
    try:
        sql_clean = (sql or "").strip()
        if not sql_clean:
            return False

        statements = sqlglot.parse(sql_clean)

        # Only one SQL statement is allowed
        if len(statements) != 1 or statements[0] is None:
            return False

        parsed = statements[0]

        # Disallow forbidden data or schema modifying statements
        for forbidden in FORBIDDEN_EXPRESSIONS:
            if parsed.find(forbidden):
                return False

        # Only SELECT queries are allowed
        if not parsed.find(sqlglot.exp.Select):
            return False

        return True

    except Exception:
        return False


def execute_sql(sql):
    try:
        with engine.connect() as connection:
            result = connection.execute(text(sql))
            return pd.DataFrame(
                result.fetchall(),
                columns=result.keys()
            )
    except Exception as e:
        raise Exception(f"Database error: {e}")