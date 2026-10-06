"""Semantic layer for the Northwind SQLite database.

The semantic layer stores database/business knowledge and interprets a user's
question. It does NOT generate SQL. The SQL generator should consume
get_sql_generator_context(question).
"""

from dataclasses import dataclass, field
from typing import Optional
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv
from groq import Groq

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DATABASE_PATH = BASE_DIR / "northwind.db"


def quote_identifier(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


@dataclass
class SemanticMeaning:
    status: str
    entity: Optional[str] = None
    business_term: Optional[str] = None
    metric: Optional[str] = None
    aggregation: Optional[str] = None
    filters: list = field(default_factory=list)
    group_by: list = field(default_factory=list)
    sort: Optional[dict] = None
    limit: Optional[int] = None
    relationships: list = field(default_factory=list)
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# 1. TABLE BUSINESS MEANINGS
# ---------------------------------------------------------------------------
TABLE_MEANINGS = {
    "Categories": "Product categories used to group products.",
    "CustomerCustomerDemo": "Bridge table assigning customers to customer demographic/types.",
    "CustomerDemographics": "Definitions/descriptions of customer demographic types.",
    "Customers": "Customers/companies that place orders.",
    "EmployeeTerritories": "Bridge table assigning employees to territories.",
    "Employees": "Employees who handle/process orders and may report to other employees.",
    "Order Details": "Order line items. Each row connects an order to a product and stores the historical selling price, quantity and discount.",
    "Orders": "Customer orders, including order dates, customer, employee, shipping information and freight.",
    "Products": "Products sold by the company, including current price and inventory information.",
    "Regions": "Geographic regions used by territories.",
    "Shippers": "Shipping companies/carriers used to ship orders.",
    "Suppliers": "Companies that supply products.",
    "Territories": "Sales territories belonging to regions and assigned to employees.",
}

# ---------------------------------------------------------------------------
# 2. COLUMN BUSINESS MEANINGS
# ---------------------------------------------------------------------------
COLUMN_MEANINGS = {
    "Categories": {
        "CategoryID": "Unique category identifier; primary key.",
        "CategoryName": "Name of the product category.",
        "Description": "Description of the category.",
        "Picture": "Binary image associated with the category.",
    },
    "CustomerCustomerDemo": {
        "CustomerID": "Customer identifier; foreign key to Customers.CustomerID.",
        "CustomerTypeID": "Customer demographic/type identifier; foreign key to CustomerDemographics.CustomerTypeID.",
    },
    "CustomerDemographics": {
        "CustomerTypeID": "Unique customer demographic/type identifier; primary key.",
        "CustomerDesc": "Description of the customer demographic/type.",
    },
    "Customers": {
        "CustomerID": "Unique customer identifier; primary key.",
        "CompanyName": "Customer company/business name.",
        "ContactName": "Main contact person's name.",
        "ContactTitle": "Job title of the main contact.",
        "Address": "Customer street address.",
        "City": "Customer city.",
        "Region": "Customer state/province/region.",
        "PostalCode": "Customer postal/ZIP code.",
        "Country": "Customer country.",
        "Phone": "Customer phone number.",
        "Fax": "Customer fax number.",
    },
    "EmployeeTerritories": {
        "EmployeeID": "Employee identifier; foreign key to Employees.EmployeeID.",
        "TerritoryID": "Territory identifier; foreign key to Territories.TerritoryID.",
    },
    "Employees": {
        "EmployeeID": "Unique employee identifier; primary key.",
        "LastName": "Employee last name.",
        "FirstName": "Employee first name.",
        "Title": "Employee job title/role.",
        "TitleOfCourtesy": "Courtesy title such as Mr., Ms., Dr., etc.",
        "BirthDate": "Employee date of birth.",
        "HireDate": "Employee hiring date.",
        "Address": "Employee street address.",
        "City": "Employee city.",
        "Region": "Employee state/province/region.",
        "PostalCode": "Employee postal/ZIP code.",
        "Country": "Employee country.",
        "HomePhone": "Employee home phone number.",
        "Extension": "Employee office phone extension.",
        "Photo": "Binary employee photo.",
        "Notes": "Free-text notes about the employee.",
        "ReportsTo": "Manager/supervisor employee ID; self-referencing foreign key to Employees.EmployeeID.",
        "PhotoPath": "Path/reference for the employee photo.",
    },
    "Order Details": {
        "OrderID": "Order identifier; foreign key to Orders.OrderID. Part of composite primary key.",
        "ProductID": "Product identifier; foreign key to Products.ProductID. Part of composite primary key.",
        "UnitPrice": "Historical unit selling price recorded on the order line. Use this for transaction revenue, not Products.UnitPrice.",
        "Quantity": "Number of units of the product on the order line.",
        "Discount": "Discount fraction stored from 0 to 1; e.g. 0.10 means 10% discount.",
    },
    "Orders": {
        "OrderID": "Unique order identifier; primary key.",
        "CustomerID": "Customer who placed the order; foreign key to Customers.CustomerID.",
        "EmployeeID": "Employee responsible for the order; foreign key to Employees.EmployeeID.",
        "OrderDate": "Date/time when the order was placed.",
        "RequiredDate": "Date/time by which the order was required.",
        "ShippedDate": "Date/time when the order was shipped.",
        "ShipVia": "Shipping carrier identifier; foreign key to Shippers.ShipperID.",
        "Freight": "Freight/shipping charge recorded at order level.",
        "ShipName": "Name used for shipping destination.",
        "ShipAddress": "Shipping street address.",
        "ShipCity": "Shipping city.",
        "ShipRegion": "Shipping state/province/region.",
        "ShipPostalCode": "Shipping postal/ZIP code.",
        "ShipCountry": "Shipping country.",
    },
    "Products": {
        "ProductID": "Unique product identifier; primary key.",
        "ProductName": "Product name.",
        "SupplierID": "Supplier of the product; foreign key to Suppliers.SupplierID.",
        "CategoryID": "Product category; foreign key to Categories.CategoryID.",
        "QuantityPerUnit": "Packaging/quantity description for one product unit.",
        "UnitPrice": "Current/list unit price stored in the Products table.",
        "UnitsInStock": "Current units physically in stock.",
        "UnitsOnOrder": "Units currently on order from suppliers.",
        "ReorderLevel": "Inventory level at which replenishment should be considered.",
        "Discontinued": "Whether the product is discontinued; this database stores it as TEXT with default '0'.",
    },
    "Regions": {
        "RegionID": "Unique region identifier; primary key.",
        "RegionDescription": "Description/name of the region.",
    },
    "Shippers": {
        "ShipperID": "Unique shipping company/carrier identifier; primary key.",
        "CompanyName": "Shipping company/carrier name.",
        "Phone": "Shipping company phone number.",
    },
    "Suppliers": {
        "SupplierID": "Unique supplier identifier; primary key.",
        "CompanyName": "Supplier company name.",
        "ContactName": "Supplier contact person's name.",
        "ContactTitle": "Job title of supplier contact.",
        "Address": "Supplier street address.",
        "City": "Supplier city.",
        "Region": "Supplier state/province/region.",
        "PostalCode": "Supplier postal/ZIP code.",
        "Country": "Supplier country.",
        "Phone": "Supplier phone number.",
        "Fax": "Supplier fax number.",
        "HomePage": "Supplier website/home page URL.",
    },
    "Territories": {
        "TerritoryID": "Unique territory identifier; primary key.",
        "TerritoryDescription": "Description/name of the sales territory.",
        "RegionID": "Region containing the territory; foreign key to Regions.RegionID.",
    },
}

# ---------------------------------------------------------------------------
# 3. RELATIONSHIPS / FOREIGN KEYS
# ---------------------------------------------------------------------------
RELATIONSHIPS = [
    {"from_table": "CustomerCustomerDemo", "from_column": "CustomerID", "to_table": "Customers", "to_column": "CustomerID", "meaning": "A customer can have customer demographic/type assignments."},
    {"from_table": "CustomerCustomerDemo", "from_column": "CustomerTypeID", "to_table": "CustomerDemographics", "to_column": "CustomerTypeID", "meaning": "A customer demographic assignment points to its demographic/type definition."},
    {"from_table": "EmployeeTerritories", "from_column": "EmployeeID", "to_table": "Employees", "to_column": "EmployeeID", "meaning": "Employees can be assigned to territories."},
    {"from_table": "EmployeeTerritories", "from_column": "TerritoryID", "to_table": "Territories", "to_column": "TerritoryID", "meaning": "Territories can be assigned to employees."},
    {"from_table": "Employees", "from_column": "ReportsTo", "to_table": "Employees", "to_column": "EmployeeID", "meaning": "Employee management hierarchy/self-reference."},
    {"from_table": "Order Details", "from_column": "OrderID", "to_table": "Orders", "to_column": "OrderID", "meaning": "An order has one or more order lines."},
    {"from_table": "Order Details", "from_column": "ProductID", "to_table": "Products", "to_column": "ProductID", "meaning": "Each order line refers to a sold product."},
    {"from_table": "Orders", "from_column": "CustomerID", "to_table": "Customers", "to_column": "CustomerID", "meaning": "Each order belongs to a customer."},
    {"from_table": "Orders", "from_column": "EmployeeID", "to_table": "Employees", "to_column": "EmployeeID", "meaning": "An order can be associated with the employee who handled it."},
    {"from_table": "Orders", "from_column": "ShipVia", "to_table": "Shippers", "to_column": "ShipperID", "meaning": "An order uses a shipping carrier."},
    {"from_table": "Products", "from_column": "CategoryID", "to_table": "Categories", "to_column": "CategoryID", "meaning": "A product belongs to a category."},
    {"from_table": "Products", "from_column": "SupplierID", "to_table": "Suppliers", "to_column": "SupplierID", "meaning": "A product is supplied by a supplier."},
    {"from_table": "Territories", "from_column": "RegionID", "to_table": "Regions", "to_column": "RegionID", "meaning": "A territory belongs to a region."},
]

# ---------------------------------------------------------------------------
# 4. METRICS
# ---------------------------------------------------------------------------
METRICS = {
    "Revenue": {
        "definition": 'SUM("Order Details"."UnitPrice" * "Order Details"."Quantity" * (1 - "Order Details"."Discount"))',
        "aggregation": "SUM",
        "meaning": "Discounted transaction sales value.",
        "source": "Order Details",
        "synonyms": ["sales", "sales revenue", "net sales", "turnover", "income from sales"],
    },
    "Gross Sales": {
        "definition": 'SUM("Order Details"."UnitPrice" * "Order Details"."Quantity")',
        "aggregation": "SUM",
        "meaning": "Transaction value before discounts.",
        "source": "Order Details",
        "synonyms": ["gross revenue", "gross sales value", "sales before discount"],
    },
    "Discount Amount": {
        "definition": 'SUM("Order Details"."UnitPrice" * "Order Details"."Quantity" * "Order Details"."Discount")',
        "aggregation": "SUM",
        "meaning": "Total monetary discount applied to order lines.",
        "source": "Order Details",
        "synonyms": ["discount value", "discount total"],
    },
    "Order Count": {
        "definition": 'COUNT(DISTINCT "Orders"."OrderID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique orders.",
        "source": "Orders",
        "synonyms": ["number of orders", "orders", "total orders"],
    },
    "Order Line Count": {
        "definition": 'COUNT(*)',
        "aggregation": "COUNT",
        "meaning": "Number of rows/order lines in Order Details after filters.",
        "source": "Order Details",
        "synonyms": ["line count", "order detail count"],
    },
    "Quantity Sold": {
        "definition": 'SUM("Order Details"."Quantity")',
        "aggregation": "SUM",
        "meaning": "Total units sold on order lines.",
        "source": "Order Details",
        "synonyms": ["units sold", "items sold", "quantity sold", "sales quantity", "most sold"],
    },
    "Average Order Value": {
        "definition": 'SUM("Order Details"."UnitPrice" * "Order Details"."Quantity" * (1 - "Order Details"."Discount")) / COUNT(DISTINCT "Orders"."OrderID")',
        "aggregation": "RATIO",
        "meaning": "Average discounted revenue per unique order.",
        "source": "Orders + Order Details",
        "synonyms": ["AOV", "average order size", "average sales per order"],
    },
    "Average Selling Price": {
        "definition": 'AVG("Order Details"."UnitPrice")',
        "aggregation": "AVG",
        "meaning": "Average historical transaction unit price.",
        "source": "Order Details",
        "synonyms": ["average sold price", "average transaction price"],
    },
    "Average Discount": {
        "definition": 'AVG("Order Details"."Discount")',
        "aggregation": "AVG",
        "meaning": "Average discount fraction on order lines.",
        "source": "Order Details",
        "synonyms": ["average discount rate"],
    },
    "Freight Cost": {
        "definition": 'SUM("Orders"."Freight")',
        "aggregation": "SUM",
        "meaning": "Total freight recorded on orders. Keep at order grain to avoid duplication after line joins.",
        "source": "Orders",
        "synonyms": ["freight", "shipping cost", "shipping charges"],
    },
    "Average Freight": {
        "definition": 'AVG("Orders"."Freight")',
        "aggregation": "AVG",
        "meaning": "Average freight charge per order row.",
        "source": "Orders",
        "synonyms": ["average shipping cost", "average freight"],
    },
    "Product Count": {
        "definition": 'COUNT(DISTINCT "Products"."ProductID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique products.",
        "source": "Products",
        "synonyms": ["number of products", "products count"],
    },
    "Customer Count": {
        "definition": 'COUNT(DISTINCT "Customers"."CustomerID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique customers.",
        "source": "Customers",
        "synonyms": ["number of customers", "customers count"],
    },
    "Employee Count": {
        "definition": 'COUNT(DISTINCT "Employees"."EmployeeID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique employees.",
        "source": "Employees",
        "synonyms": ["number of employees", "staff count"],
    },
    "Supplier Count": {
        "definition": 'COUNT(DISTINCT "Suppliers"."SupplierID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique suppliers.",
        "source": "Suppliers",
        "synonyms": ["number of suppliers"],
    },
    "Category Count": {
        "definition": 'COUNT(DISTINCT "Categories"."CategoryID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique product categories.",
        "source": "Categories",
        "synonyms": ["number of categories"],
    },
    "Shipper Count": {
        "definition": 'COUNT(DISTINCT "Shippers"."ShipperID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique shippers.",
        "source": "Shippers",
        "synonyms": ["number of shippers", "carrier count"],
    },
    "Territory Count": {
        "definition": 'COUNT(DISTINCT "Territories"."TerritoryID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique territories.",
        "source": "Territories",
        "synonyms": ["number of territories"],
    },
    "Region Count": {
        "definition": 'COUNT(DISTINCT "Regions"."RegionID")',
        "aggregation": "COUNT DISTINCT",
        "meaning": "Number of unique regions.",
        "source": "Regions",
        "synonyms": ["number of regions"],
    },
    "Products In Stock": {
        "definition": 'SUM("Products"."UnitsInStock")',
        "aggregation": "SUM",
        "meaning": "Total current units in stock across products.",
        "source": "Products",
        "synonyms": ["stock", "inventory", "available stock", "units in stock"],
    },
    "Products On Order": {
        "definition": 'SUM("Products"."UnitsOnOrder")',
        "aggregation": "SUM",
        "meaning": "Total units currently on order from suppliers.",
        "source": "Products",
        "synonyms": ["units on order", "incoming stock"],
    },
    "Average Product Price": {
        "definition": 'AVG("Products"."UnitPrice")',
        "aggregation": "AVG",
        "meaning": "Average current/list product price.",
        "source": "Products",
        "synonyms": ["average price", "mean product price"],
    },
}

# ---------------------------------------------------------------------------
# 5. AGGREGATIONS / BUSINESS RULES / SYNONYMS
# ---------------------------------------------------------------------------
AGGREGATIONS = {
    "sum": "SUM",
    "total": "SUM",
    "average": "AVG",
    "avg": "AVG",
    "mean": "AVG",
    "count": "COUNT",
    "how many": "COUNT",
    "number of": "COUNT",
    "maximum": "MAX",
    "max": "MAX",
    "highest": "MAX/ORDER DESC",
    "minimum": "MIN",
    "min": "MIN",
    "lowest": "MIN/ORDER ASC",
    "top": "ORDER DESC + LIMIT",
    "bottom": "ORDER ASC + LIMIT",
}

SYNONYMS = {
    "customer": ["customers", "client", "clients", "buyer", "buyers", "company", "companies"],
    "product": ["products", "item", "items", "goods"],
    "order": ["orders", "purchase", "purchases", "sales order"],
    "order detail": ["order details", "order line", "order lines", "line item", "line items"],
    "employee": ["employees", "staff", "worker", "workers", "sales person", "salesperson", "representative"],
    "supplier": ["suppliers", "vendor", "vendors"],
    "category": ["categories", "product category", "product categories", "type of product"],
    "shipper": ["shippers", "carrier", "carriers", "shipping company", "shipping companies"],
    "territory": ["territories", "sales territory", "sales territories", "area"],
    "region": ["regions", "area", "geographic region"],
    "revenue": ["sales", "net sales", "sales revenue", "turnover"],
    "quantity": ["qty", "units", "amount of items", "number of units"],
    "price": ["unit price", "cost", "selling price"],
    "country": ["nation"],
    "city": ["town"],
}

BUSINESS_RULES = [
    "Revenue = UnitPrice * Quantity * (1 - Discount), aggregated with SUM.",
    "Revenue uses Order Details.UnitPrice because it is the historical transaction price.",
    "Products.UnitPrice is the current/list product price and should not replace Order Details.UnitPrice for historical sales revenue.",
    "Gross Sales excludes discounts: UnitPrice * Quantity.",
    "Discount is stored as a fraction between 0 and 1; 0.10 means 10%.",
    "Order Count must use COUNT(DISTINCT Orders.OrderID) when joins can duplicate order rows.",
    "Customer Count must use COUNT(DISTINCT Customers.CustomerID) when joins can duplicate customer rows.",
    "Product Count must use COUNT(DISTINCT Products.ProductID) when joins can duplicate product rows.",
    "Order Line Count counts Order Details rows and represents line items, not unique orders.",
    "Freight is an order-level value. Do not SUM Orders.Freight after joining directly to Order Details unless order-level duplication is handled.",
    "Customer geography uses Customers.City/Region/PostalCode/Country.",
    "Shipping geography uses Orders.ShipCity/ShipRegion/ShipPostalCode/ShipCountry and is different from customer geography.",
    "OrderDate is used for when an order was placed; RequiredDate is the requested deadline; ShippedDate is the shipment date.",
    "Employee hierarchy uses Employees.ReportsTo -> Employees.EmployeeID.",
    "Discontinued is stored as TEXT in this SQLite database; default value is '0'.",
    "When a table or column name contains spaces or special characters, quote it with double quotes, e.g. \"Order Details\".",
    "For 'most sold' products, use Quantity Sold unless the user explicitly asks for revenue or another metric.",
    "For 'most expensive products', use Products.UnitPrice unless the user explicitly asks for historical selling price.",
    "For 'best customers', do not assume a metric. If no metric is specified, the intent is ambiguous and should be clarified.",
    "For 'best customers by revenue', group at customer level and use discounted Revenue.",
    "For 'best customers by orders', group at customer level and use distinct Order Count.",
    "For top/bottom N requests, preserve the requested N as LIMIT and sort the selected metric in the requested direction.",
    "Do not invent tables, columns, metrics or relationships that are not present in this semantic layer.",
]


def connect():
    return sqlite3.connect(str(DATABASE_PATH))


def get_database_metadata():
    """Return the actual current SQLite schema, including types, PKs and FKs."""
    with connect() as db:
        tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
        metadata = {}
        for table in tables:
            if table == "sqlite_sequence":
                continue
            columns = []
            for row in db.execute(f"PRAGMA table_info({quote_identifier(table)})"):
                cid, name, data_type, notnull, default_value, pk = row
                columns.append({
                    "name": name,
                    "data_type": data_type,
                    "not_null": bool(notnull),
                    "default": default_value,
                    "primary_key_position": pk,
                    "meaning": COLUMN_MEANINGS.get(table, {}).get(name, ""),
                })
            foreign_keys = []
            for row in db.execute(f"PRAGMA foreign_key_list({quote_identifier(table)})"):
                _, _, ref_table, from_col, to_col, on_update, on_delete, match = row
                foreign_keys.append({
                    "from_column": from_col,
                    "to_table": ref_table,
                    "to_column": to_col,
                    "on_update": on_update,
                    "on_delete": on_delete,
                    "match": match,
                })
            metadata[table] = {
                "meaning": TABLE_MEANINGS.get(table, ""),
                "columns": columns,
                "foreign_keys": foreign_keys,
            }
        return metadata


def get_relationships():
    return RELATIONSHIPS


def get_relationship_path(start_table, end_table):
    """Find a short FK path between two tables using the declared relationships."""
    if start_table == end_table:
        return [start_table]

    graph = {}
    for r in RELATIONSHIPS:
        graph.setdefault(r["from_table"], []).append(r["to_table"])
        graph.setdefault(r["to_table"], []).append(r["from_table"])

    queue = [(start_table, [start_table])]
    seen = {start_table}
    while queue:
        current, path = queue.pop(0)
        for nxt in graph.get(current, []):
            if nxt in seen:
                continue
            new_path = path + [nxt]
            if nxt == end_table:
                return new_path
            seen.add(nxt)
            queue.append((nxt, new_path))
    return None


def get_semantic_context(question=None):
    """Return all semantic knowledge used by the SQL generator."""
    context = {
        "database": {
            "name": "Northwind SQLite",
            "file": DATABASE_PATH.name,
            "dialect": "SQLite",
        },
        "tables": get_database_metadata(),
        "relationships": RELATIONSHIPS,
        "metrics": METRICS,
        "aggregations": AGGREGATIONS,
        "synonyms": SYNONYMS,
        "business_rules": BUSINESS_RULES,
    }
    if question:
        context["user_question"] = question
    return context


def get_semantic_context_text(question=None):
    return json.dumps(get_semantic_context(question), indent=2, ensure_ascii=False)


def parse_semantic(question):
    """Interpret a user question into structured meaning. Never generate SQL."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured.")

    context = get_semantic_context_text(question)
    prompt = f"""
You are the semantic interpretation layer for a Northwind SQLite database.
Your job is ONLY to understand the user's question. NEVER generate SQL.

Use ONLY the supplied semantic context. Do not invent tables, columns, metrics,
relationships or business definitions.

SEMANTIC CONTEXT:
{context}

USER QUESTION:
{question}

Return ONLY valid JSON with this exact structure:
{{
  "status": "clear | ambiguous | unknown",
  "entity": null,
  "business_term": null,
  "metric": null,
  "aggregation": null,
  "filters": [],
  "group_by": [],
  "sort": null,
  "limit": null,
  "relationships": [],
  "reason": null
}}

Rules:
1. Preserve every explicit filter from the user, including country, city, date,
   price, quantity, category, employee, supplier and other conditions.
2. Preserve grouping, sorting and LIMIT/top-N intent.
3. If a defined metric is explicitly mentioned, use that metric.
4. "best customers" without a metric is ambiguous; do not silently assume revenue.
5. "customers with highest revenue" is clear: entity=Customer, metric=Revenue,
   aggregation=SUM, sort=Revenue DESC, group_by=Customer.
6. "most sold products" normally means Quantity Sold unless another metric is explicit.
7. "most expensive products" normally means Products.UnitPrice.
8. A word like highest/lowest/top/best is not itself a metric.
9. Resolve synonyms using the supplied synonym dictionary.
10. Use the actual relationship path needed by the requested entities/metrics.
11. A query is unknown only when it does not map to the database knowledge.
12. A query is ambiguous only when a required interpretation genuinely has multiple
    reasonable meanings.
13. Understand English, Hindi, Hinglish and Gujarati while preserving the intended meaning.
14. Return JSON only.
"""

    client = Groq(api_key=api_key)
    response = client.chat.completions.create(
        model="qwen/qwen3.8-27b",
        messages=[{"role": "user", "content": prompt}],
        temperature=0,
    )
    content = response.choices[0].message.content.strip()
    if content.startswith("```"):
        content = content.strip("`").replace("json\n", "", 1).strip()
    return json.loads(content)


def get_sql_generator_context(question):
    """Return semantic knowledge + interpreted meaning for generate_sql()."""
    semantic_context = get_semantic_context(question)
    try:
        meaning = parse_semantic(question)
    except Exception as exc:
        meaning = {"status": "unavailable", "reason": str(exc)}

    return {
        "semantic_layer": semantic_context,
        "interpreted_question": meaning,
        "sql_rules": [
            "Generate SQLite SQL only.",
            "Generate one statement only.",
            "Generate SELECT only.",
            "Use only tables and columns present in the semantic layer.",
            "Use the declared foreign-key relationships for joins.",
            "Follow metric definitions exactly.",
            "Use DISTINCT where the semantic metric requires it.",
            "Avoid duplicating order-level metrics after line-item joins.",
            "Quote identifiers containing spaces or special characters with double quotes.",
            "Do not use Products.UnitPrice for historical revenue when Order Details.UnitPrice is available.",
        ],
    }


def validate_semantic_coverage():
    """Check that semantic documentation covers every real table/column."""
    metadata = get_database_metadata()
    missing_tables = [t for t in metadata if t not in TABLE_MEANINGS]
    missing_columns = []
    for table, info in metadata.items():
        documented = COLUMN_MEANINGS.get(table, {})
        for col in info["columns"]:
            if col["name"] not in documented:
                missing_columns.append(f"{table}.{col['name']}")
    return {
        "missing_tables": missing_tables,
        "missing_columns": missing_columns,
        "complete": not missing_tables and not missing_columns,
    }


if __name__ == "__main__":
    print(json.dumps(validate_semantic_coverage(), indent=2))
    print("\nNorthwind tables:")
    for table, info in get_database_metadata().items():
        print(f"- {table}: {len(info['columns'])} columns")
