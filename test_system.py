"""Comprehensive test suite for Text-to-SQL Northwind Chatbot."""

import sys
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import database as db
import semantic_layer as sl
import ai_provider as ai

print("=" * 60)
print("1. RUNNING CLARIFICATION TESTS")
print("=" * 60)

clarification_cases = [
    ("best customer", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("best employee", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("best product", "CLARIFY", ["Revenue", "Quantity", "Orders", "Average Product Price"]),
    ("best supplier", "CLARIFY", ["Revenue", "Quantity", "Products"]),
    ("best category", "CLARIFY", ["Revenue", "Quantity", "Orders"]),
    ("worst product", "CLARIFY", ["Revenue", "Quantity", "Orders", "Average Product Price"]),
    ("top customers", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("top products", "CLARIFY", ["Revenue", "Quantity", "Orders", "Average Product Price"]),
    ("most popular category", "CLARIFY", ["Revenue", "Quantity", "Orders"]),
    ("most productive supplier", "CLARIFY", ["Revenue", "Quantity", "Products"]),
    ("sabse achha customer kaun hai", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("sabse popular category kaunsi hai", "CLARIFY", ["Revenue", "Quantity", "Orders"]),
    ("sabse productive supplier kaun hai", "CLARIFY", ["Revenue", "Quantity", "Products"]),
    ("sauthi saras customer kon che", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("worst product kaun sa hai", "CLARIFY", ["Revenue", "Quantity", "Orders", "Average Product Price"]),
    ("best employee kaun hai", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
    ("best customer kaun hai", "CLARIFY", ["Revenue", "Orders", "Quantity"]),
]

clarify_pass = 0
for q, exp_status, exp_disp in clarification_cases:
    status = sl.check_clarification(q)
    opts = sl.get_clarification_options(q)
    disp = sl.clarification_display_options(opts)
    if status == exp_status and disp == exp_disp:
        clarify_pass += 1
        print(f" [PASS] '{q}' -> Status: {status}, Display: {disp}")
    else:
        print(f" [FAIL] '{q}' -> Status: {status} (exp {exp_status}), Display: {disp} (exp {exp_disp})")

print(f"Result: {clarify_pass}/{len(clarification_cases)} clarification tests passed.\n")

print("=" * 60)
print("2. RUNNING CLEAR RANKING INTENT TESTS")
print("=" * 60)

clear_ranking_cases = [
    ("kis customer ne sabse zyada orders kiye", "Customers", "Order Count", "DESC", 1),
    ("which customer generated the most sales", "Customers", "Revenue", "DESC", 1),
    ("top 5 customers by revenue", "Customers", "Revenue", "DESC", 5),
    ("5 best customers by sales", "Customers", "Revenue", "DESC", 5),
    ("top customers by orders", "Customers", "Order Count", "DESC", 1),
    ("best product by quantity sold", "Products", "Quantity Sold", "DESC", 1),
    ("most expensive product", "Products", "Average Product Price", "DESC", 1),
    ("best employee by revenue", "Employees", "Revenue", "DESC", 1),
    ("sabse zyada orders kis customer ne kiye", "Customers", "Order Count", "DESC", 1),
]

ranking_pass = 0
for q, exp_ent, exp_metric, exp_rank, exp_lim in clear_ranking_cases:
    intent = sl.resolve_semantic_intent(q)
    status = sl.check_clarification(q)
    ent_ok = intent["entity"] == exp_ent
    metric_ok = intent["metric"] == exp_metric
    rank_ok = intent["sort_direction"] == exp_rank
    lim_ok = intent["limit"] == exp_lim
    stat_ok = status == "CLEAR"
    if ent_ok and metric_ok and rank_ok and lim_ok and stat_ok:
        ranking_pass += 1
        print(f" [PASS] '{q}' -> Status: CLEAR, Entity: {intent['entity']}, Metric: {intent['metric']}, Dir: {intent['sort_direction']}, Limit: {intent['limit']}")
    else:
        print(f" [FAIL] '{q}' -> Entity: {intent['entity']} (exp {exp_ent}), Metric: {intent['metric']} (exp {exp_metric}), Dir: {intent['sort_direction']}, Limit: {intent['limit']}, Status: {status}")

print(f"Result: {ranking_pass}/{len(clear_ranking_cases)} clear ranking tests passed.\n")

print("=" * 60)
print("3. RUNNING SAFETY TESTS")
print("=" * 60)

safety_cases = [
    "delete all customers",
    "drop table customers",
    "update customers",
    "insert into customers",
    "alter table customers",
    "show customers; drop table orders",
    "update all product prices to 0",
]

safety_pass = 0
for q in safety_cases:
    status = sl.check_clarification(q)
    sql = ai.generate_sql(q)
    if status == "UNSAFE" and sql == "UNSAFE_QUERY":
        safety_pass += 1
        print(f" [PASS] '{q}' -> Blocked as UNSAFE_QUERY")
    else:
        print(f" [FAIL] '{q}' -> Status: {status}, SQL: {sql}")

print(f"Result: {safety_pass}/{len(safety_cases)} safety tests passed.\n")

print("=" * 60)
print("4. RUNNING UNKNOWN QUERY TESTS")
print("=" * 60)

unknown_cases = [
    "show employee salaries",
    "show product reviews",
    "what is today's weather",
]

unknown_pass = 0
for q in unknown_cases:
    status = sl.check_clarification(q)
    sql = ai.generate_sql(q)
    if status == "UNKNOWN" and sql == "UNKNOWN_QUERY":
        unknown_pass += 1
        print(f" [PASS] '{q}' -> Correctly identified as UNKNOWN_QUERY")
    else:
        print(f" [FAIL] '{q}' -> Status: {status}, SQL: {sql}")

print(f"Result: {unknown_pass}/{len(unknown_cases)} unknown query tests passed.\n")

print("=" * 60)
print("5. RUNNING SQL GENERATION AND DATABASE EXECUTION TESTS")
print("=" * 60)

execution_cases = [
    ("show me customers", "SELECT with CustomerID / CompanyName"),
    ("show all products", "SELECT Products"),
    ("show customers from Germany", "Country = 'Germany' filter"),
    ("show out of stock products", "UnitsInStock = 0 filter"),
    ("how many records are in order details", "COUNT of Order Details"),
    ("kis customer ne sabse zyada orders kiye", "Customer ranking by Order Count"),
    ("top 5 customers by revenue", "Customer ranking by Revenue with LIMIT 5"),
    ("best employee by revenue", "Employee ranking by Revenue"),
    ("average price of products", "AVG UnitPrice"),
]

exec_pass = 0
for q, desc in execution_cases:
    try:
        sql = ai.generate_sql(q)
        print(f"\nQ: '{q}' ({desc})")
        print(f"Generated SQL: {sql}")
        is_valid = db.validate_sql(sql)
        if not is_valid:
            print(" [FAIL] Invalid SQL")
            continue
        df = db.execute_sql(sql)
        row_count = len(df)
        print(f" [PASS] Executed successfully! Returned {row_count} row(s). First row: {df.iloc[0].to_dict() if row_count > 0 else 'empty'}")
        exec_pass += 1
    except Exception as e:
        print(f" [FAIL] Execution error: {e}")

print(f"\nResult: {exec_pass}/{len(execution_cases)} SQL execution tests passed.")
print("=" * 60)
