import os
import qrcode
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from fpdf import FPDF
from flask import send_file
from datetime import datetime, timezone
now = datetime.now(timezone.utc)



app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///restaurant.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-key-123' # Change this in production

db = SQLAlchemy(app)

# ==========================================
# DATABASE MODELS
# ==========================================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=True)
    password = db.Column(db.String(120), nullable=True)
    phone = db.Column(db.String(15), unique=True, nullable=True)
    role = db.Column(db.String(20), default='customer')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    price = db.Column(db.Float, nullable=False)
    cost = db.Column(db.Float, nullable=False)
    tags = db.Column(db.String(200))
    is_active = db.Column(db.Boolean, default=True)

class RestaurantTable(db.Model):
    __tablename__ = 'table' 
    id = db.Column(db.Integer, primary_key=True)
    table_number = db.Column(db.Integer, unique=True, nullable=False)
    qr_code_data = db.Column(db.String(255))
    status = db.Column(db.String(20), default='Available')

class Order(db.Model):
    __tablename__ = 'order'
    id = db.Column(db.Integer, primary_key=True)
    table_id = db.Column(db.Integer, db.ForeignKey('table.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    total_revenue = db.Column(db.Float, default=0.0)
    total_profit = db.Column(db.Float, default=0.0)
    status = db.Column(db.String(20), default='Pending')
    order_type = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    items = db.relationship('OrderItem', backref='order', cascade="all, delete-orphan", lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey('order.id'))
    product_id = db.Column(db.Integer, db.ForeignKey('product.id'))
    quantity = db.Column(db.Integer)
    price_at_time = db.Column(db.Float)
    profit_at_time = db.Column(db.Float)

# ==========================================
# AUTHENTICATION ROUTES
# ==========================================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        # Check for admin user in DB
        user = User.query.filter_by(username=username, password=password, role='admin').first()
        
        if user:
            session['admin_logged_in'] = True
            session['user_id'] = user.id
            return redirect(url_for('admin'))
        
        return "Invalid credentials or not an admin", 401
    
    return render_template('login.html')

# @app.route('/api/admin/tables/clear/<int:table_id>', methods=['POST'])
# def clear_table_session(table_id):
#     try:
#         # 1. Find all active orders for this table
#         active_orders = Order.query.filter_by(table_id=table_id).filter(Order.status != 'Completed').all()
        
#         for order in active_orders:
#             order.status = 'Completed'
        
#         # 2. Reset the Table Status
#         table = RestaurantTable.query.filter_by(table_number=table_id).first()
#         if table:
#             table.status = 'Available'
            
#         db.session.commit()
#         return jsonify({"success": true, "message": "Table cleared and bill settled."})
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"success": false, "message": str(e)})

# --- MODERN TIME CONFIG ---
def get_now():
    return datetime.now(timezone.utc)

# --- UPDATED CLEAR TABLE ROUTE ---
# @app.route('/api/admin/tables/clear/<int:table_id>', methods=['POST'])
# def clear_table_session(table_id):
#     try:
#         # 1. Fetch ALL orders for this table that aren't already finished
#         # This covers 'Pending', 'Kitchen', 'Served', etc.
#         active_orders = Order.query.filter(
#             Order.table_id == table_id,
#             Order.status.notin_(['Completed', 'Cancelled'])
#         ).all()
        
#         for order in active_orders:
#             order.status = 'Completed'
        
#         # 2. Reset the Table status to Available
#         table = db.session.get(RestaurantTable, table_id)
#         if table:
#             table.status = 'Available'
            
#         db.session.commit()
#         return jsonify({"success": True, "message": f"Table {table_id} cleared and {len(active_orders)} orders closed."})
    
#     except Exception as e:
#         db.session.rollback()
#         print(f"Error clearing table: {e}")
#         return jsonify({"success": False, "message": str(e)}), 500
# UPDATE THIS: Ensures the orders are actually marked Completed in the DB
@app.route('/api/admin/tables/clear/<int:table_id>', methods=['POST'])
def clear_table_session(table_id):
    try:
        # 1. Update ALL orders for this table number to 'Completed'
        # This is what moves them into the Invoices and Analytics sections
        orders_updated = Order.query.filter(
            Order.table_id == table_id,
            Order.status.notin_(['Completed', 'Cancelled'])
        ).update({Order.status: 'Completed'}, synchronize_session=False)

        # 2. Reset the Table status by table_number, not DB ID
        table = RestaurantTable.query.filter_by(table_number=table_id).first()
        if table:
            table.status = 'Available'
        
        db.session.commit()
        return jsonify({"success": True, "count": orders_updated})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    

