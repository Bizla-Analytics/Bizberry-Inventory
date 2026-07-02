from __future__ import annotations

from datetime import datetime, date, time, timedelta
from typing import Dict, List, Tuple, Set, Optional

import pandas as pd
import streamlit as st
from supabase import Client, create_client


# ============================================================
# Streamlit config
# ============================================================
st.set_page_config(
    page_title="Branch Inventory Manager",
    page_icon="📦",
    layout="wide",
)


# ============================================================
# Supabase connection
# ============================================================
@st.cache_resource
def get_supabase_client() -> Client:
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


def result_to_df(result) -> pd.DataFrame:
    if not result or not getattr(result, "data", None):
        return pd.DataFrame()
    return pd.DataFrame(result.data)


def clear_data_cache() -> None:
    try:
        st.cache_data.clear()
    except Exception:
        pass


def is_active_value(value) -> bool:
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ["true", "t", "1", "yes", "y", "active"]


def as_float(value, default: float = 0.0) -> float:
    try:
        if pd.isna(value):
            return default
        return float(value)
    except Exception:
        return default


def safe_iso_date(value) -> Optional[str]:
    if value is None or pd.isna(value):
        return None
    try:
        return pd.to_datetime(value).date().isoformat()
    except Exception:
        return None


# ============================================================
# Authentication
# ============================================================
def load_branch_users() -> Dict[str, Dict[str, str]]:
    """
    Streamlit secrets example:

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


def get_branch_details(branch_code: str) -> Optional[Dict[str, str]]:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("branches")
            .select("branch_code, branch_name, active")
            .eq("branch_code", branch_code)
            .limit(1)
            .execute()
        )
    except Exception as e:
        st.warning(f"Login branch exists in secrets, but branch table could not be read: {e}")
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


# ============================================================
# Core data readers
# ============================================================
@st.cache_data(ttl=30)
def get_ingredients(include_inactive: bool = False) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("ingredients")
            .select("ingredient_code, ingredient_name, category, base_unit, min_stock, source_type, active")
            .order("ingredient_name")
            .execute()
        )
    except Exception as e:
        st.error(f"Could not read ingredients table. Error: {e}")
        return pd.DataFrame()

    df = result_to_df(result)
    if df.empty:
        return df

    if not include_inactive and "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()

    for col in ["category", "source_type"]:
        if col not in df.columns:
            df[col] = None

    df["ingredient_code"] = df["ingredient_code"].astype(str).str.strip().str.upper()
    df["ingredient_name"] = df["ingredient_name"].astype(str).str.strip()
    df["base_unit"] = df["base_unit"].astype(str).str.strip()
    df["source_type"] = df["source_type"].fillna("Purchased").astype(str).str.strip()
    df["min_stock"] = pd.to_numeric(df.get("min_stock", 0), errors="coerce").fillna(0)
    return df


@st.cache_data(ttl=30)
def get_products(include_inactive: bool = False) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("products")
            .select("product_code, item_name, category_name, active")
            .order("item_name")
            .execute()
        )
        df = result_to_df(result)
    except Exception as e:
        st.error(f"Could not read products table. Error: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    if not include_inactive and "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()

    df["product_code"] = df["product_code"].astype(str).str.strip().str.upper()
    df["item_name"] = df["item_name"].astype(str).str.strip()
    df["item_name_clean"] = df["item_name"].str.lower()
    return df


@st.cache_data(ttl=30)
def get_sub_recipes(include_inactive: bool = False) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("sub_recipes")
            .select(
                "sub_recipe_code, sub_recipe_name, output_ingredient_code, expected_output_qty, "
                "output_unit, prep_type, main_equipment, standard_temperature, "
                "standard_process_minutes, standard_wastage_qty, standard_wastage_unit, "
                "shelf_life_days, data_status, active"
            )
            .order("sub_recipe_name")
            .execute()
        )
        df = result_to_df(result)
    except Exception as e:
        st.error(f"Could not read sub_recipes table. Error: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    if not include_inactive and "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()

    df["sub_recipe_code"] = df["sub_recipe_code"].astype(str).str.strip().str.upper()
    df["output_ingredient_code"] = df["output_ingredient_code"].astype(str).str.strip().str.upper()
    df["expected_output_qty"] = pd.to_numeric(df["expected_output_qty"], errors="coerce").fillna(0)
    df["prep_type"] = df["prep_type"].fillna("Countable").astype(str).str.strip()
    return df


@st.cache_data(ttl=30)
def get_recipe_ingredients(include_inactive: bool = False) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("recipe_ingredients")
            .select(
                "recipe_line_id, parent_type, parent_code, sequence, component_type, component_code, "
                "quantity, unit, waste_percent, process_loss_percent, active, note"
            )
            .order("parent_type")
            .order("parent_code")
            .order("sequence")
            .execute()
        )
        df = result_to_df(result)
    except Exception as e:
        st.error(f"Could not read recipe_ingredients table. Error: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    if not include_inactive and "active" in df.columns:
        df = df[df["active"].apply(is_active_value)].copy()

    df["parent_type"] = df["parent_type"].astype(str).str.strip()
    df["parent_type_norm"] = df["parent_type"].str.lower()
    df["parent_code"] = df["parent_code"].astype(str).str.strip().str.upper()
    df["component_type"] = df["component_type"].astype(str).str.strip()
    df["component_type_norm"] = df["component_type"].str.lower()
    df["component_code"] = df["component_code"].astype(str).str.strip().str.upper()
    df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0)
    df["waste_percent"] = pd.to_numeric(df.get("waste_percent", 0), errors="coerce").fillna(0)
    df["process_loss_percent"] = pd.to_numeric(df.get("process_loss_percent", 0), errors="coerce").fillna(0)
    return df


def get_stock_ledger_raw(branch_code: str, limit: Optional[int] = None) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        query = (
            supabase.table("stock_ledger")
            .select(
                "transaction_id, transaction_datetime, branch_code, ingredient_code, "
                "movement_type, qty_in, qty_out, reference_type, reference_id, note"
            )
            .eq("branch_code", branch_code)
            .order("transaction_id", desc=True)
        )
        if limit:
            query = query.limit(limit)
        df = result_to_df(query.execute())
    except Exception as e:
        st.error(f"Could not read stock_ledger table. Error: {e}")
        return pd.DataFrame()

    if df.empty:
        return df

    df["ingredient_code"] = df["ingredient_code"].astype(str).str.strip().str.upper()
    # Supabase may return timestamptz values as timezone-aware UTC.
    # Convert to local naive datetime so comparisons with datetime.combine(date, time) do not fail.
    df["transaction_datetime"] = (
        pd.to_datetime(df["transaction_datetime"], errors="coerce", utc=True)
        .dt.tz_convert("Asia/Kolkata")
        .dt.tz_localize(None)
    )
    for col in ["qty_in", "qty_out"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    return df


def get_current_stock(branch_code: str) -> pd.DataFrame:
    ingredients = get_ingredients()
    expected_cols = [
        "branch_code", "ingredient_code", "ingredient_name", "category", "base_unit",
        "source_type", "min_stock", "current_qty", "status",
    ]
    if ingredients.empty:
        return pd.DataFrame(columns=expected_cols)

    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        stock_sum = pd.DataFrame(columns=["ingredient_code", "qty_in", "qty_out"])
    else:
        stock_sum = ledger.groupby("ingredient_code", as_index=False)[["qty_in", "qty_out"]].sum()

    df = ingredients.merge(stock_sum, on="ingredient_code", how="left")
    df["qty_in"] = pd.to_numeric(df.get("qty_in", 0), errors="coerce").fillna(0)
    df["qty_out"] = pd.to_numeric(df.get("qty_out", 0), errors="coerce").fillna(0)
    df["current_qty"] = df["qty_in"] - df["qty_out"]
    df["branch_code"] = branch_code

    def stock_status(row):
        qty = as_float(row.get("current_qty"))
        min_stock = as_float(row.get("min_stock"))
        if qty < 0:
            return "Negative"
        if qty == 0:
            return "Out of Stock"
        if qty <= min_stock:
            return "Low"
        return "OK"

    df["status"] = df.apply(stock_status, axis=1)

    for col in expected_cols:
        if col not in df.columns:
            df[col] = None
    return df[expected_cols].sort_values("ingredient_name")


def get_stock_as_of(branch_code: str, ingredient_code: str, as_of_dt: datetime) -> float:
    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        return 0.0

    # Keep both sides timezone-naive in local app time.
    # This prevents: TypeError: Invalid comparison between dtype=datetime64[ns, UTC] and Timestamp.
    as_of_ts = pd.Timestamp(as_of_dt)
    if as_of_ts.tzinfo is not None:
        as_of_ts = as_of_ts.tz_convert("Asia/Kolkata").tz_localize(None)

    tx = pd.to_datetime(ledger["transaction_datetime"], errors="coerce")
    try:
        if getattr(tx.dt, "tz", None) is not None:
            tx = tx.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    except Exception:
        pass

    mask = (
        (ledger["ingredient_code"] == str(ingredient_code).strip().upper())
        & (tx < as_of_ts)
    )
    day = ledger[mask]
    if day.empty:
        return 0.0
    return float(day["qty_in"].sum() - day["qty_out"].sum())


def get_day_ledger(branch_code: str, target_date: date) -> pd.DataFrame:
    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        return ledger
    return ledger[ledger["transaction_datetime"].dt.date == target_date].copy()


def add_stock_ledger(
    branch_code: str,
    ingredient_code: str,
    movement_type: str,
    qty_in: float,
    qty_out: float,
    reference_type: Optional[str] = None,
    reference_id: Optional[str] = None,
    note: Optional[str] = None,
    transaction_datetime: Optional[datetime] = None,
) -> None:
    supabase = get_supabase_client()
    dt = transaction_datetime or datetime.now()
    supabase.table("stock_ledger").insert({
        "transaction_datetime": dt.isoformat(timespec="seconds"),
        "branch_code": branch_code,
        "ingredient_code": str(ingredient_code).strip().upper(),
        "movement_type": movement_type,
        "qty_in": float(qty_in or 0),
        "qty_out": float(qty_out or 0),
        "reference_type": reference_type,
        "reference_id": str(reference_id) if reference_id is not None else None,
        "note": note,
    }).execute()
    clear_data_cache()


def insert_ledger_many(payload: List[dict]) -> None:
    if not payload:
        return
    supabase = get_supabase_client()
    for i in range(0, len(payload), 500):
        supabase.table("stock_ledger").insert(payload[i:i + 500]).execute()
    clear_data_cache()


# ============================================================
# Recipe calculation engine
# ============================================================
def recipe_rows(recipe_df: pd.DataFrame, parent_type: str, parent_code: str) -> pd.DataFrame:
    if recipe_df.empty:
        return pd.DataFrame()
    return recipe_df[
        (recipe_df["parent_type_norm"] == parent_type.strip().lower())
        & (recipe_df["parent_code"] == parent_code.strip().upper())
    ].copy()


def add_waste(qty: float, waste_percent: float, process_loss_percent: float = 0) -> float:
    return float(qty or 0) * (1 + float(waste_percent or 0) / 100) * (1 + float(process_loss_percent or 0) / 100)


def explode_sub_recipe_to_raw_ingredients(
    recipe_df: pd.DataFrame,
    sub_df: pd.DataFrame,
    sub_recipe_code: str,
    required_output_qty: float,
    visited: Optional[Set[str]] = None,
    depth: int = 0,
    max_depth: int = 20,
) -> List[Dict[str, object]]:
    """
    Backflush a sub recipe into ingredient consumption.

    If SUB001 output is 625 g and product needs 140 g, factor = 140 / 625.
    Each SUB001 detail line input is multiplied by that factor.
    Nested sub recipes are also scaled by their expected output.
    """
    if visited is None:
        visited = set()

    sub_code = str(sub_recipe_code).strip().upper()
    if depth > max_depth:
        raise ValueError(f"Recipe nesting too deep near {sub_code}.")
    if sub_code in visited:
        raise ValueError(f"Circular sub recipe detected near {sub_code}.")

    visited.add(sub_code)

    sub_row = sub_df[sub_df["sub_recipe_code"] == sub_code]
    if sub_row.empty:
        raise ValueError(f"Sub recipe `{sub_code}` not found in sub_recipes table.")

    expected_output = as_float(sub_row.iloc[0]["expected_output_qty"])
    if expected_output <= 0:
        raise ValueError(f"Sub recipe `{sub_code}` has invalid expected_output_qty.")

    factor = float(required_output_qty or 0) / expected_output
    rows = recipe_rows(recipe_df, "Sub Recipe", sub_code)
    if rows.empty:
        raise ValueError(f"Sub recipe `{sub_code}` has no detail rows in recipe_ingredients.")

    out: List[Dict[str, object]] = []
    for _, row in rows.iterrows():
        component_type = str(row["component_type_norm"]).strip().lower()
        component_code = str(row["component_code"]).strip().upper()
        base_qty = float(row["quantity"] or 0) * factor
        qty_with_waste = add_waste(base_qty, row.get("waste_percent", 0), row.get("process_loss_percent", 0))

        if component_type == "ingredient":
            out.append({
                "ingredient_code": component_code,
                "used_qty": qty_with_waste,
                "calculation_note": f"Backflush {sub_code}",
            })
        elif component_type == "sub recipe":
            nested = explode_sub_recipe_to_raw_ingredients(
                recipe_df=recipe_df,
                sub_df=sub_df,
                sub_recipe_code=component_code,
                required_output_qty=qty_with_waste,
                visited=visited.copy(),
                depth=depth + 1,
                max_depth=max_depth,
            )
            out.extend(nested)
        else:
            raise ValueError(f"Invalid component_type `{row['component_type']}` in sub recipe {sub_code}.")

    visited.remove(sub_code)
    return out


def calculate_product_consumption(
    product_code: str,
    sold_qty: float,
    recipe_df: pd.DataFrame,
    sub_df: pd.DataFrame,
) -> List[Dict[str, object]]:
    """
    Product sales consumption logic:
    - Product -> Ingredient: deduct ingredient directly.
    - Product -> Countable Sub Recipe: deduct the output ingredient/prep stock.
    - Product -> Virtual Sub Recipe: backflush SOP into raw ingredients.
    """
    pcode = str(product_code).strip().upper()
    rows = recipe_rows(recipe_df, "Product", pcode)
    if rows.empty:
        return []

    out: List[Dict[str, object]] = []
    for _, row in rows.iterrows():
        component_type = str(row["component_type_norm"]).strip().lower()
        component_code = str(row["component_code"]).strip().upper()
        base_qty = float(row["quantity"] or 0) * float(sold_qty or 0)
        qty_with_waste = add_waste(base_qty, row.get("waste_percent", 0), row.get("process_loss_percent", 0))

        if component_type == "ingredient":
            out.append({
                "ingredient_code": component_code,
                "used_qty": qty_with_waste,
                "calculation_note": "Direct product ingredient",
            })
        elif component_type == "sub recipe":
            sub_row = sub_df[sub_df["sub_recipe_code"] == component_code]
            if sub_row.empty:
                raise ValueError(f"Product {pcode} uses missing sub recipe `{component_code}`.")

            prep_type = str(sub_row.iloc[0].get("prep_type") or "Countable").strip().lower()
            output_ing = str(sub_row.iloc[0]["output_ingredient_code"]).strip().upper()

            if prep_type == "countable":
                out.append({
                    "ingredient_code": output_ing,
                    "used_qty": qty_with_waste,
                    "calculation_note": f"Countable prep {component_code}",
                })
            elif prep_type == "virtual":
                out.extend(
                    explode_sub_recipe_to_raw_ingredients(
                        recipe_df=recipe_df,
                        sub_df=sub_df,
                        sub_recipe_code=component_code,
                        required_output_qty=qty_with_waste,
                    )
                )
            else:
                raise ValueError(f"Sub recipe {component_code} has invalid prep_type `{prep_type}`.")
        else:
            raise ValueError(f"Invalid component_type `{row['component_type']}` for product {pcode}.")

    return out


def calculate_sub_recipe_raw_consumption(
    sub_recipe_code: str,
    prepared_qty: float,
    recipe_df: pd.DataFrame,
    sub_df: pd.DataFrame,
) -> pd.DataFrame:
    rows = explode_sub_recipe_to_raw_ingredients(
        recipe_df=recipe_df,
        sub_df=sub_df,
        sub_recipe_code=sub_recipe_code,
        required_output_qty=prepared_qty,
    )
    df = pd.DataFrame(rows)
    if df.empty:
        return pd.DataFrame(columns=["ingredient_code", "used_qty"])
    return df.groupby("ingredient_code", as_index=False).agg(used_qty=("used_qty", "sum"))


def enrich_ingredients(df: pd.DataFrame, code_col: str = "ingredient_code") -> pd.DataFrame:
    ingredients = get_ingredients(include_inactive=True)
    if df.empty or ingredients.empty or code_col not in df.columns:
        return df
    return df.merge(
        ingredients[["ingredient_code", "ingredient_name", "base_unit", "source_type"]],
        left_on=code_col,
        right_on="ingredient_code",
        how="left",
        suffixes=("", "_ing"),
    )


# ============================================================
# Sales upload helpers
# ============================================================
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


def create_sales_batch(branch_code: str, sales_date: date, uploaded_filename: str, row_count: int) -> str:
    batch_id = f"{branch_code}-{sales_date.isoformat()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    supabase = get_supabase_client()
    supabase.table("sales_upload_batches").insert({
        "batch_id": batch_id,
        "branch_code": branch_code,
        "sales_date": sales_date.isoformat(),
        "uploaded_filename": uploaded_filename,
        "row_count": int(row_count),
        "uploaded_at": datetime.now().isoformat(timespec="seconds"),
        "uploaded_by": st.session_state.get("username"),
    }).execute()
    return batch_id


def insert_sales_lines(batch_id: str, branch_code: str, sales_date: date, sales_df: pd.DataFrame) -> None:
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
    for i in range(0, len(payload), 500):
        supabase.table("sales_upload_lines").insert(payload[i:i + 500]).execute()


def insert_consumption_rows(
    batch_id: str,
    branch_code: str,
    sales_date: date,
    consumption_df: pd.DataFrame,
    source: str = "Sales",
) -> None:
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
            "ingredient_code": str(r.get("ingredient_code") or "").strip().upper(),
            "used_qty": float(r.get("used_qty") or 0),
            "consumption_source": source,
            "calculation_note": str(r.get("calculation_note") or ""),
        })
    for i in range(0, len(payload), 500):
        supabase.table("sales_recipe_consumption").insert(payload[i:i + 500]).execute()


# ============================================================
# Reports
# ============================================================
def get_stock_ledger_report(branch_code: str, limit: Optional[int] = None) -> pd.DataFrame:
    ledger = get_stock_ledger_raw(branch_code, limit=limit)
    if ledger.empty:
        return ledger

    ingredients = get_ingredients(include_inactive=True)
    if not ingredients.empty:
        ledger = ledger.merge(
            ingredients[["ingredient_code", "ingredient_name", "base_unit", "source_type"]],
            on="ingredient_code",
            how="left",
        )

    cols = [
        "transaction_id", "transaction_datetime", "branch_code", "ingredient_name",
        "ingredient_code", "base_unit", "source_type", "movement_type", "qty_in", "qty_out",
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
            supabase.table("purchase_bill_header")
            .select("*")
            .eq("branch_code", branch_code)
            .order("bill_id", desc=True)
            .execute()
        )
        return result_to_df(result)
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
        lines = result_to_df(
            supabase.table("purchase_bill_lines")
            .select("*")
            .in_("bill_id", bill_ids)
            .order("line_id")
            .execute()
        )
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
        "bill_date", "supplier_name", "invoice_no", "ingredient_name", "ingredient_code",
        "base_qty", "unit", "total_price", "unit_price",
    ]
    result = df[cols].copy()
    result["unit_price"] = pd.to_numeric(result["unit_price"], errors="coerce").round(3)
    return result.sort_values(["ingredient_name", "bill_date"], ascending=[True, False])


def get_prep_production_report(branch_code: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        batches = result_to_df(
            supabase.table("prep_production_batches")
            .select("*")
            .eq("branch_code", branch_code)
            .order("prep_batch_id", desc=True)
            .execute()
        )
    except Exception as e:
        st.error(f"Could not read prep_production_batches. Error: {e}")
        return pd.DataFrame()
    return batches


# ============================================================
# UI helpers
# ============================================================
def section_title(title: str, caption: Optional[str] = None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def ingredient_options_with_units(ingredients: pd.DataFrame) -> Dict[str, pd.Series]:
    labels: Dict[str, pd.Series] = {}
    for _, row in ingredients.iterrows():
        label = f'{row["ingredient_code"]} - {row["ingredient_name"]} ({row["base_unit"]})'
        labels[label] = row
    return labels


def product_options(products: pd.DataFrame) -> Dict[str, pd.Series]:
    labels: Dict[str, pd.Series] = {}
    for _, row in products.iterrows():
        label = f'{row["product_code"]} - {row["item_name"]}'
        labels[label] = row
    return labels


def show_download_button(df: pd.DataFrame, file_name: str, label: str = "Download CSV"):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(label, data=csv, file_name=file_name, mime="text/csv", use_container_width=True)


def post_ledger_for_consumption(
    branch_code: str,
    target_date: date,
    consumption_summary: pd.DataFrame,
    movement_type: str,
    reference_type: str,
    reference_id: str,
    note: str,
    transaction_time: time = time(23, 59, 0),
) -> None:
    tx_dt = datetime.combine(target_date, transaction_time)
    ledger_payload = []
    for _, r in consumption_summary.iterrows():
        qty = as_float(r.get("used_qty"))
        if qty <= 0:
            continue
        ledger_payload.append({
            "transaction_datetime": tx_dt.isoformat(timespec="seconds"),
            "branch_code": branch_code,
            "ingredient_code": str(r["ingredient_code"]).strip().upper(),
            "movement_type": movement_type,
            "qty_in": 0,
            "qty_out": qty,
            "reference_type": reference_type,
            "reference_id": reference_id,
            "note": note,
        })
    insert_ledger_many(ledger_payload)



# ============================================================
# Morning count draft + auto close helpers
# ============================================================
def stock_count_draft_id(branch_code: str, count_date: date) -> str:
    return f"{branch_code}-{count_date.isoformat()}"


def get_or_create_stock_count_draft(branch_code: str, count_date: date) -> Dict[str, object]:
    """One draft per branch per morning count date."""
    supabase = get_supabase_client()
    draft_id = stock_count_draft_id(branch_code, count_date)
    result = (
        supabase.table("stock_count_drafts")
        .select("*")
        .eq("draft_id", draft_id)
        .limit(1)
        .execute()
    )
    if result.data:
        return result.data[0]

    payload = {
        "draft_id": draft_id,
        "branch_code": branch_code,
        "count_date": count_date.isoformat(),
        "closing_for_date": (count_date - timedelta(days=1)).isoformat(),
        "status": "DRAFT",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "created_by": st.session_state.get("username"),
        "posted_at": None,
        "posted_by": None,
        "posted_note": None,
    }
    supabase.table("stock_count_drafts").insert(payload).execute()
    return payload


def load_stock_count_draft_lines(draft_id: str) -> pd.DataFrame:
    supabase = get_supabase_client()
    try:
        result = (
            supabase.table("stock_count_draft_lines")
            .select("*")
            .eq("draft_id", draft_id)
            .order("ingredient_name")
            .execute()
        )
        return result_to_df(result)
    except Exception as e:
        st.warning(f"Could not read saved stock count draft lines: {e}")
        return pd.DataFrame()


def save_stock_count_draft_lines(draft_id: str, branch_code: str, count_date: date, edited: pd.DataFrame) -> None:
    """Persist the manager's count work so refresh/network issues do not lose it."""
    if edited.empty:
        return

    supabase = get_supabase_client()
    now = datetime.now().isoformat(timespec="seconds")
    payload = []
    for _, row in edited.iterrows():
        ing_code = str(row.get("ingredient_code") or "").strip().upper()
        if not ing_code:
            continue
        payload.append({
            "draft_id": draft_id,
            "branch_code": branch_code,
            "count_date": count_date.isoformat(),
            "ingredient_code": ing_code,
            "ingredient_name": str(row.get("ingredient_name") or ""),
            "source_type": str(row.get("source_type") or ""),
            "base_unit": str(row.get("base_unit") or ""),
            "system_qty_at_load": as_float(row.get("current_qty")),
            "physical_qty": as_float(row.get("physical_qty")),
            "prep_wastage_qty": as_float(row.get("prep_wastage_qty")),
            "reason": str(row.get("reason") or ""),
            "updated_at": now,
            "updated_by": st.session_state.get("username"),
        })

    if not payload:
        return

    # Requires unique index on (draft_id, ingredient_code), included in the SQL file.
    supabase.table("stock_count_draft_lines").upsert(
        payload,
        on_conflict="draft_id,ingredient_code",
    ).execute()

    supabase.table("stock_count_drafts").update({
        "updated_at": now,
        "updated_by": st.session_state.get("username"),
    }).eq("draft_id", draft_id).execute()


