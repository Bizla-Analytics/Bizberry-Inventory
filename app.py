from __future__ import annotations

from datetime import datetime, date, time
from typing import Dict, List, Tuple, Set

import pandas as pd
import streamlit as st
from supabase import Client, create_client


# -----------------------------
# Basic app config
# -----------------------------
st.set_page_config(
    page_title="Branch Inventory Manager",
    page_icon="📦",
    layout="wide",
)


# -----------------------------
# Supabase connection
# -----------------------------
@st.cache_resource
def get_supabase_client() -> Client:
    """
    Required Streamlit secrets:

    SUPABASE_URL = "https://your-project-id.supabase.co"

    Recommended for this private manager app:
    SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

    Fallback:
    SUPABASE_ANON_KEY = "your-anon-key"

    Note:
    If RLS is enabled and you use only SUPABASE_ANON_KEY without policies,
    Supabase may return empty tables even when data exists. For this server-side
    Streamlit app, the service role key can be kept inside Streamlit secrets.
    Never expose it in frontend code or public files.
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets.get("SUPABASE_SERVICE_ROLE_KEY") or st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def supabase_result_to_df(result) -> pd.DataFrame:
    """Safely convert Supabase result data to DataFrame."""
    if not result or not getattr(result, "data", None):
        return pd.DataFrame()
    return pd.DataFrame(result.data)


# -----------------------------
# Authentication
# -----------------------------
def load_branch_users() -> Dict[str, Dict[str, str]]:
    """
    Read manager users from Streamlit secrets.

    Recommended secrets.toml format:

    [BRANCH_USERS.br001_manager]
    password = "manager-password"
    branch_code = "BR001"
    display_name = "Pattambi Manager"

    Also supported as fallback:

    [branch_users.br001_manager]
    password = "manager-password"
    branch_code = "BR001"

    Or for one branch only:

    MANAGER_USERNAME = "br001_manager"
    MANAGER_PASSWORD = "manager-password"
    MANAGER_BRANCH_CODE = "BR001"
    MANAGER_DISPLAY_NAME = "Pattambi Manager"
    """
    users: Dict[str, Dict[str, str]] = {}

    def add_user(username, password, branch_code, display_name=None):
        username_clean = str(username or "").strip()
        password_clean = str(password or "").strip()
        branch_clean = str(branch_code or "").strip().upper()
        display_clean = str(display_name or username_clean).strip()
        if username_clean and password_clean and branch_clean:
            users[username_clean.lower()] = {
                "username": username_clean,
                "password": password_clean,
                "branch_code": branch_clean,
                "display_name": display_clean or username_clean,
            }

    for root_key in ["BRANCH_USERS", "branch_users"]:
        users_raw = st.secrets.get(root_key, {})
        if hasattr(users_raw, "items"):
            for username, config in users_raw.items():
                if hasattr(config, "get"):
                    add_user(
                        username=username,
                        password=config.get("password") or config.get("PASSWORD"),
                        branch_code=config.get("branch_code") or config.get("BRANCH_CODE"),
                        display_name=config.get("display_name") or config.get("DISPLAY_NAME"),
                    )

    add_user(
        username=st.secrets.get("MANAGER_USERNAME"),
        password=st.secrets.get("MANAGER_PASSWORD"),
        branch_code=st.secrets.get("MANAGER_BRANCH_CODE"),
        display_name=st.secrets.get("MANAGER_DISPLAY_NAME"),
    )

    return users


def show_login_debug(users: Dict[str, Dict[str, str]]) -> None:
    """Show safe login diagnostics without exposing passwords."""
    with st.expander("Login setup check"):
        if users:
            safe_rows = [
                {
                    "username": u["username"],
                    "branch_code": u["branch_code"],
                    "display_name": u["display_name"],
                    "password_saved": "Yes" if u.get("password") else "No",
                }
                for u in users.values()
            ]
            st.dataframe(pd.DataFrame(safe_rows), use_container_width=True, hide_index=True)
            st.caption("Passwords are hidden. Username is not case-sensitive; password spaces are trimmed.")
        else:
            st.warning("No users were read from Streamlit secrets.")
            st.code('SUPABASE_URL = "https://your-project-id.supabase.co"\\nSUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"\\n\\n[BRANCH_USERS.br001_manager]\\npassword = "manager-password"\\nbranch_code = "BR001"\\ndisplay_name = "Pattambi Manager"', language="toml")

def logout_user() -> None:
    for key in [
        "authenticated",
        "username",
        "manager_name",
        "branch_code",
        "branch_name",
    ]:
        if key in st.session_state:
            del st.session_state[key]


def is_active_value(value) -> bool:
    """Accept common Supabase active formats: true, TRUE, 1, yes, active."""
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    return text in ["true", "t", "1", "yes", "y", "active"]


def get_branch_details(branch_code: str) -> Dict[str, str] | None:
    """Return one branch from Supabase without relying on active=True filtering."""
    supabase = get_supabase_client()

    try:
        result = (
            supabase
            .table("branches")
            .select("branch_code, branch_name, active")
            .eq("branch_code", branch_code)
            .limit(1)
            .execute()
        )
    except Exception as e:
        st.error(f"Could not read branches table from Supabase. Error: {e}")
        return None

    if not result.data:
        return None

    row = result.data[0]
    if not is_active_value(row.get("active")):
        st.error(
            f"Your login is mapped to branch {branch_code}, but this branch is not active in Supabase."
        )
        return None

    return {
        "branch_code": str(row.get("branch_code") or branch_code).strip().upper(),
        "branch_name": str(row.get("branch_name") or branch_code).strip(),
    }


def check_login() -> bool:
    """Username + password login mapped to one branch code."""
    if st.session_state.get("authenticated"):
        return True

    st.title("Branch Inventory Login")
    st.caption("Each manager login opens only the branch mapped in Streamlit secrets.")

    users = load_branch_users()

    if not users:
        st.error("No branch users found in Streamlit secrets.")
        show_login_debug(users)
        return False

    username_input = st.text_input("Username")
    password_input = st.text_input("Password", type="password")

    c1, c2 = st.columns([2, 1])
    login_clicked = c1.button("Login", use_container_width=True)
    debug_clicked = c2.button("Check Setup", use_container_width=True)

    if debug_clicked:
        show_login_debug(users)

    if login_clicked:
        username_key = str(username_input or "").strip().lower()
        password_clean = str(password_input or "").strip()
        user = users.get(username_key)

        if not username_key:
            st.error("Enter username.")
            return False

        if not password_clean:
            st.error("Enter password.")
            return False

        if not user:
            st.error("Username not found in Streamlit secrets.")
            show_login_debug(users)
            return False

        if password_clean != user["password"]:
            st.error("Password is not matching the password saved for this username.")
            return False

        branch_code = user["branch_code"]
        branch = get_branch_details(branch_code)
        branch_name = branch["branch_name"] if branch else branch_code

        st.session_state.authenticated = True
        st.session_state.username = user["username"]
        st.session_state.manager_name = user["display_name"]
        st.session_state.branch_code = branch_code
        st.session_state.branch_name = branch_name
        st.rerun()

    return False

def get_logged_in_branch_code() -> str:
    branch_code = st.session_state.get("branch_code")
    if not branch_code:
        logout_user()
        st.error("Session expired. Please login again.")
        st.stop()
    return str(branch_code).strip().upper()

# -----------------------------
# Supabase data functions
# -----------------------------
def get_branches() -> pd.DataFrame:
    """Read branches without active=True filter to avoid false empty results from type mismatch."""
    supabase = get_supabase_client()

    result = (
        supabase
        .table("branches")
        .select("branch_code, branch_name, active")
        .order("branch_code")
        .execute()
    )

    df = supabase_result_to_df(result)
    if df.empty:
        return df
    if "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()
    return df


def get_ingredients() -> pd.DataFrame:
    supabase = get_supabase_client()

    result = (
        supabase
        .table("ingredients")
        .select("ingredient_code, ingredient_name, category, base_unit, min_stock, source_type")
        .eq("active", True)
        .order("ingredient_name")
        .execute()
    )

    return supabase_result_to_df(result)


def get_products() -> pd.DataFrame:
    """
    Expected Supabase table: products

    Required useful columns:
    product_code, item_name, category_name, active

    item_name must match the POS sales report item_name, or you must maintain
    a separate alias/mapping table later.
    """
    supabase = get_supabase_client()

    try:
        result = (
            supabase
            .table("products")
            .select("product_code, item_name, category_name, active")
            .eq("active", True)
            .order("item_name")
            .execute()
        )
        return supabase_result_to_df(result)
    except Exception:
        return pd.DataFrame()


def get_current_stock(branch_code: str) -> pd.DataFrame:
    """
    Requires a Supabase view named current_stock_view.

    The view should return:
    branch_code, ingredient_code, ingredient_name, category, base_unit,
    min_stock, current_qty, status
    """
    supabase = get_supabase_client()

    result = (
        supabase
        .table("current_stock_view")
        .select("*")
        .eq("branch_code", branch_code)
        .order("ingredient_name")
        .execute()
    )

    df = supabase_result_to_df(result)

    expected_cols = [
        "branch_code",
        "ingredient_code",
        "ingredient_name",
        "category",
        "base_unit",
        "min_stock",
        "current_qty",
        "status",
    ]

    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    if not df.empty:
        df["current_qty"] = pd.to_numeric(df["current_qty"], errors="coerce").fillna(0)
        df["min_stock"] = pd.to_numeric(df["min_stock"], errors="coerce").fillna(0)

    return df[expected_cols]


def get_stock_qty(branch_code: str, ingredient_code: str) -> float:
    supabase = get_supabase_client()

    result = (
        supabase
        .table("current_stock_view")
        .select("current_qty")
        .eq("branch_code", branch_code)
        .eq("ingredient_code", ingredient_code)
        .limit(1)
        .execute()
    )

    if not result.data:
        return 0.0

    return float(result.data[0].get("current_qty") or 0)


def add_stock_ledger(
    branch_code,
    ingredient_code,
    movement_type,
    qty_in,
    qty_out,
    reference_type=None,
    reference_id=None,
    note=None,
    transaction_datetime: datetime | None = None,
):
    supabase = get_supabase_client()

    dt = transaction_datetime or datetime.now()

    supabase.table("stock_ledger").insert({
        "transaction_datetime": dt.isoformat(timespec="seconds"),
        "branch_code": branch_code,
        "ingredient_code": ingredient_code,
        "movement_type": movement_type,
        "qty_in": float(qty_in or 0),
        "qty_out": float(qty_out or 0),
        "reference_type": reference_type,
        "reference_id": str(reference_id) if reference_id is not None else None,
        "note": note,
    }).execute()


def get_stock_ledger_report(branch_code: str, limit: int | None = None) -> pd.DataFrame:
    supabase = get_supabase_client()

    query = (
        supabase
        .table("stock_ledger")
        .select(
            "transaction_id, transaction_datetime, branch_code, ingredient_code, "
            "movement_type, qty_in, qty_out, reference_type, reference_id, note"
        )
        .eq("branch_code", branch_code)
        .order("transaction_id", desc=True)
    )

    if limit:
        query = query.limit(limit)

    ledger = supabase_result_to_df(query.execute())

    if ledger.empty:
        return ledger

    ingredients = get_ingredients()
    if not ingredients.empty:
        ledger = ledger.merge(
            ingredients[["ingredient_code", "ingredient_name"]],
            on="ingredient_code",
            how="left",
        )

    cols = [
        "transaction_id",
        "transaction_datetime",
        "branch_code",
        "ingredient_name",
        "ingredient_code",
        "movement_type",
        "qty_in",
        "qty_out",
        "reference_type",
        "reference_id",
        "note",
    ]

    for col in cols:
        if col not in ledger.columns:
            ledger[col] = None

    return ledger[cols]


def get_purchase_bills_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()

    result = (
        supabase
        .table("purchase_bill_header")
        .select("*")
        .eq("branch_code", branch_code)
        .order("bill_id", desc=True)
        .execute()
    )

    return supabase_result_to_df(result)


def get_purchase_bill_lines_report(branch_code: str) -> pd.DataFrame:
    headers = get_purchase_bills_report(branch_code)
    if headers.empty:
        return pd.DataFrame()

    bill_ids = headers["bill_id"].tolist()

    supabase = get_supabase_client()

    lines_result = (
        supabase
        .table("purchase_bill_lines")
        .select("*")
        .in_("bill_id", bill_ids)
        .order("line_id")
        .execute()
    )

    lines = supabase_result_to_df(lines_result)
    if lines.empty:
        return pd.DataFrame()

    ingredients = get_ingredients()

    merged = lines.merge(
        headers[["bill_id", "branch_code", "bill_date", "supplier_name", "invoice_no"]],
        on="bill_id",
        how="left",
    )

    if not ingredients.empty:
        merged = merged.merge(
            ingredients[["ingredient_code", "ingredient_name", "base_unit"]],
            on="ingredient_code",
            how="left",
        )

    cols = [
        "bill_id",
        "branch_code",
        "bill_date",
        "supplier_name",
        "invoice_no",
        "ingredient_name",
        "ingredient_code",
        "qty",
        "unit",
        "base_qty",
        "total_price",
        "unit_price",
        "expiry_date",
    ]

    for col in cols:
        if col not in merged.columns:
            merged[col] = None

    return merged[cols].sort_values(["bill_id", "ingredient_name"], ascending=[False, True])


def get_supplier_price_history_report(branch_code: str) -> pd.DataFrame:
    df = get_purchase_bill_lines_report(branch_code)
    if df.empty:
        return df

    cols = [
        "bill_date",
        "supplier_name",
        "invoice_no",
        "ingredient_name",
        "base_qty",
        "unit",
        "total_price",
        "unit_price",
    ]

    for col in cols:
        if col not in df.columns:
            df[col] = None

    result = df[cols].copy()
    result["unit_price"] = pd.to_numeric(result["unit_price"], errors="coerce").round(3)
    return result.sort_values(["ingredient_name", "bill_date"], ascending=[True, False])


# -----------------------------
# Sales upload + recipe functions
# -----------------------------
SALES_REQUIRED_COLUMNS = [
    "restaurant_name",
    "invoice_no",
    "date",
    "payment_type",
    "order_type",
    "status",
    "area",
    "virtual_brand_name",
    "brand_grouping",
    "assign_to",
    "customer_phone",
    "customer_name",
    "customer_address",
    "persons",
    "order_cancel_reason",
    "my_amount",
    "total_tax",
    "discount",
    "delivery_charge",
    "container_charge",
    "service_charge",
    "additional_charge",
    "deduction_charge",
    "waived_off",
    "round_off",
    "total",
    "item_name",
    "category_name",
    "sap_code",
    "item_price",
    "item_quantity",
    "item_total",
]


def normalize_text(value) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def normalize_key(value) -> str:
    """Case-insensitive matching key for item names."""
    return " ".join(normalize_text(value).lower().split())


def read_sales_upload(uploaded_file) -> pd.DataFrame:
    """Read CSV/XLSX sales report from POS export."""
    file_name = uploaded_file.name.lower()

    if file_name.endswith(".csv"):
        df = pd.read_csv(uploaded_file)
    elif file_name.endswith((".xlsx", ".xls")):
        df = pd.read_excel(uploaded_file)
    else:
        raise ValueError("Upload only CSV, XLSX, or XLS file.")

    df.columns = [str(c).strip() for c in df.columns]
    return df


def validate_sales_report_columns(df: pd.DataFrame) -> List[str]:
    missing = [col for col in SALES_REQUIRED_COLUMNS if col not in df.columns]
    return missing


def clean_sales_report(df: pd.DataFrame) -> pd.DataFrame:
    clean = df.copy()

    # Keep only successful sale lines. Cancelled/failed lines should not consume stock.
    clean["status"] = clean["status"].astype(str).str.strip()
    clean = clean[clean["status"].str.lower().eq("success")].copy()

    clean["sale_datetime"] = pd.to_datetime(clean["date"], errors="coerce", dayfirst=False)
    clean = clean[clean["sale_datetime"].notna()].copy()
    clean["sale_date"] = clean["sale_datetime"].dt.date

    numeric_cols = [
        "persons",
        "my_amount",
        "total_tax",
        "discount",
        "delivery_charge",
        "container_charge",
        "service_charge",
        "additional_charge",
        "deduction_charge",
        "waived_off",
        "round_off",
        "total",
        "item_price",
        "item_quantity",
        "item_total",
    ]

    for col in numeric_cols:
        if col in clean.columns:
            clean[col] = pd.to_numeric(clean[col], errors="coerce").fillna(0)

    clean["item_name"] = clean["item_name"].apply(normalize_text)
    clean["category_name"] = clean["category_name"].apply(normalize_text)
    clean = clean[clean["item_name"] != ""].copy()
    clean = clean[clean["item_quantity"] > 0].copy()

    return clean


def get_recipe_lines() -> pd.DataFrame:
    """
    Expected Supabase table: recipe_ingredients

    This single table supports product recipe, sub recipe, and sub-sub recipe.

    Required columns:
    parent_type, parent_code, component_type, component_code, quantity, unit, waste_percent, active

    Rules:
    - parent_type = Product or Sub Recipe
    - component_type = Ingredient or Sub Recipe
    - parent_code = product_code when parent_type is Product
    - parent_code = sub_recipe_code when parent_type is Sub Recipe
    - component_code = ingredient_code or child sub_recipe_code
    - quantity should be stored in the ingredient base unit or standard recipe unit.
    """
    supabase = get_supabase_client()

    result = (
        supabase
        .table("recipe_ingredients")
        .select(
            "recipe_line_id, parent_type, parent_code, component_type, component_code, "
            "quantity, unit, waste_percent, active, note"
        )
        .eq("active", True)
        .execute()
    )

    df = supabase_result_to_df(result)
    expected_cols = [
        "recipe_line_id",
        "parent_type",
        "parent_code",
        "component_type",
        "component_code",
        "quantity",
        "unit",
        "waste_percent",
        "active",
        "note",
    ]
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None

    if not df.empty:
        df["parent_type"] = df["parent_type"].astype(str).str.strip()
        df["parent_code"] = df["parent_code"].astype(str).str.strip()
        df["component_type"] = df["component_type"].astype(str).str.strip()
        df["component_code"] = df["component_code"].astype(str).str.strip()
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
        df["waste_percent"] = pd.to_numeric(df["waste_percent"], errors="coerce").fillna(0)

    return df[expected_cols]


def build_product_lookup(products: pd.DataFrame) -> Dict[str, Dict[str, str]]:
    lookup: Dict[str, Dict[str, str]] = {}
    if products.empty:
        return lookup

    for _, row in products.iterrows():
        key = normalize_key(row.get("item_name"))
        if key:
            lookup[key] = {
                "product_code": normalize_text(row.get("product_code")),
                "item_name": normalize_text(row.get("item_name")),
                "category_name": normalize_text(row.get("category_name")),
            }
    return lookup


def explode_recipe_for_parent(
    parent_type: str,
    parent_code: str,
    multiplier: float,
    recipe_lines: pd.DataFrame,
    path: str = "",
    visited: Set[Tuple[str, str]] | None = None,
) -> List[Dict]:
    """
    Recursively explode product/sub-recipe into ingredient usage.

    Example:
    Product PD001 -> Sub Recipe SUB001 -> Ingredient ING001.
    If 2 portions sold, multiplier is 2.
    """
    if visited is None:
        visited = set()

    parent_type_clean = normalize_text(parent_type)
    parent_code_clean = normalize_text(parent_code)
    current_key = (parent_type_clean.lower(), parent_code_clean.lower())

    if current_key in visited:
        raise ValueError(
            f"Circular recipe detected at {parent_type_clean} {parent_code_clean}. "
            "Check recipe_ingredients table."
        )

    visited.add(current_key)

    lines = recipe_lines[
        (recipe_lines["parent_type"].str.lower() == parent_type_clean.lower())
        & (recipe_lines["parent_code"].str.lower() == parent_code_clean.lower())
    ].copy()

    output: List[Dict] = []

    for _, line in lines.iterrows():
        component_type = normalize_text(line["component_type"])
        component_code = normalize_text(line["component_code"])
        qty = float(line["quantity"] or 0)
        waste_percent = float(line["waste_percent"] or 0)

        effective_qty = multiplier * qty * (1 + waste_percent / 100)
        child_path = f"{path} > {component_type}:{component_code}" if path else f"{component_type}:{component_code}"

        if component_type.lower() == "ingredient":
            output.append({
                "ingredient_code": component_code,
                "qty_used": effective_qty,
                "unit": normalize_text(line.get("unit")),
                "source_path": child_path,
            })
        elif component_type.lower() in ["sub recipe", "sub_recipe", "subrecipe"]:
            output.extend(
                explode_recipe_for_parent(
                    parent_type="Sub Recipe",
                    parent_code=component_code,
                    multiplier=effective_qty,
                    recipe_lines=recipe_lines,
                    path=child_path,
                    visited=visited.copy(),
                )
            )
        else:
            raise ValueError(
                f"Unknown component_type '{component_type}' for parent {parent_type_clean} {parent_code_clean}. "
                "Use Ingredient or Sub Recipe."
            )

    return output


def calculate_sales_consumption(
    sales_df: pd.DataFrame,
    products_df: pd.DataFrame,
    recipe_lines: pd.DataFrame,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Return:
    1) consumption summary by ingredient
    2) issue rows for missing products/recipes/errors
    """
    product_lookup = build_product_lookup(products_df)

    issues: List[Dict] = []
    consumption_rows: List[Dict] = []

    sold_items = (
        sales_df
        .groupby(["item_name", "category_name"], as_index=False)
        .agg(item_quantity=("item_quantity", "sum"), item_total=("item_total", "sum"))
    )

    for _, sold in sold_items.iterrows():
        item_name = normalize_text(sold["item_name"])
        item_key = normalize_key(item_name)
        sold_qty = float(sold["item_quantity"] or 0)

        product = product_lookup.get(item_key)
        if not product:
            issues.append({
                "issue_type": "Missing Product Mapping",
                "item_name": item_name,
                "product_code": None,
                "details": "This POS item_name is not found in products.item_name.",
            })
            continue

        product_code = product["product_code"]
        product_recipe = recipe_lines[
            (recipe_lines["parent_type"].str.lower() == "product")
            & (recipe_lines["parent_code"].str.lower() == product_code.lower())
        ]

        if product_recipe.empty:
            issues.append({
                "issue_type": "Missing Recipe",
                "item_name": item_name,
                "product_code": product_code,
                "details": "No active recipe_ingredients rows found for this product_code.",
            })
            continue

        try:
            ingredient_rows = explode_recipe_for_parent(
                parent_type="Product",
                parent_code=product_code,
                multiplier=sold_qty,
                recipe_lines=recipe_lines,
                path=f"Product:{product_code}",
            )
        except Exception as e:
            issues.append({
                "issue_type": "Recipe Explosion Error",
                "item_name": item_name,
                "product_code": product_code,
                "details": str(e),
            })
            continue

        for ingredient_row in ingredient_rows:
            consumption_rows.append({
                "item_name": item_name,
                "product_code": product_code,
                "sold_qty": sold_qty,
                "ingredient_code": ingredient_row["ingredient_code"],
                "qty_used": ingredient_row["qty_used"],
                "unit": ingredient_row["unit"],
                "source_path": ingredient_row["source_path"],
            })

    if not consumption_rows:
        consumption_df = pd.DataFrame(columns=[
            "ingredient_code", "qty_used", "unit", "item_name", "product_code", "sold_qty", "source_path"
        ])
    else:
        detail_df = pd.DataFrame(consumption_rows)
        consumption_df = (
            detail_df
            .groupby(["ingredient_code", "unit"], as_index=False)
            .agg(qty_used=("qty_used", "sum"))
        )

        # Keep item-level details as a pipe-separated audit trail.
        audit_df = (
            detail_df
            .assign(audit=lambda x: x["item_name"] + " (" + x["sold_qty"].astype(str) + ") via " + x["source_path"])
            .groupby(["ingredient_code", "unit"], as_index=False)
            .agg(source_items=("audit", lambda s: " | ".join(s.astype(str).tolist())))
        )
        consumption_df = consumption_df.merge(audit_df, on=["ingredient_code", "unit"], how="left")

    issues_df = pd.DataFrame(issues)
    return consumption_df, issues_df


