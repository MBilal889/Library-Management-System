from flask import Flask, render_template, request, redirect, url_for, session, flash, send_from_directory, abort
import os
import sqlite3
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta

# ── App Setup ─────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET", "supersecretkey")

# ── Upload Config ─────────────────────────────────────────────────────────────
UPLOAD_FOLDER = 'uploaded_books'
ALLOWED_EXTENSIONS = {'pdf'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ── Constants ─────────────────────────────────────────────────────────────────
FINE_RATE_PER_DAY    = 10.00   # PKR per day
LOAN_PERIOD_DAYS     = 14
DEFAULT_USER_PASSWORD = "password123"

# ── DB Helper ─────────────────────────────────────────────────────────────────
DB_FILE = "lms.db"

def get_db():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn
### Migration helper to add file_path column if missing (for PDF uploads)
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def run_migrations():
    """Safely apply schema migrations to existing databases on startup."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE books ADD COLUMN file_path TEXT")
        conn.commit()
        print("Migration applied: books.file_path column added.")
    except sqlite3.OperationalError:
        pass  # Column already exists — no action needed
    conn.close()

# Apply migrations automatically on every startup
run_migrations()

# ── Query Helpers ─────────────────────────────────────────────────────────────

def fetch_books(term=None):
    conn = get_db()
    if not term:
        books = conn.execute("SELECT * FROM books ORDER BY title").fetchall()
        conn.close()
        return books
    search_terms = [t.strip() for t in term.split(',') if t.strip()]
    if not search_terms:
        conn.close()
        return []
    clauses = []
    params  = []
    for t in search_terms:
        clauses.append("(title LIKE ? OR author LIKE ? OR genre LIKE ? OR isbn LIKE ?)")
        params.extend([f"%{t}%", f"%{t}%", f"%{t}%", f"%{t}%"])
    query = "SELECT * FROM books WHERE " + " OR ".join(clauses) + " ORDER BY title"
    books = conn.execute(query, params).fetchall()
    conn.close()
    return books


def fetch_outstanding_transactions():
    conn = get_db()
    rows = conn.execute("""
        SELECT
            t.transaction_id,
            u.username,
            u.full_name,
            b.title,
            t.issue_date,
            t.due_date
        FROM transactions t
        JOIN users u ON t.user_id = u.user_id
        JOIN books b ON t.book_id = b.book_id
        WHERE t.status = 'issued'
        ORDER BY t.due_date ASC
    """).fetchall()
    conn.close()
    return rows


def fetch_all_fines():
    conn = get_db()
    rows = conn.execute("""
        SELECT
            f.fine_id,
            f.amount,
            f.paid,
            f.paid_on,
            u.full_name,
            u.username,
            b.title,
            t.return_date,
            t.transaction_id
        FROM fines f
        JOIN transactions t ON f.transaction_id = t.transaction_id
        JOIN users u ON t.user_id = u.user_id
        JOIN books b ON t.book_id = b.book_id
        ORDER BY f.paid ASC, t.return_date DESC
    """).fetchall()
    conn.close()
    return rows


def fetch_admin_metrics():
    conn = get_db()
    try:
        total_books    = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
        total_users    = conn.execute("SELECT COUNT(*) FROM users WHERE role='user'").fetchone()[0]
        total_issued   = conn.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]
        total_returned = conn.execute("SELECT COUNT(*) FROM transactions WHERE status='returned'").fetchone()[0]
        books_out      = conn.execute("SELECT COUNT(*) FROM transactions WHERE status='issued'").fetchone()[0]
        unpaid_fines   = conn.execute("SELECT COUNT(*) FROM fines WHERE paid=0").fetchone()[0]
    except Exception as e:
        print(f"Metrics error: {e}")
        return {'total_books': 0, 'total_users': 0, 'total_issued': 0,
                'total_returned': 0, 'books_out': 0, 'unpaid_fines': 0}
    finally:
        conn.close()
    return {'total_books': total_books, 'total_users': total_users,
            'total_issued': total_issued, 'total_returned': total_returned,
            'books_out': books_out, 'unpaid_fines': unpaid_fines}


def fetch_all_users():
    conn = get_db()
    users = conn.execute(
        "SELECT user_id, username, full_name, email, role FROM users WHERE role='user' ORDER BY full_name"
    ).fetchall()
    conn.close()
    return users


def fetch_user_metrics(username):
    conn = get_db()
    user = conn.execute("SELECT user_id FROM users WHERE username=?", (username,)).fetchone()
    if not user:
        conn.close()
        return None
    uid = user['user_id']
    issued_total = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=?", (uid,)
    ).fetchone()[0]
    current_out = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE user_id=? AND status='issued'", (uid,)
    ).fetchone()[0]
    pending_fines = conn.execute("""
        SELECT COALESCE(SUM(f.amount), 0)
        FROM fines f
        JOIN transactions t ON f.transaction_id = t.transaction_id
        WHERE t.user_id = ? AND f.paid = 0
    """, (uid,)).fetchone()[0]
    conn.close()
    return {'issued_total': issued_total, 'current_out': current_out,
            'pending_fines': round(pending_fines, 2)}


# ── INDEX — Login / Signup ────────────────────────────────────────────────────
@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        action      = request.form.get("action")
        username    = request.form.get("username", "").strip()
        password    = request.form.get("password", "").strip()
        role_choice = request.form.get("role")
        conn        = get_db()

        if action == "login":
            user = conn.execute(
                "SELECT * FROM users WHERE username=? AND role=?", (username, role_choice)
            ).fetchone()
            conn.close()
            if user and check_password_hash(user["password_hash"], password):
                session["username"] = username
                session["role"]     = role_choice
                session["user_id"]  = user["user_id"]
                flash(f"Welcome back, {user['full_name']}!", "success")
                return redirect(url_for("admin_dashboard") if role_choice == "admin" else url_for("user_dashboard"))
            flash("Invalid username, password, or role.", "danger")

        elif action == "signup":
            full_name = request.form.get("full_name", "").strip()
            email     = request.form.get("email", "").strip()
            if not all([username, password, full_name, email, role_choice]):
                flash("All fields are required for signup.", "warning")
            else:
                existing = conn.execute(
                    "SELECT 1 FROM users WHERE username=? OR email=?", (username, email)
                ).fetchone()
                if existing:
                    flash("Username or email already in use.", "warning")
                else:
                    try:
                        conn.execute(
                            "INSERT INTO users (username, password_hash, role, full_name, email) VALUES (?, ?, ?, ?, ?)",
                            (username, generate_password_hash(password), role_choice, full_name, email)
                        )
                        conn.commit()
                        flash("Account created! Please log in.", "success")
                    except Exception as e:
                        flash(f"Signup error: {e}", "danger")
                    finally:
                        conn.close()
                    return render_template("index.html")
            conn.close()

    return render_template("index.html")


# ── ADMIN DASHBOARD ───────────────────────────────────────────────────────────
@app.route("/admin")
def admin_dashboard():
    if session.get("role") != "admin":
        return redirect(url_for("index"))

    current_section     = request.args.get('section', 'view')
    current_sub_section = request.args.get('sub', 'manage-catalog') if current_section == 'edit' else request.args.get('sub', 'stats')

    return render_template("admin.html",
        books=fetch_books(),
        outstanding_transactions=fetch_outstanding_transactions(),
        admin_metrics=fetch_admin_metrics(),
        all_users=fetch_all_users(),
        all_fines=fetch_all_fines(),
        current_section=current_section,
        current_sub_section=current_sub_section,
        now_date=datetime.now().strftime('%Y-%m-%d'),
        DEFAULT_USER_PASSWORD=DEFAULT_USER_PASSWORD)


# ── ADMIN: Manage Users ───────────────────────────────────────────────────────
@app.route("/manage_user/<int:user_id>/<string:action>")
def manage_user_route(user_id, action):
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    try:
        if action == 'delete':
            # Block delete if user has active loans
            active = conn.execute(
                "SELECT COUNT(*) FROM transactions WHERE user_id=? AND status='issued'", (user_id,)
            ).fetchone()[0]
            if active > 0:
                flash("Cannot delete user with active loans.", "danger")
            else:
                conn.execute("DELETE FROM users WHERE user_id=?", (user_id,))
                conn.commit()
                flash("User deleted.", "success")
        elif action == 'reset_password':
            conn.execute(
                "UPDATE users SET password_hash=? WHERE user_id=?",
                (generate_password_hash(DEFAULT_USER_PASSWORD), user_id)
            )
            conn.commit()
            flash(f"Password reset to '{DEFAULT_USER_PASSWORD}'.", "warning")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='edit', sub='manage-users'))


# ── ADMIN: Add Book ───────────────────────────────────────────────────────────
@app.route("/add_book", methods=["POST"])
def add_book_route():
    if session.get("role") != "admin":
        return redirect(url_for("index"))

    title        = request.form.get("title", "").strip()
    author       = request.form.get("author", "").strip()
    isbn         = request.form.get("isbn", "").strip()
    genre        = request.form.get("genre", "").strip()
    total_copies = request.form.get("total_copies", "").strip()

    if not all([title, author, isbn, total_copies]):
        flash("Title, Author, ISBN and Total Copies are required.", "danger")
        return redirect(url_for("admin_dashboard", section='edit', sub='add-form'))

    try:
        total_copies = int(total_copies)
        if total_copies < 1:
            raise ValueError
    except ValueError:
        flash("Total Copies must be a valid number (1 or more).", "danger")
        return redirect(url_for("admin_dashboard", section='edit', sub='add-form'))

    conn = get_db()
    try:
        file_path = None
        pdf_file = request.files.get('pdf_file')
        if pdf_file and pdf_file.filename and allowed_file(pdf_file.filename):
            filename = secure_filename(f"{isbn}_{pdf_file.filename}")
            save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            pdf_file.save(save_path)
            file_path = filename

        conn.execute(
            "INSERT INTO books (isbn, title, author, genre, total_copies, available_copies, file_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (isbn, title, author, genre or None, total_copies, total_copies, file_path)
        )
        conn.commit()
        flash(f"Book '{title}' added successfully.", "success")
    except sqlite3.IntegrityError:
        flash(f"A book with ISBN '{isbn}' already exists.", "warning")
    except Exception as e:
        flash(f"Database error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))


# ── ADMIN: Edit Book ──────────────────────────────────────────────────────────
@app.route("/edit_book/<int:book_id>", methods=["GET", "POST"])
def edit_book_route(book_id):
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    if not book:
        conn.close()
        flash("Book not found.", "danger")
        return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))

    if request.method == "POST":
        try:
            new_total = int(request.form.get("total_copies"))
            books_out = book['total_copies'] - book['available_copies']
            if new_total < books_out:
                raise ValueError("Cannot reduce copies below number currently on loan.")
            new_available = new_total - books_out

            # Handle optional PDF upload
            file_path = book['file_path']  # keep existing
            pdf_file = request.files.get('pdf_file')
            if pdf_file and pdf_file.filename and allowed_file(pdf_file.filename):
                filename = secure_filename(f"{request.form.get('isbn')}_{pdf_file.filename}")
                save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                pdf_file.save(save_path)
                # Remove old file if different
                if file_path and file_path != filename:
                    old_path = os.path.join(app.config['UPLOAD_FOLDER'], file_path)
                    if os.path.exists(old_path):
                        os.remove(old_path)
                file_path = filename

            conn.execute("""
                UPDATE books
                SET title=?, author=?, isbn=?, genre=?, total_copies=?, available_copies=?, file_path=?
                WHERE book_id=?
            """, (
                request.form.get("title"),
                request.form.get("author"),
                request.form.get("isbn"),
                request.form.get("genre"),
                new_total, new_available, file_path, book_id
            ))
            conn.commit()
            flash("Book updated successfully.", "success")
        except ValueError as e:
            flash(str(e), "danger")
        except Exception as e:
            flash(f"Update error: {e}", "danger")
        finally:
            conn.close()
        return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))

    conn.close()
    return render_template("edit_book.html", book=book)


# ── ADMIN: Delete Book ────────────────────────────────────────────────────────
@app.route("/delete_book/<int:book_id>")
def delete_book_route(book_id):
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    if not book:
        conn.close()
        flash("Book not found.", "danger")
        return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))
    active_loans = conn.execute(
        "SELECT COUNT(*) FROM transactions WHERE book_id=? AND status='issued'", (book_id,)
    ).fetchone()[0]
    if active_loans > 0:
        conn.close()
        flash(f"Cannot delete '{book['title']}' — {active_loans} copy(s) currently on loan.", "danger")
        return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))
    try:
        conn.execute("DELETE FROM books WHERE book_id=?", (book_id,))
        conn.commit()
        flash(f"'{book['title']}' deleted.", "success")
    except Exception as e:
        flash(f"Delete error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='edit', sub='manage-catalog'))


# ── ADMIN: Issue Book ─────────────────────────────────────────────────────────
@app.route("/issue_book", methods=["POST"])
def issue_book_route():
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    user_id = request.form.get("user_id")
    book_id = request.form.get("book_id")
    conn    = get_db()

    book = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    user = conn.execute("SELECT * FROM users WHERE user_id=? AND role='user'", (user_id,)).fetchone()

    if not book or not user:
        conn.close()
        flash("Invalid User ID or Book ID.", "danger")
        return redirect(url_for("admin_dashboard", section='circulation'))
    if book['available_copies'] <= 0:
        conn.close()
        flash(f"'{book['title']}' is currently out of stock.", "warning")
        return redirect(url_for("admin_dashboard", section='circulation'))

    # Prevent duplicate active loan for same user+book
    duplicate = conn.execute(
        "SELECT 1 FROM transactions WHERE user_id=? AND book_id=? AND status='issued'",
        (user_id, book_id)
    ).fetchone()
    if duplicate:
        conn.close()
        flash("This user already has an active loan for this book.", "warning")
        return redirect(url_for("admin_dashboard", section='circulation'))

    try:
        issue_date = datetime.now().strftime('%Y-%m-%d')
        due_date   = (datetime.now() + timedelta(days=LOAN_PERIOD_DAYS)).strftime('%Y-%m-%d')
        conn.execute(
            "INSERT INTO transactions (user_id, book_id, issue_date, due_date, status) VALUES (?, ?, ?, ?, 'issued')",
            (user_id, book_id, issue_date, due_date)
        )
        conn.execute(
            "UPDATE books SET available_copies = available_copies - 1 WHERE book_id=?", (book_id,)
        )
        conn.commit()
        flash(f"'{book['title']}' issued to {user['full_name']}. Due: {due_date}.", "success")
    except Exception as e:
        conn.rollback()
        flash(f"Error issuing book: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='circulation'))


# ── ADMIN: Return Book ────────────────────────────────────────────────────────
@app.route("/return_book/<int:transaction_id>")
def return_book_route(transaction_id):
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    txn = conn.execute("""
        SELECT t.*, b.book_id, b.title
        FROM transactions t
        JOIN books b ON t.book_id = b.book_id
        WHERE t.transaction_id=? AND t.status='issued'
    """, (transaction_id,)).fetchone()

    if not txn:
        conn.close()
        flash("Active transaction not found.", "danger")
        return redirect(url_for("admin_dashboard", section='circulation'))

    try:
        return_date = datetime.now().strftime('%Y-%m-%d')
        due_date_dt = datetime.strptime(txn['due_date'], '%Y-%m-%d')
        return_dt   = datetime.now()

        conn.execute(
            "UPDATE transactions SET status='returned', return_date=? WHERE transaction_id=?",
            (return_date, transaction_id)
        )
        conn.execute(
            "UPDATE books SET available_copies = available_copies + 1 WHERE book_id=?",
            (txn['book_id'],)
        )

        if return_dt > due_date_dt:
            days_late   = (return_dt - due_date_dt).days
            fine_amount = round(days_late * FINE_RATE_PER_DAY, 2)
            conn.execute(
                "INSERT INTO fines (transaction_id, amount, paid) VALUES (?, ?, 0)",
                (transaction_id, fine_amount)
            )
            flash(f"Book returned. Late by {days_late} day(s). Fine: PKR {fine_amount:.2f}.", "warning")
        else:
            flash(f"'{txn['title']}' returned on time.", "success")

        conn.commit()
    except Exception as e:
        conn.rollback()
        flash(f"Return error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='circulation'))


# ── ADMIN: Mark Fine as Paid ──────────────────────────────────────────────────
@app.route("/mark_fine_paid/<int:fine_id>")
def mark_fine_paid(fine_id):
    if session.get("role") != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    try:
        conn.execute(
            "UPDATE fines SET paid=1, paid_on=? WHERE fine_id=?",
            (datetime.now().strftime('%Y-%m-%d'), fine_id)
        )
        conn.commit()
        flash("Fine marked as paid.", "success")
    except Exception as e:
        flash(f"Error: {e}", "danger")
    finally:
        conn.close()
    return redirect(url_for("admin_dashboard", section='circulation'))


# ── USER DASHBOARD ────────────────────────────────────────────────────────────
@app.route("/user")
def user_dashboard():
    if session.get("role") != "user":
        return redirect(url_for("index"))
    current_view = request.args.get('view', 'overview')
    search_term  = request.args.get('search_term', '')
    return render_template("user.html",
        books=fetch_books(search_term),
        admin_metrics=fetch_admin_metrics(),
        user_metrics=fetch_user_metrics(session['username']),
        current_view=current_view,
        search_term=search_term)


# ── USER: My Loans & Fines ────────────────────────────────────────────────────
@app.route("/user_profile", endpoint="user_profile")
def user_profile():
    if session.get("role") != "user":
        return redirect(url_for("index"))
    conn    = get_db()
    user    = conn.execute("SELECT user_id FROM users WHERE username=?", (session['username'],)).fetchone()
    user_id = user['user_id']

    issued_books = conn.execute("""
        SELECT b.title, b.author, b.isbn, t.issue_date, t.due_date, t.transaction_id
        FROM transactions t
        JOIN books b ON t.book_id = b.book_id
        WHERE t.user_id=? AND t.status='issued'
        ORDER BY t.due_date ASC
    """, (user_id,)).fetchall()

    history = conn.execute("""
        SELECT b.title, b.author, t.issue_date, t.return_date, t.status,
               f.amount, f.paid
        FROM transactions t
        JOIN books b ON t.book_id = b.book_id
        LEFT JOIN fines f ON f.transaction_id = t.transaction_id
        WHERE t.user_id=? AND t.status='returned'
        ORDER BY t.return_date DESC
    """, (user_id,)).fetchall()

    pending_fines = conn.execute("""
        SELECT COALESCE(SUM(f.amount), 0)
        FROM fines f
        JOIN transactions t ON f.transaction_id = t.transaction_id
        WHERE t.user_id=? AND f.paid=0
    """, (user_id,)).fetchone()[0]

    conn.close()
    return render_template("user_profile.html",
        issued_books=issued_books,
        history=history,
        pending_fines=round(pending_fines, 2))


# ── USER: Security / Change Password ─────────────────────────────────────────
@app.route("/user_security", endpoint="user_security_route")
def user_security_route():
    if session.get("role") != "user":
        return redirect(url_for("index"))
    return render_template("user_security.html")


@app.route("/change_password", methods=["POST"])
def change_password_route():
    if session.get("role") != "user":
        return redirect(url_for("index"))
    old_pw  = request.form.get("old_password")
    new_pw  = request.form.get("new_password")
    conf_pw = request.form.get("confirm_password")

    if not all([old_pw, new_pw, conf_pw]):
        flash("All fields are required.", "danger")
        return redirect(url_for("user_security_route"))
    if new_pw != conf_pw:
        flash("New password and confirmation do not match.", "danger")
        return redirect(url_for("user_security_route"))

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE username=?", (session['username'],)).fetchone()
    if not user or not check_password_hash(user["password_hash"], old_pw):
        conn.close()
        flash("Incorrect current password.", "danger")
        return redirect(url_for("user_security_route"))
    try:
        conn.execute(
            "UPDATE users SET password_hash=? WHERE user_id=?",
            (generate_password_hash(new_pw), user["user_id"])
        )
        conn.commit()
        flash("Password changed. Please log in again.", "success")
        session.clear()
        return redirect(url_for("index"))
    except Exception as e:
        flash(f"Error: {e}", "danger")
        return redirect(url_for("user_security_route"))
    finally:
        conn.close()


# ── USER: Search ──────────────────────────────────────────────────────────────
@app.route("/search", methods=["POST"])
def search_route():
    if session.get("role") != "user":
        return redirect(url_for("index"))
    return redirect(url_for("user_dashboard", view='catalog', search_term=request.form.get("term", "")))


# ── SERVE PDF: inline preview ─────────────────────────────────────────────────
@app.route("/preview_book/<int:book_id>")
def preview_book(book_id):
    if not session.get("role"):
        return redirect(url_for("index"))
    conn  = get_db()
    book  = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    conn.close()
    if not book or not book['file_path']:
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], book['file_path'],
                               mimetype='application/pdf')


# ── SERVE PDF: force download ─────────────────────────────────────────────────
@app.route("/download_book/<int:book_id>")
def download_book(book_id):
    if not session.get("role"):
        return redirect(url_for("index"))
    conn  = get_db()
    book  = conn.execute("SELECT * FROM books WHERE book_id=?", (book_id,)).fetchone()
    conn.close()
    if not book or not book['file_path']:
        abort(404)
    return send_from_directory(app.config['UPLOAD_FOLDER'], book['file_path'],
                               as_attachment=True,
                               download_name=f"{book['title']}.pdf")


# ── LOGOUT ────────────────────────────────────────────────────────────────────
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("index"))


if __name__ == "__main__":
    app.run(debug=True)