# UPDATE THIS: Ensures the Table row disappears from the Orders screen
@app.route('/api/admin/orders/live')
def get_live_orders():
    # EXCLUDE Completed and Cancelled orders
    orders = Order.query.filter(
        Order.status.notin_(['Completed', 'Cancelled'])
    ).order_by(Order.created_at.desc()).all()
    
    output = []
    for o in orders:
        customer = db.session.get(User, o.user_id) if o.user_id else None
        output.append({
            "id": o.id,
            "table_id": o.table_id,
            "customer": customer.username if customer else "Guest",
            "total_revenue": o.total_revenue,
            "status": o.status or "Pending",
            "time": o.created_at.strftime("%H:%M") if o.created_at else "--:--"
        })
    return jsonify(output)


# In app.py - The route that feeds the Invoices section
@app.route('/api/admin/invoices')
def get_invoices():
    # Make sure it is looking for 'Completed' orders!
    completed_orders = Order.query.filter_by(status='Completed').order_by(Order.created_at.desc()).all()
    # ... return the JSON ...

# --- UPDATED LIVE ORDERS ROUTE ---
# @app.route('/api/admin/orders/live')
# def get_live_orders():
#     # ONLY fetch orders that are NOT Completed and NOT Cancelled
#     orders = Order.query.filter(
#         Order.status.notin_(['Completed', 'Cancelled'])
#     ).order_by(Order.created_at.desc()).all()
    
#     output = []
#     for o in orders:
#         customer = db.session.get(User, o.user_id) if o.user_id else None
#         output.append({
#             "id": o.id,
#             "source": o.order_type or "QR",
#             "table_id": o.table_id,
#             "customer": customer.username if customer else "Guest",
#             "total_revenue": o.total_revenue,
#             "status": o.status or "Pending",
#             # Ensure time is sent in a format the frontend expects
#             "time": o.created_at.strftime("%H:%M") if o.created_at else "--:--"
#         })
#     return jsonify(output)


# --- MODERN ANALYTICS (FIXING DEPRECATION) ---
@app.route('/api/analytics')
def get_analytics():
    # 1. Use Naive UTC time to match how SQLAlchemy typically saves 'default=datetime.utcnow'
    # This is the most common reason for '0' results after a refresh.
    now = datetime.utcnow()
    cutoff = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 2. Query orders
    orders = Order.query.filter(
        Order.created_at >= cutoff,
        Order.status == 'Completed'
    ).all()
    
    revenue = sum(o.total_revenue for o in orders)
    profit = sum(o.total_profit for o in orders)
    
    # 3. DEBUG PRINT (Check your CMD/Terminal when you refresh)
    print(f">>> ANALYTICS DEBUG <<<")
    print(f"Cutoff: {cutoff}")
    print(f"Orders Found: {len(orders)}")
    print(f"Revenue: {revenue}")
    
    return jsonify({
        "metrics": {
            "orders_created": len(orders),
            "revenue_generated": round(revenue, 2),
            "profits_made": round(profit, 2)
        }
    })


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ==========================================
# ADMIN & API ROUTES
# ==========================================

@app.route('/admin')
def admin():
    if not session.get('admin_logged_in'):
        return redirect(url_for('login'))
    return render_template('admin.html')

@app.route('/api/products/add', methods=['POST'])
def add_product():
    # If session is lost, this might fail. Let's make it robust.
    if not session.get('admin_logged_in'):
        return jsonify({"success": False, "message": "Unauthorized"}), 401
        
    data = request.json
    try:
        new_p = Product(
            name=data['name'], 
            price=float(data['price']), 
            cost=float(data['cost']), 
            tags=data['tags']
        )
        db.session.add(new_p)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/products/delete/<int:id>', methods=['DELETE'])
