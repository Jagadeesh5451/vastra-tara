from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from flask import session
import os
from werkzeug.utils import secure_filename
from flask import request

app = Flask(__name__)
app.secret_key = "vastra_secret"
UPLOAD_FOLDER = "static/images"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
# Admin credentials (change these)
ADMIN_USERNAME = "Jagadeesh"
ADMIN_PASSWORD = "12345"


def get_db():
    return sqlite3.connect("database.db")

# ---------- HOME ----------
@app.route("/")
def home():
    search_query = request.args.get("search", "")

    conn = get_db()
    cur = conn.cursor()

    if search_query:
        cur.execute(
            "SELECT * FROM products WHERE name LIKE ?",
            ('%' + search_query + '%',)
        )
    else:
        cur.execute("SELECT * FROM products")

    products = cur.fetchall()
    conn.close()

    return render_template("home.html", products=products, search_query=search_query)
@app.route("/product/<int:id>")
def product_details(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (id,))
    product = cur.fetchone()
    conn.close()

    if not product:
        return redirect("/")

    return render_template(
        "product.html",
        product=product,
        cart=session.get("cart", [])
    )
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin_logged_in"] = True
            return redirect(url_for("admin"))
        else:
            return render_template("admin_login.html", error="Invalid credentials")

    return render_template("admin_login.html")
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))
# ---------- ADMIN ----------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        price = request.form["price"]
        image_file = request.files["image"]

        filename = ""
        if image_file:
            filename = secure_filename(image_file.filename)
            image_file.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

        cur.execute(
            "INSERT INTO products (name, price, image) VALUES (?, ?, ?)",
            (name, price, filename)
        )
        conn.commit()

    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    conn.close()

    return render_template("admin.html", products=products)

# ---------- DELETE ----------
@app.route("/delete/<int:id>")
def delete(id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return redirect(url_for("admin"))
# ---------- ADD TO CART ----------
@app.route("/add_to_cart/<int:id>")
def add_to_cart(id):
    if "cart" not in session:
        session["cart"] = []

    if id not in session["cart"]:
        session["cart"].append(id)
        session.modified = True

    return redirect("/")

#--------Remove From cart----------------
@app.route("/remove_from_cart/<int:id>")
def remove_from_cart(id):
    if "cart" in session and id in session["cart"]:
        session["cart"].remove(id)
        session.modified = True

    return redirect("/")

# ---------- CART PAGE ----------
@app.route("/cart")
def cart():
    cart_items = session.get("cart", [])

    conn = get_db()
    cur = conn.cursor()

    products = []
    total = 0
    for item_id in cart_items:
        cur.execute("SELECT * FROM products WHERE id=?", (item_id,))
        product = cur.fetchone()
        if product:
            products.append(product)
            total += product[2]

    conn.close()
    return render_template("cart.html", products=products, total=total)
# ---------- CHECKOUT ----------
import urllib.parse

@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    if request.method == "GET" and not session.get("cart"):
        return redirect(url_for("cart"))
    if request.method == "POST":
        name = request.form["name"]
        phone = request.form["phone"]
        address = request.form["address"]

        cart_items = session.get("cart", [])

        conn = get_db()
        cur = conn.cursor()

        product_list = []
        total = 0

        for item_id in cart_items:
            cur.execute("SELECT * FROM products WHERE id=?", (item_id,))
            product = cur.fetchone()
            if product:
                product_list.append(product)
                total += product[2]

        conn.close()

        message = f"""
New Order - Vastra Tara 🧵

Name: {name}
Phone: {phone}
Address: {address}

Products:
"""
        for p in product_list:
            message += f"- {p[1]} (₹{p[2]})\n"

        message += f"\nTotal: ₹{total}\nPayment: Cash on Delivery"

        encoded_msg = urllib.parse.quote(message)

        whatsapp_number = "919390708120"  # <-- PUT YOUR NUMBER HERE (with country code)

        whatsapp_url = f"https://wa.me/{whatsapp_number}?text={encoded_msg}"

        session.pop("cart", None)

        return redirect(whatsapp_url)

    return render_template("checkout.html")


if __name__ == "__main__":
    app.run()
