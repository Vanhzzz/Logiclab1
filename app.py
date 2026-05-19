from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta
from functools import wraps
from typing import Any, Dict, Optional

import mysql.connector
from flask import Flask, flash, jsonify, redirect, render_template, request, session, url_for

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "dev-secret")

DB_CONFIG = {
    "host": os.getenv("DB_HOST", "127.0.0.1"),
    "port": int(os.getenv("DB_PORT", "3306")),
    "user": os.getenv("DB_USER", "lab"),
    "password": os.getenv("DB_PASSWORD", "labpass"),
    "database": os.getenv("DB_NAME", "labdb"),
    "autocommit": False,
}

COUPON_CODE = "BLACKBOX10"
COUPON_PERCENT = 10
COUPON_MAX_USES = 5

PRODUCT_SEED = [
    {
        "name": 'Lightweight "l33t" Leather Jacket',
        "price_cents": 50000,
        "rating": 5,
        "image": "jacket.svg",
        "description": "A premium target item for the blackbox shop. Complete this order after you have enough wallet balance.",
        "is_target": True,
    },
    {
        "name": "Balance Beams",
        "price_cents": 1611,
        "rating": 1,
        "image": "beams.svg",
        "description": "A small balance item for checkout and refund workflow testing.",
        "is_target": False,
    },
    {
        "name": "High-End Gift Wrapping",
        "price_cents": 1577,
        "rating": 2,
        "image": "wrap.svg",
        "description": "Premium wrapping with a product reference attached to each order action.",
        "is_target": False,
    },
    {
        "name": "Giant Pillow Thing",
        "price_cents": 3313,
        "rating": 4,
        "image": "pillow.svg",
        "description": "A soft item with delayed refund review behavior.",
        "is_target": False,
    },
    {
        "name": "WebSec Pro Trial Box",
        "price_cents": 4999,
        "rating": 3,
        "image": "enterprise.svg",
        "description": "A trial security box for normal checkout and refund testing.",
        "is_target": False,
    },
]


def db():
    return mysql.connector.connect(**DB_CONFIG)


def ref(n: int = 16) -> str:
    return secrets.token_hex(n // 2)


def money(cents: int | float | None) -> str:
    cents = int(cents or 0)
    return f"${cents / 100:.2f}"


app.jinja_env.filters["money"] = money


def fetch_one(sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    conn = db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def fetch_all(sql: str, params: tuple = ()) -> list[Dict[str, Any]]:
    conn = db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(sql, params)
        return cur.fetchall()
    finally:
        conn.close()


def execute(sql: str, params: tuple = ()) -> None:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_schema() -> None:
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(64) UNIQUE NOT NULL,
                password VARCHAR(128) NOT NULL,
                wallet_cents INT NOT NULL DEFAULT 10000,
                flag VARCHAR(128) NOT NULL
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ref VARCHAR(64) UNIQUE NOT NULL,
                name VARCHAR(255) NOT NULL,
                price_cents INT NOT NULL,
                rating INT NOT NULL DEFAULT 3,
                image VARCHAR(255) NOT NULL,
                description TEXT NOT NULL,
                display_order INT NOT NULL DEFAULT 0,
                is_target TINYINT NOT NULL DEFAULT 0
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ref VARCHAR(64) UNIQUE NOT NULL,
                user_id INT NOT NULL,
                product_id INT NOT NULL,
                quantity INT NOT NULL DEFAULT 1,
                amount_cents INT NOT NULL,
                discount_cents INT NOT NULL DEFAULT 0,
                coupon_code VARCHAR(64) DEFAULT NULL,
                status VARCHAR(32) NOT NULL,
                kind VARCHAR(32) NOT NULL DEFAULT 'NORMAL',
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (product_id) REFERENCES products(id)
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS refunds (
                id INT AUTO_INCREMENT PRIMARY KEY,
                ref VARCHAR(64) UNIQUE NOT NULL,
                order_id INT NOT NULL,
                requested_product_ref VARCHAR(64) NOT NULL,
                refund_amount_cents INT DEFAULT NULL,
                status VARCHAR(32) NOT NULL,
                reason VARCHAR(255) DEFAULT '',
                due_at DATETIME NOT NULL,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (order_id) REFERENCES orders(id)
            )
            """
        )
        # Backward-compatible columns for users who reuse an old MySQL volume.
        for sql in [
            "ALTER TABLE orders ADD COLUMN quantity INT NOT NULL DEFAULT 1",
            "ALTER TABLE orders ADD COLUMN discount_cents INT NOT NULL DEFAULT 0",
            "ALTER TABLE orders ADD COLUMN coupon_code VARCHAR(64) DEFAULT NULL",
        ]:
            try:
                cur.execute(sql)
            except mysql.connector.Error:
                pass
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def seed(clear: bool = False) -> None:
    conn = db()
    try:
        cur = conn.cursor(dictionary=True)
        if clear:
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            cur.execute("TRUNCATE TABLE refunds")
            cur.execute("TRUNCATE TABLE orders")
            cur.execute("TRUNCATE TABLE users")
            cur.execute("SET FOREIGN_KEY_CHECKS=1")

        cur.execute("SELECT COUNT(*) AS c FROM products")
        if cur.fetchone()["c"] > 0:
            conn.commit()
            return

        for idx, item in enumerate(PRODUCT_SEED, start=1):
            cur.execute(
                """
                INSERT INTO products (ref, name, price_cents, rating, image, description, display_order, is_target)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    ref(16),
                    item["name"],
                    item["price_cents"],
                    item["rating"],
                    item["image"],
                    item["description"],
                    idx,
                    1 if item.get("is_target") else 0,
                ),
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def boot() -> None:
    last_error = None
    for _ in range(30):
        try:
            init_schema()
            seed(clear=False)
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"Database did not become ready: {last_error}")