def save_sales_upload_to_supabase(
    branch_code: str,
    sales_date: date,
    file_name: str,
    sales_df: pd.DataFrame,
    consumption_df: pd.DataFrame,
    note: str = "",
) -> int:
    """Save upload batch, sales lines, consumption detail, and stock ledger movements."""
    supabase = get_supabase_client()

    invoice_count = int(sales_df["invoice_no"].nunique()) if "invoice_no" in sales_df.columns else 0
    item_line_count = int(len(sales_df))
    total_sales_amount = float(pd.to_numeric(sales_df.get("item_total", 0), errors="coerce").fillna(0).sum())

    batch_result = supabase.table("sales_upload_batches").insert({
        "branch_code": branch_code,
        "sales_date": sales_date.isoformat(),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "file_name": file_name,
        "invoice_count": invoice_count,
        "item_line_count": item_line_count,
        "total_sales_amount": total_sales_amount,
        "status": "Posted",
        "note": note,
    }).execute()

    if not batch_result.data:
        raise ValueError("Sales upload batch was not saved. No upload_id returned.")

    upload_id = int(batch_result.data[0]["upload_id"])

    # Save raw useful POS sales lines for audit and later analytics.
    sales_payload = []
    for _, row in sales_df.iterrows():
        sales_payload.append({
            "upload_id": upload_id,
            "branch_code": branch_code,
            "sales_date": sales_date.isoformat(),
            "restaurant_name": normalize_text(row.get("restaurant_name")),
            "invoice_no": normalize_text(row.get("invoice_no")),
            "sale_datetime": pd.to_datetime(row.get("sale_datetime")).isoformat(timespec="seconds"),
            "payment_type": normalize_text(row.get("payment_type")),
            "order_type": normalize_text(row.get("order_type")),
            "status": normalize_text(row.get("status")),
            "area": normalize_text(row.get("area")),
            "item_name": normalize_text(row.get("item_name")),
            "category_name": normalize_text(row.get("category_name")),
            "sap_code": normalize_text(row.get("sap_code")),
            "item_price": float(row.get("item_price") or 0),
            "item_quantity": float(row.get("item_quantity") or 0),
            "item_total": float(row.get("item_total") or 0),
        })

    if sales_payload:
        supabase.table("sales_upload_lines").insert(sales_payload).execute()

    consumption_payload = []
    ledger_payload = []
    movement_dt = datetime.combine(sales_date, time(23, 59, 0))

    for _, row in consumption_df.iterrows():
        ingredient_code = normalize_text(row["ingredient_code"])
        qty_used = float(row["qty_used"] or 0)
        unit = normalize_text(row.get("unit"))
        source_items = normalize_text(row.get("source_items"))

        if not ingredient_code or qty_used <= 0:
            continue

        consumption_payload.append({
            "upload_id": upload_id,
            "branch_code": branch_code,
            "sales_date": sales_date.isoformat(),
            "ingredient_code": ingredient_code,
            "qty_used": qty_used,
            "unit": unit,
            "source_items": source_items,
        })

        ledger_payload.append({
            "transaction_datetime": movement_dt.isoformat(timespec="seconds"),
            "branch_code": branch_code,
            "ingredient_code": ingredient_code,
            "movement_type": "Sales Recipe Consumption",
            "qty_in": 0,
            "qty_out": qty_used,
            "reference_type": "Sales Upload",
            "reference_id": str(upload_id),
            "note": f"Sales date: {sales_date.isoformat()} | {source_items[:800]}",
        })

    if consumption_payload:
        supabase.table("sales_recipe_consumption").insert(consumption_payload).execute()

    if ledger_payload:
        supabase.table("stock_ledger").insert(ledger_payload).execute()

    save_day_stock_snapshot(branch_code, sales_date)

    return upload_id


