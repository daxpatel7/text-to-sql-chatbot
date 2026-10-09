"""Semantic layer for the Northwind SQLite database.

The semantic layer stores database/business knowledge and interprets a user's
question. It does NOT generate SQL. The SQL generator should consume
get_sql_generator_context(question).
"""

from dataclasses import dataclass, field
from typing import Optional
from functools import lru_cache
import json
import os
import re
import difflib
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
# 4A. CANONICAL METRIC TO UI DISPLAY MAPPING
# ---------------------------------------------------------------------------

CANONICAL_TO_DISPLAY = {
    "Revenue": "Revenue",
    "Order Count": "Orders",
    "Quantity Sold": "Quantity",
    "Product Count": "Products",
    "Average Product Price": "Average Product Price",
    "Freight Cost": "Freight Cost",
    "Discount Amount": "Discount Amount",
    "Customer Count": "Customers",
    "Employee Count": "Employees",
    "Supplier Count": "Suppliers",
    "Category Count": "Categories",
    "Shipper Count": "Shippers",
    "Territory Count": "Territories",
    "Region Count": "Regions",
}

DISPLAY_TO_CANONICAL = {v.lower(): k for k, v in CANONICAL_TO_DISPLAY.items()}

# ---------------------------------------------------------------------------
# 4B. CLARIFICATION METRIC RULES (SOURCE OF TRUTH)
# ---------------------------------------------------------------------------

