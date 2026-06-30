import sqlite3
from datetime import datetime, date
from pathlib import Path

import pandas as pd
import streamlit as st


DB_PATH = Path("inventory.db")


# -----------------------------
# Basic app config
# -----------------------------
st.set_page_config(
    page_title="Branch Inventory Manager",
    page_icon="📦",
    layout="wide",
)


# -----------------------------
# Authentication
# -----------------------------
def check_password() -> bool:
    """
    Simple single-manager password login.

    Local:
    Create .streamlit/secrets.toml and add:
    APP_PASSWORD = "your-password"

    Streamlit Cloud:
    Add APP_PASSWORD inside App Secrets.

    For first local testing only, fallback password is admin123.
    Change it before real use.
    """
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("Branch Inventory Login")

    password = st.text_input("Manager Password", type="password")
    app_password = st.secrets.get("APP_PASSWORD", "admin123")

    if st.button("Login", width='stretch'):
        if password == app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")
    return False


# -----------------------------
# SQLite helpers
# -----------------------------
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def run_query(query, params=(), fetch=False):
    with get_conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        conn.commit()
        if fetch:
            rows = cur.fetchall()
            return [dict(row) for row in rows]
    return None


def table_columns(table_name: str):
    rows = run_query(f"PRAGMA table_info({table_name})", fetch=True)
    return [row["name"] for row in rows] if rows else []


