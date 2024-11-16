import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "securecookie"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.context_processor
def inject_balance():
    if session.get("user_id"):
        user_id = session["user_id"]
        user_data = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
        if user_data:
            balance = user_data[0]["cash"]
            return dict(balance=balance)
    return dict(balance=None)


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = session["user_id"]

    stocks = db.execute(
        "SELECT symbol, SUM(shares) AS total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0",
        user_id
    )

    portfolio = []
    total_stock_value = 0

    for stock in stocks:
        symbol = stock["symbol"]
        shares = stock["total_shares"]

        stock_data = lookup(symbol)
        if stock_data:
            current_price = stock_data["price"]
            total_value = shares * current_price
            total_stock_value += total_value
            total_value = usd(total_value)
            portfolio.append({
                "symbol": symbol,
                "name": stock_data["name"],
                "shares": shares,
                "price": current_price,
                "total": total_value
            })

    user_data = db.execute("SELECT cash FROM users WHERE id = ?", user_id)
    cash = user_data[0]["cash"] if user_data else 0

    grand_total = total_stock_value + cash
    return render_template("index.html", portfolio=portfolio, cash=usd(cash), grand_total=usd(grand_total))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Ensure symbol and shares were provided
        if not symbol:
            flash("Must provide symbol", "warning")
            return render_template("buy.html"),400
        if not shares or not shares.isdigit() or int(shares) <= 0:
            flash("must provide a valid number of shares", "warning")
            return render_template("buy.html"),400

        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid symbol", "warning")
            return render_template("buy.html"),400

        shares = int(shares)
        user_id = session["user_id"]
        total_cost = stock_data["price"] * shares

        # Check if user has enough cash
        user_cash = db.execute("SELECT cash FROM users WHERE id = ?", user_id)[0]["cash"]
        if user_cash < total_cost:
            flash("Not Enough cash", "danger")
            return render_template("buy.html"),400

        # Update cash and insert transaction
        db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", total_cost, user_id)
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, status) VALUES (?, ?, ?, ?, ?)",
                   user_id, symbol, shares, stock_data["price"], "BUY")

        return redirect("/")

    al_symbol = request.args.get("al_symbol")
    return render_template("buy.html", al_symbol=al_symbol)


@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    """Show history of transactions"""
    if request.method == "POST":
        id = request.form.get("clear")
        if id == "all":
            db.execute("DELETE FROM transactions")
            return redirect("/history")

    user_id = session["user_id"]

    transactions = db.execute(
        "SELECT symbol, shares, price, transacted, status FROM transactions WHERE user_id = ?", user_id)

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute(
            "SELECT * FROM users WHERE username = ?", request.form.get("username")
        )

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(
            rows[0]["hash"], request.form.get("password")
        ):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":
        symbol = request.form.get("symbol")
        if not symbol:
            flash("provide a valid symbol", "warning")
            return render_template("quote.html"),400

        stock_data = lookup(symbol)
        if stock_data:
            stock_data["price"] = usd(stock_data["price"])
            return render_template("quoted.html", symbol=symbol, name=stock_data["name"], price=stock_data["price"])
        else:
            flash("No symbol", "danger")
            return render_template("quote.html"),400

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirm_password = request.form.get("confirmation")

        if not username:
            flash("Need to provide a username", "warning")
            return render_template("register.html"),400
        if not password:
            flash("Need to set a password", "warning")
            return render_template("register.html"),400

        if not confirm_password:
            flash("comfirm password", "warning")
            return render_template("register.html"),400

        # Check if username already exists
        existing_user = db.execute("SELECT * FROM users WHERE username = ?", username)
        if existing_user:
            return apology("username already exists", 400)
        # Check if passwords match
        if password != confirm_password:
            return apology("passwords do not match", 400)

        # Hash the password
        hashed_password = generate_password_hash(password)

        try:
            # Insert new user into the database
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, hashed_password)
            return redirect("/login")

        except Exception as e:
            # Log the error if necessary and return a generic error message
            print("Error:", e)
            return apology("registration error", 500)

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    # Fetch user's stocks for the dropdown menu
    user_stocks = db.execute(
        "SELECT symbol, SUM(shares) AS total_shares FROM transactions WHERE user_id = ? GROUP BY symbol HAVING total_shares > 0", user_id)

    if request.method == "POST":
        symbol = request.form.get("symbol")
        shares = request.form.get("shares")

        # Ensure symbol and shares were provided
        if not symbol:
            flash("Need to provide a symbol", "warning")
            return render_template("sell.html", portfolio=user_stocks),400

        if not shares or not shares.isdigit() or int(shares) <= 0:
            flash("Must provide a valid number of shares", "warning")
            return render_template("sell.html", portfolio=user_stocks),400

        shares = int(shares)
        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid symbol", "warning")
            return render_template("sell.html", portfolio=user_stocks),400

        # Check if user has enough shares to sell
        stock_owned = db.execute(
            "SELECT SUM(shares) AS total_shares FROM transactions WHERE user_id = ? AND symbol = ?", user_id, symbol)[0]["total_shares"]
        if stock_owned < shares:
            flash("Too many shares", "danger")
            return render_template("sell.html", portfolio=user_stocks),400

        # Calculate sale amount, update cash, and insert transaction
        sale_amount = stock_data["price"] * shares
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sale_amount, user_id)
        db.execute("INSERT INTO transactions (user_id, symbol, shares, price, status) VALUES (?, ?, ?, ?, ?)",
                   user_id, symbol, -shares, stock_data["price"], "SELL")

        return redirect("/")

    return render_template("sell.html", portfolio=user_stocks)