def build_morning_count_table(branch_code: str, draft_id: str) -> pd.DataFrame:
    stock = get_current_stock(branch_code)
    if stock.empty:
        return stock

    count_df = stock[["ingredient_code", "ingredient_name", "source_type", "base_unit", "current_qty"]].copy()
    count_df["physical_qty"] = count_df["current_qty"]
    count_df["prep_wastage_qty"] = 0.0
    count_df["reason"] = ""

    saved = load_stock_count_draft_lines(draft_id)
    if not saved.empty:
        keep = ["ingredient_code", "physical_qty", "prep_wastage_qty", "reason"]
        saved = saved[[c for c in keep if c in saved.columns]].copy()
        saved["ingredient_code"] = saved["ingredient_code"].astype(str).str.strip().str.upper()
        count_df = count_df.merge(saved, on="ingredient_code", how="left", suffixes=("", "_saved"))
        for col in ["physical_qty", "prep_wastage_qty", "reason"]:
            saved_col = f"{col}_saved"
            if saved_col in count_df.columns:
                count_df[col] = count_df[saved_col].where(count_df[saved_col].notna(), count_df[col])
                count_df = count_df.drop(columns=[saved_col])

    count_df["prep_wastage_qty"] = pd.to_numeric(count_df["prep_wastage_qty"], errors="coerce").fillna(0)
    count_df["physical_qty"] = pd.to_numeric(count_df["physical_qty"], errors="coerce").fillna(0)
    return count_df.sort_values(["source_type", "ingredient_name"])


