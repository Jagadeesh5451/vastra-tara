from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename
import urllib.parse
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from flask import redirect, session
from datetime import timedelta
app = Flask(__name__)
app.permanent_session_lifetime = 0
app.permanent_session_lifetime = timedelta(days=1)
app.secret_key = "vastra_secret"

# ---------------- UPLOAD CONFIG ----------------
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ADMIN_USERNAME = "Jagadeesh"
ADMIN_PASSWORD = "12345"
# ---------------- DB ----------------
def get_db():
    conn = sqlite3.connect(
        "database.db",
        timeout=30,              # wait instead of locking
        check_same_thread=False  # allow Flask threads
    )
    conn.row_factory = sqlite3.Row

    # Enable WAL mode (critical)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")

    return conn

#---------------login---------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return decorated_function

#---------signup-------------------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        full_name = request.form.get("full_name")
        phone = request.form.get("phone")
        password = request.form.get("password")
        confirm = request.form.get("confirm")

        if not all([full_name, phone, password, confirm]):
            return render_template("signup.html", error="All fields required")

        if password != confirm:
            return render_template("signup.html", error="Passwords do not match")

        conn = get_db()
        cur = conn.cursor()

        # ✅ CHECK ONLY BY PHONE
        cur.execute(
            "SELECT id FROM users WHERE phone = ?",
            (phone,)
        )
        exists = cur.fetchone()

        if exists:
            conn.close()
            return render_template(
                "signup.html",
                error="Mobile already registered"
            )

        # ✅ INSERT NEW USER
        cur.execute("""
            INSERT INTO users (full_name, phone, password)
            VALUES (?, ?, ?)
        """, (full_name, phone, password))

        conn.commit()
        conn.close()

        return redirect("/login")

    return render_template("signup.html")

#-----------------login------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")

        conn = get_db()
        cur = conn.cursor()

        cur.execute("""
            SELECT id, full_name
            FROM users
            WHERE phone = ? AND password = ?
        """, (phone, password))

        user = cur.fetchone()
        conn.close()

        if user:
            session.permanent = True
            session["user_id"] = user[0]
            session["full_name"] = user[1]   # ✅ THIS FIXES "Hello None"
            # auto logout on browser close
            return redirect("/")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

#--------------logout------------
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- HOME ----------------
@app.route("/")
@login_required
def home():
    search = request.args.get("search", "").strip()

    conn = get_db()
    cur = conn.cursor()

    if search:
        cur.execute("""
            SELECT 
                p.id,
                p.name,
                p.price,
                (
                    SELECT image
                    FROM product_images
                    WHERE product_id = p.id
                    LIMIT 1
                ) AS image,
                CAST(p.quantity AS INTEGER) AS quantity
            FROM products p
            WHERE p.name LIKE ?
               OR p.description LIKE ?
            ORDER BY p.id DESC
        """, (f"%{search}%", f"%{search}%"))
    else:
        cur.execute("""
            SELECT 
                p.id,
                p.name,
                p.price,
                (
                    SELECT image
                    FROM product_images
                    WHERE product_id = p.id
                    LIMIT 1
                ) AS image,
                CAST(p.quantity AS INTEGER) AS quantity
            FROM products p
            ORDER BY p.id DESC
        """)

    products = cur.fetchall()

    # Fetch available colours
    cur.execute("""
        SELECT product_id, GROUP_CONCAT(DISTINCT color)
        FROM product_images
        GROUP BY product_id
    """)

    product_colours = {
        row[0]: row[1].split(",")
        for row in cur.fetchall()
        if row[1]
    }

    conn.close()

    return render_template(
        "home.html",
        products=products,
        product_colours=product_colours
    )
# ---------------- PRODUCT DETAILS ----------------
@app.route("/product/<int:product_id>")
def product_detail(product_id):
    conn = get_db()
    cur = conn.cursor()

    # ✅ FETCH PRODUCT WITH QUANTITY
    cur.execute("""
        SELECT id, name, price, description, quantity
        FROM products
        WHERE id = ?
    """, (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        return redirect("/")

    # ❌ If out of stock → redirect to home
    if product[4] <= 0:
        conn.close()
        return redirect("/")

    # ✅ FETCH IMAGES GROUPED BY COLOUR
    cur.execute("""
        SELECT color, image
        FROM product_images
        WHERE product_id = ?
    """, (product_id,))
    rows = cur.fetchall()
    conn.close()

    images_by_colour = {}

    for colour, image in rows:
        safe_colour = colour if colour else "Default"
        images_by_colour.setdefault(safe_colour, []).append("images/" + image)

    return render_template(
        "product.html",
        product=product,              # (id, name, price, description, quantity)
        images_by_colour=images_by_colour,
        cart=session.get("cart", [])
    )


# ======================= ADMIN =======================

# ---------------- ADMIN LOGIN ----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        if (
            request.form["username"] == ADMIN_USERNAME
            and request.form["password"] == ADMIN_PASSWORD
        ):
            session["admin_logged_in"] = True
            return redirect("/admin")
        return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")

# ---------- ADMIN PANEL ----------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute(
            "INSERT INTO products (name,price,quantity,description) VALUES (?,?,?,?)",
            (
                request.form.get("name"),
                request.form.get("price"),
                request.form.get("quantity"),
                request.form.get("description")
            )
        )
        conn.commit()

    cur.execute("SELECT id,name,price,description,quantity FROM products ORDER BY id DESC")
    products = cur.fetchall()
    conn.close()

    return render_template("admin.html", products=products)

