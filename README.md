# Library Management System (LMS)

A robust, self-contained Library Management System built from scratch using **Python (Flask)** and an **SQLite3** relational backend. This project focuses entirely on database normalization, input data integrity, and secure server-side session routing. 

To keep the architecture grounded in core full-stack principles and accessible for academic criteria, the application avoids client-side JavaScript for workflow management, relying instead on clean Flask URL parameters to drive the user interface state securely.

---

## 💾 Relational Database Architecture (`lms.db`)

The structural foundation of this system is a normalized relational schema that strictly enforces database constraints, automatic primary key increments, domain check conditions, and relational integrity rules (`ON DELETE RESTRICT` and `ON DELETE CASCADE`) across four core tables:

* **Users Table (`users`):** Persists authentication states, registration details, and system privileges (`admin` vs. `user`) with cryptographically hashed passwords.
* **Books Table (`books`):** Serves as the library inventory ledger, tracking book metadata (Title, Author, Unique ISBN, Genre) alongside floating copy counts and server-side file paths for uploaded digital PDFs.
* **Transactions Table (`transactions`):** Logs circulation history by bridging user records with book assets. It dynamically manages checking windows, due dates, return logs, and tracking states (`issued` vs. `returned`).
* **Fines Table (`fines`):** Tracks financial late fees linked dynamically to specific overdue borrowing logs, securing transaction tracking and audit transparency.

---

## 🚀 Key System Features

### 🖥️ Admin Control Panel
* **Backend UI State Navigation:** App sections (**Overview**, **Edit/Manage**, and **Circulation**) and lower-tier forms are systematically toggled via server-side parameters parsed dynamically inside Python routing endpoints.
* **Data Validation & Integrity Checks:** Enforces strict logical constraints, such as blocking manual database updates from reducing a book's inventory total below the quantity currently on loan to readers.
* **Dynamic Diagnostic Dashboards:** Features real-time analytical summaries showing total registered users, current catalog size, active loans, and outstanding system fine metrics.
* **Automated Accounting Engine:** Evaluates borrowing windows during returns. If current check-in system timestamps exceed due dates, it automatically writes calculated penalty rows to the fines table based on fixed daily rates (PKR 10.00/day).

### 👤 User Services Dashboard
* **Relational String Query Engine:** Executes targeted database searches using multi-column wildcard filtering (`LIKE` queries matching inputs against titles, authors, genres, or ISBN codes).
* **Direct Asset Access:** Users can safely interact with digital file assets directly from the local server upload folder for inline PDF previewing or local storage download backups.
* **Personal Borrowing Profile:** Dynamically retrieves active personal loan lists, historical checkout logs, and precise fine details directly from SQLite records.
* **Security Management:** A secure backend script handles explicit password alteration workflows, validating past credential hashes before updating table records.

---

## 🛠️ Technology Stack

* **Backend Engine:** Python 3 + Flask Framework
* **Data Storage Tier:** SQLite3 Relational Database Engine
* **Utility Assets:** Werkzeug Security (Cryptographic Password Hashing)
* **Frontend Interface:** Semantic HTML5, Custom CSS3 (Glassmorphism layout featuring dark transparent panels and red accent glows), and Font Awesome v6 graphic assets. No client-side JavaScript workflows.

---

## 📦 System Installation & Deployment

1. **Clone the Project Repository:**
   ```bash
   git clone [https://github.com/yourusername/relational-library-system.git](https://github.com/yourusername/relational-library-system.git)
   cd relational-library-system