def save_day_stock_snapshot(branch_code: str, snapshot_date: date) -> None:
    """
    Save a day-end stock movement snapshot for analyst-friendly CSV export.

    Expected Supabase table: stock_day_snapshot
    Recommended unique key: branch_code + snapshot_date + ingredient_code

    The snapshot is calculated after posting sales consumption:
    closing_qty = current stock after posting
    opening_qty = closing_qty - net movement during that date
    """
    supabase = get_supabase_client()

    start_dt = datetime.combine(snapshot_date, time.min).isoformat(timespec="seconds")
    end_dt = datetime.combine(snapshot_date, time.max).isoformat(timespec="seconds")

    ledger_result = (
        supabase
        .table("stock_ledger")
        .select("transaction_datetime, branch_code, ingredient_code, movement_type, qty_in, qty_out")
        .eq("branch_code", branch_code)
        .gte("transaction_datetime", start_dt)
        .lte("transaction_datetime", end_dt)
        .execute()
    )

    ledger = supabase_result_to_df(ledger_result)
    stock = get_current_stock(branch_code)

    if stock.empty:
        return

    if ledger.empty:
        ledger_summary = pd.DataFrame(columns=[
            "ingredient_code", "purchase_in", "adjustment_in", "adjustment_out", "sales_out", "other_in", "other_out"
        ])
    else:
        ledger["qty_in"] = pd.to_numeric(ledger["qty_in"], errors="coerce").fillna(0)
        ledger["qty_out"] = pd.to_numeric(ledger["qty_out"], errors="coerce").fillna(0)
        ledger["movement_type_clean"] = ledger["movement_type"].astype(str).str.lower()

        def sum_by_mask(df: pd.DataFrame, mask, value_col: str) -> pd.DataFrame:
            return (
                df[mask]
                .groupby("ingredient_code", as_index=False)[value_col]
                .sum()
            )

        purchase_in = sum_by_mask(ledger, ledger["movement_type_clean"].eq("purchase"), "qty_in").rename(columns={"qty_in": "purchase_in"})
        sales_out = sum_by_mask(ledger, ledger["movement_type_clean"].eq("sales recipe consumption"), "qty_out").rename(columns={"qty_out": "sales_out"})
        adjustment_in = sum_by_mask(
            ledger,
            ledger["movement_type_clean"].str.contains("adjustment in|correction in|transfer in|other in", regex=True, na=False),
            "qty_in",
        ).rename(columns={"qty_in": "adjustment_in"})
        adjustment_out = sum_by_mask(
            ledger,
            ledger["movement_type_clean"].str.contains("adjustment out|correction out|transfer out|wastage|staff meal|sample|other out", regex=True, na=False),
            "qty_out",
        ).rename(columns={"qty_out": "adjustment_out"})

        pieces = [purchase_in, sales_out, adjustment_in, adjustment_out]
        ledger_summary = pd.DataFrame({"ingredient_code": ledger["ingredient_code"].dropna().unique()})
        for p in pieces:
            ledger_summary = ledger_summary.merge(p, on="ingredient_code", how="left")

        for col in ["purchase_in", "adjustment_in", "adjustment_out", "sales_out"]:
            if col not in ledger_summary.columns:
                ledger_summary[col] = 0
            ledger_summary[col] = pd.to_numeric(ledger_summary[col], errors="coerce").fillna(0)

        ledger_summary["other_in"] = 0.0
        ledger_summary["other_out"] = 0.0

    snapshot = stock[["branch_code", "ingredient_code", "ingredient_name", "base_unit", "current_qty"]].copy()
    snapshot = snapshot.merge(ledger_summary, on="ingredient_code", how="left")

    for col in ["purchase_in", "adjustment_in", "adjustment_out", "sales_out", "other_in", "other_out"]:
        if col not in snapshot.columns:
            snapshot[col] = 0
        snapshot[col] = pd.to_numeric(snapshot[col], errors="coerce").fillna(0)

    snapshot["closing_qty"] = pd.to_numeric(snapshot["current_qty"], errors="coerce").fillna(0)
    net_movement = snapshot["purchase_in"] + snapshot["adjustment_in"] + snapshot["other_in"] - snapshot["sales_out"] - snapshot["adjustment_out"] - snapshot["other_out"]
    snapshot["opening_qty"] = snapshot["closing_qty"] - net_movement
    snapshot["snapshot_date"] = snapshot_date.isoformat()
    snapshot["saved_at"] = datetime.now().isoformat(timespec="seconds")

    payload = []
    for _, row in snapshot.iterrows():
        payload.append({
            "branch_code": branch_code,
            "snapshot_date": row["snapshot_date"],
            "ingredient_code": normalize_text(row["ingredient_code"]),
            "ingredient_name": normalize_text(row.get("ingredient_name")),
            "base_unit": normalize_text(row.get("base_unit")),
            "opening_qty": float(row["opening_qty"] or 0),
            "purchase_in": float(row["purchase_in"] or 0),
            "adjustment_in": float(row["adjustment_in"] or 0),
            "sales_out": float(row["sales_out"] or 0),
            "adjustment_out": float(row["adjustment_out"] or 0),
            "other_in": float(row["other_in"] or 0),
            "other_out": float(row["other_out"] or 0),
            "closing_qty": float(row["closing_qty"] or 0),
            "saved_at": row["saved_at"],
        })

    if payload:
        # Requires unique constraint on (branch_code, snapshot_date, ingredient_code).
        # If you do not create that constraint, replace upsert with insert.
        supabase.table("stock_day_snapshot").upsert(
            payload,
            on_conflict="branch_code,snapshot_date,ingredient_code",
        ).execute()