# ---------- UPDATE PRODUCT ----------
@app.route("/admin/product/update/<int:product_id>", methods=["POST"])
def admin_update_product(product_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE products SET price=?, quantity=? WHERE id=?",
        (request.form.get("price"), request.form.get("quantity"), product_id)
    )
    conn.commit()
    conn.close()
    return redirect("/admin")
#--------Admin Product Images------------
@app.route("/admin/product/<int:product_id>/images")
def admin_product_images(product_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    # Fetch product
    cur.execute(
        "SELECT id, name FROM products WHERE id = ?",
        (product_id,)
    )
    product = cur.fetchone()

    if not product:
        conn.close()
        return redirect("/admin")

    # Fetch images
    cur.execute("""
        SELECT id, color, image
        FROM product_images
        WHERE product_id = ?
    """, (product_id,))
    images = cur.fetchall()

    conn.close()

    return render_template(
        "admin_product_images.html",
        product=product,
        images=images
    )

# ---------- ADD MORE IMAGES ----------
@app.route("/admin/product/<int:product_id>/add-images", methods=["POST"])
def admin_add_more_images(product_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    for img in request.files.getlist("images"):
        if img.filename:
            filename = secure_filename(img.filename)
            img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
            color = request.form.get("color") or "default"

            cur.execute(
                "INSERT INTO product_images (product_id, color, image) VALUES (?, ?, ?)",
                (product_id, color, filename)
            )

    conn.commit()
    conn.close()
    return redirect(request.referrer)

# ---------- REPLACE IMAGE ----------
@app.route("/admin/image/replace/<int:image_id>", methods=["POST"])
def replace_image(image_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    file = request.files.get("image")
    if not file or not file.filename:
        return redirect(request.referrer)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT image FROM product_images WHERE id=?", (image_id,))
    old = cur.fetchone()

    if old:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], old[0])
        if os.path.exists(old_path):
            os.remove(old_path)

        filename = secure_filename(file.filename)
        file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        cur.execute("UPDATE product_images SET image=? WHERE id=?", (filename, image_id))

    conn.commit()
    conn.close()
    return redirect(request.referrer)

# ---------- DELETE IMAGE ----------
@app.route("/admin/image/delete/<int:image_id>")
def delete_image(image_id):
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT image FROM product_images WHERE id=?", (image_id,))
    row = cur.fetchone()

    if row:
        path = os.path.join(app.config["UPLOAD_FOLDER"], row[0])
        if os.path.exists(path):
            os.remove(path)
        cur.execute("DELETE FROM product_images WHERE id=?", (image_id,))

    conn.commit()
    conn.close()
    return redirect(request.referrer)

#------------------orders------------
@app.route("/orders")
@login_required
def orders():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            id,
            product_name,
            colour,
            quantity,
            total,
            created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, (session["user_id"],))

    orders = cur.fetchall()
    conn.close()

    return render_template("orders.html", orders=orders)

# ---------------- ADMIN ADD IMAGES ----------------
@app.route("/admin/add-images", methods=["POST"])
def add_images():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    product_id = request.form.get("product_id")
    color = request.form.get("color")
    images = request.files.getlist("images")

    conn = get_db()
    cur = conn.cursor()

    for img in images:
        if img.filename:
            filename = secure_filename(img.filename)
            img.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

            cur.execute("""
                INSERT INTO product_images (product_id, color, image)
                VALUES (?, ?, ?)
            """, (product_id, color, filename))

    conn.commit()
    conn.close()
    return redirect("/admin")




# ---------------- ADMIN LOGOUT ----------------
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect("/admin/login")


