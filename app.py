import os
import json

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import timedelta,datetime
from redis import Redis
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)
# Database configuration
app.secret_key ='qwertyuiopasdfghjklzxcvbnm'
# Custom filter
app.jinja_env.filters["usd"] = usd
# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_TYPE"] = 'redis'
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_USE_SIGNER"] = True
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(minutes=30)
app.config["SESSION_REDIS"] = Redis(
  host='redis-18595.c259.us-central1-2.gce.redns.redis-cloud.com',
  port=18595,
  password='XkRVAKRr3JXIoIeMDQ08hZ76kKyXMEJg',db=0)

# Redis client for user balances
redis_client = Redis(
  host='redis-18595.c259.us-central1-2.gce.redns.redis-cloud.com',
  port=18595,
  password='XkRVAKRr3JXIoIeMDQ08hZ76kKyXMEJg',db=0)

# Initialize session
Session(app)

db1=SQL("sqlite:///finance.db")

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
        user_data = redis_client.hget("cash", user_id)
        if user_data:
            return dict(balance=float(user_data))
    return dict(balance=None)

@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""
    user_id = str(session["user_id"])

    # Key for storing stocks in Redis
    user_stocks_key = f"user:{user_id}:transactions"

    # Initialize stocks as an empty list
    stocks = []

    # Check if stocks data exists in Redis
    if redis_client.exists(user_stocks_key):
        # Retrieve stocks from Redis
        stocks_data = redis_client.lrange(user_stocks_key, 0, -1)
        stocks = [
            json.loads(stock.decode("utf-8")) for stock in stocks_data
        ]

        # Set an expiry time for cached data (optional, e.g., 10 minutes)
        redis_client.expire(user_stocks_key, 600)

    portfolio = []
    total_stock_value = 0

    for stock in stocks:
        symbol = stock["symbol"]
        shares = stock["shares"]

        stock_data = lookup(symbol)
        if stock_data:
            current_price = stock_data["price"]
            total_value = shares * current_price
            total_stock_value += total_value
            portfolio.append({
                "symbol": symbol,
                "name": stock_data["name"],
                "shares": shares,
                "price": current_price,
                "total": usd(total_value)
            })

    # Get user's cash balance from Redis
    cash = redis_client.hget("cash",user_id)
    if cash is None:
        flash("Error getting user's balance", "danger")
        return render_template("index.html"), 400
    else:
        cash = float(cash)

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
            return render_template("buy.html"), 400
        if not shares or not shares.isdigit() or int(shares) <= 0:
            flash("Must provide a valid number of shares", "warning")
            return render_template("buy.html"), 400

        stock_data = lookup(symbol)
        if not stock_data:
            flash("Invalid symbol", "warning")
            return render_template("buy.html"), 400

        shares = int(shares)
        user_id = str(session["user_id"])
        total_cost = stock_data["price"] * shares

        # Retrieve user's cash balance from Redis
        user_cash = redis_client.hget("cash",user_id)
        user_cash = float(user_cash)

        if user_cash is None:
            flash("Error fetching user's cash balance", "danger")
            return render_template("buy.html"), 500

        # Check if user has enough cash
        if user_cash < total_cost:
            flash("Not enough cash", "danger")
            return render_template("buy.html"), 400

        # Deduct total cost from user's cash balance
        redis_client.hset("cash",user_id, user_cash - total_cost)

        # Store transaction in Redis (using a list to maintain order)
        transactions_key = f"user:{user_id}:transactions"
        transaction = {
            "symbol": symbol,
            "shares": shares,
            "price": stock_data["price"],
            "status": "BUY",
            "timestamp": datetime.now().isoformat()
        }
        redis_client.rpush(transactions_key, json.dumps(transaction))

        flash("Transaction successful!", "success")
        return redirect("/")

    # Handle GET request
    al_symbol = request.args.get("al_symbol")
    return render_template("buy.html", al_symbol=al_symbol)

