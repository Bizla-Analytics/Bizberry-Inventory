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
    SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

    SUPABASE_ANON_KEY is supported as fallback, but if RLS is enabled and no
    policies are created, the anon key can return empty data even when rows exist.
    """
    url = str(st.secrets.get("SUPABASE_URL", "")).strip()
    key = str(
        st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")
        or st.secrets.get("SUPABASE_ANON_KEY", "")
    ).strip()

    if not url or not key:
        st.error(
            "Supabase secrets missing. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY "
            "inside Streamlit App Secrets."
        )
        st.stop()

    return create_client(url, key)


def supabase_result_to_df(result) -> pd.DataFrame:
    if not result or not getattr(result, "data", None):
        return pd.DataFrame()
    return pd.DataFrame(result.data)


def safe_table_select(table_name: str, select_cols: str = "*", **filters) -> pd.DataFrame:
    """Read a Supabase table safely and show the real database error instead of silent empty data."""
    supabase = get_supabase_client()
    try:
        query = supabase.table(table_name).select(select_cols)
        for col, val in filters.items():
            query = query.eq(col, val)
        return supabase_result_to_df(query.execute())
    except Exception as e:
        st.error(f"Could not read Supabase table/view `{table_name}`. Error: {e}")
        return pd.DataFrame()


# -----------------------------
# Authentication
# -----------------------------
def load_branch_users() -> Dict[str, Dict[str, str]]:
    """
    Recommended Streamlit secrets format:

    SUPABASE_URL = "https://your-project-id.supabase.co"
    SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"

    [BRANCH_USERS.br001_manager]
    password = "manager-password"
    branch_code = "BR001"
    branch_name = "Pattambi"
    display_name = "Pattambi Manager"
    """
    users: Dict[str, Dict[str, str]] = {}

    def add_user(username, password, branch_code, display_name=None, branch_name=None):
        username_clean = str(username or "").strip()
        password_clean = str(password or "").strip()
        branch_clean = str(branch_code or "").strip().upper()
        display_clean = str(display_name or username_clean).strip()
        branch_name_clean = str(branch_name or "").strip()
        if username_clean and password_clean and branch_clean:
            users[username_clean.lower()] = {
                "username": username_clean,
                "password": password_clean,
                "branch_code": branch_clean,
                "display_name": display_clean or username_clean,
                "branch_name": branch_name_clean,
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
                        branch_name=config.get("branch_name") or config.get("BRANCH_NAME"),
                    )

    add_user(
        username=st.secrets.get("MANAGER_USERNAME"),
        password=st.secrets.get("MANAGER_PASSWORD"),
        branch_code=st.secrets.get("MANAGER_BRANCH_CODE"),
        display_name=st.secrets.get("MANAGER_DISPLAY_NAME"),
        branch_name=st.secrets.get("MANAGER_BRANCH_NAME"),
    )

    return users


def is_active_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["true", "t", "1", "yes", "y", "active"]


def get_branch_details(branch_code: str) -> Dict[str, str] | None:
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
        st.warning(f"Login branch is saved, but branch table could not be read: {e}")
        return None

    if not result.data:
        return None

    row = result.data[0]
    if not is_active_value(row.get("active")):
        st.error(f"Branch {branch_code} is not active in Supabase.")
        return None

    return {
        "branch_code": str(row.get("branch_code") or branch_code).strip().upper(),
        "branch_name": str(row.get("branch_name") or "").strip(),
    }


def logout_user() -> None:
    for key in ["authenticated", "username", "manager_name", "branch_code", "branch_name"]:
        st.session_state.pop(key, None)


def check_login() -> bool:
    if st.session_state.get("authenticated"):
        return True

    st.title("Branch Inventory Login")
    st.caption("Each manager can open only the branch mapped in Streamlit secrets.")

    users = load_branch_users()
    if not users:
        st.error("No branch users found in Streamlit secrets.")
        st.code(
            'SUPABASE_URL = "https://your-project-id.supabase.co"\n'
            'SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"\n\n'
            '[BRANCH_USERS.br001_manager]\n'
            'password = "manager-password"\n'
            'branch_code = "BR001"\n'
            'branch_name = "Pattambi"\n'
            'display_name = "Pattambi Manager"',
            language="toml",
        )
        return False

    username_input = st.text_input("Username")
    password_input = st.text_input("Password", type="password")

    if st.button("Login", use_container_width=True):
        username_key = str(username_input or "").strip().lower()
        password_clean = str(password_input or "").strip()
        user = users.get(username_key)

        if not username_key:
            st.error("Enter username.")
            return False
        if not password_clean:
            st.error("Enter password.")
            return False
        if not user or password_clean != user["password"]:
            st.error("Invalid username or password.")
            return False

        branch_code = user["branch_code"]
        branch = get_branch_details(branch_code)
        branch_name = (
            str(user.get("branch_name") or "").strip()
            or (branch.get("branch_name") if branch else "")
            or branch_code
        )

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
# Data functions - no current_stock_view required
# -----------------------------
def get_ingredients(include_inactive: bool = False) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase
            .table("ingredients")
            .select("ingredient_code, ingredient_name, category, base_unit, min_stock, source_type, active")
            .order("ingredient_name")
            .execute()
        )
    except Exception as e:
        st.error(f"Could not read ingredients table. Error: {e}")
        return pd.DataFrame()

    df = supabase_result_to_df(result)
    if df.empty:
        return df
    if not include_inactive and "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()
    for col in ["category", "source_type"]:
        if col not in df.columns:
            df[col] = None
    df["min_stock"] = pd.to_numeric(df.get("min_stock", 0), errors="coerce").fillna(0)
    return df


def get_stock_ledger_raw(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase
            .table("stock_ledger")
            .select(
                "transaction_id, transaction_datetime, branch_code, ingredient_code, "
                "movement_type, qty_in, qty_out, reference_type, reference_id, note"
            )
            .eq("branch_code", branch_code)
            .order("transaction_id", desc=True)
            .execute()
        )
        df = supabase_result_to_df(result)
    except Exception as e:
        st.error(f"Could not read stock_ledger table. Error: {e}")
        return pd.DataFrame()

    for col in ["qty_in", "qty_out"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def get_current_stock(branch_code: str) -> pd.DataFrame:
    """Calculate current stock from stock_ledger + ingredients. No Supabase view is required."""
    ingredients = get_ingredients()
    expected_cols = [
        "branch_code", "ingredient_code", "ingredient_name", "category", "base_unit",
        "min_stock", "current_qty", "status",
    ]
    if ingredients.empty:
        return pd.DataFrame(columns=expected_cols)

    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        stock_sum = pd.DataFrame(columns=["ingredient_code", "qty_in", "qty_out"])
    else:
        stock_sum = (
            ledger.groupby("ingredient_code", as_index=False)[["qty_in", "qty_out"]]
            .sum()
        )

    df = ingredients.merge(stock_sum, on="ingredient_code", how="left")
    df["qty_in"] = pd.to_numeric(df.get("qty_in", 0), errors="coerce").fillna(0)
    df["qty_out"] = pd.to_numeric(df.get("qty_out", 0), errors="coerce").fillna(0)
    df["current_qty"] = df["qty_in"] - df["qty_out"]
    df["branch_code"] = branch_code

    def status(row):
        qty = float(row.get("current_qty") or 0)
        min_stock = float(row.get("min_stock") or 0)
        if qty <= 0:
            return "Out of Stock"
        if qty <= min_stock:
            return "Low"
        return "OK"

    df["status"] = df.apply(status, axis=1)
    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
    return df[expected_cols].sort_values("ingredient_name")


def get_stock_qty(branch_code: str, ingredient_code: str) -> float:
    stock = get_current_stock(branch_code)
    row = stock[stock["ingredient_code"] == ingredient_code]
    if row.empty:
        return 0.0
    return float(row.iloc[0]["current_qty"] or 0)


def add_stock_ledger(
    branch_code: str,
    ingredient_code: str,
    movement_type: str,
    qty_in: float,
    qty_out: float,
    reference_type: str | None = None,
    reference_id: str | None = None,
    note: str | None = None,
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
    try:
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
    except Exception as e:
        st.error(f"Could not read stock_ledger table. Error: {e}")
        return pd.DataFrame()

    if ledger.empty:
        return ledger

    ingredients = get_ingredients(include_inactive=True)
    if not ingredients.empty:
        ledger = ledger.merge(
            ingredients[["ingredient_code", "ingredient_name", "base_unit"]],
            on="ingredient_code",
            how="left",
        )

    cols = [
        "transaction_id", "transaction_datetime", "branch_code", "ingredient_name",
        "ingredient_code", "base_unit", "movement_type", "qty_in", "qty_out",
        "reference_type", "reference_id", "note",
    ]
    for col in cols:
        if col not in ledger.columns:
            ledger[col] = None
    return ledger[cols]


def get_purchase_bills_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase
            .table("purchase_bill_header")
            .select("*")
            .eq("branch_code", branch_code)
            .order("bill_id", desc=True)
            .execute()
        )
        return supabase_result_to_df(result)
    except Exception as e:
        st.error(f"Could not read purchase_bill_header table. Error: {e}")
        return pd.DataFrame()


def get_purchase_bill_lines_report(branch_code: str) -> pd.DataFrame:
    headers = get_purchase_bills_report(branch_code)
    if headers.empty:
        return pd.DataFrame()

    bill_ids = headers["bill_id"].tolist()
    supabase = get_supabase_client()
    try:
        lines_result = (
            supabase
            .table("purchase_bill_lines")
            .select("*")
            .in_("bill_id", bill_ids)
            .order("line_id")
            .execute()
        )
        lines = supabase_result_to_df(lines_result)
    except Exception as e:
        st.error(f"Could not read purchase_bill_lines table. Error: {e}")
        return pd.DataFrame()

    if lines.empty:
        return pd.DataFrame()

    ingredients = get_ingredients(include_inactive=True)
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
        "bill_id", "branch_code", "bill_date", "supplier_name", "invoice_no",
        "ingredient_name", "ingredient_code", "qty", "unit", "base_qty",
        "total_price", "unit_price", "expiry_date",
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
        "bill_date", "supplier_name", "invoice_no", "ingredient_name",
        "base_qty", "unit", "total_price", "unit_price",
    ]
    result = df[cols].copy()
    result["unit_price"] = pd.to_numeric(result["unit_price"], errors="coerce").round(3)
    return result.sort_values(["ingredient_name", "bill_date"], ascending=[True, False])


# -----------------------------
# Sales upload / recipe functions
# -----------------------------
REQUIRED_SALES_COLUMNS = [
    "restaurant_name", "invoice_no", "date", "payment_type", "order_type", "status", "area",
    "virtual_brand_name", "brand_grouping", "assign_to", "customer_phone", "customer_name",
    "customer_address", "persons", "order_cancel_reason", "my_amount", "total_tax", "discount",
    "delivery_charge", "container_charge", "service_charge", "additional_charge", "deduction_charge",
    "waived_off", "round_off", "total", "item_name", "category_name", "sap_code", "item_price",
    "item_quantity", "item_total",
]


def read_uploaded_sales_file(uploaded_file) -> pd.DataFrame:
    filename = uploaded_file.name.lower()
    if filename.endswith(".csv"):
        return pd.read_csv(uploaded_file)
    if filename.endswith((".xlsx", ".xls")):
        return pd.read_excel(uploaded_file)
    raise ValueError("Upload only CSV, XLSX, or XLS file.")


def clean_sales_report(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.copy()
    df.columns = [str(c).strip() for c in df.columns]
    missing = [c for c in REQUIRED_SALES_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError("Missing required sales report columns: " + ", ".join(missing))

    df = df[REQUIRED_SALES_COLUMNS].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce", dayfirst=False)
    if df["date"].isna().any():
        bad_count = int(df["date"].isna().sum())
        raise ValueError(f"Sales report has {bad_count} row(s) with invalid date values.")

    df["sales_date"] = df["date"].dt.date
    df["status"] = df["status"].astype(str).str.strip()
    df["item_name"] = df["item_name"].astype(str).str.strip()
    df["category_name"] = df["category_name"].astype(str).str.strip()
    df["item_quantity"] = pd.to_numeric(df["item_quantity"], errors="coerce").fillna(0)
    df["item_price"] = pd.to_numeric(df["item_price"], errors="coerce").fillna(0)
    df["item_total"] = pd.to_numeric(df["item_total"], errors="coerce").fillna(0)
    df = df[df["item_quantity"] > 0].copy()
    return df


def get_products() -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase
            .table("products")
            .select("product_code, item_name, category_name, active")
            .execute()
        )
        df = supabase_result_to_df(result)
    except Exception as e:
        st.error(
            "Could not read `products` table. Create this table before using sales upload. "
            f"Error: {e}"
        )
        return pd.DataFrame()

    if df.empty:
        return df
    if "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()
    df["item_name_clean"] = df["item_name"].astype(str).str.strip().str.lower()
    return df


def get_recipe_ingredients() -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase
            .table("recipe_ingredients")
            .select(
                "recipe_line_id, parent_type, parent_code, component_type, component_code, "
                "quantity, unit, waste_percent, active, note"
            )
            .execute()
        )
        df = supabase_result_to_df(result)
    except Exception as e:
        st.error(
            "Could not read `recipe_ingredients` table. Create this table before using sales upload. "
            f"Error: {e}"
        )
        return pd.DataFrame()

    if df.empty:
        return df
    if "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()
    df["parent_type"] = df["parent_type"].astype(str).str.strip().str.lower()
    df["component_type"] = df["component_type"].astype(str).str.strip().str.lower()
    df["parent_code"] = df["parent_code"].astype(str).str.strip().str.upper()
    df["component_code"] = df["component_code"].astype(str).str.strip().str.upper()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["waste_percent"] = pd.to_numeric(df.get("waste_percent", 0), errors="coerce").fillna(0)
    return df


def explode_recipe_for_parent(
    recipe_df: pd.DataFrame,
    parent_type: str,
    parent_code: str,
    multiplier: float,
    visited: Set[Tuple[str, str]] | None = None,
    depth: int = 0,
    max_depth: int = 20,
) -> List[Dict[str, object]]:
    """Recursive recipe explosion: product/sub recipe -> ingredient/sub recipe -> ingredient."""
    if visited is None:
        visited = set()

    parent_type_clean = str(parent_type).strip().lower()
    parent_code_clean = str(parent_code).strip().upper()
    key = (parent_type_clean, parent_code_clean)

    if depth > max_depth:
        raise ValueError(f"Recipe nesting too deep near {parent_type} {parent_code}.")
    if key in visited:
        raise ValueError(f"Circular recipe detected near {parent_type} {parent_code}.")

    visited.add(key)
    rows = recipe_df[
        (recipe_df["parent_type"] == parent_type_clean)
        & (recipe_df["parent_code"] == parent_code_clean)
    ]

    output: List[Dict[str, object]] = []
    for _, row in rows.iterrows():
        component_type = str(row["component_type"]).strip().lower()
        component_code = str(row["component_code"]).strip().upper()
        base_qty = float(row["quantity"] or 0) * float(multiplier or 0)
        waste_percent = float(row.get("waste_percent") or 0)
        qty_with_waste = base_qty * (1 + waste_percent / 100)

        if component_type in ["ingredient", "direct ingredient"]:
            output.append({
                "ingredient_code": component_code,
                "used_qty": qty_with_waste,
                "source_parent_type": parent_type_clean,
                "source_parent_code": parent_code_clean,
                "recipe_line_id": row.get("recipe_line_id"),
            })
        elif component_type in ["sub recipe", "sub_recipe", "subrecipe", "produced"]:
            output.extend(
                explode_recipe_for_parent(
                    recipe_df=recipe_df,
                    parent_type="Sub Recipe",
                    parent_code=component_code,
                    multiplier=qty_with_waste,
                    visited=visited.copy(),
                    depth=depth + 1,
                    max_depth=max_depth,
                )
            )
        else:
            raise ValueError(
                f"Invalid component_type `{row['component_type']}` for parent {parent_type} {parent_code}. "
                "Use Ingredient or Sub Recipe."
            )

    visited.remove(key)
    return output


def create_sales_batch_if_table_exists(branch_code: str, sales_date: date, uploaded_filename: str, row_count: int) -> str:
    """Optional analytical table. If missing, return timestamp ID and continue."""
    batch_id = f"{branch_code}-{sales_date.isoformat()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    supabase = get_supabase_client()
    try:
        result = supabase.table("sales_upload_batches").insert({
            "batch_id": batch_id,
            "branch_code": branch_code,
            "sales_date": sales_date.isoformat(),
            "uploaded_filename": uploaded_filename,
            "row_count": int(row_count),
            "uploaded_at": datetime.now().isoformat(timespec="seconds"),
            "uploaded_by": st.session_state.get("username"),
        }).execute()
        if result.data and result.data[0].get("batch_id"):
            return str(result.data[0]["batch_id"])
    except Exception:
        pass
    return batch_id


def insert_optional_sales_lines(batch_id: str, branch_code: str, sales_date: date, sales_df: pd.DataFrame) -> None:
    supabase = get_supabase_client()
    payload = []
    for _, r in sales_df.iterrows():
        payload.append({
            "batch_id": batch_id,
            "branch_code": branch_code,
            "sales_date": sales_date.isoformat(),
            "invoice_no": str(r.get("invoice_no") or ""),
            "invoice_datetime": pd.to_datetime(r.get("date")).isoformat(),
            "item_name": str(r.get("item_name") or ""),
            "category_name": str(r.get("category_name") or ""),
            "item_quantity": float(r.get("item_quantity") or 0),
            "item_price": float(r.get("item_price") or 0),
            "item_total": float(r.get("item_total") or 0),
            "status": str(r.get("status") or ""),
            "order_type": str(r.get("order_type") or ""),
            "payment_type": str(r.get("payment_type") or ""),
        })
    if not payload:
        return
    try:
        for i in range(0, len(payload), 500):
            supabase.table("sales_upload_lines").insert(payload[i:i + 500]).execute()
    except Exception:
        pass


def insert_optional_consumption(batch_id: str, branch_code: str, sales_date: date, consumption_df: pd.DataFrame) -> None:
    if consumption_df.empty:
        return
    supabase = get_supabase_client()
    payload = []
    for _, r in consumption_df.iterrows():
        payload.append({
            "batch_id": batch_id,
            "branch_code": branch_code,
            "sales_date": sales_date.isoformat(),
            "product_code": str(r.get("product_code") or ""),
            "item_name": str(r.get("item_name") or ""),
            "sold_qty": float(r.get("sold_qty") or 0),
            "ingredient_code": str(r.get("ingredient_code") or ""),
            "used_qty": float(r.get("used_qty") or 0),
        })
    try:
        for i in range(0, len(payload), 500):
            supabase.table("sales_recipe_consumption").insert(payload[i:i + 500]).execute()
    except Exception:
        pass


def save_stock_day_snapshot(branch_code: str, snapshot_date: date) -> None:
    """Optional table for analysts. If table missing, silently skip."""
    current = get_current_stock(branch_code)
    if current.empty:
        return

    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        movements = pd.DataFrame(columns=["ingredient_code", "purchase_in", "adjustment_in", "sales_out", "adjustment_out", "other_in", "other_out"])
    else:
        ledger["transaction_datetime"] = pd.to_datetime(ledger["transaction_datetime"], errors="coerce")
        day_ledger = ledger[ledger["transaction_datetime"].dt.date == snapshot_date].copy()

        def classify(row):
            m = str(row.get("movement_type") or "").lower()
            if "purchase" in m:
                return "purchase_in"
            if "sales" in m:
                return "sales_out"
            if float(row.get("qty_in") or 0) > 0:
                return "adjustment_in"
            if float(row.get("qty_out") or 0) > 0:
                return "adjustment_out"
            return "other"

        if day_ledger.empty:
            movements = pd.DataFrame(columns=["ingredient_code", "purchase_in", "adjustment_in", "sales_out", "adjustment_out", "other_in", "other_out"])
        else:
            day_ledger["bucket"] = day_ledger.apply(classify, axis=1)
            rows = []
            for ing, g in day_ledger.groupby("ingredient_code"):
                rows.append({
                    "ingredient_code": ing,
                    "purchase_in": float(g.loc[g["bucket"] == "purchase_in", "qty_in"].sum()),
                    "adjustment_in": float(g.loc[g["bucket"] == "adjustment_in", "qty_in"].sum()),
                    "sales_out": float(g.loc[g["bucket"] == "sales_out", "qty_out"].sum()),
                    "adjustment_out": float(g.loc[g["bucket"] == "adjustment_out", "qty_out"].sum()),
                    "other_in": float(g.loc[g["bucket"] == "other", "qty_in"].sum()),
                    "other_out": float(g.loc[g["bucket"] == "other", "qty_out"].sum()),
                })
            movements = pd.DataFrame(rows)

    snap = current.merge(movements, on="ingredient_code", how="left")
    for col in ["purchase_in", "adjustment_in", "sales_out", "adjustment_out", "other_in", "other_out"]:
        snap[col] = pd.to_numeric(snap.get(col, 0), errors="coerce").fillna(0)
    snap["closing_qty"] = pd.to_numeric(snap["current_qty"], errors="coerce").fillna(0)
    snap["opening_qty"] = snap["closing_qty"] - snap["purchase_in"] - snap["adjustment_in"] - snap["other_in"] + snap["sales_out"] + snap["adjustment_out"] + snap["other_out"]

    payload = []
    for _, r in snap.iterrows():
        payload.append({
            "branch_code": branch_code,
            "snapshot_date": snapshot_date.isoformat(),
            "ingredient_code": str(r["ingredient_code"]),
            "ingredient_name": str(r.get("ingredient_name") or ""),
            "base_unit": str(r.get("base_unit") or ""),
            "opening_qty": float(r.get("opening_qty") or 0),
            "purchase_in": float(r.get("purchase_in") or 0),
            "adjustment_in": float(r.get("adjustment_in") or 0),
            "sales_out": float(r.get("sales_out") or 0),
            "adjustment_out": float(r.get("adjustment_out") or 0),
            "other_in": float(r.get("other_in") or 0),
            "other_out": float(r.get("other_out") or 0),
            "closing_qty": float(r.get("closing_qty") or 0),
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })
    try:
        supabase = get_supabase_client()
        # Remove previous snapshot for that branch/date if the table supports delete.
        try:
            supabase.table("stock_day_snapshot").delete().eq("branch_code", branch_code).eq("snapshot_date", snapshot_date.isoformat()).execute()
        except Exception:
            pass
        for i in range(0, len(payload), 500):
            supabase.table("stock_day_snapshot").insert(payload[i:i + 500]).execute()
    except Exception:
        pass


# -----------------------------
# UI helpers
# -----------------------------
def section_title(title: str, caption: str | None = None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def ingredient_options_with_units(ingredients: pd.DataFrame):
    labels = {}
    for _, row in ingredients.iterrows():
        label = f'{row["ingredient_code"]} - {row["ingredient_name"]} ({row["base_unit"]})'
        labels[label] = row
    return labels


def show_download_button(df: pd.DataFrame, file_name: str, label: str = "Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=file_name, mime="text/csv", use_container_width=True)


# -----------------------------
# Pages
# -----------------------------
def page_dashboard(branch_code: str):
    section_title("Dashboard", "Quick stock status for your branch.")
    stock = get_current_stock(branch_code)
    if stock.empty:
        st.warning("No ingredients found in Supabase, or stock ledger is not readable.")
        return

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
        st.dataframe(problem, use_container_width=True, hide_index=True)

    st.write("### Latest Stock Movements")
    latest = get_stock_ledger_report(branch_code, limit=20)
    if latest.empty:
        st.info("No stock movements recorded yet.")
    else:
        st.dataframe(latest, use_container_width=True, hide_index=True)


def page_add_purchase(branch_code: str):
    section_title("Add Purchase Bill", "Enter supplier bill lines. Each saved line increases stock.")
    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("No active ingredients found in Supabase.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)
    if "purchase_form_version" not in st.session_state:
        st.session_state.purchase_form_version = 0
    form_version = st.session_state.purchase_form_version

    with st.form(f"purchase_form_{form_version}"):
        c1, c2, c3 = st.columns(3)
        bill_date = c1.date_input("Bill Date", value=date.today(), key=f"bill_date_{form_version}")
        supplier_name = c2.text_input("Supplier Name", key=f"supplier_name_{form_version}")
        invoice_no = c3.text_input("Invoice Number", key=f"invoice_no_{form_version}")
        note = st.text_area("Bill Note", key=f"bill_note_{form_version}")

        first_ingredient = list(ingredient_labels.keys())[0]
        default_lines = pd.DataFrame([{
            "Ingredient": first_ingredient,
            "Quantity In Base Unit": 0.0,
            "Total Price": 0.0,
            "Expiry Date": None,
        }])
        edited = st.data_editor(
            default_lines,
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            key=f"purchase_lines_editor_{form_version}",
            column_config={
                "Ingredient": st.column_config.SelectboxColumn("Ingredient", options=list(ingredient_labels.keys()), required=True),
                "Quantity In Base Unit": st.column_config.NumberColumn("Quantity In Base Unit", min_value=0.0, step=1.0, required=True),
                "Total Price": st.column_config.NumberColumn("Total Price", min_value=0.0, step=1.0),
                "Expiry Date": st.column_config.DateColumn("Expiry Date", format="DD/MM/YYYY"),
            },
        )
        submitted = st.form_submit_button("Save Purchase Bill", use_container_width=True)

    if submitted:
        valid_lines = edited[(edited["Quantity In Base Unit"] > 0) & (edited["Ingredient"].notna())].copy()
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
                expiry_date = None if pd.isna(raw_expiry_date) or raw_expiry_date is None else pd.to_datetime(raw_expiry_date).date().isoformat()

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

            supabase.table("purchase_bill_lines").insert(bill_lines_payload).execute()
            supabase.table("stock_ledger").insert(ledger_payload).execute()
            st.success(f"Purchase bill saved. Bill ID: {bill_id}")
            st.session_state.purchase_form_version += 1
            st.rerun()
        except Exception as e:
            st.error(f"Could not save purchase bill. Error: {e}")


def page_stock_count(branch_code: str):
    section_title("Opening / Physical Stock Count", "Records only the difference between system stock and physical stock.")
    stock = get_current_stock(branch_code)
    if stock.empty:
        st.warning("No ingredients found.")
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
                    add_stock_ledger(
                        branch_code=branch_code,
                        ingredient_code=row["ingredient_code"],
                        movement_type="Physical Count Adjustment In" if diff > 0 else "Physical Count Adjustment Out",
                        qty_in=diff if diff > 0 else 0,
                        qty_out=abs(diff) if diff < 0 else 0,
                        reference_type="Stock Count",
                        reference_id=date.today().isoformat(),
                        note=row.get("reason") or "Physical count difference",
                    )
                    changes += 1
            st.success(f"Saved {changes} stock count difference(s).")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save stock count differences. Error: {e}")


def page_adjustment(branch_code: str):
    section_title("Stock Adjustment", "Use for wastage, correction, staff meal, transfer, or other manual movement.")
    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("No ingredients found in Supabase.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)
    with st.form("adjustment_form"):
        movement_type = st.selectbox(
            "Movement Type",
            ["Wastage", "Correction In", "Correction Out", "Transfer In", "Transfer Out", "Staff Meal", "Sample / Testing", "Other In", "Other Out"],
        )
        selected_ingredient = st.selectbox("Ingredient", list(ingredient_labels.keys()))
        qty = st.number_input("Quantity In Base Unit", min_value=0.0, step=1.0)
        note = st.text_area("Reason / Note", placeholder="Example: spoiled, branch transfer, wrong count correction")
        submitted = st.form_submit_button("Save Adjustment", use_container_width=True)

    if submitted:
        if qty <= 0:
            st.error("Quantity must be greater than zero.")
            return
        ingredient_code = ingredient_labels[selected_ingredient]["ingredient_code"]
        in_types = ["Correction In", "Transfer In", "Other In"]
        qty_in, qty_out = (qty, 0) if movement_type in in_types else (0, qty)
        try:
            add_stock_ledger(branch_code, ingredient_code, movement_type, qty_in, qty_out, "Manual Adjustment", date.today().isoformat(), note)
            st.success("Adjustment saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save adjustment. Error: {e}")


def page_sales_upload(branch_code: str):
    section_title("Sales Report Upload", "Upload POS sales report. Recipe usage will be posted to stock ledger.")

    sales_date = st.date_input("Sales Date", value=date.today())
    uploaded_file = st.file_uploader("Upload Sales Report", type=["csv", "xlsx", "xls"])

    st.caption("The selected Sales Date must match the date inside the uploaded report. If uploading yesterday's report, select yesterday before uploading.")

    if not uploaded_file:
        return

    try:
        raw = read_uploaded_sales_file(uploaded_file)
        sales_df = clean_sales_report(raw)
    except Exception as e:
        st.error(f"Could not read sales report. Error: {e}")
        return

    dates_in_file = sorted(sales_df["sales_date"].unique().tolist())
    if len(dates_in_file) != 1:
        st.error(f"Wrong file. This report contains multiple dates: {dates_in_file}")
        return
    file_date = dates_in_file[0]
    if file_date != sales_date:
        st.error(f"Wrong date file. Selected date is {sales_date}, but uploaded report date is {file_date}.")
        return

    success_df = sales_df[sales_df["status"].str.lower() == "success"].copy()
    if success_df.empty:
        st.warning("No Success sales rows found in this report.")
        return

    sold_items = (
        success_df.groupby(["item_name", "category_name"], as_index=False)
        .agg(sold_qty=("item_quantity", "sum"), gross_sales=("item_total", "sum"))
        .sort_values("item_name")
    )
    st.write("### Items found in report")
    st.dataframe(sold_items, use_container_width=True, hide_index=True)

    products = get_products()
    recipe_df = get_recipe_ingredients()
    if products.empty or recipe_df.empty:
        st.error("Sales upload cannot continue until `products` and `recipe_ingredients` tables are created and filled.")
        return

    check = sold_items.copy()
    check["item_name_clean"] = check["item_name"].astype(str).str.strip().str.lower()
    mapped = check.merge(products[["product_code", "item_name", "item_name_clean"]], on="item_name_clean", how="left", suffixes=("_sales", "_product"))
    missing_map = mapped[mapped["product_code"].isna()]
    if not missing_map.empty:
        st.error("Some POS items are not mapped in products table. Add these items first.")
        st.dataframe(missing_map[["item_name_sales", "category_name", "sold_qty"]], use_container_width=True, hide_index=True)
        return

    consumption_rows = []
    missing_recipe = []
    try:
        for _, item in mapped.iterrows():
            product_code = str(item["product_code"]).strip().upper()
            sold_qty = float(item["sold_qty"] or 0)
            exploded = explode_recipe_for_parent(recipe_df, "Product", product_code, sold_qty)
            if not exploded:
                missing_recipe.append({
                    "product_code": product_code,
                    "item_name": item["item_name_sales"],
                    "sold_qty": sold_qty,
                })
                continue
            for e in exploded:
                consumption_rows.append({
                    "product_code": product_code,
                    "item_name": item["item_name_sales"],
                    "sold_qty": sold_qty,
                    "ingredient_code": e["ingredient_code"],
                    "used_qty": float(e["used_qty"] or 0),
                })
    except Exception as e:
        st.error(f"Recipe explosion failed. Error: {e}")
        return

    if missing_recipe:
        st.error("Some products have no recipe lines in recipe_ingredients table.")
        st.dataframe(pd.DataFrame(missing_recipe), use_container_width=True, hide_index=True)
        return

    consumption = pd.DataFrame(consumption_rows)
    if consumption.empty:
        st.error("No recipe consumption calculated.")
        return

    consumption_summary = (
        consumption.groupby(["ingredient_code"], as_index=False)
        .agg(used_qty=("used_qty", "sum"))
    )
    ingredients = get_ingredients(include_inactive=True)
    if not ingredients.empty:
        consumption_summary = consumption_summary.merge(
            ingredients[["ingredient_code", "ingredient_name", "base_unit"]],
            on="ingredient_code",
            how="left",
        )
    st.write("### Calculated ingredient consumption")
    st.dataframe(consumption_summary, use_container_width=True, hide_index=True)

    if st.button("Post Sales Consumption to Stock Ledger", use_container_width=True):
        supabase = get_supabase_client()
        batch_id = create_sales_batch_if_table_exists(branch_code, sales_date, uploaded_file.name, len(success_df))
        insert_optional_sales_lines(batch_id, branch_code, sales_date, success_df)
        insert_optional_consumption(batch_id, branch_code, sales_date, consumption)

        tx_dt = datetime.combine(sales_date, time(23, 59, 0))
        ledger_payload = []
        for _, r in consumption_summary.iterrows():
            ledger_payload.append({
                "transaction_datetime": tx_dt.isoformat(timespec="seconds"),
                "branch_code": branch_code,
                "ingredient_code": str(r["ingredient_code"]),
                "movement_type": "Sales Recipe Consumption",
                "qty_in": 0,
                "qty_out": float(r["used_qty"] or 0),
                "reference_type": "Sales Upload",
                "reference_id": batch_id,
                "note": f"Sales report {uploaded_file.name} for {sales_date.isoformat()}",
            })

        try:
            for i in range(0, len(ledger_payload), 500):
                supabase.table("stock_ledger").insert(ledger_payload[i:i + 500]).execute()
            save_stock_day_snapshot(branch_code, sales_date)
            st.success(f"Sales consumption posted. Batch ID: {batch_id}")
            st.rerun()
        except Exception as e:
            st.error(f"Could not post sales consumption to stock_ledger. Error: {e}")


def page_current_stock(branch_code: str):
    section_title("Current Stock", "Calculated from stock_ledger, not manually stored.")
    stock = get_current_stock(branch_code)
    if stock.empty:
        st.warning("No stock data found.")
        return
    status_filter = st.multiselect("Filter Status", ["OK", "Low", "Out of Stock"], default=["OK", "Low", "Out of Stock"])
    filtered = stock[stock["status"].isin(status_filter)]
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    show_download_button(filtered, f"current_stock_{branch_code}.csv", "Download Current Stock CSV")


def page_reports(branch_code: str):
    section_title("Reports", "Reports for your branch only.")
    report = st.selectbox("Choose Report", ["Stock Ledger", "Purchase Bills", "Purchase Bill Lines", "Supplier Price History"])
    if report == "Stock Ledger":
        df = get_stock_ledger_report(branch_code)
    elif report == "Purchase Bills":
        df = get_purchase_bills_report(branch_code)
    elif report == "Purchase Bill Lines":
        df = get_purchase_bill_lines_report(branch_code)
    else:
        df = get_supplier_price_history_report(branch_code)

    if df.empty:
        st.info("No data found for this report.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        show_download_button(df, f"{report.lower().replace(' ', '_')}_{branch_code}.csv", "Download Report CSV")


def page_schema_help():
    section_title("Required Extra Tables", "Use these extra tables for sales upload and clean analyst reporting.")
    st.write("Your existing five tables are enough for purchase, stock count, adjustment, current stock, and reports. For sales upload, add these tables:")
    st.code(
        """
