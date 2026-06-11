"""Self-contained "ecommerce" benchmark: a real SQLite DB + gold SQL.

An online-store schema (customer / product / orders / order_item) in the Spider
style, bundled directly in code so the live server needs no external,
license-bound data download. Every gold query below executes against the
database built by :func:`build_db`, so scores are real execution-match scores.

Train and test share PATTERNS (JOIN, GROUP BY/HAVING, ORDER BY+LIMIT, subquery)
with DIFFERENT questions, so a fix learned from a train failure can generalize
to the held-out test split.
"""
from __future__ import annotations

import os
import sqlite3
import tempfile

from crucible.types import EvalItem

DB_ID = "ecommerce"

SCHEMA = """
CREATE TABLE customer (
    customer_id INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    city        TEXT NOT NULL,
    country     TEXT NOT NULL
);
CREATE TABLE product (
    product_id  INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT NOT NULL,
    price       REAL NOT NULL
);
CREATE TABLE orders (
    order_id    INTEGER PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customer(customer_id),
    order_date  TEXT NOT NULL,
    status      TEXT NOT NULL
);
CREATE TABLE order_item (
    order_id    INTEGER NOT NULL REFERENCES orders(order_id),
    product_id  INTEGER NOT NULL REFERENCES product(product_id),
    quantity    INTEGER NOT NULL
);
"""

_CUSTOMERS = [
    (1, "Lena Park", "Seoul", "South Korea"),
    (2, "Omar Haddad", "Cairo", "Egypt"),
    (3, "Priya Nair", "Mumbai", "India"),
    (4, "Sven Olsen", "Oslo", "Norway"),
    (5, "Diego Marin", "Madrid", "Spain"),
    (6, "Grace Kim", "Seoul", "South Korea"),
]

_PRODUCTS = [
    (1, "Wireless Mouse", "Electronics", 25.50),
    (2, "Mechanical Keyboard", "Electronics", 89.00),
    (3, "Coffee Mug", "Home", 12.00),
    (4, "Desk Lamp", "Home", 34.99),
    (5, "Notebook", "Stationery", 4.50),
    (6, "USB-C Cable", "Electronics", 9.99),
]

_ORDERS = [
    (1, 1, "2025-01-05", "shipped"),
    (2, 1, "2025-02-11", "shipped"),
    (3, 2, "2025-02-14", "pending"),
    (4, 3, "2025-03-02", "shipped"),
    (5, 3, "2025-03-20", "cancelled"),
    (6, 4, "2025-04-01", "shipped"),
    (7, 5, "2025-04-15", "pending"),
    (8, 1, "2025-05-09", "shipped"),
]

_ORDER_ITEMS = [
    (1, 1, 2), (1, 6, 1), (2, 2, 1), (3, 3, 4),
    (4, 4, 1), (4, 5, 3), (5, 2, 1), (6, 1, 1),
    (6, 3, 2), (7, 5, 5), (8, 6, 2), (8, 2, 1),
]

TRAIN: list[EvalItem] = [
    EvalItem("How many customers are there?",
             "SELECT count(*) FROM customer", DB_ID, "easy"),
    EvalItem("List the names of products in the Electronics category.",
             "SELECT name FROM product WHERE category='Electronics'", DB_ID, "easy"),
    # JOIN pattern
    EvalItem("Show each order id along with the name of the customer who placed it.",
             "SELECT orders.order_id, customer.name FROM orders "
             "JOIN customer ON orders.customer_id=customer.customer_id", DB_ID, "medium"),
    # GROUP BY pattern
    EvalItem("How many orders does each customer have? Return the customer id and the count.",
             "SELECT customer_id, count(*) FROM orders GROUP BY customer_id", DB_ID, "medium"),
    # GROUP BY + HAVING pattern
    EvalItem("Which customers have placed more than one order? Return the customer name.",
             "SELECT customer.name FROM orders "
             "JOIN customer ON orders.customer_id=customer.customer_id "
             "GROUP BY customer.customer_id HAVING count(*) > 1", DB_ID, "hard"),
    # ORDER BY + LIMIT pattern
    EvalItem("What is the name of the most expensive product?",
             "SELECT name FROM product ORDER BY price DESC LIMIT 1", DB_ID, "hard"),
    # subquery pattern
    EvalItem("List the names of products priced above the average product price.",
             "SELECT name FROM product WHERE price > (SELECT avg(price) FROM product)",
             DB_ID, "hard"),
    # JOIN across order_item pattern
    EvalItem("List the names of products that appear in order 1.",
             "SELECT product.name FROM product "
             "JOIN order_item ON product.product_id=order_item.product_id "
             "WHERE order_item.order_id=1", DB_ID, "hard"),
]

TEST: list[EvalItem] = [  # held-out: same patterns, different questions
    EvalItem("How many products are there?",
             "SELECT count(*) FROM product", DB_ID, "easy"),
    # JOIN pattern (order_item -> product)
    EvalItem("Show each order id along with the name of a product it contains.",
             "SELECT order_item.order_id, product.name FROM order_item "
             "JOIN product ON order_item.product_id=product.product_id", DB_ID, "medium"),
    # GROUP BY + HAVING pattern (customers per city)
    EvalItem("Which cities have more than one customer? Return the city.",
             "SELECT city FROM customer GROUP BY city HAVING count(*) > 1",
             DB_ID, "hard"),
    # ORDER BY + LIMIT pattern (cheapest product)
    EvalItem("What is the name of the cheapest product?",
             "SELECT name FROM product ORDER BY price ASC LIMIT 1", DB_ID, "hard"),
    # subquery pattern (products below average price)
    EvalItem("List the names of products priced below the average product price.",
             "SELECT name FROM product WHERE price < (SELECT avg(price) FROM product)",
             DB_ID, "hard"),
]


def build_db(target_dir: str | None = None) -> str:
    """Create and populate the bundled ecommerce SQLite DB; return its path."""
    directory = target_dir or tempfile.mkdtemp(prefix="crucible_ecommerce_")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, "ecommerce.sqlite")
    con = sqlite3.connect(path)
    try:
        con.executescript(SCHEMA)
        con.executemany("INSERT INTO customer VALUES (?,?,?,?)", _CUSTOMERS)
        con.executemany("INSERT INTO product VALUES (?,?,?,?)", _PRODUCTS)
        con.executemany("INSERT INTO orders VALUES (?,?,?,?)", _ORDERS)
        con.executemany("INSERT INTO order_item VALUES (?,?,?)", _ORDER_ITEMS)
        con.commit()
    finally:
        con.close()
    return path