boot()


def get_or_create_user() -> Dict[str, Any]:
    """Lấy user từ session, nếu chưa có thì tự tạo mới."""
    user_id = session.get("user_id")
    if user_id:
        user = fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))
        if user:
            return user

    # Tạo user mới cho session này
    username = "guest_" + ref(10)
    flag = "FLAG{B4nd1t_0f_Bu51n355_L0g1c}"
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password, wallet_cents, flag) VALUES (%s, %s, %s, %s)",
            (username, "", 10000, flag),
        )
        conn.commit()
        user_id = cur.lastrowid
    finally:
        conn.close()

    session["user_id"] = user_id
    return fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))


def current_user() -> Optional[Dict[str, Any]]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetch_one("SELECT * FROM users WHERE id=%s", (user_id,))


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        # Auto-tạo user nếu chưa có, không redirect về login
        get_or_create_user()
        return fn(*args, **kwargs)
    return wrapper


def parse_qty(value: Any, default: int = 1) -> int:
    try:
        qty = int(value)
    except (TypeError, ValueError):
        qty = default
    return max(1, min(qty, 10))


def discount_for(subtotal_cents: int, coupon_code: str | None) -> int:
    if (coupon_code or "").strip().upper() == COUPON_CODE:
        return int(round(subtotal_cents * COUPON_PERCENT / 100))
    return 0


def coupon_uses(user_id: int) -> int:
    row = fetch_one(
        "SELECT COUNT(*) AS cnt FROM orders WHERE user_id=%s AND coupon_code=%s",
        (user_id, COUPON_CODE),
    )
    return int(row["cnt"]) if row else 0


def cart_state() -> Dict[str, Any]:
    # cart_items: list of {"product_ref": str, "quantity": int}
    cart_items = session.get("cart_items", [])
    coupon_code = (session.get("cart_coupon_code") or "").strip().upper()

    items = []
    subtotal = 0
    for entry in cart_items:
        product = fetch_one("SELECT * FROM products WHERE ref=%s", (entry["product_ref"],))
        if product:
            qty = parse_qty(entry["quantity"])
            line_total = int(product["price_cents"]) * qty
            subtotal += line_total
            items.append({"product": product, "quantity": qty, "line_total": line_total})

    discount = discount_for(subtotal, coupon_code) if items else 0
    total = max(0, subtotal - discount)
    return {
        "items": items,
        "coupon_code": coupon_code,
        "subtotal_cents": subtotal,
        "discount_cents": discount,
        "total_cents": total,
        "has_coupon": bool(discount),
    }


