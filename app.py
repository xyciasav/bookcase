from flask import Flask, render_template, request, redirect, url_for, flash, send_file, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.utils import secure_filename
from datetime import datetime
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import os
import shutil
import csv

# --- Config ---
APP_VERSION = "v0.6.10-dev"  # update manually when you push changes

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
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=True)
    description = db.Column(db.Text, nullable=True)
    order_type = db.Column(db.String(50), nullable=False)
    price = db.Column(db.Float, default=0.0)
    due_date = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(20), default="New")
    file_path = db.Column(db.String(300), nullable=True)
    priority = db.Column(db.String(20), default="Medium")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="workorders")
    booking = db.relationship("Booking", back_populates="workorders")
    
class Booking(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)

    booking_type_id = db.Column(db.Integer, db.ForeignKey("booking_type.id"), nullable=False)
    booking_type = db.relationship("BookingType", backref="bookings")

    event_date = db.Column(db.Date, nullable=False)
    secondary_date = db.Column(db.Date, nullable=True)
    expected_income = db.Column(db.Float, nullable=False, default=0.0)
    paid_status = db.Column(db.String(10), default="Pending")
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="bookings")
    workorders = db.relationship("WorkOrder", back_populates="booking", lazy=True)
    invoices = db.relationship("Invoice", back_populates="booking", lazy=True)

    
