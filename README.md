# Business Tracker (Flask + SQLite)

## Quick Start
```bash
# 1) Create & activate a virtual environment
python -m venv .venv
# Windows:
.\.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# 2) Install dependencies
pip install -r requirements.txt

# 3) Run the app
python app.py

# 4) Open in browser
# http://localhost:5000
```

- Uploads are saved to: `static/receipts/`
- Database file: `business.db`
- Routes:
  - `/dashboard` — totals and recent transactions
  - `/transactions` — list + filter + delete
  - `/add` — create income/expense and attach a receipt
