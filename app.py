from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
import os
import csv
from flask import Response

# --- Config ---
APP_VERSION = "v0.3.1-dev"  # update manually when you push changes

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
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    description = db.Column(db.Text, nullable=True)
    order_type = db.Column(db.String(50), nullable=False)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="New")
    file_path = db.Column(db.String(300), nullable=True)
    priority = db.Column(db.String(20), default="Medium")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WorkOrder {self.id}: {self.title} ({self.priority})>"

class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    booking_type = db.Column(db.String(50), nullable=False)
    event_date = db.Column(db.Date, nullable=False)
    secondary_date = db.Column(db.Date, nullable=True)
    expected_income = db.Column(db.Float, nullable=False, default=0.0)
    paid_status = db.Column(db.String(10), default="Pending")  # Paid | Pending | Partial
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Booking {self.id}: {self.customer} - {self.booking_type}>"
    
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # relationships
    bookings = db.relationship("Booking", backref="customer_obj", lazy=True)
    workorders = db.relationship("WorkOrder", backref="customer_obj", lazy=True)

    def __repr__(self):
        return f"<Customer {self.name}>"

# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route('/dashboard')
def dashboard():
    # --- Transactions ---
    income_paid = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))\
        .filter_by(type='Income', status='Paid').scalar()
    expense_paid = db.session.query(db.func.coalesce(db.func.sum(Transaction.amount), 0.0))\
        .filter_by(type='Expense', status='Paid').scalar()
    profit = (income_paid or 0.0) - (expense_paid or 0.0)

    pending_income = db.session.query(db.func.count(Transaction.id))\
        .filter_by(type='Income', status='Pending').scalar()
    pending_expense = db.session.query(db.func.count(Transaction.id))\
        .filter_by(type='Expense', status='Pending').scalar()

    recent = Transaction.query.order_by(Transaction.date.desc(), Transaction.id.desc()).limit(10).all()

    # --- Bookings ---
    total_bookings = db.session.query(db.func.count(Booking.id)).scalar()
    total_expected_income = db.session.query(db.func.coalesce(db.func.sum(Booking.expected_income), 0.0)).scalar()
    pending_bookings = db.session.query(db.func.count(Booking.id))\
        .filter(Booking.paid_status != "Paid").scalar()
    paid_bookings = db.session.query(db.func.count(Booking.id))\
        .filter(Booking.paid_status == "Paid").scalar()

    # --- Work Orders ---
    total_orders = db.session.query(db.func.count(WorkOrder.id)).scalar()
    open_orders = db.session.query(db.func.count(WorkOrder.id)).filter_by(status="New").scalar()
    in_progress_orders = db.session.query(db.func.count(WorkOrder.id)).filter_by(status="In Progress").scalar()
    closed_orders = db.session.query(db.func.count(WorkOrder.id)).filter_by(status="Closed").scalar()
    high_priority = db.session.query(db.func.count(WorkOrder.id)).filter_by(priority="High").scalar()

    recent_orders = WorkOrder.query.order_by(WorkOrder.created_at.desc()).limit(5).all()

    # upcoming due date
    upcoming_order = WorkOrder.query.filter(WorkOrder.due_date != None)\
                                    .order_by(WorkOrder.due_date.asc())\
                                    .first()

    return render_template(
        'dashboard.html',
        # Transactions
        income_paid=income_paid or 0.0,
        expense_paid=expense_paid or 0.0,
        profit=profit or 0.0,
        pending_income=pending_income or 0,
        pending_expense=pending_expense or 0,
        recent=recent,
        # Bookings
        total_bookings=total_bookings or 0,
        total_expected_income=total_expected_income or 0.0,
        pending_bookings=pending_bookings or 0,
        paid_bookings=paid_bookings or 0,
        # Work Orders
        total_orders=total_orders or 0,
        open_orders=open_orders or 0,
        in_progress_orders=in_progress_orders or 0,
        closed_orders=closed_orders or 0,
        high_priority=high_priority or 0,
        recent_orders=recent_orders,
        upcoming_order=upcoming_order
    )


# ------------------ Transactions ------------------

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

@app.route('/transactions/export')
def export_transactions():
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

    # Create CSV
    def generate():
        data = [
            ["Date", "Type", "Category", "Party", "Description", "Amount", "Status"]
        ]
        for t in txns:
            data.append([
                t.date.strftime('%Y-%m-%d'),
                t.type,
                t.category,
                t.party or "",
                t.description or "",
                f"{t.amount:.2f}",
                t.status
            ])
        # Write to CSV
        output = []
        for row in data:
            output.append(",".join(f'"{col}"' for col in row))
        return "\n".join(output)

    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=transactions.csv"}
    )

@app.route('/add', methods=['GET', 'POST'])
def add_transaction():
    if request.method == 'POST':
        t_type = request.form.get('type')
        category = request.form.get('category')
        party = request.form.get('party')
        description = request.form.get('description')
        amount = float(request.form.get('amount', 0) or 0)
        status = request.form.get('status')
        date_str = request.form.get('date')
        date_val = datetime.strptime(date_str, '%Y-%m-%d').date() if date_str else datetime.utcnow().date()

        receipt_path = None
        file = request.files.get('receipt')
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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