def delete_product(id):
    product = Product.query.get_or_404(id)
    db.session.delete(product)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/admin/orders/delete/<int:id>', methods=['DELETE'])
def delete_order(id):
    order = Order.query.get_or_404(id)
    db.session.delete(order)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/admin/orders/update/<int:order_id>', methods=['POST'])
def update_order_status(order_id):
    # Use db.session.get for modern SQLAlchemy compatibility
    order = db.session.get(Order, order_id)
    if not order:
        return jsonify({"success": False, "message": "Order not found"}), 404
        
    data = request.get_json()
    new_status = data.get('status', 'Completed')
    
    # 1. Update the specific Order status
    order.status = new_status
    
    # 2. Smart Table Logic: Only free the table if NO other orders are active
    if new_status == 'Completed' and order.table_id:
        # Check if there are any OTHER orders for this table still Pending/Kitchen/Served
        other_active_orders = Order.query.filter(
            Order.table_id == order.table_id,
            Order.status.notin_(['Completed', 'Cancelled']),
            Order.id != order_id
        ).first()
        
        # If no other active orders exist, the session is truly over
        if not other_active_orders:
            table = RestaurantTable.query.filter_by(table_number=order.table_id).first()
            if table:
                table.status = 'Available'
                # Optional: log for debugging
                print(f"Table {order.table_id} is now fully cleared.")
        else:
            print(f"Table {order.table_id} remains Occupied. Other active orders exist.")

    try:
        db.session.commit()
        return jsonify({
            "success": True, 
            "message": f"Order #{order_id} updated.",
            "session_closed": not bool(other_active_orders) if new_status == 'Completed' else False
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500
    

# @app.route('/api/admin/orders/history')
# def get_order_history():
#     orders = Order.query.filter_by(status='Completed').order_by(Order.created_at.desc()).all()
#     return jsonify([{"id": o.id, "total": o.total_revenue, "time": o.created_at.strftime("%Y-%m-%d %I:%M %p")} for o in orders])

@app.route('/api/admin/orders/history')
def get_order_history():
    # Fetch all completed orders
    orders = Order.query.filter_by(status='Completed').order_by(Order.created_at.desc()).all()
    return jsonify([{
        "id": o.id,
        "total": o.total_revenue,
        "type": o.order_type, # Ensure this matches your Model
        "time": o.created_at.strftime("%Y-%m-%d %I:%M %p")
    } for o in orders])

@app.route('/api/admin/orders/receipt/<int:order_id>')
def generate_receipt(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Initialize PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Header
    pdf.cell(190, 10, "RESTAURANT RECEIPT", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(190, 10, f"Order ID: #{order.id}", ln=True, align='C')
    pdf.cell(190, 10, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(10)

    # Items Table Header
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Product", border=1)
    pdf.cell(40, 10, "Qty", border=1, align='C')
    pdf.cell(50, 10, "Total", border=1, ln=True, align='C')

    # Items Loop
    pdf.set_font("Arial", size=12)
    for item in order.items:
        # Get product name safely
        product = Product.query.get(item.product_id)
        name = product.name if product else "Unknown Item"
        
        pdf.cell(100, 10, name, border=1)
        pdf.cell(40, 10, str(item.quantity), border=1, align='C')
        pdf.cell(50, 10, f"${(item.price_at_time * item.quantity):.2f}", border=1, ln=True, align='R')

    # Total Section
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(140, 10, "GRAND TOTAL:", align='R')
    pdf.cell(50, 10, f"${order.total_revenue:.2f}", border=1, ln=True, align='R')

    # Save to file
    path = f"receipt_{order_id}.pdf"
    pdf.output(path)
    
    # Return the file for download
    return send_file(path, as_attachment=True)
    # 1. Get the order from the database
    order = Order.query.get_or_404(order_id)
    
    # 2. Create PDF object
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Title
    pdf.cell(190, 10, "OFFICIAL RECEIPT", ln=True, align='C')
    pdf.ln(5)
    
    # Order Info
    pdf.set_font("Arial", size=12)
    pdf.cell(95, 10, f"Order ID: #{order.id}")
    pdf.cell(95, 10, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", ln=True, align='R')
    pdf.line(10, 35, 200, 35)
    pdf.ln(10)

    # Table Header
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Item Name", border=1)
    pdf.cell(40, 10, "Qty", border=1, align='C')
    pdf.cell(50, 10, "Total", border=1, ln=True, align='C')

    # Table Rows (Items)
    pdf.set_font("Arial", size=12)
    for item in order.items:
        # Check if product exists to avoid crashes
        product_name = item.product.name if item.product else "Unknown Product"
        pdf.cell(100, 10, product_name, border=1)
        pdf.cell(40, 10, str(item.quantity), border=1, align='C')
        pdf.cell(50, 10, f"${(item.price_at_time * item.quantity):.2f}", border=1, ln=True, align='R')

    # Grand Total
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(140, 10, "TOTAL AMOUNT:", align='R')
    pdf.cell(50, 10, f"${order.total_revenue:.2f}", border=1, ln=True, align='R')

    # 3. Save and Send
    filename = f"receipt_{order_id}.pdf"
    pdf.output(filename)
    
    # as_attachment=True forces the browser to download it
    return send_file(filename, as_attachment=True)
    order = Order.query.get_or_404(order_id)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    
    # Header
    pdf.cell(190, 10, "RESTAURANT RECEIPT", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(190, 10, f"Order ID: #{order.id}", ln=True, align='C')
    pdf.cell(190, 10, f"Date: {order.created_at.strftime('%Y-%m-%d %H:%M')}", ln=True, align='C')
    pdf.ln(10)

    # Items Table Header
    pdf.set_font("Arial", 'B', 12)
    pdf.cell(100, 10, "Product", border=1)
    pdf.cell(40, 10, "Qty", border=1)
    pdf.cell(50, 10, "Total", border=1, ln=True)

    # Items
    pdf.set_font("Arial", size=12)
    for item in order.items:
        product = Product.query.get(item.product_id)
        name = product.name if product else "Unknown"
        pdf.cell(100, 10, name, border=1)
        pdf.cell(40, 10, str(item.quantity), border=1)
        pdf.cell(50, 10, f"${(item.price_at_time * item.quantity):.2f}", border=1, ln=True)

    # Total
    pdf.ln(5)
    pdf.set_font("Arial", 'B', 14)
    pdf.cell(140, 10, "GRAND TOTAL:", align='R')
    pdf.cell(50, 10, f"${order.total_revenue:.2f}", ln=True)

    # Save to a temporary file and send
    path = f"receipt_{order_id}.pdf"
    pdf.output(path)
    return send_file(path, as_attachment=True)

@app.route('/api/admin/users/create', methods=['POST'])
def create_backend_user():
    data = request.json
    if User.query.filter_by(username=data['username']).first():
        return jsonify({"success": False, "message": "Exists"}), 400
    new_user = User(
        username=data['username'], 
        password=data['password'], 
        role=data['role']
    )
    db.session.add(new_user)
    db.session.commit()
    return jsonify({"success": True})

@app.route('/api/orders/complete/<int:order_id>', methods=['POST'])
def complete_order_route(order_id):
    order = Order.query.get_or_404(order_id)
    order.status = 'Completed'
    db.session.commit()
    return jsonify({"success": True})

@app.route('/menu')
def guest_menu():
    return render_template('menu.html')

@app.route('/api/admin/tables/add', methods=['POST'])
def add_table():
    data = request.json
    table_num = data.get('table_number')
    
    # Check if table already exists
    if RestaurantTable.query.filter_by(table_number=table_num).first():
        return jsonify({"success": False, "message": "Table already exists"}), 400
        
    try:
        new_table = RestaurantTable(table_number=table_num, status='Available')
        db.session.add(new_table)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500



@app.route('/api/orders/cancel/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    order = Order.query.get_or_404(order_id)
    
    # Calculate time difference
    # order.created_at should be a DateTime column in your Model
    now = datetime.utcnow()
    time_diff = now - order.created_at
    
    if time_diff > timedelta(minutes=5):
        return jsonify({
            "success": False, 
            "message": "Cancellation window (5 mins) has expired. Please contact staff."
        }), 400
    
    if order.status == 'Completed':
        return jsonify({
            "success": False, 
            "message": "Order is already served and cannot be cancelled."
        }), 400

    try:
        # Instead of deleting, we usually mark as 'Cancelled' for records
        order.status = 'Cancelled'
        db.session.commit()
        return jsonify({"success": True, "message": "Order cancelled successfully."})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "message": str(e)}), 500

# @app.route('/api/admin/orders/create', methods=['POST'])
# def create_manual_order():
#     data = request.json
#     try:
#         new_order = Order(table_id=data.get('table_id'), user_id=session.get('user_id', 1), order_type='Manual', status='Pending')
#         db.session.add(new_order)
#         db.session.flush()
#         total_rev, total_cost = 0, 0
#         for item in data.get('items', []):
#             product = Product.query.get(item['product_id'])
#             qty = int(item['quantity'])
#             total_rev += product.price * qty
#             total_cost += product.cost * qty
#             db.session.add(OrderItem(order_id=new_order.id, product_id=product.id, quantity=qty, price_at_time=product.price))
#         new_order.total_revenue, new_order.total_profit = total_rev, total_rev - total_cost
#         db.session.commit()
#         return jsonify({"success": True, "order_id": new_order.id})
#     except Exception as e:
#         db.session.rollback()
#         return jsonify({"success": False, "message": str(e)}), 500

# @app.route('/api/admin/orders/create', methods=['POST'])
# def create_order():
    # data = request.json
    # items = data.get('items', [])
    # table_id = data.get('table_id')
    # order_type = data.get('order_type', 'Manual')
    # customer_phone = data.get('customer_phone') # From our new OTP flow

    # if not items:
    #     return jsonify({"success": False, "message": "No items in order"}), 400

    # try:
    #     # 1. Handle Customer Persistence
    #     # If order comes with a phone number, ensure user exists in DB
    #     if customer_phone:
    #         user = User.query.filter_by(username=customer_phone).first()
    #         if not user:
    #             new_user = User(username=customer_phone, role='customer')
    #             db.session.add(new_user)
        
    #     # 2. Calculate Total & Create Order
    #     total_price = 0
    #     for item in items:
    #         product = Product.query.get(item['product_id'])
    #         if product:
    #             total_price += product.price * item['quantity']

    #     new_order = Order(
    #         table_id=table_id,
    #         total_amount=total_price,
    #         status='Pending',
    #         order_type=order_type,
    #         created_at=datetime.utcnow() # Essential for the 5-min cancel fix
    #     )
    #     db.session.add(new_order)
    #     db.session.flush() # Gets the order ID before committing

    #     # 3. Add Order Items
    #     for item in items:
    #         order_item = OrderItem(
    #             order_id=new_order.id,
    #             product_id=item['product_id'],
    #             quantity=item['quantity']
    #         )
    #         db.session.add(order_item)

    #     # 4. Update Table Status
    #     # If a table is assigned, mark it as Occupied
    #     if table_id:
    #         table = RestaurantTable.query.filter_by(table_number=table_id).first()
    #         if table:
    #             table.status = 'Occupied'

    #     db.session.commit()
    #     return jsonify({
    #         "success": True, 
    #         "order_id": new_order.id, 
    #         "message": "Order placed and table status updated!"
    #     })

    # except Exception as e:
    #     db.session.rollback()
    #     return jsonify({"success": False, "message": str(e)}), 500


# @app.route('/api/admin/orders/create', methods=['POST'])
# def create_order():
#     data = request.json
#     items = data.get('items', [])
#     table_id = data.get('table_id')
#     order_type = data.get('order_type', 'Manual')
#     customer_phone = data.get('customer_phone')

#     if not items:
#         return jsonify({"success": False, "message": "No items in order"}), 400

#     try:
#         # 1. Handle User
#         user_id = None
#         if customer_phone:
#             user = User.query.filter_by(username=customer_phone).first()
#             if not user:
#                 user = User(username=customer_phone, role='customer')
#                 db.session.add(user)
#                 db.session.flush()
#             user_id = user.id

#         # 2. Calculate Revenue and Profit
#         calc_revenue = 0
#         calc_profit = 0
        
#         for item in items:
#             product = Product.query.get(item['product_id'])
#             if product:
#                 qty = int(item['quantity'])
#                 calc_revenue += product.price * qty
#                 # Calculate profit: (Price - Cost) * Qty
#                 # If your Product model doesn't have 'cost', use 0 or a default
#                 product_cost = getattr(product, 'cost', 0) or 0
#                 calc_profit += (product.price - product_cost) * qty

#         # 3. Create the Order (Using your exact column names)
#         new_order = Order(
#             table_id=table_id,
#             user_id=user_id,
#             total_revenue=calc_revenue, # Matches your model
#             total_profit=calc_profit,   # Matches your model
#             status='Pending',
#             order_type=order_type,
#             created_at=datetime.utcnow()
#         )
        
#         db.session.add(new_order)
#         db.session.flush()

#         # 4. Add Order Items
#         for item in items:
#             order_item = OrderItem(
#                 order_id=new_order.id,
#                 product_id=item['product_id'],
#                 quantity=item['quantity']
#             )
#             db.session.add(order_item)

#         # 5. Update Table Status
#         if table_id:
#             # Note: Your model has a ForeignKey to table.id
#             # Ensure table_id passed from frontend is the actual ID, not just number
#             table = RestaurantTable.query.get(table_id)
#             if table:
#                 table.status = 'Occupied'

#         db.session.commit()
#         return jsonify({"success": True, "message": "Order created successfully!"})

#     except Exception as e:
#         db.session.rollback()
#         print(f"Error: {str(e)}") # Useful for debugging in terminal
#         return jsonify({"success": False, "message": str(e)}), 500

# @app.route('/api/admin/orders/create', methods=['POST'])
# def create_order():
#     data = request.json
#     items = data.get('items', [])
#     table_id = data.get('table_id')
#     order_type = data.get('order_type', 'Manual')
#     customer_phone = data.get('customer_phone')

#     if not items:
#         return jsonify({"success": False, "message": "No items in order"}), 400

#     try:
#         # 1. Handle User (Modern Get)
#         user_id = None
#         if customer_phone:
#             user = User.query.filter_by(username=customer_phone).first()
#             if not user:
#                 user = User(username=customer_phone, role='customer')
#                 db.session.add(user)
#                 db.session.flush()
#             user_id = user.id

#         # 2. Calculate Revenue and Profit
#         calc_revenue = 0
#         calc_profit = 0
        
#         for item in items:
#             # FIX: Use db.session.get instead of legacy .query.get
#             product = db.session.get(Product, item['product_id'])
#             if product:
#                 qty = int(item['quantity'])
#                 calc_revenue += product.price * qty
#                 product_cost = getattr(product, 'cost', 0) or 0
#                 calc_profit += (product.price - product_cost) * qty

#         # 3. Create the Order (Using modern UTC time)
#         new_order = Order(
#             table_id=table_id,
#             user_id=user_id,
#             total_revenue=calc_revenue,
#             total_profit=calc_profit,
#             status='Pending',
#             order_type=order_type,
#             # FIX: Use timezone-aware UTC
#             created_at=datetime.now(timezone.utc)
#         )
        
#         db.session.add(new_order)
#         db.session.flush()

#         # 4. Add Order Items
#         for item in items:
#             order_item = OrderItem(
#                 order_id=new_order.id,
#                 product_id=item['product_id'],
#                 quantity=item['quantity'],
#                 price_at_time=db.session.get(Product, item['product_id']).price
#             )
#             db.session.add(order_item)

#         # 5. Update Table Status
#         if table_id:
#             # FIX: Use db.session.get
#             table = db.session.get(RestaurantTable, table_id)
#             if table:
#                 table.status = 'Occupied'

#         db.session.commit()
#         return jsonify({"success": True, "message": "Order created successfully!"})

#     except Exception as e:
#         db.session.rollback()
#         print(f"Error: {str(e)}")
#         return jsonify({"success": False, "message": str(e)}), 500

@app.route('/api/admin/orders/create', methods=['POST'])
def create_order():
    data = request.json
    items = data.get('items', [])
    table_id = data.get('table_id')
    order_type = data.get('order_type', 'Manual')
    customer_phone = data.get('customer_phone')

    if not items:
        return jsonify({"success": False, "message": "No items in order"}), 400

    try:
        # 1. Handle User
        user_id = None
        if customer_phone:
            user = User.query.filter_by(username=customer_phone).first()
            if not user:
                user = User(username=customer_phone, role='customer')
                db.session.add(user)
                db.session.flush()
            user_id = user.id

        # 2. Find existing active order or create new one
        # This is the "Session" logic: 
        # If the table was cleared, status won't be 'Pending', so this returns None.
        current_order = None
        if table_id:
            current_order = Order.query.filter_by(
                table_id=table_id, 
                status='Pending'
            ).first()

        if not current_order:
            current_order = Order(
                table_id=table_id,
                user_id=user_id,
                total_revenue=0,
                total_profit=0,
                status='Pending',
                order_type=order_type,
                created_at=datetime.now(timezone.utc)
            )
            db.session.add(current_order)
            db.session.flush()

        # 3. Add Order Items and Update Totals
        for item in items:
            product = db.session.get(Product, item['product_id'])
            if product:
                qty = int(item['quantity'])
                price = product.price
                cost = getattr(product, 'cost', 0) or 0
                
                # Update Order Totals
                current_order.total_revenue += price * qty
                current_order.total_profit += (price - cost) * qty

                # Create OrderItem
                order_item = OrderItem(
                    order_id=current_order.id,
                    product_id=item['product_id'],
                    quantity=qty,
                    price_at_time=price
                )
                db.session.add(order_item)

        # 4. Ensure Table is marked Occupied
        if table_id:
            table = db.session.get(RestaurantTable, table_id)
            if table:
                table.status = 'Occupied'

        db.session.commit()
        return jsonify({"success": True, "message": "Order processed successfully!", "order_id": current_order.id})

    except Exception as e:
        db.session.rollback()
        print(f"Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)}), 500



# (Keeping your other functional API routes below)
# @app.route('/api/analytics')
# def get_analytics():
#     now = datetime.utcnow()
#     cutoff = now.replace(hour=0, minute=0, second=0)
#     orders = Order.query.filter(Order.created_at >= cutoff).all()
#     return jsonify({"metrics": {"orders_created": len(orders), "revenue_generated": sum(o.total_revenue for o in orders), "profits_made": sum(o.total_profit for o in orders)}})

@app.route('/api/admin/tables', methods=['GET'])
def get_tables():
    tables = RestaurantTable.query.order_by(RestaurantTable.table_number).all()
    return jsonify([{"id": t.id, "table_number": t.table_number, "status": t.status} for t in tables])

@app.route('/api/admin/users')
def get_all_users():
    users = User.query.order_by(User.created_at.desc()).all()
    return jsonify([{"id": u.id, "username": u.username, "phone": u.phone, "role": u.role, "joined": u.created_at.strftime("%Y-%m-%d")} for u in users])

# @app.route('/api/admin/orders/live')
# def get_live_orders():
#     # Fetch the 50 most recent orders, including linked user data
#     orders = Order.query.order_by(Order.created_at.desc()).limit(50).all()
    
#     output = []
#     for o in orders:
#         # Get the associated user's phone if available
#         customer = User.query.get(o.user_id) if o.user_id else None
        
#         output.append({
#             "id": o.id,
#             "source": o.order_type or "QR",
#             "table_id": o.table_id,
#             "customer": customer.username if customer else "Guest",
#             "total": o.total_revenue,          # Legacy support for total.toFixed()
#             "total_revenue": o.total_revenue,  # Standardized key
#             "status": o.status or "Pending",
#             # ISO format is mandatory for the frontend 5-minute cancel logic
#             "time": o.created_at.isoformat() if o.created_at else datetime.utcnow().isoformat()
#         })
    
#     return jsonify(output)

@app.route('/api/products')
def get_prods():
    ps = Product.query.all()
    return jsonify([{"id":p.id,"name":p.name,"price":p.price,"tags":p.tags} for p in ps])

# ==========================================
# SEEDER
# ==========================================

@app.cli.command("init-db")
def init_db():
    db.drop_all()
    db.create_all()
    # Create default Admin
    admin_user = User(username="admin", password="password123", role="admin")
    db.session.add(admin_user)
    db.session.commit()
    print("Database Initialized! Login with admin / password123")

if __name__ == '__main__':
    app.run(debug=True)