def countable_output_map() -> Dict[str, Dict[str, object]]:
    countable = get_countable_prep_table()
    if countable.empty:
        return {}
    out = {}
    for _, row in countable.iterrows():
        output_ing = str(row.get("output_ingredient_code") or "").strip().upper()
        if output_ing:
            out[output_ing] = {
                "sub_recipe_code": str(row.get("sub_recipe_code") or "").strip().upper(),
                "prep_item": row.get("ingredient_name") or row.get("sub_recipe_name") or output_ing,
                "unit": row.get("base_unit") or row.get("output_unit") or "",
            }
    return out


def ledger_exists_before(branch_code: str, before_dt: datetime) -> bool:
    ledger = get_stock_ledger_raw(branch_code)
    if ledger.empty:
        return False
    return not ledger[ledger["transaction_datetime"] < pd.Timestamp(before_dt)].empty


def has_sales_upload_for_date(branch_code: str, target_date: date) -> bool:
    ledger = get_day_ledger(branch_code, target_date)
    if ledger.empty:
        return False
    return not ledger[ledger["movement_type"] == "Sales Recipe Consumption"].empty


def draft_already_posted(draft: Dict[str, object]) -> bool:
    return str(draft.get("status") or "").strip().upper() == "POSTED"


def post_morning_stock_count_and_auto_prep(
    branch_code: str,
    count_date: date,
    draft: Dict[str, object],
    edited: pd.DataFrame,
) -> Tuple[int, int, int, List[str]]:
    """
    Save one morning count.

    - Purchased/Both items: post physical count differences.
    - Countable produced prep items: calculate yesterday auto prep from morning count.
    - If it is the first day/no prior ledger, treat count as initial stock and skip auto prep.
    """
    if draft_already_posted(draft):
        return 0, 0, 0, ["This draft is already posted. No duplicate ledger entries were created."]

    supabase = get_supabase_client()
    draft_id = str(draft["draft_id"])
    production_date = count_date - timedelta(days=1)
    start_dt = datetime.combine(production_date, time(0, 0, 0))
    end_dt = datetime.combine(count_date, time(0, 0, 0))

    countable_map = countable_output_map()
    recipe_df = get_recipe_ingredients()
    sub_df = get_sub_recipes()

    first_day_mode = not ledger_exists_before(branch_code, end_dt)
    has_yesterday_sales = has_sales_upload_for_date(branch_code, production_date)

    adjustment_count = 0
    prep_batch_count = 0
    prep_line_count = 0
    warnings: List[str] = []

    # First day / new branch: count becomes opening stock, no auto prep because there is no previous day POS/SOP base.
    if first_day_mode:
        tx_dt = datetime.combine(count_date, time(7, 0, 0))
        ledger_payload = []
        for _, row in edited.iterrows():
            physical_qty = as_float(row.get("physical_qty"))
            if physical_qty <= 0:
                continue
            ledger_payload.append({
                "transaction_datetime": tx_dt.isoformat(timespec="seconds"),
                "branch_code": branch_code,
                "ingredient_code": str(row["ingredient_code"]).strip().upper(),
                "movement_type": "Initial Stock Count",
                "qty_in": physical_qty,
                "qty_out": 0,
                "reference_type": "Morning Stock Count Draft",
                "reference_id": draft_id,
                "note": row.get("reason") or "Initial stock loaded from morning count",
            })
        insert_ledger_many(ledger_payload)
        adjustment_count = len(ledger_payload)
        warnings.append("First stock count detected, so auto prep was skipped and physical quantities were loaded as initial stock.")
    else:
        # Normal mode: close yesterday using today's morning physical count.
        for _, row in edited.iterrows():
            ing_code = str(row.get("ingredient_code") or "").strip().upper()
            physical_qty = as_float(row.get("physical_qty"))
            prep_wastage_qty = as_float(row.get("prep_wastage_qty"))
            reason = str(row.get("reason") or "").strip()
            system_end_qty = get_stock_as_of(branch_code, ing_code, end_dt)
            diff = round(physical_qty - system_end_qty, 6)

            # Countable prep items are handled by auto prep, not direct physical adjustment, when possible.
            if ing_code in countable_map:
                prep_info = countable_map[ing_code]
                sub_code = str(prep_info["sub_recipe_code"])
                opening_qty = get_stock_as_of(branch_code, ing_code, start_dt)
                day_ledger = get_day_ledger(branch_code, production_date)

                if day_ledger.empty:
                    sales_usage = 0.0
                    ledger_wastage = 0.0
                else:
                    same_ing = day_ledger[day_ledger["ingredient_code"] == ing_code]
                    sales_usage = float(same_ing[same_ing["movement_type"] == "Sales Recipe Consumption"]["qty_out"].sum())
                    ledger_wastage = float(same_ing[same_ing["movement_type"].isin(["Prep Item Wastage"])]["qty_out"].sum())

                total_wastage = ledger_wastage + prep_wastage_qty
                prepared_qty = round(physical_qty + sales_usage + total_wastage - opening_qty, 6)

                # If manager enters wastage in the morning count, post it as yesterday prep wastage.
                if prep_wastage_qty > 0:
                    add_stock_ledger(
                        branch_code=branch_code,
                        ingredient_code=ing_code,
                        movement_type="Prep Item Wastage",
                        qty_in=0,
                        qty_out=prep_wastage_qty,
                        reference_type="Morning Stock Count Draft",
                        reference_id=draft_id,
                        note=reason or "Prep wastage entered during morning count",
                        transaction_datetime=datetime.combine(production_date, time(23, 57, 0)),
                    )
                    adjustment_count += 1

                if prepared_qty > 0 and has_yesterday_sales:
                    try:
                        batch_result = supabase.table("prep_production_batches").insert({
                            "branch_code": branch_code,
                            "production_date": production_date.isoformat(),
                            "sub_recipe_code": sub_code,
                            "output_ingredient_code": ing_code,
                            "prepared_qty": prepared_qty,
                            "output_unit": str(prep_info.get("unit") or row.get("base_unit") or ""),
                            "calculation_type": "Auto From Morning Count",
                            "opening_qty": opening_qty,
                            "sales_usage_qty": sales_usage,
                            "wastage_qty": total_wastage,
                            "closing_physical_qty": physical_qty,
                            "note": reason,
                            "created_at": datetime.now().isoformat(timespec="seconds"),
                            "created_by": st.session_state.get("username"),
                        }).execute()

                        prep_batch_id = batch_result.data[0]["prep_batch_id"]
                        tx_dt = datetime.combine(production_date, time(23, 58, 0))

                        add_stock_ledger(
                            branch_code=branch_code,
                            ingredient_code=ing_code,
                            movement_type="Prep Production Output",
                            qty_in=prepared_qty,
                            qty_out=0,
                            reference_type="Morning Stock Count Draft",
                            reference_id=str(prep_batch_id),
                            note=f"{sub_code} auto production from morning count. Draft {draft_id}. {reason}",
                            transaction_datetime=tx_dt,
                        )

                        raw_df = calculate_sub_recipe_raw_consumption(sub_code, prepared_qty, recipe_df, sub_df)
                        line_payload = []
                        ledger_payload = []
                        for _, raw in raw_df.iterrows():
                            component_ing = str(raw["ingredient_code"]).strip().upper()
                            used_qty = as_float(raw["used_qty"])
                            if used_qty <= 0:
                                continue
                            line_payload.append({
                                "prep_batch_id": prep_batch_id,
                                "component_ingredient_code": component_ing,
                                "used_qty": used_qty,
                                "unit": None,
                                "note": f"Raw consumption for {sub_code} from morning count draft {draft_id}",
                            })
                            ledger_payload.append({
                                "transaction_datetime": tx_dt.isoformat(timespec="seconds"),
                                "branch_code": branch_code,
                                "ingredient_code": component_ing,
                                "movement_type": "Prep Production Consumption",
                                "qty_in": 0,
                                "qty_out": used_qty,
                                "reference_type": "Morning Stock Count Draft",
                                "reference_id": str(prep_batch_id),
                                "note": f"Raw material used to produce {sub_code} from morning count draft {draft_id}",
                            })

                        if line_payload:
                            supabase.table("prep_production_lines").insert(line_payload).execute()
                        insert_ledger_many(ledger_payload)
                        prep_batch_count += 1
                        prep_line_count += len(line_payload)
                    except Exception as e:
                        warnings.append(f"Auto prep failed for {ing_code} / {sub_code}: {e}")
                else:
                    # No positive production. Correct the remaining physical difference if any.
                    # This handles shortage/missing countable prep without falsely creating production.
                    if abs(diff) > 0.000001:
                        add_stock_ledger(
                            branch_code=branch_code,
                            ingredient_code=ing_code,
                            movement_type="Physical Count Adjustment In" if diff > 0 else "Physical Count Adjustment Out",
                            qty_in=diff if diff > 0 else 0,
                            qty_out=abs(diff) if diff < 0 else 0,
                            reference_type="Morning Stock Count Draft",
                            reference_id=draft_id,
                            note=reason or "Morning physical count difference for countable prep",
                            transaction_datetime=datetime.combine(production_date, time(23, 59, 30)),
                        )
                        adjustment_count += 1
                    if prepared_qty > 0 and not has_yesterday_sales:
                        warnings.append(f"{ing_code}: positive prep was detected but yesterday POS sales are not uploaded, so auto prep was not posted.")
                continue

            # Purchased / non-countable items: normal physical count difference.
            if abs(diff) > 0.000001:
                add_stock_ledger(
                    branch_code=branch_code,
                    ingredient_code=ing_code,
                    movement_type="Physical Count Adjustment In" if diff > 0 else "Physical Count Adjustment Out",
                    qty_in=diff if diff > 0 else 0,
                    qty_out=abs(diff) if diff < 0 else 0,
                    reference_type="Morning Stock Count Draft",
                    reference_id=draft_id,
                    note=reason or "Morning physical count difference",
                    transaction_datetime=datetime.combine(production_date, time(23, 59, 30)),
                )
                adjustment_count += 1

    save_stock_day_snapshot(branch_code, count_date - timedelta(days=1))
    save_stock_day_snapshot(branch_code, count_date)

    supabase.table("stock_count_drafts").update({
        "status": "POSTED",
        "posted_at": datetime.now().isoformat(timespec="seconds"),
        "posted_by": st.session_state.get("username"),
        "posted_note": f"Adjustments: {adjustment_count}, prep batches: {prep_batch_count}, prep lines: {prep_line_count}",
    }).eq("draft_id", draft_id).execute()

    clear_data_cache()
    return adjustment_count, prep_batch_count, prep_line_count, warnings