def process_due_refunds() -> None:
    conn = db()
    try:
        cur = conn.cursor(dictionary=True)
        cur.execute(
            """
            SELECT r.*, o.user_id, o.quantity, o.amount_cents AS order_amount_cents
            FROM refunds r
            JOIN orders o ON o.id = r.order_id
            WHERE r.status='PENDING' AND r.due_at <= NOW()
            FOR UPDATE
            """
        )
        refunds = cur.fetchall()
        for r in refunds:
            cur.execute("SELECT * FROM products WHERE ref=%s", (r["requested_product_ref"],))
            product = cur.fetchone()
            if not product:
                cur.execute("UPDATE refunds SET status='REJECTED', refund_amount_cents=0 WHERE id=%s", (r["id"],))
                cur.execute("UPDATE orders SET status='PAID' WHERE id=%s", (r["order_id"],))
                continue

            refund_amount = int(product["price_cents"]) * int(r.get("quantity") or 1)
            cur.execute(
                "UPDATE users SET wallet_cents = wallet_cents + %s WHERE id=%s",
                (refund_amount, r["user_id"]),
            )
            cur.execute(
                "UPDATE refunds SET status='ACCEPTED', refund_amount_cents=%s WHERE id=%s",
                (refund_amount, r["id"]),
            )
            cur.execute("UPDATE orders SET status='REFUNDED' WHERE id=%s", (r["order_id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@app.before_request
def before_request() -> None:
    if request.endpoint not in {"static"}:
        try:
            process_due_refunds()
        except Exception:
            pass


@app.context_processor
def inject_globals():
    return {
        "user": current_user(),
        "cart_ref": None,
        "cart_count": sum(e["quantity"] for e in session.get("cart_items", [])),
        "coupon_code": COUPON_CODE,
        "coupon_percent": COUPON_PERCENT,
    }


@app.get("/")
def home():
    get_or_create_user()
    products = fetch_all("SELECT * FROM products ORDER BY display_order ASC")
    return render_template("home.html", products=products)



@app.post("/reset")
def reset_lab():
    user = current_user()
    if user:
        conn = db()
        try:
            cur = conn.cursor()
            cur.execute("SET FOREIGN_KEY_CHECKS=0")
            cur.execute("DELETE FROM refunds WHERE order_id IN (SELECT id FROM orders WHERE user_id=%s)", (user["id"],))
            cur.execute("DELETE FROM orders WHERE user_id=%s", (user["id"],))
            cur.execute("UPDATE users SET wallet_cents=10000 WHERE id=%s", (user["id"],))
            cur.execute("SET FOREIGN_KEY_CHECKS=1")
            conn.commit()
        finally:
            conn.close()
    session.pop("cart_items", None)
    session.pop("cart_coupon_code", None)
    flash("Lab reset complete.", "success")
    return redirect(url_for("home"))


@app.get("/product/<product_ref>")
def product_detail(product_ref: str):
    product = fetch_one("SELECT * FROM products WHERE ref=%s", (product_ref,))
    if not product:
        return render_template("404.html"), 404
    return render_template("product.html", product=product)


@app.post("/cart/add")
def cart_add():
    product_ref = request.form.get("product_ref", "")
    quantity = parse_qty(request.form.get("quantity", 1))
    product = fetch_one("SELECT * FROM products WHERE ref=%s", (product_ref,))
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("home"))

    cart_items = session.get("cart_items", [])
    for entry in cart_items:
        if entry["product_ref"] == product_ref:
            entry["quantity"] = parse_qty(entry["quantity"] + quantity)
            session["cart_items"] = cart_items
            flash("Product added to cart.", "success")
            return redirect(url_for("product_detail", product_ref=product_ref))

    cart_items.append({"product_ref": product_ref, "quantity": quantity})
    session["cart_items"] = cart_items
    flash("Product added to cart.", "success")
    return redirect(url_for("product_detail", product_ref=product_ref))


@app.get("/cart")
def cart():
    return render_template("cart.html", **cart_state())


@app.post("/cart/update")
def cart_update():
    action = request.form.get("action", "")
    product_ref = request.form.get("product_ref", "")
    cart_items = session.get("cart_items", [])

    if action == "remove":
        session["cart_items"] = [e for e in cart_items if e["product_ref"] != product_ref]
        if not session["cart_items"]:
            session.pop("cart_coupon_code", None)
        return redirect(url_for("cart"))

    for entry in cart_items:
        if entry["product_ref"] == product_ref:
            qty = int(entry["quantity"])
            if action == "increase":
                qty += 1
            elif action == "decrease":
                qty -= 1
            elif action == "set":
                qty = parse_qty(request.form.get("quantity", qty))
            entry["quantity"] = parse_qty(qty)
            # Nếu qty xuống 0 thì xoá
            if entry["quantity"] <= 0:
                session["cart_items"] = [e for e in cart_items if e["product_ref"] != product_ref]
                if not session["cart_items"]:
                    session.pop("cart_coupon_code", None)
                return redirect(url_for("cart"))
            break

    session["cart_items"] = cart_items
    return redirect(url_for("cart"))


@app.post("/cart/apply-coupon")
def cart_apply_coupon():
    code = (request.form.get("coupon_code") or "").strip().upper()
    if not session.get("cart_items"):
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))
    if code == COUPON_CODE:
        user = current_user()
        if user and coupon_uses(user["id"]) >= COUPON_MAX_USES:
            session.pop("cart_coupon_code", None)
            flash(f"Coupon has reached its usage limit ({COUPON_MAX_USES} uses).", "error")
        else:
            session["cart_coupon_code"] = code
            flash("Coupon applied.", "success")
    else:
        session.pop("cart_coupon_code", None)
        flash("Invalid coupon.", "error")
    return redirect(url_for("cart"))