# ---------------- DELETE PRODUCT ----------------
@app.route("/delete/<int:id>")
@login_required
def delete(id):
    conn = get_db()
    cur = conn.cursor()

    try:
        cur.execute("DELETE FROM product_images WHERE product_id = ?", (id,))
        cur.execute("DELETE FROM orders WHERE product_id = ?", (id,))
        cur.execute("DELETE FROM products WHERE id = ?", (id,))
        conn.commit()
    except Exception as e:
        conn.rollback()
        print("Delete error:", e)
    finally:
        conn.close()

    return redirect("/admin")


# ---------------- ADD TO CART ----------------
@app.route("/add_to_cart", methods=["POST"])
def add_to_cart():
    try:
        product_id = int(request.form.get("product_id"))
        colour = request.form.get("colour")
        qty = int(request.form.get("quantity", 1))
    except (TypeError, ValueError):
        return redirect("/")

    if qty <= 0:
        return redirect("/cart")

    conn = get_db()
    cur = conn.cursor()

    # -------- Fetch Stock --------
    cur.execute("""
        SELECT quantity
        FROM product_images
        WHERE product_id = ? AND color = ?
        LIMIT 1
    """, (product_id, colour))
    row = cur.fetchone()

    if not row:
        conn.close()
        return redirect("/")

    stock = row[0]

    session.setdefault("cart", [])

    # -------- Merge Same Product + Colour --------
    for item in session["cart"]:
        if item["id"] == product_id and item["colour"] == colour:
            new_qty = item["quantity"] + qty

            # ❌ Prevent exceeding stock
            if new_qty > stock:
                item["quantity"] = stock
            else:
                item["quantity"] = new_qty

            session.modified = True
            conn.close()
            return redirect("/cart")

    # -------- New Cart Item --------
    if qty > stock:
        qty = stock

    session["cart"].append({
        "id": product_id,
        "colour": colour,
        "quantity": qty
    })

    session.modified = True
    conn.close()
    return redirect("/cart")


# ---------------- REMOVE FROM CART ----------------


# ---------------- CART ----------------
@login_required
@app.route("/cart")
def cart():
    conn = get_db()
    cur = conn.cursor()

    products = []
    total = 0

    for index, item in enumerate(session.get("cart", [])):

        cur.execute("""
            SELECT 
                p.id,
                p.name,
                p.price,
                p.quantity,
                (
                    SELECT image
                    FROM product_images
                    WHERE product_id = p.id
                    AND color = ?
                    LIMIT 1
                )
            FROM products p
            WHERE p.id = ?
        """, (item["colour"], item["id"]))

        row = cur.fetchone()

        if row:
            product_id, name, price, stock, image = row
            qty = item["quantity"]

            subtotal = price * qty
            total += subtotal

            products.append({
                "index": index,
                "id": product_id,
                "name": name,
                "price": price,
                "quantity": qty,        # ✅ IMPORTANT
                "subtotal": subtotal,   # ✅ IMPORTANT
                "image": image,
                "colour": item["colour"],
                "stock": stock
            })

    conn.close()

    return render_template(
        "cart.html",
        products=products,
        total=total
    )
#-----------------Remove from cart----------------
@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):
    cart = session.get("cart", [])

    if 0 <= index < len(cart):
        cart.pop(index)
        session.modified = True

    return redirect("/cart")
# ---------------- BUY NOW ----------------
@app.route("/buy_now/<int:id>", methods=["POST"])
def buy_now(id):
    colour = request.form.get("colour")  # may be None
    qty = int(request.form.get("quantity", 1))

    conn = get_db()
    cur = conn.cursor()

    # 🔹 If colour is NOT provided, pick first image automatically
    if not colour:
        cur.execute("""
            SELECT color
            FROM product_images
            WHERE product_id = ?
            LIMIT 1
        """, (id,))
        row = cur.fetchone()
        colour = row[0] if row else None

    cur.execute("""
        SELECT 
            p.id,
            p.name,
            p.price,
            p.quantity,
            (
                SELECT image
                FROM product_images
                WHERE product_id = p.id
                AND color = ?
                LIMIT 1
            )
        FROM products p
        WHERE p.id = ?
    """, (colour, id))

    row = cur.fetchone()
    conn.close()

    if not row:
        return redirect("/")

    pid, name, price, stock, image = row

    if qty > stock:
        qty = stock

    subtotal = price * qty

    session["buy_now"] = [{
        "id": pid,
        "name": name,
        "price": price,
        "quantity": qty,
        "subtotal": subtotal,
        "image": image,
        "colour": colour or "Default"
    }]

    session["buy_now_total"] = subtotal
    session.modified = True

    return redirect("/checkout")



