from flask import Flask, render_template, url_for, request, redirect, flash, Response
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
import re
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
from datetime import timedelta, date, datetime
import os
# 🔥 MongoDB
from pymongo import MongoClient
from bson.objectid import ObjectId

client = MongoClient(os.environ.get("MONGO_URI"))
mongo_db = client["hisaabkitaab"]

users_collection = mongo_db["users"]
expenses_collection = mongo_db["expenses"]

login_manager = LoginManager()

# 👤 USER CLASS
class User(UserMixin):
    def __init__(self, user):
        self.id = str(user["_id"])
        self.username = user["username"]
        self.email = user["email"]
        self.password_hash = user["password_hash"]

def create_app():
    app = Flask(__name__)

    app.config['SECRET_KEY'] = 'my-secret-key'
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=15)

    login_manager.init_app(app)
    login_manager.login_view = "login"
    login_manager.login_message = "Please login first"
    login_manager.login_message_category = "error"

    # 🔄 Load user
    @login_manager.user_loader
    def load_user(user_id):
        user = users_collection.find_one({"_id": ObjectId(user_id)})
        return User(user) if user else None

    # 🔒 Safe redirect (same as original)
    def is_safe_local_path(target: str) -> bool:
        if not target:
            return False
        parts = urlparse(target)
        return parts.scheme == "" and parts.netloc == "" and target.startswith("/")

    # 🏠 Home
    @app.route("/")
    def index():
        return render_template("index.html")

    # 📊 Dashboard (same logic as original)
    @app.route("/dashboard")
    @login_required
    def dashboard():

        start_str = (request.args.get("start") or "").strip()
        end_str = (request.args.get("end") or "").strip()
        selected_category = (request.args.get("category") or "").strip()

        def parse_date_or_none(s):
            if not s:
                return None
            try:
                return datetime.strptime(s, "%Y-%m-%d")
            except:
                return None

        start_date = parse_date_or_none(start_str)
        end_date = parse_date_or_none(end_str)

        # 🔥 Date validation (NEW)
        if start_date is not None and end_date is not None:
            if start_date > end_date:
                flash("Start date cannot be after end date", "error")
                return redirect(url_for("dashboard"))

        query = {"user_id": current_user.id}

        if start_date:
            query["date"] = {"$gte": start_date}
        if end_date:
            query.setdefault("date", {})
            query["date"]["$lte"] = end_date
        if selected_category:
            query["category"] = selected_category

        data = list(expenses_collection.find(query).sort("date", -1))

        # 🔥 make Mongo behave like SQL (IMPORTANT)
        for e in data:
            e["id"] = str(e["_id"])

        total = round(sum(e["amount"] for e in data), 2)

        # 📊 Category chart (same logic)
        cat_data = list(expenses_collection.aggregate([
            {"$match": query},
            {"$group": {"_id": "$category", "total": {"$sum": "$amount"}}}
        ]))

        cat_labels = [c["_id"] for c in cat_data]
        cat_values = [round(c["total"], 2) for c in cat_data]

        # 📊 Day chart (same logic)
        day_data = list(expenses_collection.aggregate([
            {"$match": query},
            {"$group": {
                "_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$date"}},
                "total": {"$sum": "$amount"}
            }},
            {"$sort": {"_id": 1}}
        ]))

        day_labels = [d["_id"] for d in day_data]
        day_values = [round(d["total"], 2) for d in day_data]

        return render_template(
            "expense_dashboard.html",
            expenses=data,
            total=total,
            categories=['Food','transport','Health','Utilities','Rent'],
            today=date.today().isoformat(),
            start_str=start_str,
            end_str=end_str,
            selected_category=selected_category,
            cat_labels=cat_labels,
            cat_values=cat_values,
            day_labels=day_labels,
            day_values=day_values
        )

    # 📝 Register (same logic)
    @app.route("/register", methods=["GET", "POST"])
    def register():
        errors = []

        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""
            confirm = request.form.get("confirm_password") or ""

            if not (3 <= len(username) <= 80):
                errors.append("Username must be between 3 and 80 characters.")

            if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
                errors.append("Please Enter a valid Email Address!")

            if len(password) < 6:
                errors.append("Password needs to be atleast 6 characters!")

            if password != confirm:
                errors.append("Passwords don't match!")

            if users_collection.find_one({"email": email}):
                errors.append("that username or email is already registered.")

            if not errors:
                pw_hash = generate_password_hash(password)

                users_collection.insert_one({
                    "username": username,
                    "email": email,
                    "password_hash": pw_hash
                })

                flash("Account created Successfully!, Please login", "success")
                return redirect(url_for('login'))

        return render_template("register.html", errors=errors)

    # 🔐 Login (same logic)
    @app.route("/login", methods=["GET","POST"])
    def login():
        errors = []

        if request.method == "POST":
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""

            if not email:
                errors.append("Email is required")

            if not password:
                errors.append("Password is required")

            if not errors:
                user = users_collection.find_one({"email": email})

                if not user or not check_password_hash(user["password_hash"], password):
                    errors.append("Invalid Email or Password.")
                else:
                    remember_flag = request.form.get("remember") == "1"
                    login_user(User(user), remember=remember_flag)
                    flash(f"Welcome Back {user['username']}", "success")

                    next_url = request.form.get("next") or request.args.get("next") or ""
                    if is_safe_local_path(next_url):
                        return redirect(next_url)

                    return redirect(url_for("dashboard"))

        return render_template("login.html", errors=errors)

    # 🚪 Logout
    @app.route("/logout")
    def logout():
        logout_user()
        flash("You have been logged out", "success")
        return redirect(url_for("index"))

    # ➕ Add
    @app.route("/add", methods=["POST"])
    @login_required
    def add():
        description = request.form.get("description")
        amount = request.form.get("amount")
        category = request.form.get("category")
        date_str = request.form.get("date")

        if not description or not amount:
            flash("Please fill all required fields", "error")
            return redirect(url_for("dashboard"))

        try:
            amount = float(amount)
            d = datetime.strptime(date_str, "%Y-%m-%d") if date_str else datetime.utcnow()

            expenses_collection.insert_one({
                "description": description,
                "amount": amount,
                "category": category,
                "date": d,
                "user_id": current_user.id
            })

            flash("Expense added successfully", "success")

        except:
            flash("Error adding expense", "error")

        return redirect(url_for("dashboard"))

    # ✏️ Edit (id used everywhere)
    @app.route("/edit/<id>", methods=["GET", "POST"])
    @login_required
    def edit(id):

        exp = expenses_collection.find_one({"_id": ObjectId(id)})

        if exp["user_id"] != current_user.id:
            flash("Unauthorized access", "error")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            exp_update = {
                "description": request.form.get("description"),
                "amount": float(request.form.get("amount")),
                "category": request.form.get("category")
            }

            date_str = request.form.get("date")
            if date_str:
                exp_update["date"] = datetime.strptime(date_str, "%Y-%m-%d")

            expenses_collection.update_one(
                {"_id": ObjectId(id)},
                {"$set": exp_update}
            )

            flash("Expense updated successfully", "success")
            return redirect(url_for("dashboard"))

        exp["id"] = str(exp["_id"])

        return render_template(
            "edit.html",
            expenses=exp,
            categories=['Food','transport','Health','Utilities','Rent'],
            today=date.today().isoformat()
        )

    @app.route("/export")
    @login_required
    def export_csv():
        start = request.args.get("start")
        end = request.args.get("end")
        category = request.args.get("category")

        query = {"user_id": current_user.id}

        if start:
            query["date"] = {"$gte": datetime.strptime(start, "%Y-%m-%d")}
        if end:
            query.setdefault("date", {})
            query["date"]["$lte"] = datetime.strptime(end, "%Y-%m-%d")
        if category:
            query["category"] = category

        data = list(expenses_collection.find(query))

        def generate():
            yield "Description,Amount,Category,Date\n"
            for e in data:
                yield f"{e['description']},{e['amount']},{e['category']},{e['date']}\n"

        return Response(
            generate(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=expenses.csv"},
        )  

    # ❌ Delete
    @app.route("/delete/<id>", methods=["POST"])
    @login_required
    def delete(id):

        exp = expenses_collection.find_one({"_id": ObjectId(id)})

        if exp["user_id"] != current_user.id:
            flash("Unauthorized access", "error")
            return redirect(url_for("dashboard"))

        expenses_collection.delete_one({"_id": ObjectId(id)})

        flash("Expense deleted successfully", "success")
        return redirect(url_for("dashboard"))

    # 🔑 Change Password
    @app.route("/change-password", methods=["GET", "POST"])
    @login_required
    def change_password():
        errors = []

        if request.method =="POST":
            current_pw = request.form.get("current_password") or ""
            new_pw = request.form.get("new_password") or ""
            confirm_pw = request.form.get("confirm_password") or ""

            user = users_collection.find_one({"_id": ObjectId(current_user.id)})

            if not check_password_hash(user["password_hash"], current_pw):
                errors.append("Current password is incorrect")

            if len(new_pw) < 6:
                errors.append("New Password needs to be atleast 6 characters")

            if new_pw != confirm_pw:
                errors.append("New Password and confirmation do not match!")

            if not errors:
                users_collection.update_one(
                    {"_id": ObjectId(current_user.id)},
                    {"$set": {"password_hash": generate_password_hash(new_pw)}}
                )

                flash("Password has been updated!", "success")
                return redirect(url_for("dashboard"))

        return render_template("change_password.html", errors=errors)

    return app


app = create_app()

if __name__ == "__main__":
    app.run()
