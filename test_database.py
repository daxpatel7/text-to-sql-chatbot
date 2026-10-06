from sqlalchemy import create_engine, inspect 

engine = create_engine("sqlite:///database.db")

inspector = inspect(engine)
tables = inspector.get_table_names()

print("Tables:")

for table in tables:
    print(f"\n{table}")
