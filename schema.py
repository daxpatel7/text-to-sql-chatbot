from functools import lru_cache
from sqlalchemy import create_engine, inspect

engine = create_engine("sqlite:///northwind.db")


@lru_cache(maxsize=1)
def get_schema():
    inspector = inspect(engine)

    schema = ""

    for table in inspector.get_table_names():
        schema += f"Table: {table}\n"

        for column in inspector.get_columns(table):
            schema += f"- {column['name']} ({column['type']})\n"

        schema += "\n"

    return schema