METRIC_RULES = {
    "Customers": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "lowest", "most valuable", "most active", "most loyal",
            "valuable", "active", "loyal",
            "achha", "acha", "achhi", "acche", "badiya", "sabse achha", "sabse acha", "sabse achhi", "sabse acche",
            "bura", "buri", "sabse bura", "sabse buri", "kharab", "sabse kharab",
            "saras", "sauthi saras", "sauthi kharab",
            "સૌથી સરસ", "સરસ", "સૌથી ખરાબ", "ખરાબ",
            "सबसे अच्छा", "सबसे अच्छे", "अच्छा", "अच्छे", "सबसे खराब", "खराब", "उत्तम", "श्रेष्ठ",
        ],
        "metrics": [
            "Revenue",
            "Order Count",
            "Quantity Sold",
        ],
    },
    "Products": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "lowest", "popular", "valuable", "most popular", "most valuable",
            "leading", "performing",
            "achha", "acha", "achhi", "acche", "sabse achha", "sabse acha", "sabse acche",
            "bura", "buri", "sabse bura", "kharab", "sabse kharab",
            "mashhoor", "mashhur", "sabse popular", "lokpriya", "lokpriy", "sabse lokpriya",
            "saras", "sauthi saras", "sauthi popular", "sauthi lokpriya", "sauthi kharab",
            "સૌથી લોકપ્રિય", "લોકપ્રિય", "સૌથી સરસ", "સરસ", "સૌથી ખરાબ", "ખરાબ",
            "सबसे अच्छा", "सबसे अच्छे", "अच्छा", "सबसे लोकप्रिय", "लोकप्रिय", "मशहूर", "सबसे खराब", "खराब",
        ],
        "metrics": [
            "Revenue",
            "Quantity Sold",
            "Order Count",
            "Average Product Price",
        ],
    },
    "Employees": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "lowest", "most productive", "productive", "most active", "active",
            "leading", "performing",
            "achha", "acha", "achhi", "acche", "sabse achha", "sabse acha", "sabse acche",
            "bura", "sabse bura", "sabse productive", "kabil", "sabse kabil",
            "saras", "sauthi saras", "sauthi productive",
            "સૌથી સરસ", "સરસ", "સૌથી ઉત્પાદક", "ઉત્પાદક",
            "सबसे अच्छा", "सबसे अच्छे", "अच्छा", "सबसे कर्मठ", "कर्मठ", "सक्षम",
        ],
        "metrics": [
            "Revenue",
            "Order Count",
            "Quantity Sold",
        ],
    },
    "Categories": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "lowest", "popular", "most popular",
            "leading", "performing",
            "achha", "acha", "achhi", "acche", "sabse achha", "sabse acha",
            "bura", "sabse bura", "kharab", "sabse kharab",
            "mashhoor", "mashhur", "sabse popular", "lokpriya", "lokpriy", "sabse lokpriya",
            "saras", "sauthi saras", "sauthi popular", "sauthi lokpriya",
            "સૌથી લોકપ્રિય", "લોકપ્રિય", "સૌથી સરસ", "સરસ",
            "सबसे अच्छा", "सबसे अच्छे", "सबसे लोकप्रिय", "लोकप्रिय", "मशहूर",
        ],
        "metrics": [
            "Revenue",
            "Quantity Sold",
            "Order Count",
        ],
    },
    "Suppliers": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "lowest", "productive", "most productive",
            "leading", "performing",
            "achha", "acha", "sabse achha", "sabse acha", "sabse productive",
            "bura", "sabse bura", "kharab", "sabse kharab",
            "saras", "sauthi saras", "sauthi productive",
            "સૌથી સરસ", "સરસ", "સૌથી ઉત્પાદક",
            "सबसे अच्छा", "सबसे अच्छे", "सबसे कर्मठ",
        ],
        "metrics": [
            "Revenue",
            "Quantity Sold",
            "Product Count",
        ],
    },
    "Orders": {
        "ambiguous_words": [
            "best", "worst", "top", "highest", "largest", "most expensive", "recent",
            "bada", "sabse bada", "badi", "sabse badi", "mota", "sauthi mota",
        ],
        "metrics": [
            "Revenue",
            "Quantity Sold",
            "Freight Cost",
        ],
    },
    "Order Details": {
        "ambiguous_words": [
            "best", "worst", "top", "highest",
        ],
        "metrics": [
            "Revenue",
            "Quantity Sold",
            "Discount Amount",
        ],
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

ENTITY_SYNONYMS = {
    "Customers": [
        "customer", "customers", "client", "clients", "buyer", "buyers",
        "customer company", "customer companies",
        "grahak", "grahako", "khedut", "kheduto", "ग्राहक", "ग्राहकों", "ગ્રાહક", "ગ્રાહકો",
    ],
    "Products": [
        "product", "products", "item", "items", "goods", "merchandise",
        "utpadan", "utpadano", "vastu", "vastuo", "cheej", "cheeje", "maal",
        "उत्पाद", "उत्पादों", "वस्तु", "ચીજ", "વસ્તુઓ", "ઉત્પાદન", "ઉત્પાદનો",
    ],
    "Employees": [
        "employee", "employees", "staff", "worker", "workers",
        "salesperson", "sales person", "salespersons", "representative", "representatives",
        "karmchari", "karmachari", "karmchario", "karmachariyo",
        "कर्मचारी", "कर्मचारियों", "કર્મચારી", "કર્મચારીઓ",
    ],
    "Categories": [
        "category", "categories", "product category", "product categories", "type of product",
        "shreni", "shreniyo", "varg", "vargo", "श्रेणी", "श्रेणियां", "શ્રેણી", "શ્રેણીઓ",
    ],
    "Suppliers": [
        "supplier", "suppliers", "vendor", "vendors",
        "vyapari", "vyapariyo", "purvatha", "purvathadar",
        "व्यापारी", "व्यापारियों", "આપનાર", "વેપારી", "વેપારીઓ",
    ],
    "Order Details": [
        "order detail", "order details", "order line", "order lines",
        "line item", "line items", "order detail record", "order detail records",
    ],
    "Orders": [
        "order", "orders", "purchase", "purchases", "sales order", "sales orders",
        "kharid", "kharidi", "kharidari", "ऑर्डर", "खरीद", "ખરીદી", "ઓર્ડર",
    ],
    "Shippers": [
        "shipper", "shippers", "carrier", "carriers", "shipping company", "shipping companies",
    ],
    "Territories": [
        "territory", "territories", "sales territory", "sales territories", "area", "areas",
    ],
    "Regions": [
        "region", "regions", "geographic region", "geographic regions", "zone", "zones",
    ],
    "CustomerDemographics": [
        "customer demographic", "customer demographics", "customer type", "customer types",
    ],
}

SYNONYMS = {k.lower(): v for k, v in ENTITY_SYNONYMS.items()}

METRIC_SYNONYMS = {
    "Revenue": [
        "revenue", "sales", "sales revenue", "net sales", "turnover", "income from sales",
        "sales amount", "sales value", "total sales", "total sales amount",
        "money generated", "money made", "earnings", "income generated",
        "kamai", "bikri", "aavak", "aavako", "આવક", "बिक्री", "कमाई",
    ],
    "Gross Sales": [
        "gross sales", "gross revenue", "gross sales value", "sales before discount",
    ],
    "Discount Amount": [
        "discount amount", "discount value", "discount total", "total discount",
        "discount", "chhoot", "chut", "छूट",
    ],
    "Order Count": [
        "order count", "number of orders", "total orders", "orders count",
        "count of orders", "kitne orders", "ketla orders",
    ],
    "Order Line Count": [
        "order line count", "line count", "order detail count", "records in order details",
        "number of records in order details", "records are in order details",
    ],
    "Quantity Sold": [
        "quantity sold", "units sold", "items sold", "sales quantity",
        "most sold", "units", "quantity", "qty",
        "sabse zyada bike", "sabse zyada bika", "vadhu vechayel",
    ],
    "Average Order Value": [
        "average order value", "aov", "average order size", "average sales per order",
    ],
    "Average Selling Price": [
        "average selling price", "average sold price", "average transaction price",
    ],
    "Average Discount": [
        "average discount", "average discount rate",
    ],
    "Freight Cost": [
        "freight cost", "freight charges", "freight", "shipping cost", "shipping charges",
    ],
    "Average Freight": [
        "average freight", "average shipping cost",
    ],
    "Product Count": [
        "product count", "number of products", "products count", "total products",
    ],
    "Customer Count": [
        "customer count", "number of customers", "customers count", "total customers",
    ],
    "Employee Count": [
        "employee count", "number of employees", "staff count", "total employees",
    ],
    "Supplier Count": [
        "supplier count", "number of suppliers", "total suppliers",
    ],
    "Category Count": [
        "category count", "number of categories", "total categories",
    ],
    "Shipper Count": [
        "shipper count", "number of shippers", "carrier count",
    ],
    "Territory Count": [
        "territory count", "number of territories",
    ],
    "Region Count": [
        "region count", "number of regions",
    ],
    "Products In Stock": [
        "products in stock", "units in stock", "available stock", "inventory",
    ],
    "Average Product Price": [
        "average product price", "average price", "mean product price",
        "products ki average price", "average price of products",
    ],
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
    "Out of stock means Products.UnitsInStock = 0. Do not use Discontinued unless the user explicitly asks for discontinued products.",
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


@lru_cache(maxsize=1)
def get_database_metadata():
    """Return the actual current SQLite schema, cached."""
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


# ---------------------------------------------------------------------------
# 6. TEXT PROCESSING & SAFETY HELPERS
# ---------------------------------------------------------------------------

PUNCT_RE = re.compile(r"""[.,;:?!\"'(){}\[\]/\\`~@#$%^&*+=<>|_]""")


def _normalize_semantic_text(text):
    """Normalize wording without destroying non-ASCII Unicode letters and combining marks."""
    text = (text or "").lower().strip()
    text = text.replace("’", "'").replace("‘", "'")
    text = PUNCT_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _phrase_in_text(text, phrase):
    """Word-boundary phrase match; avoids substring false positives."""
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text, flags=re.UNICODE) is not None


def _is_unsafe(text):
    """Detect queries attempting database modifications or injection."""
    q = _normalize_semantic_text(text)
    patterns = [
        r"\b(?:drop\s+table|delete\s+from|truncate\s+table|alter\s+table|insert\s+into)\b",
        r"\b(?:delete|drop|update|insert|alter|truncate)\s+(?:all\s+)?(?:customers?|orders?|products?|employees?|suppliers?|categories?)\b",
        r"\bdelete\s+everything\b",
        r"\bdrop\s+all\b",
        r"\bupdate\s+\w+\s+set\b",
        r"\bupdate\s+all\s+\w+\s+prices\b",
        r"\bignore\s+previous\s+instructions\b",
        r";\s*drop\s+table\b",
        r";\s*delete\s+from\b",
    ]
    return any(re.search(p, q, flags=re.UNICODE) for p in patterns)


def _is_unknown(text):
    """Detect queries asking for concepts that do not exist in the Northwind DB."""
    q = _normalize_semantic_text(text)
    unknown_patterns = [
        r"\b(?:salary|salaries|pay|wages?)\b",
        r"\b(?:product\s+reviews?|reviews?|ratings?)\b",
        r"\b(?:today'?s\s+weather|weather|temperature)\b",
        r"\b(?:password|passwords|auth\s+token)\b",
    ]
    return any(re.search(p, q, flags=re.UNICODE) for p in unknown_patterns)


# ---------------------------------------------------------------------------
# 7. ENTITY & METRIC RESOLUTION
# ---------------------------------------------------------------------------

def _resolve_entities(question):
    """Resolve database entities using multilingual synonym mapping."""
    q = _normalize_semantic_text(question)
    found = []

    # Check Order Details before Orders so "order details" isn't shadowed by "orders"
    priority_order = [
        "Order Details", "Customers", "Products", "Employees", "Categories",
        "Suppliers", "Orders", "Shippers", "Territories", "Regions", "CustomerDemographics"
    ]

    for entity in priority_order:
        aliases = sorted(ENTITY_SYNONYMS.get(entity, []), key=lambda a: -len(a))
        for alias in aliases:
            alias_n = _normalize_semantic_text(alias)
            if alias_n and _phrase_in_text(q, alias_n):
                if entity not in found:
                    found.append(entity)
                break

    # Safe typo recovery for single words >= 5 chars
    alias_to_table = {}
    for table, aliases in ENTITY_SYNONYMS.items():
        for alias in aliases:
            alias_n = _normalize_semantic_text(alias)
            if len(alias_n.split()) == 1 and len(alias_n) >= 5:
                alias_to_table[alias_n] = table
    for word in q.split():
        if len(word) < 5:
            continue
        matches = difflib.get_close_matches(word, alias_to_table.keys(), n=1, cutoff=0.82)
        if matches:
            table = alias_to_table[matches[0]]
            if table not in found:
                found.append(table)

    return found


def _resolve_metric(question, primary_entity=None):
    """Resolve a business metric from explicit names, configured synonyms and contextual cues."""
    q = _normalize_semantic_text(question)
    candidates = []

    # 1. Exact metric synonyms
    for metric_name, aliases in METRIC_SYNONYMS.items():
        for alias in [metric_name] + aliases:
            alias_n = _normalize_semantic_text(alias)
            if alias_n and _phrase_in_text(q, alias_n):
                candidates.append((len(alias_n), metric_name, alias_n))

    # 2. Contextual Order Count when another entity (Customers, Employees) is primary
    if primary_entity in {"Customers", "Employees"}:
        order_patterns = [
            r"\b(?:by|with|most|highest|zyada|jyada|vadhu|sabse\s+zyada|sabse\s+jyada|sauthi\s+vadhu)\s+orders?\b",
            r"\borders?\s+(?:kiye|handled?|handle\s+kiye|placed|sanbhalya|na\s+che)\b",
            r"\borders?\s+by\b",
            r"\bkis\s+(?:customer|employee)\s+ne\s+sabse\s+zyada\s+orders?\b",
            r"\bkaya\s+customer\s+na\s+vadhu\s+orders?\b",
            r"\bunke\s+orders?\b",
        ]
        if any(re.search(p, q, flags=re.UNICODE) for p in order_patterns):
            candidates.append((25, "Order Count", "contextual order count"))

    # 3. Contextual Most Expensive / Unit Price
    expensive_patterns = [
        r"\b(?:most\s+expensive|highest\s+price|costliest)\b",
        r"\b(?:mehnga|mehnge|sabse\s+mehnga|sabse\s+mehnge|mongha|sauthi\s+mongha)\b",
        r"\b(?:महंगा|महंगे|सबसे\s+महंगा|સૌથી\s+મોંઘા|મોંઘા)\b",
    ]
    if any(re.search(p, q, flags=re.UNICODE) for p in expensive_patterns):
        candidates.append((20, "Average Product Price", "contextual price"))

    # 4. Contextual Most Sold -> Quantity Sold
    if _phrase_in_text(q, "most sold") or _phrase_in_text(q, "sabse zyada bike"):
        candidates.append((18, "Quantity Sold", "most sold"))

    # 5. Fuzzy typo recovery for metrics
    words = q.split()
    known_aliases = {}
    for metric_name, aliases in METRIC_SYNONYMS.items():
        for alias in [metric_name] + aliases:
            alias_n = _normalize_semantic_text(alias)
            if len(alias_n.split()) == 1 and len(alias_n) >= 5:
                known_aliases[alias_n] = metric_name

    for word in words:
        if len(word) < 5:
            continue
        matches = difflib.get_close_matches(word, known_aliases.keys(), n=1, cutoff=0.84)
        if matches:
            alias = matches[0]
            candidates.append((len(alias) - 1, known_aliases[alias], f"typo:{word}->{alias}"))

    if not candidates:
        return None

    # Prefer longest matched phrase
    candidates.sort(key=lambda x: -x[0])
    return candidates[0][1]


def _resolve_ranking(question):
    """Resolve ranking direction (ASC or DESC) across languages."""
    q = _normalize_semantic_text(question)

    asc_patterns = [
        r"\b(?:worst|bottom|lowest|least|minimum|poorest|smallest)\b",
        r"\b(?:bura|buri|sabse\s+bura|sabse\s+buri|kharab|sabse\s+kharab|sabse\s+kam|kam\s+se\s+kam)\b",
        r"\b(?:sauthi\s+kharab|sauthi\s+ochhu|ochhu)\b",
        r"\b(?:સૌથી\s+ખરાબ|ખરાબ|સૌથી\s+ઓછું|ઓછું)\b",
        r"\b(?:सबसे\s+खराब|खराब|सबसे\s+कम|कम\s+से\s+कम|न्यूनतम)\b",
    ]
    if any(re.search(p, q, flags=re.UNICODE) for p in asc_patterns):
        return "ASC"

    desc_patterns = [
        r"\b(?:best|top|highest|most|largest|maximum|leading|valuable|loyal|active|productive|popular)\b",
        r"\b(?:achha|acha|achhi|acche|badiya|sabse\s+achha|sabse\s+acha|sabse\s+achhi|sabse\s+acche|sabse\s+badiya)\b",
        r"\b(?:sabse\s+zyada|sabse\s+jyada|zyada|jyada|adhik|sabse\s+adhik|bada|sabse\s+bada)\b",
        r"\b(?:mashhoor|lokpriya|lokpriy|sabse\s+popular|sabse\s+lokpriya|sabse\s+productive|kabil)\b",
        r"\b(?:sauthi\s+saras|saras|sauthi\s+vadhu|vadhu|sauthi\s+mota|mota|sauthi\s+popular|sauthi\s+lokpriya)\b",
        r"\b(?:સૌથી\s+સરસ|સરસ|સૌથી\s+વધુ|વધુ|સૌથી\s+લોકપ્રિય|લોકપ્રિય)\b",
        r"\b(?:सबसे\s+अच्छा|सबसे\s+अच्छे|अच्छा|अच्छे|सबसे\s+ज्यादा|सबसे\s+अधिक|ज्यादा|अधिक|सबसे\s+लोकप्रिय|लोकप्रिय)\b",
        r"\b(?:mehnge|mehnga|sabse\s+mehnga|sabse\s+mehnge|mongha|sauthi\s+mongha)\b",
        r"\b(?:महंगे|महंगा|સૌથી\s+મોંઘા)\b",
    ]
    if any(re.search(p, q, flags=re.UNICODE) for p in desc_patterns):
        return "DESC"

    return None


def _resolve_limit(question):
    """Extract requested top/bottom N count or superlative limit 1."""
    q = _normalize_semantic_text(question)

    m = re.search(r"\b(?:top|bottom|first|last)\s+(\d+)\b", q)
    if m:
        return int(m.group(1))

    m = re.search(r"\b(\d+)\s+(?:top|bottom|best|worst|first|last|mehnge|mehnga|customers|products|orders)\b", q)
    if m:
        return int(m.group(1))

    m = re.search(r"\b(?:સૌથી\s+મોંઘા|સૌથી\s+સરસ|સૌથી\s+વધુ|सबसे\s+महंगे|sabse\s+mehnge)\s+(\d+)\b", q)
    if m:
        return int(m.group(1))

    if _resolve_ranking(q):
        return 1

    return None


def _resolve_aggregation(question, metric):
    q = _normalize_semantic_text(question)
    if metric and metric in METRICS:
        default = METRICS[metric].get("aggregation")
    else:
        default = None

    if re.search(r"\b(?:average|avg|mean)\b", q):
        return "AVG"
    if re.search(r"\b(?:how many|number of|count|total number of|kitne|ketla|कुल कितने)\b", q):
        if metric and metric.endswith("Count"):
            return METRICS[metric].get("aggregation")
        return "COUNT"
    if re.search(r"\b(?:total|sum|कुल)\b", q):
        return "SUM"
    return default


# ---------------------------------------------------------------------------
# 8. STRUCTURED SEMANTIC INTENT (CORE ENGINE)
# ---------------------------------------------------------------------------

def resolve_semantic_intent(question, conversation_history=None):
    """Deterministically resolve complete semantic intent before SQL generation."""
    q = _normalize_semantic_text(question)

    if _is_unsafe(q):
        return {
            "status": "unsafe",
            "entity": None,
            "entities": [],
            "metric": None,
            "ranking": None,
            "limit": None,
            "aggregation": None,
            "needs_clarification": False,
            "allowed_metrics": [],
            "display_options": [],
            "ambiguous_terms": [],
            "conditions": {},
            "group_by": [],
            "filters": [],
        }

    if _is_unknown(q):
        return {
            "status": "unknown",
            "entity": None,
            "entities": [],
            "metric": None,
            "ranking": None,
            "limit": None,
            "aggregation": None,
            "needs_clarification": False,
            "allowed_metrics": [],
            "display_options": [],
            "ambiguous_terms": [],
            "conditions": {},
            "group_by": [],
            "filters": [],
        }

    entities = _resolve_entities(q)
    primary_entity = entities[0] if entities else None

    # Resolve entity from conversation history for follow-ups if missing in current question
    if not primary_entity and conversation_history:
        for hist in reversed(conversation_history):
            h_entities = _resolve_entities(hist)
            if h_entities:
                primary_entity = h_entities[0]
                if primary_entity not in entities:
                    entities.append(primary_entity)
                break

    metric = _resolve_metric(q, primary_entity)
    ranking = _resolve_ranking(q)
    limit = _resolve_limit(q)
    aggregation = _resolve_aggregation(q, metric)
    out_of_stock = bool(re.search(r"\b(?:out of stock|outofstock|outof stock|no stock|zero stock|stock is zero|stock khatam|stock nathi)\b", q))

    # Clarification checking
    needs_clarification = False
    ambiguous_terms = []
    allowed_metrics = []

    if primary_entity and primary_entity in METRIC_RULES:
        rule = METRIC_RULES[primary_entity]
        allowed_metrics = rule["metrics"]

        # If user explicitly specified an allowed metric for this entity -> CLEAR
        if metric and metric in allowed_metrics:
            needs_clarification = False
        elif ranking:
            # Check ambiguous ranking words for this entity
            ambiguous_words = rule["ambiguous_words"]
            if any(_phrase_in_text(q, _normalize_semantic_text(w)) for w in ambiguous_words):
                needs_clarification = True
                ambiguous_terms.append(f"{primary_entity} ranking needs a metric")

    # Specific phrase clarification (e.g. "recent orders")
    if re.search(r"\b(?:recent\s+orders|show\s+recent\s+orders)\b", q):
        needs_clarification = True
        primary_entity = "Orders"
        allowed_metrics = METRIC_RULES["Orders"]["metrics"]
        ambiguous_terms.append("recent orders needs clarification")

    # Grouping cues
    group_by = []
    group_patterns = {
        "country": "Customers.Country",
        "city": "Customers.City",
        "category": "Categories.CategoryName",
        "product": "Products.ProductName",
        "customer": "Customers.CustomerID",
        "employee": "Employees.EmployeeID",
        "supplier": "Suppliers.SupplierID",
        "region": "Regions.RegionDescription",
        "territory": "Territories.TerritoryDescription",
    }
    for phrase, field_name in group_patterns.items():
        if re.search(r"\b(?:per|by|each|wise|har|darek)\s+(?:the\s+)?" + re.escape(phrase) + r"s?\b", q):
            group_by.append(field_name)

    display_options = clarification_display_options(allowed_metrics) if allowed_metrics else []

    status = "clarify" if needs_clarification else "clear"

    return {
        "status": status,
        "entity": primary_entity,
        "entities": entities,
        "business_term": None,
        "metric": metric,
        "aggregation": aggregation,
        "group_by": group_by,
        "sort_direction": ranking,
        "limit": limit,
        "needs_clarification": needs_clarification,
        "allowed_metrics": allowed_metrics,
        "display_options": display_options,
        "ambiguous_terms": ambiguous_terms,
        "conditions": {"out_of_stock": out_of_stock},
        "filters": [],
    }


def check_clarification(question, conversation_history=None):
    """Deterministic check returning 'UNSAFE', 'UNKNOWN', 'CLARIFY', or 'CLEAR'."""
    intent = resolve_semantic_intent(question, conversation_history)
    if intent["status"] == "unsafe":
        return "UNSAFE"
    if intent["status"] == "unknown":
        return "UNKNOWN"
    if intent["needs_clarification"]:
        return "CLARIFY"
    return "CLEAR"


def get_clarification_options(question):
    """Return entity-specific allowed canonical metrics for clarification."""
    intent = resolve_semantic_intent(question)
    return intent.get("allowed_metrics", ["Revenue", "Order Count", "Quantity Sold"])


def clarification_display_options(allowed_metrics):
    """Convert canonical internal metric names to user-friendly presentation display names."""
    return [CANONICAL_TO_DISPLAY.get(metric, metric) for metric in allowed_metrics]


def normalize_clarification_answer(answer, allowed_metrics):
    """Robustly map user selected display option or typed input back to internal canonical metric."""
    if not answer:
        return None
    ans = _normalize_semantic_text(answer)

    # 1. Direct display name lookup
    if ans in DISPLAY_TO_CANONICAL:
        canonical = DISPLAY_TO_CANONICAL[ans]
        if canonical in allowed_metrics:
            return canonical

    # 2. Check canonical and display names
    for metric in allowed_metrics:
        if ans == metric.lower() or ans == f"by {metric.lower()}":
            return metric
        disp = CANONICAL_TO_DISPLAY.get(metric, metric).lower()
        if ans == disp or ans == f"by {disp}":
            return metric

        # 3. Check metric synonyms
        syns = METRIC_SYNONYMS.get(metric, [])
        for synonym in syns:
            s_low = synonym.lower()
            if ans == s_low or ans == f"by {s_low}":
                return metric

    return None


def needs_semantic_layer(question):
    """Return True when semantic understanding helps this question."""
    intent = resolve_semantic_intent(question)
    return bool(
        intent.get("entities")
        or intent.get("metric")
        or intent.get("group_by")
        or intent.get("limit")
        or intent.get("sort_direction")
        or intent.get("conditions", {}).get("out_of_stock")
        or intent.get("ambiguous_terms")
    )


# ---------------------------------------------------------------------------
# 9. SQL GENERATOR CONTEXT
# ---------------------------------------------------------------------------

ESSENTIAL_COLUMNS = {
    "Customers": {"CustomerID", "CompanyName", "ContactName", "City", "Country", "Phone"},
    "Products": {"ProductID", "ProductName", "UnitPrice", "UnitsInStock", "CategoryID", "SupplierID", "Discontinued"},
    "Orders": {"OrderID", "CustomerID", "EmployeeID", "OrderDate", "RequiredDate", "ShippedDate", "Freight", "ShipCountry"},
    "Order Details": {"OrderID", "ProductID", "UnitPrice", "Quantity", "Discount"},
    "Employees": {"EmployeeID", "LastName", "FirstName", "Title", "ReportsTo"},
    "Categories": {"CategoryID", "CategoryName", "Description"},
    "Suppliers": {"SupplierID", "CompanyName", "Country"},
    "Shippers": {"ShipperID", "CompanyName", "Phone"},
    "Territories": {"TerritoryID", "TerritoryDescription", "RegionID"},
    "Regions": {"RegionID", "RegionDescription"},
}


def get_compact_semantic_context(question=None, conversation_history=None):
    """Return compact, deterministic semantic knowledge for the SQL generator."""
    context = get_semantic_context(question)
    if not question:
        return context

    history_text = " ".join(conversation_history) if conversation_history else ""
    full_text = f"{question} {history_text}".strip()
    question_lower = _normalize_semantic_text(full_text)
    intent = resolve_semantic_intent(question, conversation_history)
    relevant_tables = set(intent["entities"])
    if conversation_history:
        for hist in conversation_history:
            for ent in _resolve_entities(hist):
                relevant_tables.add(ent)
    if intent.get("conditions", {}).get("out_of_stock"):
        relevant_tables.add("Products")
    relevant_metrics = {}

    if intent["metric"] in context["metrics"]:
        relevant_metrics[intent["metric"]] = context["metrics"][intent["metric"]]

    # Count-style questions
    count_patterns = ["how many", "number of", "count of", "count", "kitne", "ketla"]
    if any(_phrase_in_text(question_lower, p) for p in count_patterns):
        count_map = {
            "Customers": "Customer Count", "Products": "Product Count",
            "Orders": "Order Count", "Employees": "Employee Count",
            "Suppliers": "Supplier Count", "Categories": "Category Count",
            "Shippers": "Shipper Count", "Territories": "Territory Count",
            "Regions": "Region Count",
        }
        for table, metric_name in count_map.items():
            if table in relevant_tables and metric_name in context["metrics"]:
                relevant_metrics[metric_name] = context["metrics"][metric_name]

    # Add source tables required by metrics
    for metric in relevant_metrics.values():
        source = metric.get("source", "")
        for table_name in context["tables"]:
            if table_name.lower() in source.lower():
                relevant_tables.add(table_name)

    # Revenue/sales metrics require Order Details and Orders
    if intent["metric"] in {"Revenue", "Gross Sales", "Discount Amount", "Quantity Sold", "Average Order Value", "Average Selling Price", "Average Discount"}:
        relevant_tables.add("Order Details")
        if "Customers" in relevant_tables or "Employees" in relevant_tables or "Orders" in relevant_tables or "customer" in question_lower or "employee" in question_lower or "order" in question_lower:
            relevant_tables.add("Orders")

    # Date/geography filters
    if re.search(r"\b(?:order date|ordered|orders in|shipped|ship date|2016|2017|2018|2026)\b", question_lower):
        relevant_tables.add("Orders")
    if re.search(r"\b(?:customer country|customer city|from|in|country|city)\b", question_lower) and "Customers" in relevant_tables:
        relevant_tables.add("Customers")

    if not relevant_tables:
        relevant_tables = {"Customers", "Products", "Orders", "Order Details"}

    # Include FK paths between all relevant tables
    path_tables = set(relevant_tables)
    table_list = list(relevant_tables)
    for i, start_table in enumerate(table_list):
        for end_table in table_list[i + 1:]:
            path = get_relationship_path(start_table, end_table)
            if path:
                path_tables.update(path)
    relevant_tables = path_tables

    compact_tables = {}
    for table_name in sorted(relevant_tables):
        if table_name not in context["tables"]:
            continue
        table_info = context["tables"][table_name]
        essential = ESSENTIAL_COLUMNS.get(table_name, set())
        columns = []
        for column in table_info["columns"]:
            keep = (
                column["primary_key_position"] > 0
                or column["name"] in essential
                or any(fk["from_column"] == column["name"] for fk in table_info["foreign_keys"])
                or _phrase_in_text(question_lower, _normalize_semantic_text(column["name"]))
            )
            for metric in relevant_metrics.values():
                if column["name"] in metric.get("definition", ""):
                    keep = True
            if keep:
                columns.append({
                    "name": column["name"],
                    "type": column["data_type"],
                    "meaning": column["meaning"],
                })

        compact_tables[table_name] = {
            "meaning": table_info["meaning"],
            "columns": columns,
            "foreign_keys": [
                {"from": fk["from_column"], "to_table": fk["to_table"], "to": fk["to_column"]}
                for fk in table_info["foreign_keys"]
                if fk["to_table"] in relevant_tables
            ],
        }

    relevant_relationships = []
    for relationship in context["relationships"]:
        if relationship["from_table"] in relevant_tables and relationship["to_table"] in relevant_tables:
            relevant_relationships.append({
                "from": relationship["from_table"] + "." + relationship["from_column"],
                "to": relationship["to_table"] + "." + relationship["to_column"],
            })

    relevant_business_rules = []
    metric_rule_names = set(relevant_metrics)
    if intent["metric"]:
        metric_rule_names.add(intent["metric"])
    for rule in context["business_rules"]:
        rule_lower = rule.lower()
        keep = False
        if any(name.lower() in rule_lower for name in metric_rule_names):
            keep = True
        if intent["metric"] in {"Revenue", "Gross Sales", "Discount Amount", "Quantity Sold", "Average Order Value", "Average Selling Price", "Average Discount"} and "order details" in rule_lower:
            keep = True
        if "spaces or special characters" in rule_lower or "do not invent" in rule_lower:
            keep = True
        if intent.get("conditions", {}).get("out_of_stock") and "out of stock" in rule_lower:
            keep = True
        if keep and rule not in relevant_business_rules:
            relevant_business_rules.append(rule)

    return {
        "database": {"name": "Northwind SQLite", "dialect": "SQLite"},
        "resolved_intent": intent,
        "tables": compact_tables,
        "relationships": relevant_relationships,
        "metrics": relevant_metrics,
        "business_rules": relevant_business_rules,
    }


def get_sql_generator_context(question, conversation_history=None):
    return {
        "semantic_layer": get_compact_semantic_context(question, conversation_history)
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

