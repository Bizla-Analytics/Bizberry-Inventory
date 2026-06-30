from datetime import datetime, date

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

    APP_PASSWORD = "your-manager-password"
    SUPABASE_URL = "https://your-project-id.supabase.co"
    SUPABASE_ANON_KEY = "your-anon-key"
    """
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_ANON_KEY"]
    return create_client(url, key)


def supabase_result_to_df(result) -> pd.DataFrame:
    """Safely convert Supabase result data to DataFrame."""
    if not result or not getattr(result, "data", None):
        return pd.DataFrame()
    return pd.DataFrame(result.data)


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
    """
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if st.session_state.authenticated:
        return True

    st.title("Branch Inventory Login")

    password = st.text_input("Manager Password", type="password")
    app_password = st.secrets.get("APP_PASSWORD", "admin123")

    if st.button("Login", use_container_width=True):
        if password == app_password:
            st.session_state.authenticated = True
            st.rerun()
        else:
            st.error("Incorrect password")

    return False


# -----------------------------
# Supabase data functions
# -----------------------------
def get_branches() -> pd.DataFrame:
    supabase = get_supabase_client()

    result = (
        supabase
        .table("branches")
        .select("branch_code, branch_name")
        .eq("active", True)
        .order("branch_code")
        .execute()
    )

    return supabase_result_to_df(result)


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
):
    supabase = get_supabase_client()

    supabase.table("stock_ledger").insert({
        "transaction_datetime": datetime.now().isoformat(timespec="seconds"),
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
# UI helpers
# -----------------------------
def section_title(title, caption=None):
    st.subheader(title)
    if caption:
        st.caption(caption)


def branch_selector():
    branches = get_branches()
    if branches.empty:
        st.error(
            "No active branches found in Supabase. "
            "Please insert at least one branch in the branches table."
        )
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


def page_master_data():
    section_title(
        "Master Data",
        "Add branches and ingredients. Ingredients are not auto-inserted by this app.",
    )

    tab1, tab2 = st.tabs(["Branches", "Ingredients"])

    with tab1:
        st.write("### Add Branch")
        with st.form("add_branch_form"):
            branch_code = st.text_input("Branch Code", placeholder="BR002").strip().upper()
            branch_name = st.text_input("Branch Name", placeholder="New Branch").strip()
            submitted = st.form_submit_button("Add Branch", use_container_width=True)

        if submitted:
            if not branch_code or not branch_name:
                st.error("Branch code and branch name are required.")
            else:
                try:
                    supabase = get_supabase_client()
                    supabase.table("branches").insert({
                        "branch_code": branch_code,
                        "branch_name": branch_name,
                        "active": True,
                    }).execute()

                    st.success("Branch added to Supabase.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Could not add branch. Error: {e}")

        st.write("### Existing Branches")
        branches = get_branches()
        st.dataframe(branches, use_container_width=True, hide_index=True)

    with tab2:
        st.write("### Add Ingredient")
        st.caption(
            "Use this only for adding new single ingredients manually. "
            "Your existing SQL-inserted ingredients will not be touched."
        )

        with st.form("add_ingredient_form"):
            ingredient_code = st.text_input("Ingredient Code", placeholder="ING235").strip().upper()
            ingredient_name = st.text_input("Ingredient Name", placeholder="Tomato").strip().title()
            category = st.text_input("Category", placeholder="Vegetable").strip().title()
            base_unit = st.selectbox("Base Unit", ["g", "kg", "ml", "L", "pcs", "piece", "pack", "scoop", "spoon"])
            min_stock = st.number_input("Minimum Stock", min_value=0.0, step=0.1)
            source_type = st.selectbox("Source Type", ["Purchased", "Produced", "Both"])
            submitted = st.form_submit_button("Add Ingredient", use_container_width=True)

        if submitted:
            if not ingredient_code or not ingredient_name:
                st.error("Ingredient code and ingredient name are required.")
            else:
                try:
                    supabase = get_supabase_client()
                    supabase.table("ingredients").insert({
                        "ingredient_code": ingredient_code,
                        "ingredient_name": ingredient_name,
                        "category": category,
                        "base_unit": base_unit,
                        "min_stock": float(min_stock or 0),
                        "source_type": source_type,
                        "active": True,
                    }).execute()

                    st.success("Ingredient added to Supabase.")
                    st.rerun()

                except Exception as e:
                    st.error(f"Could not add ingredient. Error: {e}")

        st.write("### Existing Ingredients")
        ingredients = get_ingredients()
        st.dataframe(ingredients, use_container_width=True, hide_index=True)


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

    # This is used to clear the form after saving.
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

            st.success(f"Purchase bill saved to Supabase. Bill ID: {bill_id}")

            # Clear the form after saving.
            st.session_state.purchase_form_version += 1
            st.rerun()

        except Exception as e:
            st.error(f"Could not save purchase bill. Error: {e}")


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
        ["Stock Ledger", "Purchase Bills", "Purchase Bill Lines", "Supplier Price History"],
    )

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
        show_download_button(
            df,
            file_name=f"{report.lower().replace(' ', '_')}_{branch_code}.csv",
            label="Download Report CSV",
        )


# -----------------------------
# Main app
# -----------------------------
def main():
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
