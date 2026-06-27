# -*- coding: utf-8 -*-
"""
BargainBot - database.py
SQLite database helpers using prices.db
"""

import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "prices.db")


def get_db_connection():
    """Returns a sqlite3 connection with row_factory set."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Creates all 3 tables if they do not already exist."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            name       TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            platform     TEXT,
            price        INTEGER,
            timestamp    TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            email        TEXT,
            target_price INTEGER,
            created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_sent      INTEGER DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()
    print("[DB] Tables initialized successfully.")


def save_price(product_name: str, platform: str, price: int):
    """Saves a price record and ensures the product exists in products table."""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Upsert into products table
    cursor.execute(
        "INSERT OR IGNORE INTO products (name) VALUES (?)",
        (product_name,)
    )

    # Insert price record
    cursor.execute(
        "INSERT INTO prices (product_name, platform, price) VALUES (?, ?, ?)",
        (product_name, platform, int(price))
    )

    conn.commit()
    conn.close()


def get_history(product_name: str) -> list:
    """Returns last 30 days of price records for a product, all platforms."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_name, platform, price, timestamp
        FROM prices
        WHERE product_name = ?
          AND timestamp >= datetime('now', '-30 days')
        ORDER BY timestamp ASC
    """, (product_name,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def get_full_history(product_name: str) -> list:
    """Returns ALL scraped price records for a product (no time limit).
    Used to build real analytics and the monthly price trend chart.
    Returns rows with keys: product_name, platform, price, timestamp.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT product_name, platform, price, timestamp
        FROM prices
        WHERE product_name = ?
        ORDER BY timestamp ASC
    """, (product_name,))

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def save_alert(product_name: str, email: str, target_price: int):
    """Saves a new price alert."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "INSERT INTO alerts (product_name, email, target_price) VALUES (?, ?, ?)",
        (product_name, email, int(target_price))
    )

    conn.commit()
    conn.close()


def get_all_alerts() -> list:
    """Returns all active (unsent) alerts."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM alerts WHERE is_sent = 0"
    )

    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows


def mark_alert_sent(alert_id: int):
    """Marks an alert as sent so it does not fire again."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "UPDATE alerts SET is_sent = 1 WHERE id = ?",
        (alert_id,)
    )

    conn.commit()
    conn.close()


def get_latest_price(product_name: str) -> dict:
    """Returns the most recent price per platform for a product."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT platform, price
        FROM prices
        WHERE product_name = ?
          AND (platform, timestamp) IN (
              SELECT platform, MAX(timestamp)
              FROM prices
              WHERE product_name = ?
              GROUP BY platform
          )
    """, (product_name, product_name))

    rows = {row["platform"]: row["price"] for row in cursor.fetchall()}
    conn.close()
    return rows


def get_all_tracked_products() -> list:
    """Returns all unique product names that have at least one price record."""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT DISTINCT product_name FROM prices"
    )

    names = [row["product_name"] for row in cursor.fetchall()]
    conn.close()
    return names