# ---------------- CHECKOUT ----------------
@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    products = []
    total = 0

    # ================= PLACE ORDER =================
    if request.method == "POST" and request.form.get("place_order"):

        name = request.form.get("name")
        phone = request.form.get("phone")
        address = request.form.get("address")

        products = session.get("checkout_products", [])
        total = session.get("checkout_total", 0)

        if not products or not name or not phone or not address:
            return redirect("/checkout")

        message = "🧵 *New Order - VastraTara*\n\n"
        message += f"👤 Name: {name}\n"
        message += f"📞 Phone: {phone}\n"
        message += f"🏠 Address: {address}\n\n"
        message += "*Products:*\n"

        conn = get_db()
        cur = conn.cursor()

        for p in products:
            message += (
                f"- {p['name']} ({p['colour']}) "
                f"x{p['quantity']} = ₹{p['subtotal']}\n"
            )

            cur.execute("""
                INSERT INTO orders (
                    user_id, product_name, colour,
                    quantity, price, total
                ) VALUES (?, ?, ?, ?, ?, ?)
            """, (
                session["user_id"],
                p["name"],
                p["colour"],
                p["quantity"],
                p["price"],
                p["subtotal"]
            ))

            cur.execute("""
                UPDATE products
                SET quantity = quantity - ?
                WHERE id = ? AND quantity >= ?
            """, (p["quantity"], p["id"], p["quantity"]))

        conn.commit()
        conn.close()

        # clear sessions safely
        session.pop("checkout_products", None)
        session.pop("checkout_total", None)
        session.pop("cart", None)
        session.pop("buy_now", None)
        session.pop("buy_now_total", None)

        message += f"\n💰 *Total: ₹{total}*\n"
        message += "💳 Payment: Cash on Delivery"

        whatsapp_url = (
            "https://wa.me/919390708120?text="
            + urllib.parse.quote(message)
        )
        session["whatsapp_url"] = whatsapp_url
        return redirect("/order-success")

    # ================= FROM CART =================
    if request.method == "POST" and request.form.get("from_cart"):

        cart = session.get("cart", [])
        if not cart:
            return redirect("/cart")

        conn = get_db()
        cur = conn.cursor()

        selected_ids = request.form.getlist("selected_products")

        for idx in selected_ids:
            idx = int(idx)

            if idx >= len(cart):
                continue

            item = cart[idx]
            qty = int(request.form.get(f"quantity_{idx}", 1))

            if qty <= 0:
                continue

            cur.execute("""
                SELECT 
                    p.id, p.name, p.price,
                    (
                        SELECT image
                        FROM product_images
                        WHERE product_id = p.id
                        AND color = ?
                        LIMIT 1
                    )
                FROM products p
                WHERE p.id = ?
            """, (item["colour"], item["id"]))

            row = cur.fetchone()
            if not row:
                continue

            pid, name, price, image = row
            subtotal = price * qty
            total += subtotal

            products.append({
                "id": pid,
                "name": name,
                "price": price,
                "quantity": qty,
                "subtotal": subtotal,
                "image": image,
                "colour": item["colour"]
            })

        conn.close()

        session["checkout_products"] = products
        session["checkout_total"] = total

    # ================= BUY NOW =================
    elif session.get("buy_now"):
        products = session["buy_now"]
        total = session.get("buy_now_total", 0)

        session["checkout_products"] = products
        session["checkout_total"] = total

    return render_template(
        "checkout.html",
        products=products,
        total=total
    )

@app.route("/cancel_order/<int:order_id>")
@login_required
def cancel_order(order_id):
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT product_name, colour, quantity, total
        FROM orders
        WHERE id = ? AND user_id = ?
    """, (order_id, session["user_id"]))

    order = cur.fetchone()
    if not order:
        conn.close()
        return redirect("/orders")

    product_name, colour, qty, total = order

    # Restore stock
    cur.execute("""
        UPDATE products
        SET quantity = quantity + ?
        WHERE name = ?
    """, (qty, product_name))

    # Delete order
    cur.execute("DELETE FROM orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    # WhatsApp message
    customer = session.get("full_name", "Customer")

    message = (
        "❌ *Order Cancelled - VastraTara*\n\n"
        f"Customer: {customer}\n"
        f"Product: {product_name}\n"
        f"Colour: {colour}\n"
        f"Quantity: {qty}\n"
        f"Amount: ₹{total}\n\n"
        "Stock restored successfully."
    )

    whatsapp_url = (
        "https://wa.me/919390708120?text="
        + urllib.parse.quote(message)
    )

    return redirect(whatsapp_url)

@app.route("/order-success")
@login_required
def order_success():
    return render_template("order_success.html")


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)
