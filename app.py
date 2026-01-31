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

    # Products + one image
    cur.execute("""
        SELECT p.id, p.name, p.price,
               (SELECT image FROM product_images
                WHERE product_id = p.id
                LIMIT 1)
        FROM products p
    """)
    products = cur.fetchall()

    # Colours per product
    cur.execute("""
        SELECT product_id, GROUP_CONCAT(DISTINCT color)
        FROM product_images
        GROUP BY product_id
    """)

    product_colours = {
        row[0]: row[1].split(",")
        for row in cur.fetchall()
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

    cur.execute("SELECT id, name, price FROM products WHERE id=?", (product_id,))
    product = cur.fetchone()

    if not product:
        conn.close()
        return redirect("/")

    cur.execute("""
        SELECT color, image
        FROM product_images
        WHERE product_id=?
    """, (product_id,))

    rows = cur.fetchall()
    conn.close()

    images_by_colour = {}
    for colour, image in rows:
        images_by_colour.setdefault(colour, []).append("images/" + image)

    return render_template(
        "product.html",
        product=product,
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

    if request.method == "POST":
        name = request.form.get("name")
        price = request.form.get("price")
        if name and price:
            cur.execute(
                "INSERT INTO products (name, price) VALUES (?, ?)",
                (name, price)
            )
            conn.commit()

    cur.execute("SELECT * FROM products")
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
    product_id = request.form.get("product_id")
    colour = request.form.get("colour")

    if not product_id:
        return redirect("/")

    session.setdefault("cart", [])
    session["cart"].append({
        "id": int(product_id),
        "colour": colour
    })
    session.modified = True
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
            SELECT p.id, p.name, p.price,
                   (SELECT image FROM product_images
                    WHERE product_id = p.id
                    AND color = ?
                    LIMIT 1)
            FROM products p
            WHERE p.id = ?
        """, (item["colour"], item["id"]))

        product = cur.fetchone()
        if product:
            products.append({
                "index": index,
                "id": product[0],
                "name": product[1],
                "price": product[2],
                "image": product[3],
                "colour": item["colour"]
            })
            total += product[2]
    conn.close()
    return render_template("cart.html", products=products, total=total)
#-----------------Remove from cart----------------
@app.route("/remove_from_cart/<int:index>")
def remove_from_cart(index):
    cart = session.get("cart", [])

    if 0 <= index < len(cart):
        cart.pop(index)
        session.modified = True

    return redirect("/cart")
# ---------------- BUY NOW ----------------
@app.route("/buy_now/<int:id>")
def buy_now(id):
    session["buy_now"] = id
    session.modified = True
    return redirect("/checkout")


# ---------------- CHECKOUT ----------------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    conn = get_db()
    cur = conn.cursor()

    products = []
    total = 0

    # ---------------- BUY NOW FLOW ----------------
    if request.method == "POST" and request.form.get("buy_now"):
        product_id = request.form.get("product_id")
        colour = request.form.get("colour")

        cur.execute("""
            SELECT p.id, p.name, p.price,
                   (SELECT image FROM product_images
                    WHERE product_id = p.id AND color = ?
                    LIMIT 1)
            FROM products p
            WHERE p.id = ?
        """, (colour, product_id))

        row = cur.fetchone()
        if row:
            products.append({
                "id": row[0],
                "name": row[1],
                "price": row[2],
                "image": row[3],
                "colour": colour
            })
            total = row[2]

    # ---------------- CART FLOW ----------------
    elif request.method == "POST":
        selected_ids = request.form.getlist("selected_products")

        for idx in selected_ids:
            item = session["cart"][int(idx)]

            cur.execute("""
                SELECT p.id, p.name, p.price,
                       (SELECT image FROM product_images
                        WHERE product_id = p.id AND color = ?
                        LIMIT 1)
                FROM products p
                WHERE p.id = ?
            """, (item["colour"], item["id"]))

            row = cur.fetchone()
            if row:
                products.append({
                    "id": row[0],
                    "name": row[1],
                    "price": row[2],
                    "image": row[3],
                    "colour": item["colour"]
                })
                total += row[2]

    # ---------------- PLACE ORDER ----------------
    if request.method == "POST" and products:
        name = request.form.get("name")
        phone = request.form.get("phone")
        address = request.form.get("address")

        if name and phone and address:
            message = "New Order - Vastra Tara 🧵\n\n"
            message += f"Name: {name}\nPhone: {phone}\nAddress: {address}\n\nProducts:\n"

            for p in products:
                message += f"- {p['name']} ({p['colour']}) ₹{p['price']}\n"

            message += f"\nTotal: ₹{total}\nPayment: Cash on Delivery"

            whatsapp_url = (
                "https://wa.me/919390708120?text=" +
                urllib.parse.quote(message)
            )

            conn.close()
            return redirect(whatsapp_url)

    conn.close()
    return render_template("checkout.html", products=products, total=total)


if __name__ == "__main__":
    app.run(debug=True)