class Customer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    address = db.Column(db.String(250), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    bookings = db.relationship("Booking", back_populates="customer", lazy=True)
    workorders = db.relationship("WorkOrder", back_populates="customer", lazy=True)
    invoices = db.relationship("Invoice", back_populates="customer", lazy=True)

class WorkOrderType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    base_price = db.Column(db.Float, default=0.0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<WorkOrderType {self.name} - ${self.base_price:.2f}>"
    
class JobType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    base_price = db.Column(db.Float, default=0.0)   #  add this
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<JobType {self.name} - ${self.base_price:.2f}>"

class Invoice(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    customer_id = db.Column(db.Integer, db.ForeignKey("customer.id"), nullable=False)
    booking_id = db.Column(db.Integer, db.ForeignKey("booking.id"), nullable=True)
    total = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default="Draft")
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    customer = db.relationship("Customer", back_populates="invoices")
    booking = db.relationship("Booking", back_populates="invoices")
    items = db.relationship(
        "InvoiceItem",
        backref="invoice",
        lazy=True,
        cascade="all, delete-orphan"  
    )

class InvoiceItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoice.id"), nullable=False)
    description = db.Column(db.String(200))
    price = db.Column(db.Float, default=0.0)
    quantity = db.Column(db.Integer, default=1)

    def subtotal(self):
        return self.price * self.quantity

class BookingType(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), unique=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<BookingType {self.name}>"
    

class Lead(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    contact_name = db.Column(db.String(120), nullable=False)
    business_name = db.Column(db.String(120), nullable=True)  # optional
    type = db.Column(db.String(20), nullable=False, default="Personal")  # Business/Personal
    phone = db.Column(db.String(20), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    preferred_contact = db.Column(db.String(20), nullable=True)  # phone, text, email, other
    last_contacted = db.Column(db.Date, nullable=True)

    status = db.Column(db.String(50), nullable=False, default="New")
    source = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)


# --- Routes ---
@app.route('/')
def index():
    return redirect(url_for('dashboard'))

@app.route("/bookings/<int:booking_id>")
def view_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    return render_template("view_booking.html", booking=booking)

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
        query = query.join(Customer).filter(
            db.or_(
                Customer.name.ilike(like),
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
        order_types = request.form.getlist("order_types")
        description = request.form.get("description")
        priority = request.form.get("priority", "Medium")
        due_date_str = request.form.get("due_date")
        status = request.form.get("status", "New")
        booking_id = request.form.get("booking_id")

        due_date = datetime.strptime(due_date_str, "%Y-%m-%d").date() if due_date_str else None

        for ot in order_types:
            new_order = WorkOrder(
                customer_id=customer_id,
                booking_id=int(booking_id) if booking_id else None,
                description=description,
                order_type=ot,
                price=0.0,
                priority=priority,
                due_date=due_date,
                status=status
            )
            db.session.add(new_order)
        db.session.commit()

        flash("Work order(s) added successfully!", "success")
        if booking_id:
            return redirect(url_for("view_booking", booking_id=booking_id))
        return redirect(url_for("workorders"))

    booking_id = request.args.get("booking_id")
    preselected_customer = None
    if booking_id:
        booking = Booking.query.get(int(booking_id))
        if booking:
            preselected_customer = booking.customer_id

    customers = Customer.query.order_by(Customer.name.asc()).all()
    workorder_types = WorkOrderType.query.order_by(WorkOrderType.name.asc()).all()
    return render_template(
        "add_workorder.html",
        customers=customers,
        workorder_types=workorder_types,
        preselected_customer=preselected_customer,
        booking_id=booking_id
    )
    
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

        db.session.commit()
        flash("Work order updated successfully!", "success")
        return redirect(url_for("workorders"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    job_types = JobType.query.order_by(JobType.name.asc()).all()   # ensure this is passed
    return render_template("edit_workorder.html", order=order, customers=customers, job_types=job_types)

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

# ------------------Workorder type -----------------

@app.route("/settings/workordertypes")
def workorder_types():
    types = WorkOrderType.query.order_by(WorkOrderType.name.asc()).all()
    return render_template("workordertypes.html", workorder_types=types)

@app.route("/settings/workordertypes/add", methods=["POST"])
def add_workorder_type():
    name = request.form.get("name")
    price = float(request.form.get("price", 0))
    if name:
        existing = WorkOrderType.query.filter_by(name=name).first()
        if not existing:
            db.session.add(WorkOrderType(name=name, base_price=price))
            db.session.commit()
            flash("Work order type added!", "success")
        else:
            flash("Work order type already exists!", "warning")
    return redirect(url_for("workorder_types"))

@app.route("/settings/workordertypes/delete/<int:type_id>", methods=["POST"])
def delete_workordertype(type_id):
    wt = WorkOrderType.query.get_or_404(type_id)
    db.session.delete(wt)
    db.session.commit()
    flash("Work order type deleted!", "danger")
    return redirect(url_for("settings_workordertypes"))

@app.route("/settings/workordertypes/edit/<int:type_id>", methods=["GET", "POST"])
def edit_workorder_type(type_id):
    wt = WorkOrderType.query.get_or_404(type_id)
    if request.method == "POST":
        wt.name = request.form.get("name")
        wt.base_price = float(request.form.get("price", 0))
        db.session.commit()
        flash("Work order type updated!", "success")
        return redirect(url_for("workorder_types"))
    return render_template("edit_workorder_type.html", workorder_type=wt)

@app.route("/settings/workordertypes", methods=["GET", "POST"])
def settings_workordertypes():
    if request.method == "POST":
        name = request.form["name"]
        if name:
            new_type = WorkOrderType(name=name)
            db.session.add(new_type)
            db.session.commit()
            flash("Work order type added!", "success")
        return redirect(url_for("settings_workordertypes"))

    workorder_types = WorkOrderType.query.order_by(WorkOrderType.name.asc()).all()
    return render_template("settings_workordertypes.html", workorder_types=workorder_types)
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
        booking_type_id = int(request.form["booking_type_id"])
        event_date = request.form["event_date"]
        secondary_date = request.form.get("secondary_date")
        expected_income = float(request.form["expected_income"])
        paid_status = request.form["paid_status"]
        partial_amount = request.form.get("partial_amount")
        notes = request.form.get("notes")

        new_booking = Booking(
            customer_id=customer_id,
            booking_type_id=booking_type_id,
            event_date=event_date,
            secondary_date=secondary_date,
            expected_income=expected_income,
            paid_status=paid_status,
            partial_amount=partial_amount if paid_status == "Partial" else None,
            notes=notes,
        )
        db.session.add(new_booking)
        db.session.commit()
        flash("Booking added successfully!", "success")
        return redirect(url_for("bookings"))

    customers = Customer.query.order_by(Customer.name.asc()).all()
    booking_types = BookingType.query.order_by(BookingType.name.asc()).all()
    return render_template("add_booking.html", customers=customers, booking_types=booking_types)

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
        booking_type_id = int(request.form["booking_type_id"])

        
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


@app.before_request
def seed_job_types():
    if not hasattr(app, "jobtypes_seeded"):
        if JobType.query.count() == 0:
            defaults = ["Design", "Photography", "Videography", "Print", "Consultation", "Other"]
            for d in defaults:
                db.session.add(JobType(name=d))
            db.session.commit()
        app.jobtypes_seeded = True

# -------------------- Invoices -----------------------------

@app.route("/invoices", endpoint="invoices")
def invoices():
    invoices = Invoice.query.order_by(Invoice.created_at.desc()).all()
    return render_template("invoices.html", invoices=invoices)

@app.route("/invoices/create/<int:customer_id>", methods=["POST"])
def create_invoice(customer_id):
    customer = Customer.query.get_or_404(customer_id)
    workorder_ids = request.form.getlist("workorders")  # list of selected orders
    
    invoice = Invoice(customer_id=customer.id, status="Draft")
    db.session.add(invoice)
    db.session.commit()

    total = 0.0
    for wid in workorder_ids:
        order = WorkOrder.query.get(int(wid))
        if order:
            item = InvoiceItem(
                invoice_id=invoice.id,
                description=order.order_type,
                price=order.price,
                quantity=1
            )
            total += order.price
            db.session.add(item)

    invoice.total = total
    db.session.commit()

    flash("Invoice created!", "success")
    return redirect(url_for("view_invoice", invoice_id=invoice.id))

@app.route("/invoices/<int:invoice_id>")
def view_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    customer = Customer.query.get(invoice.customer_id)
    return render_template("view_invoice.html", invoice=invoice, customer=customer)

@app.route("/invoices/create_from_booking/<int:booking_id>", methods=["POST"])
def create_invoice_from_booking(booking_id):
    booking = Booking.query.get_or_404(booking_id)
    customer = booking.customer

    workorder_ids = request.form.getlist("workorders")
    if not workorder_ids:
        flash("No work orders selected.", "warning")
        return redirect(url_for("view_booking", booking_id=booking.id))

    invoice = Invoice(customer_id=customer.id, booking_id=booking.id, status="Draft")  #  link booking
    db.session.add(invoice)
    db.session.commit()

    total = 0.0
    for wid in workorder_ids:
        order = WorkOrder.query.get(int(wid))
        if order:
            item = InvoiceItem(
                invoice_id=invoice.id,
                description=order.order_type,
                price=order.price,
                quantity=1
            )
            total += order.price
            db.session.add(item)

    invoice.total = total
    db.session.commit()

    flash("Invoice created!", "success")
    return redirect(url_for("view_invoice", invoice_id=invoice.id))

@app.route("/invoices/<int:invoice_id>/mark_paid", methods=["POST"])
def mark_invoice_paid(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "Paid"
    db.session.commit()

    # Optional: log a transaction when invoice is marked paid
    txn = Transaction(
        type="Income",
        category="Invoice",
        party=invoice.customer.name,
        description=f"Invoice #{invoice.id}",
        amount=invoice.total,
        status="Paid",
        date=datetime.utcnow().date(),
    )
    db.session.add(txn)
    db.session.commit()

    flash(f"Invoice #{invoice.id} marked as Paid", "success")
    return redirect(url_for("view_invoice", invoice_id=invoice.id))

@app.route("/invoices/delete/<int:invoice_id>", methods=["POST"])
def delete_invoice(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    db.session.delete(invoice)
    db.session.commit()
    flash(f"Invoice #{invoice.id} deleted!", "danger")
    return redirect(url_for("invoices"))

@app.route("/invoices/<int:invoice_id>/pdf")
def invoice_pdf(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    customer = invoice.customer

    filename = f"invoice_{invoice.id}.pdf"
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

    doc = SimpleDocTemplate(filepath, pagesize=letter)
    styles = getSampleStyleSheet()
    elements = []

    # --- Header ---
    elements.append(Paragraph(f"Invoice #{invoice.id}", styles['Title']))
    elements.append(Paragraph(f"Date: {invoice.created_at.strftime('%Y-%m-%d')}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # --- Customer Info ---
    elements.append(Paragraph(f"<b>Customer:</b> {customer.name}", styles['Normal']))
    if customer.email:
        elements.append(Paragraph(f"<b>Email:</b> {customer.email}", styles['Normal']))
    if customer.phone:
        elements.append(Paragraph(f"<b>Phone:</b> {customer.phone}", styles['Normal']))
    elements.append(Spacer(1, 12))

    # --- Invoice Items ---
    data = [["Description", "Quantity", "Price", "Subtotal"]]
    for item in invoice.items:
        data.append([
            item.description,
            str(item.quantity),
            f"${item.price:.2f}",
            f"${item.subtotal():.2f}"
        ])
    data.append(["", "", "Total", f"${invoice.total:.2f}"])

    table = Table(data, colWidths=[200, 80, 80, 80])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.grey),
        ('TEXTCOLOR',(0,0),(-1,0),colors.whitesmoke),
        ('ALIGN',(1,1),(-1,-1),'CENTER'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('BACKGROUND',(0,1),(-1,-1),colors.beige),
    ]))
    elements.append(table)

    # --- Build PDF ---
    doc.build(elements)

    return send_file(filepath, as_attachment=True)

# ------------------ Leads ------------------

@app.route("/leads")
def leads():
    page = request.args.get("page", 1, type=int)
    search = request.args.get("search", "")
    status_filter = request.args.get("status", "")
    type_filter = request.args.get("type", "")

    query = Lead.query

    if search:
        query = query.filter(
            (Lead.contact_name.ilike(f"%{search}%")) |
            (Lead.business_name.ilike(f"%{search}%")) |
            (Lead.email.ilike(f"%{search}%")) |
            (Lead.phone.ilike(f"%{search}%"))
        )
    if status_filter:
        query = query.filter_by(status=status_filter)
    if type_filter:
        query = query.filter_by(type=type_filter)

    leads = query.order_by(Lead.contact_name.asc()).paginate(page=page, per_page=20)

    return render_template("leads.html", leads=leads, search=search,
                           status_filter=status_filter, type_filter=type_filter)


@app.route("/leads/add", methods=["GET", "POST"])
def add_lead():
    if request.method == "POST":
        contact_name = request.form["contact_name"]
        business_name = request.form.get("business_name")
        lead_type = request.form.get("type", "Personal")
        phone = request.form.get("phone")
        email = request.form.get("email")
        preferred_contact = request.form.get("preferred_contact")
        last_contacted = request.form.get("last_contacted")
        status = request.form.get("status", "New")
        notes = request.form.get("notes")

        new_lead = Lead(
            contact_name=contact_name,
            business_name=business_name,
            type=lead_type,
            phone=phone,
            email=email,
            preferred_contact=preferred_contact,
            last_contacted=datetime.strptime(last_contacted, "%Y-%m-%d").date() if last_contacted else None,
            status=status,
            notes=notes
        )
        db.session.add(new_lead)
        db.session.commit()
        flash("Lead added successfully!", "success")
        return redirect(url_for("leads"))

    return render_template("add_lead.html")


@app.route("/leads/edit/<int:lead_id>", methods=["GET", "POST"])
def edit_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    if request.method == "POST":
        lead.contact_name = request.form["contact_name"]
        lead.business_name = request.form.get("business_name")
        lead.type = request.form.get("type", lead.type)
        lead.phone = request.form.get("phone")
        lead.email = request.form.get("email")
        lead.preferred_contact = request.form.get("preferred_contact")
        last_contacted = request.form.get("last_contacted")
        lead.last_contacted = datetime.strptime(last_contacted, "%Y-%m-%d").date() if last_contacted else None
        lead.status = request.form.get("status", lead.status)
        lead.notes = request.form.get("notes")

        db.session.commit()
        flash("Lead updated!", "success")
        return redirect(url_for("leads"))

    return render_template("edit_lead.html", lead=lead)


@app.route("/leads/delete/<int:lead_id>", methods=["POST"])
def delete_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    db.session.delete(lead)
    db.session.commit()
    flash("Lead deleted!", "danger")
    return redirect(url_for("leads"))


@app.route("/leads/convert/<int:lead_id>", methods=["POST"])
def convert_lead(lead_id):
    lead = Lead.query.get_or_404(lead_id)

    # Create a new customer from lead data
    customer = Customer(
        name=lead.contact_name,   # <-- was lead.name
        email=lead.email,
        phone=lead.phone,
        notes=lead.notes
    )
    db.session.add(customer)

    # Mark lead as converted
    lead.status = "Converted"
    db.session.commit()

    flash(f"Lead {lead.contact_name} converted to customer!", "success")
    return redirect(url_for("customers"))

# ------------------ Settings (Job Types) ------------------

@app.route("/settings/jobtypes")
def jobtypes():
    types = JobType.query.order_by(JobType.name.asc()).all()
    return render_template("jobtypes.html", job_types=types)

@app.route("/settings/jobtypes/add", methods=["POST"])
def add_jobtype():
    name = request.form.get("name")
    price = float(request.form.get("price", 0))
    if name:
        existing = JobType.query.filter_by(name=name).first()
        if not existing:
            db.session.add(JobType(name=name, base_price=price))
            db.session.commit()
            flash("Job type added!", "success")
        else:
            flash("Job type already exists!", "warning")
    return redirect(url_for("jobtypes"))

@app.route("/settings/jobtypes/delete/<int:type_id>", methods=["POST"])
def delete_jobtype(type_id):
    jobtype = JobType.query.get_or_404(type_id)
    db.session.delete(jobtype)
    db.session.commit()
    flash("Job type deleted!", "danger")
    return redirect(url_for("jobtypes"))

@app.route("/settings/jobtypes/edit/<int:type_id>", methods=["GET", "POST"])
def edit_jobtype(type_id):
    jt = JobType.query.get_or_404(type_id)
    if request.method == "POST":
        jt.name = request.form.get("name")
        jt.base_price = float(request.form.get("price", 0))
        db.session.commit()
        flash("Job type updated!", "success")
        return redirect(url_for("jobtypes"))
    return render_template("edit_jobtype.html", jobtype=jt)

@app.before_request
def seed_booking_types():
    if not hasattr(app, "bookingtypes_seeded"):
        if BookingType.query.count() == 0:
            defaults = ["Wedding Package", "School Package", "Business Package"]
            for d in defaults:
                db.session.add(BookingType(name=d))
            db.session.commit()
        app.bookingtypes_seeded = True

# --------------------Booking Types --------------

@app.route("/settings/bookingtypes")
def bookingtypes():
    types = BookingType.query.order_by(BookingType.name.asc()).all()
    return render_template("bookingtypes.html", booking_types=types)

@app.route("/settings/bookingtypes/add", methods=["POST"])
def add_bookingtype():
    name = request.form.get("name")
    if name:
        existing = BookingType.query.filter_by(name=name).first()
        if not existing:
            db.session.add(BookingType(name=name))
            db.session.commit()
            flash("Booking type added!", "success")
        else:
            flash("Booking type already exists!", "warning")
    return redirect(url_for("bookingtypes"))

@app.route("/settings/bookingtypes", methods=["GET", "POST"])
def settings_bookingtypes():
    if request.method == "POST":
        name = request.form["name"]
        if name:
            new_type = BookingType(name=name)
            db.session.add(new_type)
            db.session.commit()
            flash("Booking type added!", "success")
        return redirect(url_for("settings_bookingtypes"))

    booking_types = BookingType.query.order_by(BookingType.name.asc()).all()
    return render_template("settings_bookingtypes.html", booking_types=booking_types)

@app.route("/settings/bookingtypes/delete/<int:type_id>", methods=["POST"])
def delete_bookingtype(type_id):
    btype = BookingType.query.get_or_404(type_id)
    db.session.delete(btype)
    db.session.commit()
    flash("Booking type deleted!", "danger")
    return redirect(url_for("bookingtypes"))

@app.route("/settings/bookingtypes/edit/<int:type_id>", methods=["GET", "POST"])
def edit_bookingtype(type_id):
    bt = BookingType.query.get_or_404(type_id)
    if request.method == "POST":
        bt.name = request.form.get("name")
        db.session.commit()
        flash("Booking type updated!", "success")
        return redirect(url_for("bookingtypes"))
    return render_template("edit_bookingtype.html", bookingtype=bt)

# -------------------Backup ---------------------

@app.route("/settings/backup", methods=["POST"])
def backup_database():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join(app.root_path, "backups")
    os.makedirs(backup_dir, exist_ok=True)

    # Path to SQLite file inside Flask's instance folder
    db_path = os.path.join(app.instance_path, "business.db")

    backup_filename = f"backup_{timestamp}.db"
    backup_path = os.path.join(backup_dir, backup_filename)

    shutil.copy(db_path, backup_path)

    flash(f"Database backup created: {backup_filename}", "success")
    return redirect(url_for("jobtypes"))  # back to settings

# ------------------ Run ------------------
@app.context_processor
def inject_version():
    return dict(version=APP_VERSION)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)