create table if not exists products (
    product_code text primary key,
    item_name text not null unique,
    category_name text,
    active boolean default true
);

create table if not exists recipe_ingredients (
    recipe_line_id bigint generated by default as identity primary key,
    parent_type text not null,        -- Product or Sub Recipe
    parent_code text not null,        -- product_code or sub recipe code
    component_type text not null,     -- Ingredient or Sub Recipe
    component_code text not null,     -- ingredient_code or sub recipe code
    quantity numeric not null,        -- quantity in stock base unit per 1 parent unit
    unit text,
    waste_percent numeric default 0,
    active boolean default true,
    note text
);

create table if not exists sales_upload_batches (
    batch_id text primary key,
    branch_code text not null references branches(branch_code),
    sales_date date not null,
    uploaded_filename text,
    row_count int,
    uploaded_at timestamp with time zone default now(),
    uploaded_by text
);

create table if not exists sales_upload_lines (
    line_id bigint generated by default as identity primary key,
    batch_id text,
    branch_code text not null references branches(branch_code),
    sales_date date not null,
    invoice_no text,
    invoice_datetime timestamp with time zone,
    item_name text,
    category_name text,
    item_quantity numeric,
    item_price numeric,
    item_total numeric,
    status text,
    order_type text,
    payment_type text
);