# ============================================================
# Pages
# ============================================================
def page_dashboard(branch_code: str):
    section_title("Dashboard", "Quick stock status for your branch.")
    stock = get_current_stock(branch_code)
    if stock.empty:
        st.warning("No ingredients found in Supabase, or stock ledger is not readable.")
        return

    total_items = len(stock)
    low_items = int((stock["status"] == "Low").sum())
    out_items = int((stock["status"] == "Out of Stock").sum())
    neg_items = int((stock["status"] == "Negative").sum())

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Items", total_items)
    c2.metric("Low Stock", low_items)
    c3.metric("Out of Stock", out_items)
    c4.metric("Negative Stock", neg_items)

    st.divider()
    st.write("### Problem stock")
    problem = stock[stock["status"].isin(["Low", "Out of Stock", "Negative"])]
    if problem.empty:
        st.success("No low, out, or negative stock items for this branch.")
    else:
        st.dataframe(problem, use_container_width=True, hide_index=True)

    st.write("### Latest stock movements")
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
                ingredient_code = str(selected_row["ingredient_code"]).strip().upper()
                base_unit = str(selected_row["base_unit"]).strip()
                base_qty = as_float(line["Quantity In Base Unit"])
                total_price = as_float(line["Total Price"])
                unit_price = total_price / base_qty if base_qty else 0
                expiry_date = safe_iso_date(line.get("Expiry Date"))

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
            insert_ledger_many(ledger_payload)

            st.success(f"Purchase bill saved. Bill ID: {bill_id}")
            st.session_state.purchase_form_version += 1
            st.rerun()

        except Exception as e:
            st.error(f"Could not save purchase bill. Error: {e}")