@app.route('/edit/<int:transaction_id>', methods=['GET', 'POST'])
def edit_transaction(transaction_id):
    txn = Transaction.query.get_or_404(transaction_id)
    if request.method == "POST":
        txn.date = datetime.strptime(request.form["date"], "%Y-%m-%d").date()
        txn.type = request.form["type"]
        txn.category = request.form["category"]
        txn.party = request.form.get("party")
        txn.description = request.form.get("description")
        txn.amount = float(request.form["amount"])
        txn.status = request.form["status"]

        receipt = request.files.get("receipt")
        if receipt and receipt.filename:
            path = os.path.join("static/receipts", receipt.filename)
            receipt.save(path)
            txn.receipt_path = path

        db.session.commit()
        flash("Transaction updated successfully!", "success")
        return redirect(url_for("transactions"))

    return render_template("edit_transaction.html", txn=txn)

@app.route('/delete/<int:txn_id>', methods=['POST'])
def delete_transaction(txn_id):
    t = Transaction.query.get_or_404(txn_id)
    if t.receipt_path and os.path.exists(t.receipt_path):
        try:
            os.remove(t.receipt_path)
        except Exception:
            pass
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for('transactions'))

# ------------------ Work Orders ------------------

@app.route("/workorders")
def workorders():
    q_type = request.args.get("type", "All")
    q_status = request.args.get("status", "All")
    q_text = request.args.get("q", "").strip()

    query = WorkOrder.query

    if q_type != "All":
        query = query.filter(WorkOrder.order_type == q_type)
    if q_status in ("New", "In Progress", "Closed"):
        query = query.filter(WorkOrder.status == q_status)
    if q_text:
        like = f"%{q_text}%"
        query = query.filter(
            db.or_(
                WorkOrder.customer.ilike(like),
                WorkOrder.description.ilike(like)
            )
        )

    all_orders = query.order_by(WorkOrder.due_date.asc()).all()

    # 🔹 Stats for tiles
    total_orders = WorkOrder.query.count()
    open_orders = WorkOrder.query.filter_by(status="New").count()
    in_progress_orders = WorkOrder.query.filter_by(status="In Progress").count()
    closed_orders = WorkOrder.query.filter_by(status="Closed").count()
    high_priority = WorkOrder.query.filter_by(priority="High").count()

    return render_template(
        "workorders.html",
        workorders=all_orders,
        q_type=q_type,
        q_status=q_status,
        q_text=q_text,
        total_orders=total_orders,
        open_orders=open_orders,
        in_progress_orders=in_progress_orders,
        closed_orders=closed_orders,
        high_priority=high_priority
    )