create table if not exists sales_recipe_consumption (
    consumption_id bigint generated by default as identity primary key,
    batch_id text,
    branch_code text not null references branches(branch_code),
    sales_date date not null,
    product_code text,
    item_name text,
    sold_qty numeric,
    ingredient_code text not null references ingredients(ingredient_code),
    used_qty numeric not null
);

create table if not exists stock_day_snapshot (
    snapshot_id bigint generated by default as identity primary key,
    branch_code text not null references branches(branch_code),
    snapshot_date date not null,
    ingredient_code text not null references ingredients(ingredient_code),
    ingredient_name text,
    base_unit text,
    opening_qty numeric default 0,
    purchase_in numeric default 0,
    adjustment_in numeric default 0,
    sales_out numeric default 0,
    adjustment_out numeric default 0,
    other_in numeric default 0,
    other_out numeric default 0,
    closing_qty numeric default 0,
    saved_at timestamp with time zone default now(),
    unique(branch_code, snapshot_date, ingredient_code)
);
        """,
        language="sql",
    )



# -----------------------------
# Database connection diagnostics
# -----------------------------
def page_database_connection_test(branch_code: str):
    section_title(
        "Database Connection Test",
        "Use this page when Supabase tables exist but the app shows no data. It does not show your secret keys.",
    )

    url = str(st.secrets.get("SUPABASE_URL", "")).strip()
    service_key = str(st.secrets.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    anon_key = str(st.secrets.get("SUPABASE_ANON_KEY", "")).strip()

    st.write("### Secrets check")
    secrets_rows = [
        {"Setting": "SUPABASE_URL", "Status": "Found" if url else "Missing", "Note": url[:35] + "..." if url else "Add this in Streamlit secrets"},
        {"Setting": "SUPABASE_SERVICE_ROLE_KEY", "Status": "Found" if service_key else "Missing", "Note": "Recommended when RLS is enabled"},
        {"Setting": "SUPABASE_ANON_KEY", "Status": "Found" if anon_key else "Missing", "Note": "Fallback only. Can show empty data when RLS blocks reads"},
        {"Setting": "Logged-in branch_code", "Status": branch_code, "Note": "This must exactly match branches.branch_code"},
    ]
    st.dataframe(pd.DataFrame(secrets_rows), use_container_width=True, hide_index=True)

    if not url or not (service_key or anon_key):
        st.error("Supabase connection secrets are incomplete. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY.")
        return

    if not service_key and anon_key:
        st.warning(
            "You are using SUPABASE_ANON_KEY fallback. If RLS is enabled, Supabase may return empty tables. "
            "For this manager app, use SUPABASE_SERVICE_ROLE_KEY in Streamlit secrets."
        )

    st.write("### Table read test")
    tests = [
        ("branches", "branch_code, branch_name, active", None),
        ("ingredients", "ingredient_code, ingredient_name, base_unit, active", None),
        ("stock_ledger", "transaction_id, branch_code, ingredient_code, movement_type, qty_in, qty_out", branch_code),
        ("purchase_bill_header", "bill_id, branch_code, bill_date, supplier_name, invoice_no", branch_code),
    ]

    results = []
    previews = {}
    supabase = get_supabase_client()

    for table_name, cols, branch_filter in tests:
        try:
            q = supabase.table(table_name).select(cols)
            if branch_filter and table_name != "ingredients":
                q = q.eq("branch_code", branch_filter)
            res = q.limit(5).execute()
            df = supabase_result_to_df(res)
            results.append({
                "Table": table_name,
                "Result": "Readable",
                "Rows returned first 5": len(df),
                "Meaning": "OK" if len(df) > 0 else "Readable but no rows returned",
            })
            previews[table_name] = df
        except Exception as e:
            results.append({
                "Table": table_name,
                "Result": "Error",
                "Rows returned first 5": 0,
                "Meaning": str(e),
            })
            previews[table_name] = pd.DataFrame()

    st.dataframe(pd.DataFrame(results), use_container_width=True, hide_index=True)

    st.write("### Preview returned rows")
    for table_name, df in previews.items():
        with st.expander(f"{table_name} preview", expanded=False):
            if df.empty:
                st.info("No rows returned for this test.")
            else:
                st.dataframe(df, use_container_width=True, hide_index=True)

    st.write("### Most common causes")
    st.markdown(
        """
