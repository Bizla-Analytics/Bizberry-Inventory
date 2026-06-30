
# Branch Inventory Manager - Streamlit + SQLite

This is a local starter app for multi-branch inventory management.

## Features

- Single manager password login
- Multi-branch selection
- Ingredient master
- Branch master
- Purchase bill entry
- Automatic stock ledger entry
- Opening / physical stock count adjustment
- Manual stock adjustment
- Current stock report
- CSV exports

## Local setup

1. Create a virtual environment:

```bash
python -m venv .venv
```

2. Activate it:

Windows:

```bash
.venv\Scripts\activate
```

Mac/Linux:

```bash
source .venv/bin/activate
```

3. Install packages:

```bash
pip install -r requirements.txt
```

4. Create local secrets file:

Copy:

```text
.streamlit/secrets.toml.example
```

Rename to:

```text
.streamlit/secrets.toml
```

Then change:

```toml
APP_PASSWORD = "change-this-password"
```

5. Run app:

```bash
streamlit run app.py
```

## Important

- The app creates `inventory.db` automatically.
- Do not upload `.streamlit/secrets.toml` to GitHub.
- Do not upload real `inventory.db` to GitHub unless you intentionally want to share local data.
- For Streamlit Cloud, add APP_PASSWORD in the Streamlit Cloud Secrets area.
