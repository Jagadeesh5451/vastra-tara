from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from flask import session

app = Flask(__name__)
app.secret_key = "vastra_secret"

def get_db():
    return sqlite3.connect("database.db")

# ---------- HOME ----------
@app.route("/")
def home():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM products")
    products = cur.fetchall()
    conn.close()
    return render_template("home.html", products=products)

# ---------- ADMIN ----------
@app.route("/admin", methods=["GET", "POST"])
def admin():
    conn = get_db()
    cur = conn.cursor()

    if request.method == "POST":
        name = request.form["name"]
        price = request.form["price"]

        cur.execute("INSERT INTO products (name, price) VALUES (?, ?)", (name, price))
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

    session["cart"].append(id)
    session.modified = True
    return redirect(url_for("cart"))

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