1. **Wrong Streamlit project secrets**: the app is connected to another Supabase project URL.
2. **Using anon key while RLS is enabled**: tables exist, but Supabase returns empty data.
3. **Branch code mismatch**: secrets say `BR001`, but Supabase has `br001`, `BR-001`, or another code.
4. **Data exists in Supabase dashboard but not in the selected project/environment**.
5. **Service role key copied with extra spaces or wrong key**.
        """
    )

    st.write("### Recommended Streamlit secrets")
    st.code(
        'SUPABASE_URL = "https://your-project-id.supabase.co"\n'
        'SUPABASE_SERVICE_ROLE_KEY = "your-service-role-key"\n\n'
        '[BRANCH_USERS.br001_manager]\n'
        'password = "your-password"\n'
        'branch_code = "BR001"\n'
        'branch_name = "Pattambi"\n'
        'display_name = "Pattambi Manager"',
        language="toml",
    )


# -----------------------------
# Main app
# -----------------------------
def main():
    if not check_login():
        return

    branch_code = get_logged_in_branch_code()
    branch_name = str(st.session_state.get("branch_name") or branch_code).strip()
    branch_label = branch_code if branch_name == branch_code else f"{branch_code} - {branch_name}"

    st.sidebar.title("📦 Inventory")
    st.sidebar.caption(f"Manager: {st.session_state.get('manager_name', '')}")
    st.sidebar.caption(f"Branch: {branch_label}")

    page = st.sidebar.radio(
        "Menu",
        [
            "Dashboard",
            "Add Purchase Bill",
            "Opening / Stock Count",
            "Stock Adjustment",
            "Sales Report Upload",
            "Current Stock",
            "Reports",
            "Database Connection Test",
            "Required Extra Tables",
        ],
    )

    st.sidebar.divider()
    if st.sidebar.button("Logout"):
        logout_user()
        st.rerun()

    st.title("Branch Inventory Manager")
    st.caption(f"Selected branch: {branch_label}")

    if page == "Dashboard":
        page_dashboard(branch_code)
    elif page == "Add Purchase Bill":
        page_add_purchase(branch_code)
    elif page == "Opening / Stock Count":
        page_stock_count(branch_code)
    elif page == "Stock Adjustment":
        page_adjustment(branch_code)
    elif page == "Sales Report Upload":
        page_sales_upload(branch_code)
    elif page == "Current Stock":
        page_current_stock(branch_code)
    elif page == "Reports":
        page_reports(branch_code)
    elif page == "Database Connection Test":
        page_database_connection_test(branch_code)
    elif page == "Required Extra Tables":
        page_schema_help()


if __name__ == "__main__":
    main()
