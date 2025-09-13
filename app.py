from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import os

# --- Config ---
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-key")
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///business.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join('static', 'receipts')
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db = SQLAlchemy(app)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp', 'pdf'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# --- Models ---
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    type = db.Column(db.String(10), nullable=False)      # Income | Expense
    category = db.Column(db.String(50), nullable=False)
    party = db.Column(db.String(120), nullable=True)     # Client/Vendor
    description = db.Column(db.String(300), nullable=True)
    amount = db.Column(db.Float, nullable=False, default=0.0)
    status = db.Column(db.String(10), nullable=False)     # Paid | Pending
    date = db.Column(db.Date, nullable=False, default=datetime.utcnow)
    receipt_path = db.Column(db.String(300), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WorkOrder(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    asset = db.Column(db.String(120), nullable=True)   # what equipment/job it's for
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="Open")  # Open, In Progress, Closed

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    # Totals (paid only)
    income_paid = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))\
        .filter_by(type='Income', status='Paid').scalar()
    expense_paid = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))\
        .filter_by(type='Expense', status='Paid').scalar()
    profit = (income_paid or 0.0) - (expense_paid or 0.0)

    # Pending counts
    pending_income = db.session.query(db.func.count(Transaction.id))\
        .filter_by(type='Income', status='Pending').scalar()
    pending_expense = db.session.query(db.func.count(Transaction.id))\
        .filter_by(type='Expense', status='Pending').scalar()

    # Recent transactions
    recent = Transaction.query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(10).all()

    return render_template('dashboard.html',
                           income_paid=income_paid or 0.0,
                           expense_paid=expense_paid or 0.0,
                           profit=profit or 0.0,
                           pending_income=pending_income or 0,
                           pending_expense=pending_expense or 0,
                           recent=recent)


@app.route('/transactions')
def transactions():
    q_type = request.args.get('type', 'All')
    q_status = request.args.get('status', 'All')
    q_text = request.args.get('q', '').strip()

    query = Transaction.query
    if q_type in ('Income', 'Expense'):
        query = query.filter(Transaction.type == q_type)
    if q_status in ('Paid', 'Pending'):
        query = query.filter(Transaction.status == q_status)
    if q_text:
        like = f"%{q_text}%"
        query = query.filter(
            db.or_(
                Transaction.category.ilike(like),
                Transaction.description.ilike(like),
                Transaction.party.ilike(like)
            )
        )

    txns = query.order_by(Transaction.date.desc(), Transaction.id.desc()).all()
    return render_template('transactions.html', transactions=txns, q_type=q_type, q_status=q_status, q_text=q_text)

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        # Parse form
        t_type = request.form.get('type')
        category = request.form.get('category')
        party = request.form.get('party')
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0) or 0)
        status = request.form.get('status')
        date_str = request.form.get('date')  # yyyy-mm-dd
        date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()

        # Handle file
        receipt_path = None
        file = request.files.get('receipt')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            # Prevent overwrite by appending a counter if exists
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                filename = f"{base}_{counter}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            file.save(save_path)
            receipt_path = save_path

        t = Transaction(
            type=t_type,
            category=category,
            party=party,
            description=description,
            amount=amount,
            status=status,
            date=date_val,
            receipt_path=receipt_path
        )
        db.session.add(t)
        db.session.commit()
        return redirect(url_for('transactions'))
    return render_template('add_transaction.html')

@app.route('/delete/<int:txn_id>', methods=['POST'])
def delete_transaction(txn_id):
    t = Transaction.query.get_or_404(txn_id)
    # Optionally delete associated receipt file
    if t.receipt_path and os.path.exists(t.receipt_path):
        try:
            os.remove(t.receipt_path)
        except Exception:
            pass
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for('transactions'))

# Edit transaction
@app.route("/edit/<int:transaction_id>", methods=["GET", "POST"])
def edit_transaction(transaction_id):
    txn = Transaction.query.get_or_404(transaction_id)

    if request.method == "POST":
        txn.date = request.form["date"]
        txn.type = request.form["type"]
        txn.category = request.form["category"]
        txn.party = request.form.get("party")
        txn.description = request.form.get("description")
        txn.amount = float(request.form["amount"])
        txn.status = request.form["status"]

        # ✅ Convert string to Python date object
        txn.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()

        # If user uploads a new receipt, save it
        receipt = request.files.get("receipt")
        if receipt:
            path = os.path.join("static/receipts", receipt.filename)
            receipt.save(path)
            txn.receipt_path = path

        db.session.commit()
        flash("Transaction updated successfully!", "success")
        return redirect(url_for("transactions"))

    return render_template("edit_transaction.html", txn=txn)


if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