def page_stock_count(branch_code: str):
    section_title(
        "Morning Stock Count / Close Yesterday",
        "Enter today morning physical count. This closes yesterday and becomes today's opening stock. Countable prep is calculated automatically on final post.",
    )

    count_date = st.date_input("Morning Count Date", value=date.today())
    production_date = count_date - timedelta(days=1)
    st.caption(
        f"This count will close: {production_date.isoformat()} and become opening stock for: {count_date.isoformat()}."
    )

    draft = get_or_create_stock_count_draft(branch_code, count_date)
    draft_id = str(draft["draft_id"])

    if draft_already_posted(draft):
        st.success("This morning count draft is already posted to the stock ledger.")
        posted = load_stock_count_draft_lines(draft_id)
        if not posted.empty:
            st.dataframe(posted, use_container_width=True, hide_index=True)
        return

    # ------------------------------------------------------------------
    # IMPORTANT: Load from Supabase only once per browser session/date.
    # Do not rebuild the editor from Supabase on every rerun, because it
    # interrupts typing and moves the manager back to the top of the table.
    # ------------------------------------------------------------------
    editor_df_key = f"morning_count_df_{draft_id}"
    editor_widget_key = f"morning_stock_count_editor_{draft_id}"
    last_saved_key = f"morning_count_last_saved_{draft_id}"

    if editor_df_key not in st.session_state:
        st.session_state[editor_df_key] = build_morning_count_table(branch_code, draft_id)

    if st.session_state[editor_df_key].empty:
        st.warning("No ingredients found.")
        return

    top1, top2 = st.columns([2, 1])
    with top1:
        type_filter = st.multiselect(
            "Item Type",
            ["Purchased", "Produced", "Both"],
            default=["Purchased", "Produced", "Both"],
            help="This only filters the visible rows. It does not delete hidden draft rows.",
        )
    with top2:
        if st.button("Reload Saved Draft", use_container_width=True):
            # User-controlled reload only. This may move the table, but it is intentional.
            st.session_state[editor_df_key] = build_morning_count_table(branch_code, draft_id)
            st.success("Saved draft reloaded from Supabase.")

    full_df = st.session_state[editor_df_key].copy()
    visible_mask = full_df["source_type"].isin(type_filter)
    visible_df = full_df[visible_mask].copy()

    st.info(
        "The table is kept in browser session while editing. It will not save on every rerun. "
        "Use Save Draft to store progress in Supabase, and Post Final only when the count is complete."
    )

    with st.form(f"morning_count_form_{draft_id}", clear_on_submit=False):
        edited_visible = st.data_editor(
            visible_df,
            use_container_width=True,
            hide_index=True,
            key=editor_widget_key,
            column_config={
                "ingredient_code": st.column_config.TextColumn("Code", disabled=True),
                "ingredient_name": st.column_config.TextColumn("Ingredient", disabled=True),
                "source_type": st.column_config.TextColumn("Type", disabled=True),
                "base_unit": st.column_config.TextColumn("Unit", disabled=True),
                "current_qty": st.column_config.NumberColumn("System Stock Now", disabled=True),
                "physical_qty": st.column_config.NumberColumn("Morning Physical Count", step=1.0),
                "prep_wastage_qty": st.column_config.NumberColumn(
                    "Prep Wastage Qty",
                    step=1.0,
                    help="Use mainly for countable prep items when manager knows yesterday prep was wasted/spoiled.",
                ),
                "reason": st.column_config.TextColumn("Reason / Note"),
            },
        )

        c1, c2 = st.columns(2)
        save_pressed = c1.form_submit_button("Save Draft", use_container_width=True)
        post_pressed = c2.form_submit_button("Post Final Count & Auto Prep", use_container_width=True, type="primary")

    # Merge only visible edited rows back into the full session dataframe.
    # This keeps hidden rows safe when the manager uses the item type filter.
    if not edited_visible.empty:
        edited_visible = edited_visible.copy()
        edited_visible["ingredient_code"] = edited_visible["ingredient_code"].astype(str).str.strip().str.upper()
        full_df = full_df.copy()
        full_df["ingredient_code"] = full_df["ingredient_code"].astype(str).str.strip().str.upper()
        full_df = full_df.set_index("ingredient_code")
        edited_visible = edited_visible.set_index("ingredient_code")
        for col in edited_visible.columns:
            if col in full_df.columns:
                full_df.loc[edited_visible.index, col] = edited_visible[col]
        full_df = full_df.reset_index()
        st.session_state[editor_df_key] = full_df

    edited = st.session_state[editor_df_key].copy()

    if save_pressed:
        try:
            save_stock_count_draft_lines(draft_id, branch_code, count_date, edited)
            st.session_state[last_saved_key] = datetime.now().strftime("%d/%m/%Y %I:%M:%S %p")
            st.success("Draft saved to Supabase. You can close/reopen this page and continue from this saved point.")
        except Exception as e:
            st.error(f"Could not save draft. Error: {e}")

    if st.session_state.get(last_saved_key):
        st.caption(f"Last manually saved: {st.session_state[last_saved_key]}")

    countable_map = countable_output_map()
    preview_rows = []
    start_dt = datetime.combine(production_date, time(0, 0, 0))
    end_dt = datetime.combine(count_date, time(0, 0, 0))
    day_ledger = get_day_ledger(branch_code, production_date)

    for _, row in edited.iterrows():
        ing_code = str(row.get("ingredient_code") or "").strip().upper()
        physical_qty = as_float(row.get("physical_qty"))
        current_qty = as_float(row.get("current_qty"))
        system_end_qty = get_stock_as_of(branch_code, ing_code, end_dt)
        prep_wastage_qty = as_float(row.get("prep_wastage_qty"))

        preview = {
            "ingredient_code": ing_code,
            "ingredient_name": row.get("ingredient_name"),
            "source_type": row.get("source_type"),
            "system_stock_now": current_qty,
            "morning_physical_qty": physical_qty,
            "difference_if_adjusted": round(physical_qty - system_end_qty, 6),
            "auto_prep_sub_recipe": "",
            "sales_usage_yesterday": 0.0,
            "prep_wastage_yesterday": prep_wastage_qty,
            "calculated_prepared_qty": 0.0,
            "posting_action": "Physical count difference",
        }

        if ing_code in countable_map:
            sub_code = countable_map[ing_code]["sub_recipe_code"]
            opening_qty = get_stock_as_of(branch_code, ing_code, start_dt)
            if day_ledger.empty:
                sales_usage = 0.0
                ledger_wastage = 0.0
            else:
                same_ing = day_ledger[day_ledger["ingredient_code"] == ing_code]
                sales_usage = float(same_ing[same_ing["movement_type"] == "Sales Recipe Consumption"]["qty_out"].sum())
                ledger_wastage = float(same_ing[same_ing["movement_type"].isin(["Prep Item Wastage"])]["qty_out"].sum())
            prepared_qty = round(physical_qty + sales_usage + ledger_wastage + prep_wastage_qty - opening_qty, 6)
            preview.update({
                "auto_prep_sub_recipe": sub_code,
                "sales_usage_yesterday": sales_usage,
                "prep_wastage_yesterday": ledger_wastage + prep_wastage_qty,
                "calculated_prepared_qty": prepared_qty,
                "posting_action": "Auto prep production" if prepared_qty > 0 else "Physical count difference only",
            })
        preview_rows.append(preview)

    st.write("### Posting Preview")
    preview_df = pd.DataFrame(preview_rows)
    st.dataframe(preview_df, use_container_width=True, hide_index=True)

    if post_pressed:
        try:
            # Save the final edited version first, then post from the same session dataframe.
            save_stock_count_draft_lines(draft_id, branch_code, count_date, edited)
            adjustments, prep_batches, prep_lines, warnings = post_morning_stock_count_and_auto_prep(
                branch_code=branch_code,
                count_date=count_date,
                draft=draft,
                edited=edited,
            )
            # Clear only this editor from session after successful final post.
            st.session_state.pop(editor_df_key, None)
            st.session_state.pop(last_saved_key, None)
            st.success(
                f"Posted morning count. Adjustments: {adjustments}, auto prep batches: {prep_batches}, raw material lines: {prep_lines}."
            )
            for msg in warnings:
                st.warning(msg)
            st.rerun()
        except Exception as e:
            st.error(f"Could not post morning count. Error: {e}")

