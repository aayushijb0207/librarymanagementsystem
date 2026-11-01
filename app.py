from flask import Flask, render_template, request, redirect, url_for, session
import sqlite3
from datetime import date

app = Flask(__name__)
app.secret_key = "library_secret_key"


# Database connection
def get_db_connection():
    conn = sqlite3.connect("library.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


# Create database tables
def create_tables():
    conn = get_db_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            author TEXT NOT NULL,
            category TEXT NOT NULL,
            quantity INTEGER NOT NULL CHECK(quantity >= 0)
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL,
            course TEXT NOT NULL
        )
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS issued_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            issue_date TEXT NOT NULL,
            due_date TEXT NOT NULL,
            return_date TEXT,
            status TEXT NOT NULL DEFAULT 'Issued',
            FOREIGN KEY (book_id) REFERENCES books(id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    """)

    conn.commit()
    conn.close()


# Home page
@app.route("/")
def home():
    if "user" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))


# Login
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")

        if username == "admin" and password == "admin123":
            session["user"] = username
            return redirect(url_for("dashboard"))

        return render_template(
            "login.html",
            error="Invalid username or password!"
        )

    return render_template("login.html")


# Dashboard
@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    total_books = conn.execute(
        "SELECT COUNT(*) FROM books"
    ).fetchone()[0]

    total_copies = conn.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM books"
    ).fetchone()[0]

    total_students = conn.execute(
        "SELECT COUNT(*) FROM students"
    ).fetchone()[0]

    total_issued = conn.execute(
        "SELECT COUNT(*) FROM issued_books WHERE status = 'Issued'"
    ).fetchone()[0]

    total_overdue = conn.execute(
        """
        SELECT COUNT(*) FROM issued_books
        WHERE status = 'Issued' AND due_date < ?
        """,
        (date.today().isoformat(),)
    ).fetchone()[0]

    conn.close()

    return render_template(
        "dashboard.html",
        total_books=total_books,
        total_copies=total_copies,
        total_students=total_students,
        total_issued=total_issued,
        total_overdue=total_overdue
    )


# View and search books
@app.route("/books")
def books():
    if "user" not in session:
        return redirect(url_for("login"))

    search = request.args.get("search", "").strip()

    conn = get_db_connection()

    book_list = conn.execute(
        """
        SELECT * FROM books
        WHERE title LIKE ? OR author LIKE ? OR category LIKE ?
        ORDER BY id DESC
        """,
        (f"%{search}%", f"%{search}%", f"%{search}%")
    ).fetchall()

    conn.close()

    return render_template(
        "books.html",
        books=book_list,
        search=search
    )


# Add book
@app.route("/add-book", methods=["GET", "POST"])
def add_book():
    if "user" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()

        try:
            quantity = int(request.form.get("quantity", ""))

            if not title or not author or not category or quantity < 0:
                raise ValueError

        except ValueError:
            return render_template(
                "add_book.html",
                error="Enter valid details and a quantity of zero or more."
            )

        conn = get_db_connection()

        conn.execute(
            """
            INSERT INTO books (title, author, category, quantity)
            VALUES (?, ?, ?, ?)
            """,
            (title, author, category, quantity)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("books"))

    return render_template("add_book.html")


# Edit book
@app.route("/edit-book/<int:book_id>", methods=["GET", "POST"])
def edit_book(book_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    book = conn.execute(
        "SELECT * FROM books WHERE id = ?",
        (book_id,)
    ).fetchone()

    if book is None:
        conn.close()
        return "Book not found.", 404

    if request.method == "POST":
        title = request.form.get("title", "").strip()
        author = request.form.get("author", "").strip()
        category = request.form.get("category", "").strip()

        try:
            quantity = int(request.form.get("quantity", ""))

            if not title or not author or not category or quantity < 0:
                raise ValueError

        except ValueError:
            conn.close()
            return "Please enter valid book details.", 400

        active_issues = conn.execute(
            """
            SELECT COUNT(*) FROM issued_books
            WHERE book_id = ? AND status = 'Issued'
            """,
            (book_id,)
        ).fetchone()[0]

        if quantity < active_issues:
            conn.close()
            return (
                "Quantity cannot be less than the number of copies "
                "currently issued.",
                400
            )

        conn.execute(
            """
            UPDATE books
            SET title = ?, author = ?, category = ?, quantity = ?
            WHERE id = ?
            """,
            (title, author, category, quantity, book_id)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("books"))

    conn.close()

    return render_template("edit_book.html", book=book)


# Delete book
@app.route("/delete-book/<int:book_id>", methods=["POST"])
def delete_book(book_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    active_issues = conn.execute(
        """
        SELECT COUNT(*) FROM issued_books
        WHERE book_id = ? AND status = 'Issued'
        """,
        (book_id,)
    ).fetchone()[0]

    if active_issues > 0:
        conn.close()
        return "This book cannot be deleted while copies are issued.", 400

    conn.execute("DELETE FROM books WHERE id = ?", (book_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("books"))


# Student registration and list
@app.route("/students", methods=["GET", "POST"])
def students():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        course = request.form.get("course", "").strip()

        if not name or not email or not course:
            student_list = conn.execute(
                "SELECT * FROM students ORDER BY id DESC"
            ).fetchall()

            conn.close()

            return render_template(
                "students.html",
                students=student_list,
                error="Please fill in all student details."
            )

        conn.execute(
            """
            INSERT INTO students (name, email, course)
            VALUES (?, ?, ?)
            """,
            (name, email, course)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("students"))

    student_list = conn.execute(
        "SELECT * FROM students ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return render_template("students.html", students=student_list)


# Issue a book
@app.route("/issue-book", methods=["GET", "POST"])
def issue_book():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        try:
            book_id = int(request.form.get("book_id", ""))
            student_id = int(request.form.get("student_id", ""))
            due_date = request.form.get("due_date", "").strip()

            parsed_due_date = date.fromisoformat(due_date)

            if parsed_due_date < date.today():
                raise ValueError

        except (ValueError, TypeError):
            book_list = conn.execute(
                "SELECT * FROM books WHERE quantity > 0 ORDER BY title"
            ).fetchall()

            student_list = conn.execute(
                "SELECT * FROM students ORDER BY name"
            ).fetchall()

            conn.close()

            return render_template(
                "issue_book.html",
                books=book_list,
                students=student_list,
                error="Choose a valid book, student, and due date (today or later)."
            )

        book = conn.execute(
            "SELECT * FROM books WHERE id = ? AND quantity > 0",
            (book_id,)
        ).fetchone()

        student = conn.execute(
            "SELECT * FROM students WHERE id = ?",
            (student_id,)
        ).fetchone()

        if book is None or student is None:
            book_list = conn.execute(
                "SELECT * FROM books WHERE quantity > 0 ORDER BY title"
            ).fetchall()

            student_list = conn.execute(
                "SELECT * FROM students ORDER BY name"
            ).fetchall()

            conn.close()

            return render_template(
                "issue_book.html",
                books=book_list,
                students=student_list,
                error="Selected book is unavailable or student does not exist."
            )

        conn.execute(
            """
            INSERT INTO issued_books
            (book_id, student_id, issue_date, due_date, status)
            VALUES (?, ?, ?, ?, 'Issued')
            """,
            (book_id, student_id, date.today().isoformat(), due_date)
        )

        conn.execute(
            "UPDATE books SET quantity = quantity - 1 WHERE id = ?",
            (book_id,)
        )

        conn.commit()
        conn.close()

        return redirect(url_for("issued_books"))

    book_list = conn.execute(
        "SELECT * FROM books WHERE quantity > 0 ORDER BY title"
    ).fetchall()

    student_list = conn.execute(
        "SELECT * FROM students ORDER BY name"
    ).fetchall()

    conn.close()

    return render_template(
        "issue_book.html",
        books=book_list,
        students=student_list
    )


# View issued books, returned books and overdue books
@app.route("/issued-books")
def issued_books():
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    records = conn.execute(
        """
        SELECT
            issued_books.*,
            books.title AS book_title,
            books.author AS book_author,
            students.name AS student_name,
            students.email AS student_email,
            CASE
                WHEN issued_books.status = 'Issued'
                     AND issued_books.due_date < ?
                THEN 'Overdue'
                ELSE issued_books.status
            END AS display_status
        FROM issued_books
        JOIN books ON issued_books.book_id = books.id
        JOIN students ON issued_books.student_id = students.id
        ORDER BY
            CASE WHEN issued_books.status = 'Issued' THEN 0 ELSE 1 END,
            issued_books.due_date ASC
        """,
        (date.today().isoformat(),)
    ).fetchall()

    conn.close()

    return render_template("issued_books.html", records=records)


# Return a book
@app.route("/return-book/<int:issue_id>", methods=["POST"])
def return_book(issue_id):
    if "user" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    record = conn.execute(
        """
        SELECT * FROM issued_books
        WHERE id = ? AND status = 'Issued'
        """,
        (issue_id,)
    ).fetchone()

    if record is None:
        conn.close()
        return "Issue record not found or the book has already been returned.", 404

    conn.execute(
        """
        UPDATE issued_books
        SET status = 'Returned', return_date = ?
        WHERE id = ?
        """,
        (date.today().isoformat(), issue_id)
    )

    conn.execute(
        "UPDATE books SET quantity = quantity + 1 WHERE id = ?",
        (record["book_id"],)
    )

    conn.commit()
    conn.close()

    return redirect(url_for("issued_books"))


# Logout
@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# Start application
if __name__ == "__main__":
    create_tables()
    app.run(debug=True)