@app.post("/checkout")
@login_required
def checkout():
    user = current_user()
    state = cart_state()
    items = state["items"]
    coupon_code = state["coupon_code"]

    if not items:
        flash("Your cart is empty.", "error")
        return redirect(url_for("cart"))

    if coupon_code == COUPON_CODE and coupon_uses(user["id"]) >= COUPON_MAX_USES:
        flash(f"Coupon has reached its usage limit ({COUPON_MAX_USES} uses).", "error")
        session.pop("cart_coupon_code", None)
        return redirect(url_for("cart"))

    # Tính tổng tiền toàn bộ giỏ (đã áp dụng coupon theo tỷ lệ)
    total_needed = state["total_cents"]
    if int(user["wallet_cents"]) < total_needed:
        flash("Insufficient wallet balance for this checkout.", "error")
        return redirect(url_for("cart"))

    conn = db()
    last_order_ref = None
    try:
        cur = conn.cursor()
        remaining_discount = state["discount_cents"]

        for i, entry in enumerate(items):
            product = entry["product"]
            quantity = entry["quantity"]
            subtotal = int(product["price_cents"]) * quantity

            # Phân bổ discount: item cuối nhận phần còn lại để tránh rounding
            if i < len(items) - 1:
                item_discount = int(round(subtotal * COUPON_PERCENT / 100)) if coupon_code == COUPON_CODE else 0
                item_discount = min(item_discount, remaining_discount)
            else:
                item_discount = remaining_discount

            remaining_discount -= item_discount
            item_total = max(0, subtotal - item_discount)
            used_coupon = coupon_code if item_discount else None

            order_ref = ref(18)
            is_target = int(product.get("is_target") or 0) == 1
            status = "PAID"
            kind = "TARGET" if is_target else "NORMAL"

            cur.execute("UPDATE users SET wallet_cents = wallet_cents - %s WHERE id=%s", (item_total, user["id"]))
            cur.execute(
                """
                INSERT INTO orders (ref, user_id, product_id, quantity, amount_cents, discount_cents, coupon_code, status, kind)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (order_ref, user["id"], product["id"], quantity, item_total, item_discount, used_coupon, status, kind),
            )
            last_order_ref = order_ref

        conn.commit()
        session.pop("cart_items", None)
        session.pop("cart_coupon_code", None)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    flash("Checkout completed.", "success")
    return redirect(url_for("account"))


@app.get("/account")
@login_required
def account():
    user = current_user()
    orders = fetch_all(
        """
        SELECT o.*, p.name AS product_name, p.ref AS product_ref, p.price_cents AS product_price_cents, p.image
        FROM orders o
        JOIN products p ON p.id = o.product_id
        WHERE o.user_id=%s
        ORDER BY CASE WHEN o.kind='TARGET' THEN 0 ELSE 1 END, o.created_at DESC
        """,
        (user["id"],),
    )
    refunds = fetch_all(
        """
        SELECT r.*, o.ref AS order_ref
        FROM refunds r
        JOIN orders o ON o.id = r.order_id
        JOIN users u ON u.id = o.user_id
        WHERE u.id=%s
        ORDER BY r.created_at DESC
        """,
        (user["id"],),
    )
    return render_template("account.html", orders=orders, refunds=refunds)


@app.get("/order/<order_ref>")
@login_required
def order_detail(order_ref: str):
    user = current_user()
    order = fetch_one(
        """
        SELECT o.*, p.name AS product_name, p.ref AS product_ref, p.price_cents AS product_price_cents,
               p.description, p.image, u.flag
        FROM orders o
        JOIN products p ON p.id = o.product_id
        JOIN users u ON u.id = o.user_id
        WHERE o.ref=%s AND o.user_id=%s
        """,
        (order_ref, user["id"]),
    )
    if not order:
        return render_template("404.html"), 404
    latest_refund = fetch_one(
        "SELECT * FROM refunds WHERE order_id=%s ORDER BY created_at DESC LIMIT 1",
        (order["id"],),
    )
    return render_template("order.html", order=order, latest_refund=latest_refund)


@app.get("/api/order/data")
@login_required
def api_order_data():
    user = current_user()
    order_ref = request.args.get("order_ref", "")
    order = fetch_one(
        """
        SELECT o.ref AS order_ref, o.status, o.kind, o.amount_cents, o.quantity,
               p.name AS product_name, p.ref AS product_ref, p.price_cents AS product_price_cents
        FROM orders o
        JOIN products p ON p.id=o.product_id
        WHERE o.ref=%s AND o.user_id=%s
        """,
        (order_ref, user["id"]),
    )
    if not order:
        return jsonify({"error": "order not found"}), 404
    return jsonify(order)


@app.post("/api/refund/request")
@login_required
def api_refund_request():
    user = current_user()
    data = request.get_json(silent=True) or {}
    product_ref = str(data.get("product_ref", ""))
    order_ref = str(data.get("order_ref", ""))
    reason = str(data.get("reason", ""))[:240]

    order = fetch_one(
        """
        SELECT o.*, p.ref AS original_product_ref
        FROM orders o
        JOIN products p ON p.id=o.product_id
        WHERE o.ref=%s AND o.user_id=%s
        """,
        (order_ref, user["id"]),
    )
    if not order:
        return jsonify({"error": "order not found"}), 404
    if order["kind"] != "NORMAL" or order["status"] != "PAID":
        return jsonify({"error": "this order is not refundable"}), 400

    # product_ref phải là sản phẩm user đã từng mua
    purchased = fetch_one(
        """
        SELECT p.ref FROM orders o
        JOIN products p ON p.id = o.product_id
        WHERE o.user_id=%s AND p.ref=%s
        LIMIT 1
        """,
        (user["id"], product_ref),
    )
    if not purchased:
        return jsonify({"error": "product reference not found in your orders"}), 400

    refund_ref = ref(18)
    due_at = datetime.utcnow() + timedelta(seconds=5)
    conn = db()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO refunds (ref, order_id, requested_product_ref, status, reason, due_at)
            VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (refund_ref, order["id"], product_ref, "PENDING", reason, due_at.strftime("%Y-%m-%d %H:%M:%S")),
        )
        cur.execute("UPDATE orders SET status='REFUND_PENDING' WHERE id=%s", (order["id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return jsonify({"ok": True, "refund_ref": refund_ref, "status": "PENDING", "message": "Wait admin accept"})


@app.get("/api/refund/status/<refund_ref>")
@login_required
def api_refund_status(refund_ref: str):
    user = current_user()
    refund = fetch_one(
        """
        SELECT r.*, o.ref AS order_ref, u.wallet_cents
        FROM refunds r
        JOIN orders o ON o.id=r.order_id
        JOIN users u ON u.id=o.user_id
        WHERE r.ref=%s AND u.id=%s
        """,
        (refund_ref, user["id"]),
    )
    if not refund:
        return jsonify({"error": "refund not found"}), 404
    return jsonify(
        {
            "refund_ref": refund["ref"],
            "order_ref": refund["order_ref"],
            "status": refund["status"],
            "refund_amount": money(refund["refund_amount_cents"] or 0),
            "wallet": money(refund["wallet_cents"]),
        }
    )


@app.post("/api/order/complete")
@login_required
def api_order_complete():
    user = current_user()
    data = request.get_json(silent=True) or {}
    order_ref = str(data.get("order_ref", ""))
    order = fetch_one(
        """
        SELECT o.*, p.name AS product_name
        FROM orders o
        JOIN products p ON p.id=o.product_id
        WHERE o.ref=%s AND o.user_id=%s
        """,
        (order_ref, user["id"]),
    )
    if not order:
        return jsonify({"error": "order not found"}), 404
    if order["kind"] != "TARGET":
        return jsonify({"error": "only the target order can be completed here"}), 400
    if order["status"] == "COMPLETED":
        return jsonify({"ok": True, "flag": user["flag"], "message": "already completed"})

    conn = db()
    try:
        cur = conn.cursor()
        cur.execute("UPDATE orders SET status='COMPLETED' WHERE id=%s", (order["id"],))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return jsonify({"ok": True, "flag": user["flag"], "message": "order completed"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=14900, debug=False)