def page_adjustment(branch_code: str):
    section_title("Stock Adjustment", "Use for ingredient wastage, prep wastage, correction, staff meal, transfer, or other movement.")
    ingredients = get_ingredients()
    if ingredients.empty:
        st.warning("No ingredients found in Supabase.")
        return

    ingredient_labels = ingredient_options_with_units(ingredients)

    with st.form("adjustment_form"):
        movement_type = st.selectbox(
            "Movement Type",
            [
                "Ingredient Wastage",
                "Prep Item Wastage",
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
        selected_ingredient = st.selectbox("Ingredient / Prep Item", list(ingredient_labels.keys()))
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
            add_stock_ledger(
                branch_code=branch_code,
                ingredient_code=ingredient_code,
                movement_type=movement_type,
                qty_in=qty_in,
                qty_out=qty_out,
                reference_type="Manual Adjustment",
                reference_id=date.today().isoformat(),
                note=note,
            )
            st.success("Adjustment saved.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not save adjustment. Error: {e}")


def page_sales_upload(branch_code: str):
    section_title(
        "Sales Report Upload",
        "Uploads POS sales. Direct ingredients and countable prep are deducted; virtual prep is backflushed to raw materials.",
    )

    sales_date = st.date_input("Sales Date", value=date.today())
    if "sales_upload_uploader_version" not in st.session_state:
        st.session_state.sales_upload_uploader_version = 0

    uploaded_file = st.file_uploader(
        "Upload Sales Report",
        type=["csv", "xlsx", "xls"],
        key=f"sales_upload_file_{st.session_state.sales_upload_uploader_version}",
    )
    st.caption("Selected Sales Date must match the date inside the uploaded report.")

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
    sub_df = get_sub_recipes()

    if products.empty or recipe_df.empty:
        st.error("Sales upload cannot continue until products and recipe_ingredients are filled.")
        return

    check = sold_items.copy()
    check["item_name_clean"] = check["item_name"].astype(str).str.strip().str.lower()
    mapped = check.merge(
        products[["product_code", "item_name", "item_name_clean"]],
        on="item_name_clean",
        how="left",
        suffixes=("_sales", "_product"),
    )

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
            sold_qty = as_float(item["sold_qty"])
            exploded = calculate_product_consumption(product_code, sold_qty, recipe_df, sub_df)
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
                    "used_qty": as_float(e["used_qty"]),
                    "calculation_note": e.get("calculation_note", ""),
                })
    except Exception as e:
        st.error(f"Recipe calculation failed. Error: {e}")
        return

    if missing_recipe:
        st.error("Some products have no active recipe lines in recipe_ingredients table.")
        st.dataframe(pd.DataFrame(missing_recipe), use_container_width=True, hide_index=True)
        return

    consumption = pd.DataFrame(consumption_rows)
    if consumption.empty:
        st.error("No recipe consumption calculated.")
        return

    consumption_summary = consumption.groupby(["ingredient_code"], as_index=False).agg(used_qty=("used_qty", "sum"))
    consumption_summary = enrich_ingredients(consumption_summary)
    st.write("### Calculated stock deduction")
    st.dataframe(consumption_summary, use_container_width=True, hide_index=True)

    with st.expander("Calculation detail by product"):
        detail = enrich_ingredients(consumption)
        st.dataframe(detail, use_container_width=True, hide_index=True)

    if st.button("Post Sales Consumption to Stock Ledger", use_container_width=True):
        try:
            batch_id = create_sales_batch(branch_code, sales_date, uploaded_file.name, len(success_df))
            insert_sales_lines(batch_id, branch_code, sales_date, success_df)
            insert_consumption_rows(batch_id, branch_code, sales_date, consumption, source="Sales")

            post_ledger_for_consumption(
                branch_code=branch_code,
                target_date=sales_date,
                consumption_summary=consumption_summary,
                movement_type="Sales Recipe Consumption",
                reference_type="Sales Upload",
                reference_id=batch_id,
                note=f"Sales report {uploaded_file.name} for {sales_date.isoformat()}",
                transaction_time=time(23, 59, 0),
            )

            save_stock_day_snapshot(branch_code, sales_date)
            st.success(f"Sales consumption posted. Batch ID: {batch_id}")
            st.session_state.sales_upload_uploader_version += 1
            st.rerun()

        except Exception as e:
            st.error(f"Could not post sales consumption. Error: {e}")