def ensure_column(table_name: str, column_name: str, column_definition: str):
    """Small SQLite migration helper for local development."""
    cols = table_columns(table_name)
    if column_name not in cols:
        run_query(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")


def init_db():
    with get_conn() as conn:
        cur = conn.cursor()

        cur.execute("""
        CREATE TABLE IF NOT EXISTS branches (
            branch_code TEXT PRIMARY KEY,
            branch_name TEXT NOT NULL,
            active INTEGER DEFAULT 1
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS ingredients (
            ingredient_code TEXT PRIMARY KEY,
            ingredient_name TEXT NOT NULL,
            category TEXT,
            base_unit TEXT NOT NULL,
            min_stock REAL DEFAULT 0,
            source_type TEXT DEFAULT 'Purchased',
            active INTEGER DEFAULT 1
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_bill_header (
            bill_id INTEGER PRIMARY KEY AUTOINCREMENT,
            branch_code TEXT NOT NULL,
            bill_date TEXT NOT NULL,
            supplier_name TEXT,
            invoice_no TEXT,
            total_amount REAL DEFAULT 0,
            note TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY (branch_code) REFERENCES branches(branch_code)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS purchase_bill_lines (
            line_id INTEGER PRIMARY KEY AUTOINCREMENT,
            bill_id INTEGER NOT NULL,
            ingredient_code TEXT NOT NULL,
            qty REAL NOT NULL,
            unit TEXT NOT NULL,
            base_qty REAL NOT NULL,
            total_price REAL DEFAULT 0,
            unit_price REAL DEFAULT 0,
            expiry_date TEXT,
            FOREIGN KEY (bill_id) REFERENCES purchase_bill_header(bill_id),
            FOREIGN KEY (ingredient_code) REFERENCES ingredients(ingredient_code)
        )
        """)

        cur.execute("""
        CREATE TABLE IF NOT EXISTS stock_ledger (
            transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_datetime TEXT NOT NULL,
            branch_code TEXT NOT NULL,
            ingredient_code TEXT NOT NULL,
            movement_type TEXT NOT NULL,
            qty_in REAL DEFAULT 0,
            qty_out REAL DEFAULT 0,
            reference_type TEXT,
            reference_id TEXT,
            note TEXT,
            FOREIGN KEY (branch_code) REFERENCES branches(branch_code),
            FOREIGN KEY (ingredient_code) REFERENCES ingredients(ingredient_code)
        )
        """)

        conn.commit()

    # Safe migrations if you already created an older local inventory.db
    ensure_column("ingredients", "source_type", "TEXT DEFAULT 'Purchased'")
    ensure_column("ingredients", "active", "INTEGER DEFAULT 1")
    ensure_column("branches", "active", "INTEGER DEFAULT 1")

    with get_conn() as conn:
        cur = conn.cursor()

        # Seed branch only if branch table is empty
        cur.execute("SELECT COUNT(*) AS c FROM branches")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                "INSERT INTO branches (branch_code, branch_name, active) VALUES (?, ?, 1)",
                [
                    ("BR001", "Pattambi Branch"),
                ],
            )

        # Seed ingredients only if ingredient table is empty
        cur.execute("SELECT COUNT(*) AS c FROM ingredients")
        if cur.fetchone()["c"] == 0:
            cur.executemany(
                """
                INSERT INTO ingredients
                (ingredient_code, ingredient_name, category, base_unit, min_stock, source_type, active)
                VALUES (?, ?, ?, ?, ?, ?, 1)
                """,
                [
                    ('ING001', 'Almond', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING002', 'Apple', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING003', 'Avocado Pulp', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING004', 'Baby Bun', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING005', 'Banana', 'Fruit', 'pcs', 0, 'Purchased'),
                    ('ING006', 'Beef Keema', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING007', 'Beef Keema Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING008', 'Beef Tawa Patty Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING009', 'Black Pepper Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING010', 'Black Sesame Seed', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING011', 'White Sesame Seed', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING012', 'Blue Ocean Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING013', 'Boiled Semiya Prep', 'Oil / Fat', 'g', 0, 'Produced'),
                    ('ING014', 'Boneless Chicken Frozen', 'Meat / Poultry', 'g', 0, 'Purchased'),
                    ('ING015', 'Boost Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING016', 'Brownie Cake', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING017', 'Bubblegum Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING018', 'Bubbles Prep', 'Beverage Base', 'g', 0, 'Produced'),
                    ('ING019', 'Burger Bun', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING020', 'Butter', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING021', 'Butterscotch Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING022', 'Capsicum Green', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING023', 'Capsicum Red', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING024', 'Capsicum Yellow', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING025', 'Capsicum Mix', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING026', 'Caramel Sauce', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING027', 'Caramel Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING028', 'Caramelized Onion Prep', 'Vegetable / Herb', 'g', 0, 'Produced'),
                    ('ING029', 'Cashew', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING030', 'Cheddar Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING031', 'Cheddar Cheese Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING032', 'Cheesy Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING033', 'Chicken Keema', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING034', 'Chicken Keema Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING035', 'Chicken Momo', 'Meat / Poultry', 'pcs', 0, 'Purchased'),
                    ('ING036', 'Chicken Strips', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING037', 'Chicken Strips Prep', 'Meat / Poultry', 'pcs', 0, 'Produced'),
                    ('ING038', 'Chicken Tawa Patty Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING039', 'Chicken Wings Prep', 'Meat / Poultry', 'pcs', 0, 'Produced'),
                    ('ING040', 'Chicku Pulp', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING041', 'Chilli Flakes', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING042', 'Chipotle Sauce', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING043', 'Chipotle Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING044', 'Chocolate Chips Mix', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING045', 'Chocolate Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING046', 'Chocolate Sauce', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING047', 'Chocolate Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING048', 'Club Bread', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING049', 'Cocktail Powder', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING050', 'Cocktail Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING051', 'Coffee Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING052', 'Cooking Cream', 'Dairy / Cheese', 'ml', 0, 'Purchased'),
                    ('ING053', 'Corn Flour', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING054', 'Cornflakes', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING055', 'Cream Cheese', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING056', 'Cream Cheese Filling Prep', 'Dairy / Cheese', 'g', 0, 'Produced'),
                    ('ING057', 'Cream Sauce', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING058', 'Creamy Momo Prep', 'Dairy / Cheese', 'pcs', 0, 'Produced'),
                    ('ING059', 'Creamy Sauce Prep', 'Produced Prep / Sub Recipe', 'g', 0, 'Produced'),
                    ('ING060', 'Crumbs Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING061', 'Cucumber', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING062', 'Curd', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING063', 'Custard Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING064', 'Custard Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING065', 'Dark Chocolate Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING066', 'Dark Chocolate Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING067', 'Dates', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING068', 'Dry Fruits', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING069', 'Dynamite Momo Prep', 'Other Ingredient', 'pcs', 0, 'Produced'),
                    ('ING070', 'Dynamite Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING071', 'Egg', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING072', 'Frappe Powder', 'Seasoning / Powder', 'spoon', 0, 'Purchased'),
                    ('ING073', 'French Fries Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING074', 'Fresh Cream', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING075', 'Fresh Fruits Prep', 'Fruit', 'g', 0, 'Produced'),
                    ('ING076', 'Fried Egg Prep', 'Other Ingredient', 'pcs', 0, 'Produced'),
                    ('ING077', 'Frozen / Raw Veg Patty', 'Veg Patty / Component', 'pcs', 0, 'Purchased'),
                    ('ING078', 'Frozen Milk Prep', 'Dairy / Cheese', 'g', 0, 'Produced'),
                    ('ING079', 'Frozen Porotta', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING080', 'Frozen Potato Fries', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING081', 'Garlic', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING082', 'Ginger', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING083', 'Grapes', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING084', 'Green Apple Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING085', 'Green Chilli', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING086', 'Green Lettuce', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING087', 'Hazelnut Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING088', 'Hazelnut Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING089', 'Hazelnut Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING090', 'Honey Chilli Momo Prep', 'Vegetable / Herb', 'pcs', 0, 'Produced'),
                    ('ING091', 'Honey Chilli Sauce Base', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING092', 'Honey Chilli Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING093', 'Honey Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING094', 'Hot And Spicy Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING095', 'Ice Cube', 'Water / Ice', 'pcs', 0, 'Purchased'),
                    ('ING096', 'Ice Water', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING097', 'Iceberg Lettuce', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING098', 'Instant Coffee', 'Beverage Base', 'g', 0, 'Purchased'),
                    ('ING099', 'Instant Coffee Sachet', 'Beverage Base', 'pcs', 0, 'Purchased'),
                    ('ING100', 'Irish Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING101', 'Jalapeno', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING102', 'Kanthari Chicken Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING103', 'Kanthari Marinade', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING104', 'Kanthari Momo Prep', 'Other Ingredient', 'pcs', 0, 'Produced'),
                    ('ING105', 'Kanthari Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING106', 'Kaskas', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING107', 'Kinder Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING108', 'Kinder Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING109', 'KitKat', 'Sweetener / Dessert', 'g', 0, 'Purchased'),
                    ('ING110', 'Lemon', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING111', 'Lotus Biscoff Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING112', 'Lotus Biscoff Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING113', 'Lotus Biscuit', 'Sweetener / Dessert', 'pcs', 0, 'Purchased'),
                    ('ING114', 'Mac And Cheese Prep', 'Dairy / Cheese', 'g', 0, 'Produced'),
                    ('ING115', 'Macaroni', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING116', 'Maida', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING117', 'Malai Cream Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING118', 'Mango', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING119', 'Mango Crush', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING120', 'Mango Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING121', 'Mango Passion Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING122', 'Mango Pulp', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING123', 'Masala Tea Mix', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING124', 'Matcha Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING125', 'Milk', 'Dairy / Cheese', 'ml', 0, 'Purchased'),
                    ('ING126', 'Milk Syrup Prep', 'Sauce / Dressing', 'ml', 0, 'Produced'),
                    ('ING127', 'Mint Leaves', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING128', 'Mint Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING129', 'Mosambi', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING130', 'Mozzarella Cheese', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING131', 'Muskmelon', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING132', 'Nashville Chicken Strips Prep', 'Meat / Poultry', 'pcs', 0, 'Produced'),
                    ('ING133', 'Nashville Mix', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING134', 'Nashville Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING135', 'Nashville Powder Prep', 'Seasoning / Powder', 'g', 0, 'Produced'),
                    ('ING136', 'Nutella Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING137', 'Nutella Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING138', 'Onion', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING139', 'Orange', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING140', 'Oregano', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING141', 'Oreo Biscuit', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING142', 'Oreo Garnish', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING143', 'Oreo Packet', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING144', 'Palm Oil', 'Oil / Fat', 'ml', 0, 'Purchased'),
                    ('ING145', 'Paneer', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING146', 'Paneer Momo', 'Dairy / Cheese', 'pcs', 0, 'Purchased'),
                    ('ING147', 'Papaya', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING148', 'Passion Fruit Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING149', 'Peri Peri Chicken Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING150', 'Peri Peri Powder Prep', 'Seasoning / Powder', 'g', 0, 'Produced'),
                    ('ING151', 'Peri Peri Sauce Mix', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING152', 'Peri Peri Sauce Prep', 'Produced Prep / Sub Recipe', 'g', 0, 'Produced'),
                    ('ING153', 'Peri Peri Sprinkles', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING154', 'Pineapple', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING155', 'Pistachio Nuts', 'Sweetener / Dessert', 'g', 0, 'Purchased'),
                    ('ING156', 'Pistachio Powder', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING157', 'Pistachio Sauce', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING158', 'Pistachio Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING159', 'Pitta Pocket', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING160', 'Raw Boneless Beef', 'Meat / Poultry', 'g', 0, 'Purchased'),
                    ('ING161', 'Raw Boneless Chicken', 'Meat / Poultry', 'g', 0, 'Purchased'),
                    ('ING162', 'Raw Chicken Wings', 'Meat / Poultry', 'pcs', 0, 'Purchased'),
                    ('ING163', 'Red Chilli Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING164', 'Red Paprika', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING165', 'Roasted Kunafa', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING166', 'Roasted Kunafa Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING167', 'Rumali Roti', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING168', 'Rusk', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING169', 'Sabja Seeds Dry', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING170', 'Salt', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING171', 'Schezwan Momo Prep', 'Other Ingredient', 'pcs', 0, 'Produced'),
                    ('ING172', 'Schezwan Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING173', 'Schezwan Sauce Prep', 'Produced Prep / Sub Recipe', 'g', 0, 'Produced'),
                    ('ING174', 'Semiya Dry', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING175', 'Vanilla Cake Slice', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING176', 'Smash Beef Patty Prep', 'Meat / Poultry', 'g', 0, 'Produced'),
                    ('ING177', 'Soaked Sabja Seeds Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING178', 'Spanish Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING179', 'Spicy Mayonnaise Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING180', 'Spring Onion', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING181', 'Sprite', 'Other Ingredient', 'ml', 0, 'Purchased'),
                    ('ING182', 'Strawberry', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING183', 'Strawberry Crush', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING184', 'Strawberry Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING185', 'Strawberry Pulp', 'Fruit', 'g', 0, 'Purchased'),
                    ('ING186', 'Strawberry Sauce', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING187', 'Strawberry Slice', 'Fruit', 'pcs', 0, 'Purchased'),
                    ('ING188', 'Sugar', 'Sweetener / Dessert', 'g', 0, 'Purchased'),
                    ('ING189', 'Sugar Syrup Prep', 'Sauce / Dressing', 'ml', 0, 'Produced'),
                    ('ING190', 'Taro Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING191', 'Tea Decoction Prep', 'Beverage Base', 'g', 0, 'Produced'),
                    ('ING192', 'Signature Tea Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING193', 'Tender Coconut Pulp', 'Meat / Poultry', 'g', 0, 'Purchased'),
                    ('ING194', 'Thai Tea Powder', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING195', 'Thousand Island', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING196', 'Tomato', 'Vegetable / Herb', 'g', 0, 'Purchased'),
                    ('ING197', 'Tomato Ketchup', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING198', 'Tortilla Wrap', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING199', 'Vanilla Cake', 'Bakery / Bread', 'pcs', 0, 'Purchased'),
                    ('ING200', 'Slice Cheese', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING201', 'Vanilla Ice Cream', 'Dairy / Cheese', 'scoop', 0, 'Purchased'),
                    ('ING202', 'Veg Momo', 'Other Ingredient', 'pcs', 0, 'Purchased'),
                    ('ING203', 'Veg Patty Prep', 'Veg Patty / Fried Prep', 'pcs', 0, 'Produced'),
                    ('ING204', 'Water', 'Water / Ice', 'ml', 0, 'Purchased'),
                    ('ING205', 'Watermelon', 'Fruit', 'ml', 0, 'Purchased'),
                    ('ING206', 'Watermelon Syrup', 'Sauce / Dressing', 'ml', 0, 'Purchased'),
                    ('ING207', 'Whipped Cream', 'Dairy / Cheese', 'g', 0, 'Purchased'),
                    ('ING208', 'Whipped Cream Prep', 'Dairy / Cheese', 'g', 0, 'Produced'),
                    ('ING209', 'White Chocolate Sauce', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING210', 'White Chocolate Sauce Prep', 'Sauce / Dressing', 'g', 0, 'Produced'),
                    ('ING211', 'White Eggless Mayonnaise', 'Other Ingredient', 'g', 0, 'Purchased'),
                    ('ING212', 'White Mayonnaise', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING213', 'White Sauce Mix', 'Sauce / Dressing', 'g', 0, 'Purchased'),
                    ('ING214', 'Tapioca Boba Pearls', 'Beverage Base', 'g', 0, 'Purchased'),
                    ('ING215', 'Schezwan Chicken Momo Prep', 'Momos', 'pcs', 0, 'Produced'),
                    ('ING216', 'Honey Chilli Chicken Momo Prep', 'Momos', 'pcs', 0, 'Produced'),
                    ('ING217', 'Kanthari Chicken Momo Prep', 'Momos', 'pcs', 0, 'Produced'),
                    ('ING218', 'Dynamite Chicken Momo Prep', 'Momos', 'pcs', 0, 'Produced'),
                    ('ING219', 'Creamy Chicken Momo Prep', 'Momos', 'pcs', 0, 'Produced'),
                    ('ING220', 'Toned Milk', 'Dairy / Cheese', 'ml', 0, 'Purchased'),
                    ('ING221', 'Tea Powder Prep', 'Seasoning / Powder', 'g', 0, 'Produced'),
                    ('ING222', 'Tea Powder - AVT', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING223', 'Tea Powder - RED LABEL', 'Seasoning / Powder', 'g', 0, 'Purchased'),
                    ('ING224', 'Mini Zinger Burger Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING225', 'Mini Chicken Tawa Burger Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING226', 'Mini Smash Beef Burger Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING227', 'Mini Zinger Cheese Blast Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING228', 'Mini Chicken Tawa Cheese Blast Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING229', 'Mini Beef Burger Prep', 'Burger / Mini Bites', 'pcs', 0, 'Produced'),
                    ('ING230', 'Almond Garnish Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING231', 'KitKat Garnish Prep', 'Other Ingredient', 'pcs', 0, 'Produced'),
                    ('ING232', 'Cashew Garnish Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING233', 'Pistachio And Almond Mix Prep', 'Other Ingredient', 'g', 0, 'Produced'),
                    ('ING234', 'Lotus Biscoff Garnish Prep', 'Seasoning / Powder', 'pcs', 0, 'Produced'),
                ]
            )

        conn.commit()


def df_query(query, params=()):
    with get_conn() as conn:
        return pd.read_sql_query(query, conn, params=params)


def get_branches():
    return df_query(
        """
        SELECT branch_code, branch_name
        FROM branches
        WHERE active = 1
        ORDER BY branch_code
        """
    )


def get_ingredients():
    return df_query(
        """
        SELECT
            ingredient_code,
            ingredient_name,
            category,
            base_unit,
            min_stock,
            COALESCE(source_type, 'Purchased') AS source_type
        FROM ingredients
        WHERE active = 1
        ORDER BY ingredient_name
        """
    )


def get_current_stock(branch_code):
    return df_query(
        """
        SELECT
            i.ingredient_code,
            i.ingredient_name,
            i.category,
            i.base_unit,
            i.min_stock,
            ROUND(COALESCE(SUM(sl.qty_in - sl.qty_out), 0), 3) AS current_qty,
            CASE
                WHEN ROUND(COALESCE(SUM(sl.qty_in - sl.qty_out), 0), 3) <= 0 THEN 'Out of Stock'
                WHEN ROUND(COALESCE(SUM(sl.qty_in - sl.qty_out), 0), 3) < COALESCE(i.min_stock, 0) THEN 'Low'
                ELSE 'OK'
            END AS status
        FROM ingredients i
        LEFT JOIN stock_ledger sl
            ON i.ingredient_code = sl.ingredient_code
            AND sl.branch_code = ?
        WHERE i.active = 1
        GROUP BY
            i.ingredient_code,
            i.ingredient_name,
            i.category,
            i.base_unit,
            i.min_stock
        ORDER BY i.ingredient_name
        """,
        (branch_code,),
    )


def get_stock_qty(branch_code, ingredient_code):
    rows = run_query(
        """
        SELECT ROUND(COALESCE(SUM(qty_in - qty_out), 0), 6) AS qty
        FROM stock_ledger
        WHERE branch_code = ? AND ingredient_code = ?
        """,
        (branch_code, ingredient_code),
        fetch=True,
    )
    return float(rows[0]["qty"] or 0)


def add_stock_ledger(
    branch_code,
    ingredient_code,
    movement_type,
    qty_in,
    qty_out,
    reference_type=None,
    reference_id=None,
    note=None,
):
    run_query(
        """
        INSERT INTO stock_ledger
        (transaction_datetime, branch_code, ingredient_code, movement_type, qty_in, qty_out, reference_type, reference_id, note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            datetime.now().isoformat(timespec="seconds"),
            branch_code,
            ingredient_code,
            movement_type,
            float(qty_in or 0),
            float(qty_out or 0),
            reference_type,
            str(reference_id) if reference_id is not None else None,
            note,
        ),
    )


# -----------------------------
# UI helpers
# -----------------------------
def section_title(title, caption=None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def branch_selector():
    branches = get_branches()
    if branches.empty:
        st.error("No active branches found. Add a branch first.")
        st.stop()

    labels = {
        row["branch_code"]: f'{row["branch_code"]} - {row["branch_name"]}'
        for _, row in branches.iterrows()
    }

    selected = st.sidebar.selectbox(
        "Select Branch",
        options=list(labels.keys()),
        format_func=lambda x: labels[x],
    )
    return selected


def ingredient_options_with_units(ingredients: pd.DataFrame):
    labels = {}
    for _, row in ingredients.iterrows():
        label = f'{row["ingredient_code"]} - {row["ingredient_name"]} ({row["base_unit"]})'
        labels[label] = row
    return labels


# -----------------------------
# Pages
# -----------------------------
def page_dashboard(branch_code):
    section_title("Dashboard", "Quick stock status for the selected branch.")

    stock = get_current_stock(branch_code)

    total_items = len(stock)
    low_items = int((stock["status"] == "Low").sum())
    out_items = int((stock["status"] == "Out of Stock").sum())

    c1, c2, c3 = st.columns(3)
    c1.metric("Total Items", total_items)
    c2.metric("Low Stock Items", low_items)
    c3.metric("Out of Stock Items", out_items)

    st.divider()

    st.write("### Low / Out of Stock Items")
    problem = stock[stock["status"].isin(["Low", "Out of Stock"])]
    if problem.empty:
        st.success("No low-stock items for this branch.")
    else:
        st.dataframe(problem, width='stretch', hide_index=True)

    st.write("### Latest Stock Movements")
    latest = df_query(
        """
        SELECT
            sl.transaction_datetime,
            sl.branch_code,
            i.ingredient_name,
            sl.movement_type,
            sl.qty_in,
            sl.qty_out,
            sl.reference_type,
            sl.reference_id,
            sl.note
        FROM stock_ledger sl
        JOIN ingredients i ON i.ingredient_code = sl.ingredient_code
        WHERE sl.branch_code = ?
        ORDER BY sl.transaction_id DESC
        LIMIT 20
        """,
        (branch_code,),
    )
    st.dataframe(latest, width='stretch', hide_index=True)


def page_master_data():
    section_title(
        "Master Data",
        "Add branches and ingredients. Keep this clean because all stock depends on it.",
    )

    tab1, tab2 = st.tabs(["Branches", "Ingredients"])

    with tab1:
        st.write("### Add Branch")
        with st.form("add_branch_form"):
            branch_code = st.text_input("Branch Code", placeholder="BR002").strip().upper()
            branch_name = st.text_input("Branch Name", placeholder="New Branch").strip()
            submitted = st.form_submit_button("Add Branch", width='stretch')

        if submitted:
            if not branch_code or not branch_name:
                st.error("Branch code and branch name are required.")
            else:
                try:
                    run_query(
                        "INSERT INTO branches (branch_code, branch_name, active) VALUES (?, ?, 1)",
                        (branch_code, branch_name),
                    )
                    st.success("Branch added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This branch code already exists.")

        st.write("### Existing Branches")
        st.dataframe(get_branches(), width='stretch', hide_index=True)

    with tab2:
        st.write("### Add Ingredient")
        with st.form("add_ingredient_form"):
            ingredient_code = st.text_input("Ingredient Code", placeholder="ING011").strip().upper()
            ingredient_name = st.text_input("Ingredient Name", placeholder="Tomato").strip().title()
            category = st.text_input("Category", placeholder="Vegetable").strip().title()
            base_unit = st.selectbox("Base Unit", ["g", "kg", "ml", "L", "piece", "pack"])
            min_stock = st.number_input("Minimum Stock", min_value=0.0, step=0.1)
            source_type = st.selectbox("Source Type", ["Purchased", "Produced / Prepared", "Both"])
            submitted = st.form_submit_button("Add Ingredient", width='stretch')

        if submitted:
            if not ingredient_code or not ingredient_name:
                st.error("Ingredient code and ingredient name are required.")
            else:
                try:
                    run_query(
                        """
                        INSERT INTO ingredients
                        (ingredient_code, ingredient_name, category, base_unit, min_stock, source_type, active)
                        VALUES (?, ?, ?, ?, ?, ?, 1)
                        """,
                        (ingredient_code, ingredient_name, category, base_unit, min_stock, source_type),
                    )
                    st.success("Ingredient added.")
                    st.rerun()
                except sqlite3.IntegrityError:
                    st.error("This ingredient code already exists.")

        st.write("### Existing Ingredients")
        st.dataframe(get_ingredients(), width='stretch', hide_index=True)

def page_add_purchase(branch_code):
    section_title(
        "Add Purchase Bill",
        "Enter supplier bill lines. Each saved line automatically increases stock.",
    )

    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("Add ingredients first.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)

    # This is used to clear the form after saving.
    # After each successful save, we increase this number and rerun the page.
    if "purchase_form_version" not in st.session_state:
        st.session_state.purchase_form_version = 0

    form_version = st.session_state.purchase_form_version

    with st.form(f"purchase_form_{form_version}"):
        c1, c2, c3 = st.columns(3)

        bill_date = c1.date_input(
            "Bill Date",
            value=date.today(),
            key=f"bill_date_{form_version}",
        )

        supplier_name = c2.text_input(
            "Supplier Name",
            placeholder="We5 Mansoor Traders",
            key=f"supplier_name_{form_version}",
        )

        invoice_no = c3.text_input(
            "Invoice Number",
            placeholder="Bill number",
            key=f"invoice_no_{form_version}",
        )

        note = st.text_area(
            "Bill Note",
            placeholder="Optional note",
            key=f"bill_note_{form_version}",
        )

        st.write("### Bill Lines")
        st.caption(
            "Quantity must be entered in the ingredient base unit shown in brackets. "
            "Example: if Chicken is stored as g, enter 6400 for 6.4 kg."
        )

        first_ingredient = list(ingredient_labels.keys())[0]

        default_lines = pd.DataFrame(
            [
                {
                    "Ingredient": first_ingredient,
                    "Quantity In Base Unit": 0.0,
                    "Total Price": 0.0,
                    "Expiry Date": None,
                }
            ]
        )

        edited = st.data_editor(
            default_lines,
            num_rows="dynamic",
            width='stretch',
            key=f"purchase_lines_editor_{form_version}",
            column_config={
                "Ingredient": st.column_config.SelectboxColumn(
                    "Ingredient",
                    options=list(ingredient_labels.keys()),
                    required=True,
                ),
                "Quantity In Base Unit": st.column_config.NumberColumn(
                    "Quantity In Base Unit",
                    min_value=0.0,
                    step=1.0,
                    required=True,
                ),
                "Total Price": st.column_config.NumberColumn(
                    "Total Price",
                    min_value=0.0,
                    step=1.0,
                ),
                "Expiry Date": st.column_config.DateColumn(
                    "Expiry Date",
                    help="Optional expiry date",
                    format="DD/MM/YYYY",
                ),
            },
            hide_index=True,
        )

        submitted = st.form_submit_button(
            "Save Purchase Bill",
            width='stretch',
        )

    if submitted:
        valid_lines = edited[
            (edited["Quantity In Base Unit"] > 0) & (edited["Ingredient"].notna())
        ].copy()

        if valid_lines.empty:
            st.error("Add at least one valid bill line with quantity greater than zero.")
            return

        total_amount = float(valid_lines["Total Price"].fillna(0).sum())

        with get_conn() as conn:
            cur = conn.cursor()

            cur.execute(
                """
                INSERT INTO purchase_bill_header
                (branch_code, bill_date, supplier_name, invoice_no, total_amount, note, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    branch_code,
                    bill_date.isoformat(),
                    supplier_name,
                    invoice_no,
                    total_amount,
                    note,
                    datetime.now().isoformat(timespec="seconds"),
                ),
            )

            bill_id = cur.lastrowid

            for _, line in valid_lines.iterrows():
                selected_row = ingredient_labels[line["Ingredient"]]

                ingredient_code = selected_row["ingredient_code"]
                base_unit = selected_row["base_unit"]

                base_qty = float(line["Quantity In Base Unit"])
                total_price = float(line["Total Price"] or 0)
                unit_price = total_price / base_qty if base_qty else 0

                raw_expiry_date = line.get("Expiry Date")

                if pd.isna(raw_expiry_date) or raw_expiry_date is None:
                    expiry_date = ""
                else:
                    expiry_date = pd.to_datetime(raw_expiry_date).date().isoformat()

                cur.execute(
                    """
                    INSERT INTO purchase_bill_lines
                    (bill_id, ingredient_code, qty, unit, base_qty, total_price, unit_price, expiry_date)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        bill_id,
                        ingredient_code,
                        base_qty,
                        base_unit,
                        base_qty,
                        total_price,
                        unit_price,
                        expiry_date,
                    ),
                )

                cur.execute(
                    """
                    INSERT INTO stock_ledger
                    (transaction_datetime, branch_code, ingredient_code, movement_type, qty_in, qty_out, reference_type, reference_id, note)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        branch_code,
                        ingredient_code,
                        "Purchase",
                        base_qty,
                        0,
                        "Purchase Bill",
                        str(bill_id),
                        f"Invoice: {invoice_no}, Supplier: {supplier_name}",
                    ),
                )

            conn.commit()

        st.success(f"Purchase bill saved. Bill ID: {bill_id}")

        # This clears all previously entered form data.
        st.session_state.purchase_form_version += 1

        # Refresh page so the form becomes blank again.
        st.rerun()


def page_stock_count(branch_code):
    section_title(
        "Opening / Physical Stock Count",
        "Use this before opening or during stock checking. It records only the difference.",
    )

    stock = get_current_stock(branch_code)

    if stock.empty:
        st.warning("No ingredients found.")
        return

    count_df = stock[["ingredient_code", "ingredient_name", "base_unit", "current_qty"]].copy()
    count_df["physical_qty"] = count_df["current_qty"]
    count_df["reason"] = ""

    edited = st.data_editor(
        count_df,
        width='stretch',
        hide_index=True,
        column_config={
            "ingredient_code": st.column_config.TextColumn("Code", disabled=True),
            "ingredient_name": st.column_config.TextColumn("Ingredient", disabled=True),
            "base_unit": st.column_config.TextColumn("Unit", disabled=True),
            "current_qty": st.column_config.NumberColumn("System Stock", disabled=True),
            "physical_qty": st.column_config.NumberColumn("Physical Count", min_value=0.0, step=1.0),
            "reason": st.column_config.TextColumn("Reason / Note"),
        },
    )

    if st.button("Save Stock Count Differences", width='stretch'):
        changes = 0

        for _, row in edited.iterrows():
            system_qty = float(row["current_qty"] or 0)
            physical_qty = float(row["physical_qty"] or 0)
            diff = round(physical_qty - system_qty, 6)

            if abs(diff) > 0.000001:
                if diff > 0:
                    add_stock_ledger(
                        branch_code,
                        row["ingredient_code"],
                        "Physical Count Adjustment In",
                        diff,
                        0,
                        "Stock Count",
                        date.today().isoformat(),
                        row["reason"],
                    )
                else:
                    add_stock_ledger(
                        branch_code,
                        row["ingredient_code"],
                        "Physical Count Adjustment Out",
                        0,
                        abs(diff),
                        "Stock Count",
                        date.today().isoformat(),
                        row["reason"],
                    )
                changes += 1

        st.success(f"Saved {changes} stock count difference(s).")
        st.rerun()


def page_adjustment(branch_code):
    section_title(
        "Stock Adjustment",
        "Use this for wastage, correction, staff meal, transfer in/out, or other manual movement.",
    )

    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("Add ingredients first.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)

    with st.form("adjustment_form"):
        movement_type = st.selectbox(
            "Movement Type",
            [
                "Wastage",
                "Correction In",
                "Correction Out",
                "Transfer In",
                "Transfer Out",
                "Staff Meal",
                "Sample / Testing",
                "Other In",
                "Other Out",
            ],
        )
        selected_ingredient = st.selectbox("Ingredient", list(ingredient_labels.keys()))
        qty = st.number_input("Quantity In Base Unit", min_value=0.0, step=1.0)
        note = st.text_area(
            "Reason / Note",
            placeholder="Example: spoiled, branch transfer, wrong count correction",
        )
        submitted = st.form_submit_button("Save Adjustment", width='stretch')

    if submitted:
        if qty <= 0:
            st.error("Quantity must be greater than zero.")
            return

        ingredient_code = ingredient_labels[selected_ingredient]["ingredient_code"]

        in_types = ["Correction In", "Transfer In", "Other In"]
        if movement_type in in_types:
            qty_in, qty_out = qty, 0
        else:
            qty_in, qty_out = 0, qty

        current_qty = get_stock_qty(branch_code, ingredient_code)
        if qty_out > 0 and qty_out > current_qty:
            st.warning(
                f"This adjustment will make stock negative. Current stock is {current_qty}, "
                f"but you are reducing {qty_out}."
            )

        add_stock_ledger(
            branch_code,
            ingredient_code,
            movement_type,
            qty_in,
            qty_out,
            "Manual Adjustment",
            date.today().isoformat(),
            note,
        )

        st.success("Adjustment saved.")
        st.rerun()


def page_current_stock(branch_code):
    section_title("Current Stock", "Calculated from stock ledger, not manually stored.")

    stock = get_current_stock(branch_code)

    status_filter = st.multiselect(
        "Filter Status",
        options=["OK", "Low", "Out of Stock"],
        default=["OK", "Low", "Out of Stock"],
    )
    filtered = stock[stock["status"].isin(status_filter)]

    st.dataframe(filtered, width='stretch', hide_index=True)

    csv = filtered.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Current Stock CSV",
        data=csv,
        file_name=f"current_stock_{branch_code}.csv",
        mime="text/csv",
        width='stretch',
    )


def page_reports(branch_code):
    section_title("Reports", "Basic local reports from SQLite.")

    report = st.selectbox(
        "Choose Report",
        ["Stock Ledger", "Purchase Bills", "Purchase Bill Lines", "Supplier Price History"],
    )

    if report == "Stock Ledger":
        df = df_query(
            """
            SELECT
                sl.transaction_id,
                sl.transaction_datetime,
                sl.branch_code,
                i.ingredient_name,
                sl.movement_type,
                sl.qty_in,
                sl.qty_out,
                sl.reference_type,
                sl.reference_id,
                sl.note
            FROM stock_ledger sl
            JOIN ingredients i ON i.ingredient_code = sl.ingredient_code
            WHERE sl.branch_code = ?
            ORDER BY sl.transaction_id DESC
            """,
            (branch_code,),
        )

    elif report == "Purchase Bills":
        df = df_query(
            """
            SELECT *
            FROM purchase_bill_header
            WHERE branch_code = ?
            ORDER BY bill_id DESC
            """,
            (branch_code,),
        )

    elif report == "Purchase Bill Lines":
        df = df_query(
            """
            SELECT
                h.bill_id,
                h.branch_code,
                h.bill_date,
                h.supplier_name,
                h.invoice_no,
                i.ingredient_name,
                l.qty,
                l.unit,
                l.base_qty,
                l.total_price,
                l.unit_price,
                l.expiry_date
            FROM purchase_bill_lines l
            JOIN purchase_bill_header h ON h.bill_id = l.bill_id
            JOIN ingredients i ON i.ingredient_code = l.ingredient_code
            WHERE h.branch_code = ?
            ORDER BY h.bill_id DESC, l.line_id
            """,
            (branch_code,),
        )

    else:
        df = df_query(
            """
            SELECT
                h.bill_date,
                h.supplier_name,
                h.invoice_no,
                i.ingredient_name,
                l.base_qty,
                i.base_unit,
                l.total_price,
                ROUND(l.unit_price, 3) AS unit_price
            FROM purchase_bill_lines l
            JOIN purchase_bill_header h ON h.bill_id = l.bill_id
            JOIN ingredients i ON i.ingredient_code = l.ingredient_code
            WHERE h.branch_code = ?
            ORDER BY i.ingredient_name, h.bill_date DESC
            """,
            (branch_code,),
        )

    st.dataframe(df, width='stretch', hide_index=True)

    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download Report CSV",
        data=csv,
        file_name=f"{report.lower().replace(' ', '_')}_{branch_code}.csv",
        mime="text/csv",
        width='stretch',
    )


# -----------------------------
# Main app
# -----------------------------
def main():
    init_db()

    if not check_password():
        return

    st.sidebar.title("📦 Inventory")
    branch_code = branch_selector()

    page = st.sidebar.radio(
        "Menu",
        [
            "Dashboard",
            "Add Purchase Bill",
            "Opening / Stock Count",
            "Stock Adjustment",
            "Current Stock",
            "Reports",
            "Master Data",
        ],
    )

    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        st.session_state.authenticated = False
        st.rerun()

    st.title("Branch Inventory Manager")
    st.caption(f"Selected branch: {branch_code}")

    if page == "Dashboard":
        page_dashboard(branch_code)
    elif page == "Add Purchase Bill":
        page_add_purchase(branch_code)
    elif page == "Opening / Stock Count":
        page_stock_count(branch_code)
    elif page == "Stock Adjustment":
        page_adjustment(branch_code)
    elif page == "Current Stock":
        page_current_stock(branch_code)
    elif page == "Reports":
        page_reports(branch_code)
    elif page == "Master Data":
        page_master_data()


if __name__ == "__main__":
    main()