def get_sales_upload_batches_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    result = (
        supabase
        .table("sales_upload_batches")
        .select("*")
        .eq("branch_code", branch_code)
        .order("upload_id", desc=True)
        .execute()
    )
    return supabase_result_to_df(result)


def get_sales_consumption_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    result = (
        supabase
        .table("sales_recipe_consumption")
        .select("*")
        .eq("branch_code", branch_code)
        .order("consumption_id", desc=True)
        .execute()
    )
    return supabase_result_to_df(result)


def get_day_stock_snapshot_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    result = (
        supabase
        .table("stock_day_snapshot")
        .select("*")
        .eq("branch_code", branch_code)
        .order("snapshot_date", desc=True)
        .execute()
    )
    return supabase_result_to_df(result)


# -----------------------------
# UI helpers
# -----------------------------
def section_title(title, caption=None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def branch_selector():
    """Managers cannot select branches; branch is fixed by login secrets."""
    branch_code = get_logged_in_branch_code()
    branch_name = st.session_state.get("branch_name", branch_code)
    st.sidebar.info(f"Branch: {branch_code} - {branch_name}")
    return branch_code


def ingredient_options_with_units(ingredients: pd.DataFrame):
    labels = {}
    for _, row in ingredients.iterrows():
        label = f'{row["ingredient_code"]} - {row["ingredient_name"]} ({row["base_unit"]})'
        labels[label] = row
    return labels


def show_download_button(df: pd.DataFrame, file_name: str, label: str = "Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label,
        data=csv,
        file_name=file_name,
        mime="text/csv",
        use_container_width=True,
    )


# -----------------------------
# Pages
# -----------------------------
def page_dashboard(branch_code):
    section_title("Dashboard", "Quick stock status for the selected branch.")

    stock = get_current_stock(branch_code)

    if stock.empty:
        st.warning(
            "No stock data found. This usually means ingredients or current_stock_view "
            "are not available in Supabase."
        )
        return

    total_items = len(stock)
    low_items = int((stock["status"] == "Low").sum())
    out_items = int((stock["status"] == "Out of Stock").sum())
    negative_items = int((stock["current_qty"] < 0).sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Items", total_items)
    c2.metric("Low Stock Items", low_items)
    c3.metric("Out of Stock Items", out_items)
    c4.metric("Negative Stock", negative_items)

    st.divider()

    st.write("### Low / Out / Negative Stock Items")
    problem = stock[(stock["status"].isin(["Low", "Out of Stock"])) | (stock["current_qty"] < 0)]
    if problem.empty:
        st.success("No low/out/negative stock items for this branch.")
    else:
        st.dataframe(problem, use_container_width=True, hide_index=True)

    st.write("### Latest Stock Movements")
    latest = get_stock_ledger_report(branch_code, limit=20)
    if latest.empty:
        st.info("No stock movements recorded yet.")
    else:
        st.dataframe(latest, use_container_width=True, hide_index=True)


def page_master_data():
    section_title(
        "Master Data",
        "Read-only master data visible to the logged-in branch manager. Branch creation is handled directly in Supabase.",
    )

    tab1, tab2 = st.tabs(["Ingredients", "Products"])

    with tab1:
        st.write("### Existing Ingredients")
        ingredients = get_ingredients()
        if ingredients.empty:
            st.info("No active ingredients found, or the app cannot read the ingredients table.")
        else:
            st.dataframe(ingredients, use_container_width=True, hide_index=True)
            show_download_button(ingredients, "ingredients_master.csv", "Download Ingredients CSV")

    with tab2:
        st.write("### Existing Products")
        st.caption("products.item_name must match the POS sales report item_name.")
        products = get_products()
        if products.empty:
            st.info("No active products found, or products table is not created yet.")
        else:
            st.dataframe(products, use_container_width=True, hide_index=True)
            show_download_button(products, "products_master.csv", "Download Products CSV")


def page_add_purchase(branch_code):
    section_title(
        "Add Purchase Bill",
        "Enter supplier bill lines. Each saved line automatically increases stock.",
    )

    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("No ingredients found in Supabase. Insert your ingredients first.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)

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
            use_container_width=True,
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
            use_container_width=True,
        )

    if submitted:
        valid_lines = edited[
            (edited["Quantity In Base Unit"] > 0) & (edited["Ingredient"].notna())
        ].copy()

        if valid_lines.empty:
            st.error("Add at least one valid bill line with quantity greater than zero.")
            return

        total_amount = float(valid_lines["Total Price"].fillna(0).sum())
        supabase = get_supabase_client()

        try:
            header_result = supabase.table("purchase_bill_header").insert({
                "branch_code": branch_code,
                "bill_date": bill_date.isoformat(),
                "supplier_name": supplier_name,
                "invoice_no": invoice_no,
                "total_amount": total_amount,
                "note": note,
                "created_at": datetime.now().isoformat(timespec="seconds"),
            }).execute()

            if not header_result.data:
                st.error("Purchase bill header was not saved. No bill ID returned.")
                return

            bill_id = header_result.data[0]["bill_id"]

            bill_lines_payload = []
            ledger_payload = []

            for _, line in valid_lines.iterrows():
                selected_row = ingredient_labels[line["Ingredient"]]

                ingredient_code = selected_row["ingredient_code"]
                base_unit = selected_row["base_unit"]

                base_qty = float(line["Quantity In Base Unit"])
                total_price = float(line["Total Price"] or 0)
                unit_price = total_price / base_qty if base_qty else 0

                raw_expiry_date = line.get("Expiry Date")

                if pd.isna(raw_expiry_date) or raw_expiry_date is None:
                    expiry_date = None
                else:
                    expiry_date = pd.to_datetime(raw_expiry_date).date().isoformat()

                bill_lines_payload.append({
                    "bill_id": bill_id,
                    "ingredient_code": ingredient_code,
                    "qty": base_qty,
                    "unit": base_unit,
                    "base_qty": base_qty,
                    "total_price": total_price,
                    "unit_price": unit_price,
                    "expiry_date": expiry_date,
                })

                ledger_payload.append({
                    "transaction_datetime": datetime.now().isoformat(timespec="seconds"),
                    "branch_code": branch_code,
                    "ingredient_code": ingredient_code,
                    "movement_type": "Purchase",
                    "qty_in": base_qty,
                    "qty_out": 0,
                    "reference_type": "Purchase Bill",
                    "reference_id": str(bill_id),
                    "note": f"Invoice: {invoice_no}, Supplier: {supplier_name}",
                })

            if bill_lines_payload:
                supabase.table("purchase_bill_lines").insert(bill_lines_payload).execute()

            if ledger_payload:
                supabase.table("stock_ledger").insert(ledger_payload).execute()

            save_day_stock_snapshot(branch_code, bill_date)

            st.success(f"Purchase bill saved to Supabase. Bill ID: {bill_id}")
            st.session_state.purchase_form_version += 1
            st.rerun()

        except Exception as e:
            st.error(f"Could not save purchase bill. Error: {e}")


def page_sales_upload(branch_code):
    section_title(
        "Sales Report Upload",
        "Upload the POS sales report. The app calculates recipe consumption and reduces stock through the stock ledger.",
    )

    st.warning(
        "Default sales date is today. If the manager is uploading yesterday's report, select yesterday before posting. "
        "The app will reject files where the report date does not match the selected sales date."
    )

    selected_sales_date = st.date_input("Sales Date", value=date.today(), format="DD/MM/YYYY")
    uploaded_file = st.file_uploader("Upload Sales Report", type=["csv", "xlsx", "xls"])
    note = st.text_area("Upload Note", placeholder="Optional note, e.g. final day-end sales report")

    if uploaded_file is None:
        st.info("Upload the POS export to preview consumption before posting.")
        return

    try:
        raw_sales = read_sales_upload(uploaded_file)
    except Exception as e:
        st.error(f"Could not read uploaded file. Error: {e}")
        return

    missing_cols = validate_sales_report_columns(raw_sales)
    if missing_cols:
        st.error("The uploaded sales report is missing required columns.")
        st.write(missing_cols)
        return

    sales = clean_sales_report(raw_sales)
    if sales.empty:
        st.error("No valid successful sale lines found after cleaning the report.")
        return

    report_dates = sorted(sales["sale_date"].dropna().unique().tolist())
    if len(report_dates) != 1:
        st.error("Wrong date file or mixed-date file. The uploaded report contains more than one sales date.")
        st.write("Dates found:", [d.isoformat() for d in report_dates])
        return

    report_date = report_dates[0]
    if report_date != selected_sales_date:
        st.error(
            f"Wrong date file. You selected {selected_sales_date.isoformat()}, "
            f"but the uploaded report contains {report_date.isoformat()}."
        )
        return

    st.success(f"Sales report date verified: {report_date.isoformat()}")

    products = get_products()
    recipe_lines = get_recipe_lines()

    if products.empty:
        st.error("No active products found. Create products table and map POS item_name to product_code first.")
        return

    if recipe_lines.empty:
        st.error("No active recipe_ingredients rows found. Upload recipe details to Supabase first.")
        return

    consumption, issues = calculate_sales_consumption(sales, products, recipe_lines)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Invoices", int(sales["invoice_no"].nunique()))
    c2.metric("Sales Lines", len(sales))
    c3.metric("Unique Items", int(sales["item_name"].nunique()))
    c4.metric("Consumption Ingredients", len(consumption))

    st.write("### Sold Item Summary")
    sold_summary = (
        sales
        .groupby(["item_name", "category_name"], as_index=False)
        .agg(item_quantity=("item_quantity", "sum"), item_total=("item_total", "sum"))
        .sort_values("item_quantity", ascending=False)
    )
    st.dataframe(sold_summary, use_container_width=True, hide_index=True)

    if not issues.empty:
        st.error("Some sold items cannot be posted because product mapping or recipe is missing.")
        st.dataframe(issues, use_container_width=True, hide_index=True)
        show_download_button(
            issues,
            file_name=f"sales_upload_issues_{branch_code}_{selected_sales_date.isoformat()}.csv",
            label="Download Issues CSV",
        )
        st.stop()

    st.write("### Ingredient Consumption Preview")
    ingredients = get_ingredients()
    preview = consumption.copy()
    if not ingredients.empty and not preview.empty:
        preview = preview.merge(
            ingredients[["ingredient_code", "ingredient_name", "base_unit"]],
            on="ingredient_code",
            how="left",
        )
        preview = preview[["ingredient_code", "ingredient_name", "qty_used", "unit", "base_unit", "source_items"]]

    st.dataframe(preview, use_container_width=True, hide_index=True)
    show_download_button(
        preview,
        file_name=f"consumption_preview_{branch_code}_{selected_sales_date.isoformat()}.csv",
        label="Download Consumption Preview CSV",
    )

    st.divider()
    st.caption(
        "Posting will create: sales_upload_batches, sales_upload_lines, sales_recipe_consumption, "
        "stock_ledger entries, and stock_day_snapshot rows. Negative stock is allowed."
    )

    confirm_text = st.text_input("Type POST to confirm sales stock deduction")
    if st.button("Post Sales Consumption", type="primary", use_container_width=True):
        if confirm_text.strip().upper() != "POST":
            st.error("Type POST before posting sales consumption.")
            return

        try:
            upload_id = save_sales_upload_to_supabase(
                branch_code=branch_code,
                sales_date=selected_sales_date,
                file_name=uploaded_file.name,
                sales_df=sales,
                consumption_df=consumption,
                note=note,
            )
            st.success(f"Sales consumption posted successfully. Upload ID: {upload_id}")
            st.rerun()
        except Exception as e:
            st.error(f"Could not post sales consumption. Error: {e}")


def page_stock_count(branch_code):
    section_title(
        "Opening / Physical Stock Count",
        "Use this before opening or during stock checking. It records only the difference.",
    )

    stock = get_current_stock(branch_code)

    if stock.empty:
        st.warning("No ingredients or stock view data found.")
        return

    count_df = stock[["ingredient_code", "ingredient_name", "base_unit", "current_qty"]].copy()
    count_df["physical_qty"] = count_df["current_qty"]
    count_df["reason"] = ""

    edited = st.data_editor(
        count_df,
        use_container_width=True,
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

    if st.button("Save Stock Count Differences", use_container_width=True):
        changes = 0

        try:
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

            save_day_stock_snapshot(branch_code, date.today())

            st.success(f"Saved {changes} stock count difference(s).")
            st.rerun()

        except Exception as e:
            st.error(f"Could not save stock count differences. Error: {e}")


def page_adjustment(branch_code):
    section_title(
        "Stock Adjustment",
        "Use this for wastage, correction, staff meal, transfer in/out, or other manual movement.",
    )

    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("No ingredients found in Supabase.")
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
        submitted = st.form_submit_button("Save Adjustment", use_container_width=True)

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

        try:
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

            save_day_stock_snapshot(branch_code, date.today())

            st.success("Adjustment saved to Supabase.")
            st.rerun()

        except Exception as e:
            st.error(f"Could not save adjustment. Error: {e}")


def page_current_stock(branch_code):
    section_title("Current Stock", "Calculated from Supabase stock ledger, not manually stored.")

    stock = get_current_stock(branch_code)

    if stock.empty:
        st.warning("No current stock data found.")
        return

    status_filter = st.multiselect(
        "Filter Status",
        options=["OK", "Low", "Out of Stock"],
        default=["OK", "Low", "Out of Stock"],
    )

    filtered = stock[stock["status"].isin(status_filter)]

    st.dataframe(filtered, use_container_width=True, hide_index=True)

    show_download_button(
        filtered,
        file_name=f"current_stock_{branch_code}.csv",
        label="Download Current Stock CSV",
    )


def page_reports(branch_code):
    section_title("Reports", "Reports from Supabase.")

    report = st.selectbox(
        "Choose Report",
        [
            "Stock Ledger",
            "Purchase Bills",
            "Purchase Bill Lines",
            "Supplier Price History",
            "Sales Upload Batches",
            "Sales Recipe Consumption",
            "Day Stock Snapshot",
        ],
    )

    if report == "Stock Ledger":
        df = get_stock_ledger_report(branch_code)

    elif report == "Purchase Bills":
        df = get_purchase_bills_report(branch_code)

    elif report == "Purchase Bill Lines":
        df = get_purchase_bill_lines_report(branch_code)

    elif report == "Supplier Price History":
        df = get_supplier_price_history_report(branch_code)

    elif report == "Sales Upload Batches":
        df = get_sales_upload_batches_report(branch_code)

    elif report == "Sales Recipe Consumption":
        df = get_sales_consumption_report(branch_code)

    else:
        df = get_day_stock_snapshot_report(branch_code)

    if df.empty:
        st.info("No data found for this report.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        show_download_button(
            df,
            file_name=f"{report.lower().replace(' ', '_')}_{branch_code}.csv",
            label="Download Report CSV",
        )


# -----------------------------
# Main app
# -----------------------------
def main():
    if not check_login():
        return

    st.sidebar.title("📦 Inventory")
    st.sidebar.caption(f"Logged in: {st.session_state.get('manager_name', '')}")
    branch_code = branch_selector()

    page = st.sidebar.radio(
        "Menu",
        [
            "Dashboard",
            "Add Purchase Bill",
            "Sales Report Upload",
            "Opening / Stock Count",
            "Stock Adjustment",
            "Current Stock",
            "Reports",
        ],
    )

    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        logout_user()
        st.rerun()

    st.title("Branch Inventory Manager")
    st.caption(f"Logged-in branch: {branch_code} - {st.session_state.get('branch_name', branch_code)}")

    if page == "Dashboard":
        page_dashboard(branch_code)
    elif page == "Add Purchase Bill":
        page_add_purchase(branch_code)
    elif page == "Sales Report Upload":
        page_sales_upload(branch_code)
    elif page == "Opening / Stock Count":
        page_stock_count(branch_code)
    elif page == "Stock Adjustment":
        page_adjustment(branch_code)
    elif page == "Current Stock":
        page_current_stock(branch_code)
    elif page == "Reports":
        page_reports(branch_code)


if __name__ == "__main__":
    main()