def page_finished_product_wastage(branch_code: str):
    section_title(
        "Finished Product Wastage",
        "Use when a completed item is wasted. The app deducts the same ingredients/prep as a sale, but marks it as finished product wastage.",
    )
    products = get_products()
    recipe_df = get_recipe_ingredients()
    sub_df = get_sub_recipes()

    if products.empty or recipe_df.empty:
        st.warning("Products and recipe_ingredients must be filled first.")
        return

    labels = product_options(products)

    with st.form("finished_product_wastage_form"):
        wastage_date = st.date_input("Wastage Date", value=date.today())
        selected_product = st.selectbox("Finished Product", list(labels.keys()))
        qty = st.number_input("Wasted Quantity", min_value=0.0, step=1.0)
        note = st.text_area("Reason", placeholder="Example: wrong order, dropped item, burnt item")
        submitted = st.form_submit_button("Calculate Wastage", use_container_width=True)

    if not submitted:
        return

    if qty <= 0:
        st.error("Quantity must be greater than zero.")
        return

    product_row = labels[selected_product]
    product_code = str(product_row["product_code"]).strip().upper()
    item_name = str(product_row["item_name"])

    try:
        exploded = calculate_product_consumption(product_code, qty, recipe_df, sub_df)
    except Exception as e:
        st.error(f"Recipe calculation failed. Error: {e}")
        return

    if not exploded:
        st.error("No recipe found for this product.")
        return

    consumption = pd.DataFrame([
        {
            "product_code": product_code,
            "item_name": item_name,
            "sold_qty": qty,
            "ingredient_code": r["ingredient_code"],
            "used_qty": r["used_qty"],
            "calculation_note": r.get("calculation_note", ""),
        }
        for r in exploded
    ])
    summary = consumption.groupby("ingredient_code", as_index=False).agg(used_qty=("used_qty", "sum"))
    summary = enrich_ingredients(summary)

    st.write("### Stock deduction for this wastage")
    st.dataframe(summary, use_container_width=True, hide_index=True)

    if st.button("Post Finished Product Wastage", use_container_width=True):
        try:
            ref_id = f"FPW-{branch_code}-{wastage_date.isoformat()}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
            post_ledger_for_consumption(
                branch_code=branch_code,
                target_date=wastage_date,
                consumption_summary=summary,
                movement_type="Finished Product Wastage Consumption",
                reference_type="Finished Product Wastage",
                reference_id=ref_id,
                note=f"{item_name} x {qty}. Reason: {note}",
                transaction_time=datetime.now().time().replace(microsecond=0),
            )
            save_stock_day_snapshot(branch_code, wastage_date)
            st.success("Finished product wastage posted.")
            st.rerun()
        except Exception as e:
            st.error(f"Could not post finished product wastage. Error: {e}")


def get_countable_prep_table() -> pd.DataFrame:
    sub_df = get_sub_recipes()
    ingredients = get_ingredients(include_inactive=True)
    if sub_df.empty:
        return pd.DataFrame()

    countable = sub_df[sub_df["prep_type"].str.lower() == "countable"].copy()
    if ingredients.empty:
        return countable

    countable = countable.merge(
        ingredients[["ingredient_code", "ingredient_name", "base_unit"]],
        left_on="output_ingredient_code",
        right_on="ingredient_code",
        how="left",
    )
    return countable


def page_current_stock(branch_code: str):
    section_title("Current Stock", "Calculated from stock_ledger, not manually stored.")
    stock = get_current_stock(branch_code)
    if stock.empty:
        st.warning("No stock data found.")
        return

    status_filter = st.multiselect(
        "Filter Status",
        ["OK", "Low", "Out of Stock", "Negative"],
        default=["OK", "Low", "Out of Stock", "Negative"],
    )
    source_filter = st.multiselect(
        "Source Type",
        ["Purchased", "Produced", "Both"],
        default=["Purchased", "Produced", "Both"],
    )

    filtered = stock[stock["status"].isin(status_filter) & stock["source_type"].isin(source_filter)]
    st.dataframe(filtered, use_container_width=True, hide_index=True)
    show_download_button(filtered, f"current_stock_{branch_code}.csv", "Download Current Stock CSV")