@app.route("/history", methods=["GET", "POST"])
@login_required
def history():
    """Show history of transactions"""
    if request.method == "POST":
        id = request.form.get("clear")
        if id == "all":
            db1.execute("DELETE FROM transactions")
            return redirect("/history")

    user_id = session["user_id"]

    transactions_key = f"user:{user_id}:transactions"
    user_transactions = redis_client.lrange(transactions_key, 0, -1)
    transactions = [
        json.loads(transaction.decode("utf-8")) for transaction in user_transactions
    ]

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""
    session.clear()  # Clear existing sessions

    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        # Retrieve hashed password from Redis
        stored_hash = redis_client.hget("users", username)

        if not stored_hash:
            flash("Invalid username or password", "danger")
            return render_template("login.html"), 403

        # Decode if necessary
        if isinstance(stored_hash, bytes):
            stored_hash = stored_hash.decode("utf-8")

        # Check the password
        if not check_password_hash(stored_hash, password):
            flash("Invalid username or password", "danger")
            return render_template("login.html"), 403

        # Set session data
        session["user_id"] = username
        flash("Logged in successfully!", "success")
        return redirect("/")

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
            return render_template("register.html"), 400
        if not password:
            flash("Need to set a password", "warning")
            return render_template("register.html"), 400
        if not confirm_password:
            flash("Need to confirm password", "warning")
            return render_template("register.html"), 400

        # Check if username already exists in Redis
        if redis_client.hexists("users", username):
            flash("Username already exists", "warning")
            return render_template("register.html"), 400

        # Check if passwords match
        if password != confirm_password:
            flash("Passwords do not match", "warning")
            return render_template("register.html"), 400

        # Hash the password
        hashed_password = generate_password_hash(password)

        try:
            # Store user details in Redis
            redis_client.hset("users", username, hashed_password)
            redis_client.hset("cash", username, 10000)  # Initialize account balance as 0
            flash("Registered successfully!", "success")
            return redirect("/login")

        except Exception as e:
            # Log the error if necessary and return a generic error message
            print("Error:", e)
            flash("Registration error", "danger")
            return render_template("register.html"), 500

    return render_template("register.html")

@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    user_id = session["user_id"]

    # Fetch user's stocks for the dropdown menu
    user_stocks_key = f"user:{user_id}:transactions"
    user_stocks_data = redis_client.lrange(user_stocks_key,0,-1)
    user_stocks = [
        json.loads(stock.decode("utf-8")) for stock in user_stocks_data
    ]


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

        # Fetch all transactions
        user_stocks_key = f"user:{user_id}:transactions"
        user_transactions = redis_client.lrange(user_stocks_key, 0, -1)  # Retrieve all transactions (list)

        # Calculate total shares for the symbol
        stock_owned = sum(
            int(json.loads(transaction.decode("utf-8"))["shares"])
            for transaction in user_transactions
            if json.loads(transaction.decode("utf-8"))["symbol"] == symbol
        )

        # Check if the user has enough shares to sell
        if stock_owned < shares:
            flash("Too many shares", "danger")
            return render_template("sell.html", portfolio=user_stocks), 400

        # Calculate sale amount
        sale_amount = stock_data["price"] * shares

        # Update user's cash in Redis
        user_cash = float(redis_client.hget("cash",user_id) or 0)
        redis_client.hset("cash",user_id,user_cash + sale_amount)

        # Log the transaction in Redis (using a list for ordered history)
        transactions_key = f"user:{user_id}:transactions"
        transaction = {
            "symbol": symbol,
            "shares": -shares,
            "price": stock_data["price"],
            "status": "SELL",
            "timestamp": datetime.now().isoformat()
        }
        redis_client.rpush(transactions_key, json.dumps(transaction))

        flash(f"Sold {shares} shares of {symbol}!", "success")
        return redirect("/")

    return render_template("sell.html", portfolio=user_stocks)

if __name__=='__main__':
    app.run(debug=True)
