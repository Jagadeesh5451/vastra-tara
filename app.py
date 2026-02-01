from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
import os
from werkzeug.utils import secure_filename
import urllib.parse

app = Flask(__name__)
app.secret_key = "vastra_secret"

# ---------------- UPLOAD CONFIG ----------------
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "images")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

ADMIN_USERNAME = "Jagadeesh"
ADMIN_PASSWORD = "12345"


def get_db():
    return sqlite3.connect("database.db")


# ---------------- HOME ----------------
@app.route("/")
def home():
    conn = get_db()
    cur = conn.cursor()

    # ✅ FETCH ALL PRODUCTS (including out of stock)
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

    # ✅ Fetch available colours per product
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
        images_by_colour.setdefault(colour, []).append("images/" + image)

    return render_template(
        "product.html",
        product=product,              # (id, name, price, description, quantity)
        images_by_colour=images_by_colour,
        cart=session.get("cart", [])
    )



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


# ---------------- ADMIN PANEL ----------------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect("/admin/login")

    conn = get_db()
    cur = conn.cursor()

    # ---------- CREATE PRODUCT ----------
    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        quantity = request.form.get("quantity")
        description = request.form.get("description")

        if name and price and quantity:
            cur.execute("""
                INSERT INTO products (name, price, quantity, description)
                VALUES (?, ?, ?, ?)
            """, (name, price, quantity, description))

            conn.commit()

    # ---------- FETCH PRODUCTS ----------
    cur.execute("""
        SELECT id, name, price, description, quantity
        FROM products
        ORDER BY id DESC
    """)
    products = cur.fetchall()

    conn.close()

    return render_template("admin.html", products=products)

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
            cur.execute(
                "INSERT INTO product_images (product_id, color, image) VALUES (?, ?, ?)",
                (product_id, color, filename)
            )

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
def delete(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (id,))
    conn.commit()
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
    cur.execute(
        "SELECT quantity FROM products WHERE id = ?",
        (product_id,)
    )
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
    colour = request.form.get("colour")
    qty = int(request.form.get("quantity", 1))

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT 
            p.id,
            p.name,
            p.price,
            p.quantity,
            (
                SELECT image
                FROM product_images
                WHERE product_id = p.id AND color = ?
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
        "colour": colour
    }]

    session["buy_now_total"] = subtotal
    session.modified = True

    return redirect("/checkout")


# ---------------- CHECKOUT ----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    products = []
    total = 0

    # ================= BUY NOW =================
    if session.get("buy_now"):
        products = session["buy_now"]
        total = session.get("buy_now_total", 0)

    # ================= FROM CART =================
    elif request.method == "POST" and request.form.get("from_cart"):
        conn = get_db()
        cur = conn.cursor()

        selected_ids = request.form.getlist("selected_products")

        for idx in selected_ids:
            item = session["cart"][int(idx)]

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
            if not row:
                continue

            pid, name, price, stock, image = row
            qty = int(item.get("quantity", 1))

            # ❌ Prevent over-buy
            if qty > stock:
                qty = stock

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

    # ================= PLACE ORDER =================
    if request.method == "POST" and products:
        name = request.form.get("name")
        phone = request.form.get("phone")
        address = request.form.get("address")

        if name and phone and address:

            # -------- WhatsApp Message --------
            message = "New Order - Vastra Tara 🧵\n\n"
            message += f"Name: {name}\nPhone: {phone}\nAddress: {address}\n\nProducts:\n"

            for p in products:
                message += (
                    f"- {p['name']} ({p['colour']}) "
                    f"x{p['quantity']} = ₹{p['subtotal']}\n"
                )

            message += f"\nTotal: ₹{total}\nPayment: Cash on Delivery"

            # -------- Reduce Stock --------
            conn = get_db()
            cur = conn.cursor()

            for p in products:
                cur.execute("""
                    UPDATE products
                    SET quantity = quantity - ?
                    WHERE id = ? AND quantity >= ?
                """, (p["quantity"], p["id"], p["quantity"]))

            conn.commit()
            conn.close()

            # -------- Clear Sessions --------
            session.pop("buy_now", None)
            session.pop("buy_now_total", None)
            session.pop("cart", None)

            whatsapp_url = (
                "https://wa.me/919390708120?text="
                + urllib.parse.quote(message)
            )
            return redirect(whatsapp_url)

    return render_template("checkout.html", products=products, total=total)

if __name__ == "__main__":
    app.run(debug=True)