def page_reports(branch_code: str):
    section_title("Reports", "Reports for your branch only.")
    report = st.selectbox(
        "Choose Report",
        [
            "Stock Ledger",
            "Purchase Bills",
            "Purchase Bill Lines",
            "Supplier Price History",
            "Prep Production Batches",
            "Products",
            "Ingredients",
            "Sub Recipes",
            "Recipe Ingredients",
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
    elif report == "Prep Production Batches":
        df = get_prep_production_report(branch_code)
    elif report == "Products":
        df = get_products(include_inactive=True)
    elif report == "Ingredients":
        df = get_ingredients(include_inactive=True)
    elif report == "Sub Recipes":
        df = get_sub_recipes(include_inactive=True)
    else:
        df = get_recipe_ingredients(include_inactive=True)

    if df.empty:
        st.info("No data found for this report.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
        show_download_button(df, f"{report.lower().replace(' ', '_')}_{branch_code}.csv", "Download Report CSV")


def page_recipe_validation():
    section_title("Recipe Validation", "Checks missing mappings, missing sub recipes, missing ingredients, and possible circular references.")
    ingredients = get_ingredients(include_inactive=True)
    products = get_products(include_inactive=True)
    sub_df = get_sub_recipes(include_inactive=True)
    recipe_df = get_recipe_ingredients(include_inactive=True)

    if recipe_df.empty:
        st.warning("No recipe_ingredients rows found.")
        return

    issues = []

    ingredient_codes = set(ingredients["ingredient_code"].astype(str).str.upper()) if not ingredients.empty else set()
    product_codes = set(products["product_code"].astype(str).str.upper()) if not products.empty else set()
    sub_codes = set(sub_df["sub_recipe_code"].astype(str).str.upper()) if not sub_df.empty else set()

    for _, row in recipe_df.iterrows():
        parent_type = str(row["parent_type"]).strip()
        parent_code = str(row["parent_code"]).strip().upper()
        component_type = str(row["component_type"]).strip()
        component_code = str(row["component_code"]).strip().upper()

        if parent_type == "Product" and parent_code not in product_codes:
            issues.append({
                "Issue": "Parent product missing",
                "Code": parent_code,
                "Recipe Line ID": row.get("recipe_line_id"),
            })
        if parent_type == "Sub Recipe" and parent_code not in sub_codes:
            issues.append({
                "Issue": "Parent sub recipe missing",
                "Code": parent_code,
                "Recipe Line ID": row.get("recipe_line_id"),
            })
        if component_type == "Ingredient" and component_code not in ingredient_codes:
            issues.append({
                "Issue": "Component ingredient missing",
                "Code": component_code,
                "Recipe Line ID": row.get("recipe_line_id"),
            })
        if component_type == "Sub Recipe" and component_code not in sub_codes:
            issues.append({
                "Issue": "Component sub recipe missing",
                "Code": component_code,
                "Recipe Line ID": row.get("recipe_line_id"),
            })

    if not sub_df.empty:
        for _, sub in sub_df.iterrows():
            output_ing = str(sub["output_ingredient_code"]).strip().upper()
            if output_ing not in ingredient_codes:
                issues.append({
                    "Issue": "Sub recipe output ingredient missing",
                    "Code": output_ing,
                    "Recipe Line ID": sub["sub_recipe_code"],
                })

    # Try calculation for all products with qty 1 to catch circular/missing nested recipes.
    active_recipe = get_recipe_ingredients()
    active_sub = get_sub_recipes()
    for _, product in get_products().iterrows():
        try:
            calculate_product_consumption(product["product_code"], 1, active_recipe, active_sub)
        except Exception as e:
            issues.append({
                "Issue": "Calculation error",
                "Code": product["product_code"],
                "Recipe Line ID": "",
                "Details": str(e),
            })

    if not issues:
        st.success("No validation issues found.")
    else:
        issue_df = pd.DataFrame(issues)
        st.dataframe(issue_df, use_container_width=True, hide_index=True)
        show_download_button(issue_df, "recipe_validation_issues.csv")


def classify_snapshot_bucket(row) -> Tuple[str, float]:
    movement = str(row.get("movement_type") or "")
    qty_in = as_float(row.get("qty_in"))
    qty_out = as_float(row.get("qty_out"))

    if movement == "Purchase":
        return "purchase_in", qty_in
    if movement == "Prep Production Output":
        return "prep_output_in", qty_in
    if movement in ["Correction In", "Physical Count Adjustment In"]:
        return "adjustment_in", qty_in
    if movement == "Transfer In":
        return "transfer_in", qty_in
    if movement == "Sales Recipe Consumption":
        return "sales_out", qty_out
    if movement == "Prep Production Consumption":
        return "prep_consumption_out", qty_out
    if movement in ["Ingredient Wastage", "Prep Item Wastage"]:
        return "wastage_out", qty_out
    if movement == "Finished Product Wastage Consumption":
        return "finished_product_wastage_out", qty_out
    if movement in ["Correction Out", "Physical Count Adjustment Out"]:
        return "adjustment_out", qty_out
    if movement == "Transfer Out":
        return "transfer_out", qty_out
    if qty_in > 0:
        return "other_in", qty_in
    return "other_out", qty_out


def save_stock_day_snapshot(branch_code: str, snapshot_date: date) -> None:
    current = get_current_stock(branch_code)
    if current.empty:
        return

    ledger = get_stock_ledger_raw(branch_code)
    bucket_cols = [
        "purchase_in", "prep_output_in", "adjustment_in", "transfer_in",
        "sales_out", "prep_consumption_out", "wastage_out",
        "finished_product_wastage_out", "adjustment_out", "transfer_out",
        "other_in", "other_out",
    ]

    movements = pd.DataFrame(columns=["ingredient_code"] + bucket_cols)

    if not ledger.empty:
        day_ledger = ledger[ledger["transaction_datetime"].dt.date == snapshot_date].copy()
        rows = []
        for ing, g in day_ledger.groupby("ingredient_code"):
            rec = {"ingredient_code": ing}
            for c in bucket_cols:
                rec[c] = 0.0
            for _, move in g.iterrows():
                bucket, qty = classify_snapshot_bucket(move)
                rec[bucket] += qty
            rows.append(rec)
        if rows:
            movements = pd.DataFrame(rows)

    snap = current.merge(movements, on="ingredient_code", how="left")
    for c in bucket_cols:
        snap[c] = pd.to_numeric(snap.get(c, 0), errors="coerce").fillna(0)

    snap["system_closing_qty"] = pd.to_numeric(snap["current_qty"], errors="coerce").fillna(0)
    snap["opening_qty"] = (
        snap["system_closing_qty"]
        - snap["purchase_in"]
        - snap["prep_output_in"]
        - snap["adjustment_in"]
        - snap["transfer_in"]
        + snap["sales_out"]
        + snap["prep_consumption_out"]
        + snap["wastage_out"]
        + snap["finished_product_wastage_out"]
        + snap["adjustment_out"]
        + snap["transfer_out"]
        + snap["other_out"]
        - snap["other_in"]
    )

    payload = []
    for _, r in snap.iterrows():
        payload.append({
            "branch_code": branch_code,
            "snapshot_date": snapshot_date.isoformat(),
            "ingredient_code": str(r["ingredient_code"]),
            "ingredient_name": str(r.get("ingredient_name") or ""),
            "base_unit": str(r.get("base_unit") or ""),
            "opening_qty": as_float(r.get("opening_qty")),
            "purchase_in": as_float(r.get("purchase_in")),
            "prep_output_in": as_float(r.get("prep_output_in")),
            "adjustment_in": as_float(r.get("adjustment_in")),
            "transfer_in": as_float(r.get("transfer_in")),
            "sales_out": as_float(r.get("sales_out")),
            "prep_consumption_out": as_float(r.get("prep_consumption_out")),
            "wastage_out": as_float(r.get("wastage_out")),
            "finished_product_wastage_out": as_float(r.get("finished_product_wastage_out")),
            "adjustment_out": as_float(r.get("adjustment_out")),
            "transfer_out": as_float(r.get("transfer_out")),
            "other_in": as_float(r.get("other_in")),
            "other_out": as_float(r.get("other_out")),
            "system_closing_qty": as_float(r.get("system_closing_qty")),
            "physical_closing_qty": None,
            "variance_qty": None,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
        })

    try:
        supabase = get_supabase_client()
        supabase.table("stock_day_snapshot").delete().eq("branch_code", branch_code).eq("snapshot_date", snapshot_date.isoformat()).execute()
        for i in range(0, len(payload), 500):
            supabase.table("stock_day_snapshot").insert(payload[i:i + 500]).execute()
    except Exception:
        # Snapshot is only analytical. Do not block main operation.
        pass


def page_database_connection_test(branch_code: str):
    section_title("Database Connection Test", "Checks whether the required tables can be read.")
    tables = [
        "branches",
        "ingredients",
        "products",
        "sub_recipes",
        "recipe_ingredients",
        "purchase_bill_header",
        "purchase_bill_lines",
        "stock_ledger",
        "sales_upload_batches",
        "sales_upload_lines",
        "sales_recipe_consumption",
        "prep_production_batches",
        "prep_production_lines",
        "stock_day_snapshot",
        "stock_count_drafts",
        "stock_count_draft_lines",
    ]

    rows = []
    supabase = get_supabase_client()
    for table in tables:
        try:
            result = supabase.table(table).select("*", count="exact").limit(1).execute()
            rows.append({
                "table": table,
                "status": "OK",
                "sample_rows_returned": len(result.data or []),
                "error": "",
            })
        except Exception as e:
            rows.append({
                "table": table,
                "status": "ERROR",
                "sample_rows_returned": 0,
                "error": str(e),
            })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.write("### Branch current stock calculation test")
    stock = get_current_stock(branch_code)
    st.dataframe(stock.head(20), use_container_width=True, hide_index=True)




# ============================================================
# Main app
# ============================================================
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
            "Morning Stock Count / Close Yesterday",
            "Stock Adjustment",
            "Sales Report Upload",
            "Finished Product Wastage",
            "Current Stock",
            "Reports",
            "Recipe Validation",
            "Database Connection Test",
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
    elif page == "Morning Stock Count / Close Yesterday":
        page_stock_count(branch_code)
    elif page == "Stock Adjustment":
        page_adjustment(branch_code)
    elif page == "Sales Report Upload":
        page_sales_upload(branch_code)
    elif page == "Finished Product Wastage":
        page_finished_product_wastage(branch_code)
    elif page == "Current Stock":
        page_current_stock(branch_code)
    elif page == "Reports":
        page_reports(branch_code)
    elif page == "Recipe Validation":
        page_recipe_validation()
    elif page == "Database Connection Test":
        page_database_connection_test(branch_code)


if __name__ == "__main__":
    main()
