from flask import Flask, render_template, url_for, request, redirect, flash, make_response, Response
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from sqlalchemy import text
import re
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse
from datetime import timedelta, date, date as dt_date, datetime
from sqlalchemy import func

db = SQLAlchemy()
login_manager = LoginManager()

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)

    expenses = db.relationship('Expenses', backref='user', lazy=True)

    def __repr__(self):
        return f"<User {self.username}>"


class Expenses(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    description = db.Column(db.String(120), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    category = db.Column(db.String(50), nullable=False)
    date = db.Column(db.Date, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)


def create_app():
    app = Flask(__name__)

    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///app.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['SECRET_KEY'] = 'my-secret-key'
    app.config['REMEMBER_COOKIE_DURATION'] = timedelta(days=15)


    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "login"

    login_manager.login_message = "Please login first"
    login_manager.login_message_category = "error"

    @app.route("/health/db")
    def health_db():
        try:
            db.session.execute(text("SELECT 1"))
            return {"db": "ok"}, 200

        except Exception as e:
            return {"db": "error", "detail": str(e)}, 500

    with app.app_context():
        db.create_all()



    def is_safe_local_path(target: str) -> bool:
        if not target:
            return False
        parts = urlparse(target)
        return parts.scheme == "" and parts.netloc== "" and target.startswith("/")

    @app.route("/")
    def index():
        return render_template("index.html")

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
                return datetime.strptime(s, "%Y-%m-%d").date()
            except:
                return None

        start_date = parse_date_or_none(start_str)
        end_date = parse_date_or_none(end_str)

        q = Expenses.query.filter_by(user_id=current_user.id)

        if start_date:
            q = q.filter(Expenses.date >= start_date)
        if end_date:
            q = q.filter(Expenses.date <= end_date)
        if selected_category:
            q = q.filter(Expenses.category == selected_category)

        expenses = q.order_by(Expenses.date.desc(), Expenses.id.desc()).all()
        total = round(sum(e.amount for e in expenses), 2)

        # 🔥 Category chart
        cat_q = db.session.query(Expenses.category, func.sum(Expenses.amount)).filter_by(user_id=current_user.id)

        if start_date:
            cat_q = cat_q.filter(Expenses.date >= start_date)
        if end_date:
            cat_q = cat_q.filter(Expenses.date <= end_date)
        if selected_category:
            cat_q = cat_q.filter(Expenses.category == selected_category)

        cat_rows = cat_q.group_by(Expenses.category).all()
        cat_labels = [c for c, _ in cat_rows]
        cat_values = [round(float(s or 0), 2) for _, s in cat_rows]

        # 🔥 Day chart
        day_q = db.session.query(Expenses.date, func.sum(Expenses.amount)).filter_by(user_id=current_user.id)

        if start_date:
            day_q = day_q.filter(Expenses.date >= start_date)
        if end_date:
            day_q = day_q.filter(Expenses.date <= end_date)
        if selected_category:
            day_q = day_q.filter(Expenses.category == selected_category)

        day_rows = day_q.group_by(Expenses.date).order_by(Expenses.date).all()
        day_labels = [d.isoformat() for d, _ in day_rows]
        day_values = [round(float(s or 0), 2) for _, s in day_rows]

        return render_template(
            "expense_dashboard.html",
            expenses=expenses,
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

            if not errors:
                try:
                    pw_hash = generate_password_hash(password)
                    user = User(username=username, email=email, password_hash=pw_hash)
                    db.session.add(user)
                    db.session.commit()

                    flash("Account created Successfully!, Please login", "success")

                    return redirect(url_for('login'))
                
                except IntegrityError:
                    db.session.rollback()
                    errors.append("that username or email is already registered. ")

            # return f"Received data - {email}"

        return render_template("register.html",errors = errors)



    @app.route("/login", methods=["GET","POST"])
    def login():

        errors= []

        if request.method == "POST":
            email = (request.form.get("email") or "").strip()
            password = request.form.get("password") or ""

            if not email:
                errors.append("Email is required")

            if not password:
                errors.append("Password is required")

            if not errors:
                user = User.query.filter_by(email=email).first()

                if not user or not check_password_hash(user.password_hash, password):
                    errors.append("Invalid Email or Password.")

                else:
                    remember_flag = request.form.get("remember") == "1"
                    login_user(user, remember=remember_flag)
                    flash(f"Welcome Back {user.username}", "success")

                    # urlparse("https://example/com/page")
                    

                    next_url = request.form.get("next") or request.args.get("next") or ""
                    if is_safe_local_path(next_url):
                        return redirect(next_url)


                    return redirect(url_for("dashboard"))

        return render_template("login.html", errors=errors)


    @app.route("/logout")
    def logout():
        logout_user()
        flash("You have been logged out", "success")
        return redirect(url_for("index"))

    @app.route("/change-password", methods=["GET", "POST"])
    def change_password():
        errors = []
        if request.method =="POST":
           current_pw = request.form.get("current_password") or ""
           new_pw = request.form.get("new_password") or ""
           confirm_pw = request.form.get("confirm_password") or ""


           if not check_password_hash(current_user.password_hash, current_pw):
              errors.append("Current password is incorrect")
           
           if len(new_pw)<6:
              errors.append("New Password needs to be atleast 6 characters")

           if new_pw != confirm_pw:
              errors.append("New Password and confirmation do not match!")
           
           if not errors:
            current_user.password_hash = generate_password_hash(new_pw)
            db.session.commit()

            flash("Password has been updated!", "success")
            return redirect(url_for("dashboard"))
        

        


        return render_template("change_password.html", errors=errors)

    

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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
            d = datetime.strptime(date_str, "%Y-%m-%d").date() if date_str else date.today()

            e = Expenses(
                description=description,
                amount=amount,
                category=category,
                date=d,
                user_id=current_user.id   # 🔥 VERY IMPORTANT
            )

            db.session.add(e)
            db.session.commit()

            flash("Expense added successfully", "success")

        except Exception as e:
            flash("Error adding expense", "error")

        return redirect(url_for("dashboard"))

    @app.route("/edit/<int:expense_id>", methods=["GET", "POST"])
    @login_required
    def edit(expense_id):
        expenses = Expenses.query.get_or_404(expense_id)

        # 🔥 security check (VERY IMPORTANT)
        if expenses.user_id != current_user.id:
            flash("Unauthorized access", "error")
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            expenses.description = request.form.get("description")
            expenses.amount = float(request.form.get("amount"))
            expenses.category = request.form.get("category")
            date_str = request.form.get("date")

            if date_str:
                expenses.date = datetime.strptime(date_str, "%Y-%m-%d").date()

            db.session.commit()
            flash("Expense updated successfully", "success")
            return redirect(url_for("dashboard"))

        return render_template("edit.html", expenses=expenses, categories=['Food','transport','Health','Utilities','Rent'],
    today=dt_date.today().isoformat())

    @app.route("/export")
    @login_required
    def export_csv():
        start = request.args.get("start")
        end = request.args.get("end")
        category = request.args.get("category")

        q = Expenses.query.filter_by(user_id=current_user.id)

        if start:
            q = q.filter(Expenses.date >= start)
        if end:
            q = q.filter(Expenses.date <= end)
        if category:
            q = q.filter(Expenses.category == category)

        expenses = q.all()

        def generate():
            yield "Description,Amount,Category,Date\n"
            for e in expenses:
                yield f"{e.description},{e.amount},{e.category},{e.date}\n"

        return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=expenses.csv"},
        )

    @app.route("/delete/<int:expense_id>", methods=["POST"])
    @login_required
    def delete(expense_id):
        expenses = Expenses.query.get_or_404(expense_id)

        # 🔥 VERY IMPORTANT: user isolation
        if expenses.user_id != current_user.id:
            flash("Unauthorized access", "error")
            return redirect(url_for("dashboard"))

        try:
            db.session.delete(expenses)
            db.session.commit()
            flash("Expense deleted successfully", "success")

        except Exception as e:
            db.session.rollback()
            flash("Error deleting expense", "error")

        return redirect(url_for("dashboard"))
        
    return app



if __name__ == "__main__":
    app = create_app()
    app.run(debug=True, port=5555)