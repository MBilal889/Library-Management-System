import sqlite3

DB_FILE = "lms.db"

def initialize_database():
    conn = sqlite3.connect(DB_FILE)
    conn.execute("PRAGMA foreign_keys = ON;")
    c = conn.cursor()
### users table with role and full_name
    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id       INTEGER  PRIMARY KEY AUTOINCREMENT,
            username      TEXT     NOT NULL UNIQUE,
            password_hash TEXT     NOT NULL,
            role          TEXT     NOT NULL DEFAULT 'user'
                                   CHECK(role IN ('admin', 'user')),
            full_name     TEXT     NOT NULL,
            email         TEXT     NOT NULL UNIQUE,
            created_at    DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
### books table with total_copies and available_copies
    c.execute("""
        CREATE TABLE IF NOT EXISTS books (
            book_id          INTEGER  PRIMARY KEY AUTOINCREMENT,
            isbn             TEXT     NOT NULL UNIQUE,
            title            TEXT     NOT NULL,
            author           TEXT     NOT NULL,
            genre            TEXT,
            total_copies     INTEGER  NOT NULL CHECK(total_copies >= 1),
            available_copies INTEGER  NOT NULL CHECK(available_copies >= 0),
            file_path        TEXT,
            added_on         DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    """)
### transactions table with status and return_date
    c.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            transaction_id  INTEGER  PRIMARY KEY AUTOINCREMENT,
            user_id         INTEGER  NOT NULL,
            book_id         INTEGER  NOT NULL,
            issue_date      DATE     NOT NULL,
            due_date        DATE     NOT NULL,
            return_date     DATE,
            status          TEXT     NOT NULL DEFAULT 'issued'
                                     CHECK(status IN ('issued', 'returned')),
            FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE RESTRICT,
            FOREIGN KEY (book_id) REFERENCES books(book_id) ON DELETE RESTRICT
        );
    """)
### fines table with amount and paid status
    c.execute("""
        CREATE TABLE IF NOT EXISTS fines (
            fine_id        INTEGER  PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER  NOT NULL UNIQUE,
            amount         REAL     NOT NULL CHECK(amount > 0),
            paid           INTEGER  NOT NULL DEFAULT 0 CHECK(paid IN (0, 1)),
            paid_on        DATE,
            FOREIGN KEY (transaction_id) REFERENCES transactions(transaction_id)
                ON DELETE CASCADE
        );
    """)

    conn.commit()
    conn.close()
    print(f"Database '{DB_FILE}' initialized successfully.")


def run_migrations():
    """Add any missing columns to existing databases."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    try:
        c.execute("ALTER TABLE books ADD COLUMN file_path TEXT")
        conn.commit()
        print("Migration applied: books.file_path column added.")
    except sqlite3.OperationalError:
        pass  # Column already exists
    conn.close()


if __name__ == "__main__":
    initialize_database()
    run_migrations()