@app.route("/workorders/add", methods=["GET", "POST"])
def add_workorder():
    if request.method == "POST":
        customer_id = int(request.form["customer_id"])
        description = request.form.get("description")
        order_type = request.form["order_type"]
        priority = request.form.get("priority", "Medium")
        due_date_str = request.form.get("due_date")
        status = request.form.get("status", "New")

        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

        # Handle file upload
        file_path = None
        file = request.files.get("file")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            base, ext = os.path.splitext(filename)
            counter = 1
            while os.path.exists(save_path):
                filename = f"{base}_{counter}{ext}"
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                counter += 1
            file.save(save_path)
            file_path = save_path

        new_order = WorkOrder(
            customer_id=customer_id,
            description=description,
            order_type=order_type,
            priority=priority,
            due_date=due_date,
            status=status,
            file_path=file_path
        )
        db.session.add(new_order)
        db.session.commit()
        flash("Work order added successfully!", "success")
        return redirect(url_for("workorders"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("add_workorder.html", customers=customers)

@app.route("/workorders/edit/<int:workorder_id>", methods=["GET", "POST"])
def edit_workorder(workorder_id):
    order = WorkOrder.query.get_or_404(workorder_id)

    if request.method == "POST":
        order.customer_id = int(request.form["customer_id"])
        order.description = request.form.get("description")
        order.order_type = request.form["order_type"]
        order.status = request.form.get("status")
        order.priority = request.form.get("priority", order.priority)
        due_date_str = request.form.get("due_date")
        order.due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

        # Replace file if new one uploaded
        file = request.files.get("file")
        if file and file.filename and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(save_path)
            order.file_path = save_path

        db.session.commit()
        flash("Work order updated successfully!", "success")
        return redirect(url_for("workorders"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("edit_workorder.html", order=order, customers=customers)

@app.route("/workorders/delete/<int:workorder_id>", methods=["POST"])
def delete_workorder(workorder_id):
    order = WorkOrder.query.get_or_404(workorder_id)
    if order.file_path and os.path.exists(order.file_path):
        try:
            os.remove(order.file_path)
        except Exception:
            pass
    db.session.delete(order)
    db.session.commit()
    flash("Work order deleted!", "danger")
    return redirect(url_for("workorders"))

# ------------------ Bookings ------------------

@app.route("/bookings")
def bookings():
    q_status = request.args.get("status", "All")
    query = Booking.query
    if q_status in ("Paid", "Pending", "Partial"):
        query = query.filter(Booking.paid_status == q_status)

    all_bookings = query.order_by(Booking.event_date.asc()).all()
    return render_template("bookings.html", bookings=all_bookings, q_status=q_status)

@app.route("/bookings/add", methods=["GET", "POST"])
def add_booking():
    if request.method == "POST":
        customer_id = int(request.form["customer_id"])
        booking_type = request.form["booking_type"]
        event_date = datetime.strptime(request.form["event_date"], "%Y-%m-%d").date()
        secondary_date_str = request.form.get("secondary_date")
        secondary_date = datetime.strptime(secondary_date_str, "%Y-%m-%d").date() if secondary_date_str else None
        expected_income = float(request.form.get("expected_income", 0))
        paid_status = request.form.get("paid_status", "Pending")
        notes = request.form.get("notes")

        new_booking = Booking(
            customer_id=customer_id,
            booking_type=booking_type,
            event_date=event_date,
            secondary_date=secondary_date,
            expected_income=expected_income,
            paid_status=paid_status,
            notes=notes
        )
        db.session.add(new_booking)
        db.session.commit()

        # Transaction logging
        customer = Customer.query.get(customer_id)
        if paid_status == "Paid":
            txn = Transaction(
                type="Income",
                category="Booking",
                party=customer.name,
                description=f"{booking_type} Booking",
                amount=expected_income,
                status="Paid",
                date=datetime.utcnow().date()
            )
            db.session.add(txn)

        elif paid_status == "Partial":
            partial_amount = float(request.form.get("partial_amount", 0))
            if partial_amount > 0:
                txn = Transaction(
                    type="Income",
                    category="Booking",
                    party=customer.name,
                    description=f"{booking_type} Booking (Partial Payment)",
                    amount=partial_amount,
                    status="Paid",
                    date=datetime.utcnow().date(),
                )
                db.session.add(txn)

        db.session.commit()
        flash("Booking added successfully!", "success")
        return redirect(url_for("bookings"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("add_booking.html", customers=customers)


@app.route("/bookings/edit/<int:booking_id>", methods=["GET", "POST"])
def edit_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)

    if request.method == "POST":
        booking.customer_id = int(request.form["customer_id"])
        booking.booking_type = request.form["booking_type"]
        booking.event_date = datetime.strptime(request.form["event_date"], "%Y-%m-%d").date()
        secondary_date_str = request.form.get("secondary_date")
        booking.secondary_date = datetime.strptime(secondary_date_str, "%Y-%m-%d").date() if secondary_date_str else None
        booking.expected_income = float(request.form.get("expected_income", 0))
        booking.paid_status = request.form.get("paid_status", "Pending")
        booking.notes = request.form.get("notes")

        db.session.commit()
        flash("Booking updated successfully!", "success")
        return redirect(url_for("bookings"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("edit_booking.html", booking=booking, customers=customers)

@app.route("/bookings/delete/<int:booking_id>", methods=["POST"])
def delete_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    db.session.delete(booking)
    db.session.commit()
    flash("Booking deleted!", "danger")
    return redirect(url_for("bookings"))


# ------------------ Customers ------------------

@app.route("/customers")
def customers():
    all_customers = Customer.query.order_by(Customer.name.asc()).all()
    return render_template("customers.html", customers=all_customers)

@app.route("/customers/add", methods=["GET", "POST"])
def add_customer():
    if request.method == "POST":
        name = request.form["name"]
        email = request.form.get("email")
        phone = request.form.get("phone")
        address = request.form.get("address")
        notes = request.form.get("notes")

        new_customer = Customer(
            name=name, email=email, phone=phone, address=address, notes=notes
        )
        db.session.add(new_customer)
        db.session.commit()
        flash("Customer added successfully!", "success")
        return redirect(url_for("customers"))

    return render_template("add_customer.html")

@app.route("/customers/edit/<int:customer_id>", methods=["GET", "POST"])
def edit_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    if request.method == "POST":
        customer.name = request.form["name"]
        customer.email = request.form.get("email")
        customer.phone = request.form.get("phone")
        customer.address = request.form.get("address")
        customer.notes = request.form.get("notes")

        db.session.commit()
        flash("Customer updated successfully!", "success")
        return redirect(url_for("customers"))

    return render_template("edit_customer.html", customer=customer)

@app.route("/customers/delete/<int:customer_id>", methods=["POST"])
def delete_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    db.session.delete(customer)
    db.session.commit()
    flash("Customer deleted!", "danger")
    return redirect(url_for("customers"))

@app.route("/customers/<int:customer_id>")
def view_customer(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    return render_template("view_customer.html", customer=customer)


# ------------------ Run ------------------
@app.context_processor
def inject_version():
    return dict(version=APP_VERSION)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)