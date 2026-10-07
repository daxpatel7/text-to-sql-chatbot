import pandas as pd
import sqlglot

from sqlalchemy import create_engine, text
from sqlalchemy import inspect
from difflib import SequenceMatcher

engine = create_engine("sqlite:///northwind.db")

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
    keywords = get_database_keywords()

    matches = find_similar_keywords(word, keywords)

    if not matches:
        return None

    best_match, best_score = matches[0]

    # Very short/common words should not trigger typo correction
    if len(word) <= 3:
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

def get_database_keywords():
    inspector = inspect(engine)
    tables = inspector.get_table_names()

    keywords = []

    for table in inspector.get_table_names():
        keywords.append(table)
        
        for column in inspector.get_columns(table):
            keywords.append(column['name'])

    return keywords

def validate_sql(sql):
    try:
        statements = sqlglot.parse(sql)

        # Only one SQL statement is allowed
        if len(statements) != 1:
            return False

        parsed = statements[0]

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