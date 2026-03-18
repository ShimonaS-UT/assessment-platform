from flask import Flask, flash, render_template, request, jsonify, redirect, url_for, session
import sqlite3, json, csv, subprocess, tempfile, sys, os
import re

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "assessment.db")
SAMPLE_SQL_DB = os.path.join(BASE_DIR, "sample_sql.db")
EMPLOYEE_CSV = os.path.join(BASE_DIR, "Employee.csv")

app = Flask(__name__)
app.secret_key = "super_secret_key"

DB_FILE = "assessment.db"
SAMPLE_SQL_DB = "sample_sql.db"
EMPLOYEE_CSV = "Employee.csv"


# -----------------------
# HELPERS
# -----------------------

def get_db_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def load_questions(file):
    with open(file, "r", encoding="utf-8") as f:
        return json.load(f)
# -----------------------
# USER HELPERS
# -----------------------
def get_user_progress_by_id(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM progress WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    conn.close()

    progress = {}
    for r in rows:
        progress[r["assessment_type"]] = {
            "completed": r["completed"],
            "score": r["score"],
            "attempts": r["attempts"],
            # max_attempts will be fetched from assignments
            "max_attempts": 0
        }
    return progress
def get_all_users_with_attempts():

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT 
        users.id,
        users.username,
        assignments.mcq,
        assignments.sql,
        assignments.coding
    FROM users
    LEFT JOIN assignments 
    ON users.id = assignments.user_id
    """)

    users = cur.fetchall()

    conn.close()

    return users
def get_user_assigned_by_id(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assignments WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"mcq": row["mcq"], "sql": row["sql"], "coding": row["coding"]}
    else:
        return {"mcq": 0, "sql": 0, "coding": 0}

def get_user_assigned_assessments_by_id(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM assignments WHERE user_id=?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row:
        return {"mcq": row["mcq"], "sql": row["sql"], "coding": row["coding"]}
    else:
        return {"mcq": 0, "sql": 0, "coding": 0}
def get_all_users_with_attempts():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    SELECT u.id, u.username, a.mcq, a.sql, a.coding
    FROM users u
    LEFT JOIN assignments a ON u.id = a.user_id
    WHERE u.role='user'
    """)

    rows = cur.fetchall()
    conn.close()

    return rows
def get_user_from_db(username, password):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE username=? AND password=?", (username, password))
    row = cur.fetchone()
    conn.close()

    if row:
        # Convert sqlite3.Row to a simple object
        class User:
            def __init__(self, id, username, role):
                self.id = id
                self.username = username
                self.role = role

        return User(row["id"], row["username"], row["role"])
    else:
        return None

# -----------------------
# DATABASE INIT
# -----------------------

def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT DEFAULT 'user'
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS assignments(
        user_id INTEGER PRIMARY KEY,
        mcq INTEGER DEFAULT 0,
        sql INTEGER DEFAULT 0,
        coding INTEGER DEFAULT 0
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS progress(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        assessment_type TEXT,
        attempts INTEGER DEFAULT 0,
        completed INTEGER DEFAULT 0,
        score INTEGER DEFAULT 0,
        UNIQUE(user_id,assessment_type)
    )
    """)

    conn.commit()
    conn.close()


# -----------------------
# HOME
# -----------------------

@app.route("/")
def home():
    return render_template("home.html")


# -----------------------
# LOGIN
# -----------------------
# LOGIN
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        user = get_user_from_db(username, password)
        if not user:
            flash("Invalid username or password", "error")
            return redirect(url_for('login'))

        # Save user info in session
        session['user_id'] = user.id
        session['username'] = user.username  # <--- ADD THIS
        session['role'] = user.role

        if user.role == 'admin':
            return redirect(url_for('admin_dashboard'))
        else:
            return redirect(url_for('dashboard'))

    return render_template('login.html')
# -----------------------
# SIGNUP
# -----------------------



EMAIL_REGEX = r'^[\w\.-]+@[\w\.-]+\.\w+$'

@app.route("/signup", methods=["GET","POST"])
def signup():

    if request.method == "POST":

        username = request.form["username"]
        password = request.form["password"]

        # ✅ Validate email format
        if not re.match(EMAIL_REGEX, username):
            flash("Please enter a valid email address", "error")
            return redirect(url_for("signup"))

        conn = get_db_connection()
        cur = conn.cursor()

        try:
            cur.execute(
                "INSERT INTO users(username,password,role) VALUES(?,?,?)",
                (username, password, "user")
            )

            user_id = cur.lastrowid
            cur.execute("INSERT INTO assignments(user_id) VALUES(?)", (user_id,))
            conn.commit()

        except sqlite3.IntegrityError:
            flash("Email already registered", "error")
            return redirect(url_for("signup"))

        finally:
            conn.close()

        flash("Signup successful! Please login.", "success")
        return redirect(url_for("login"))

    return render_template("signup.html")

# -----------------------
# USER DASHBOARD
# -----------------------

@app.route('/dashboard')
def dashboard():
    # Must be logged in
    if 'user_id' not in session:
        return redirect(url_for('login'))

    # Admins go to admin dashboard
    if session.get('role') == 'admin':
        return redirect(url_for('admin_dashboard'))

    user_id = session['user_id']

    # Fetch progress and assignments
    progress = get_user_progress_by_id(user_id)
    assigned = get_user_assigned_by_id(user_id)

    # Fill in max_attempts for each assessment in progress
    for key in ['mcq','sql','coding']:
        if key in progress:
            progress[key]['max_attempts'] = assigned.get(key,0)
        else:
            # If user has no progress yet, initialize
            progress[key] = {"completed": 0, "score": 0, "attempts": 0, "max_attempts": assigned.get(key,0)}

    return render_template('dashboard.html', progress=progress, assigned=assigned)
# -----------------------
# ADMIN DASHBOARD
# -----------------------

@app.route('/admin_dashboard')
def admin_dashboard():

    if 'username' not in session:
        return redirect(url_for('login'))

    if session.get('role') != 'admin':
        return redirect(url_for('login'))

    users = get_all_users_with_attempts()

    return render_template('admin_dashboard.html', users=users)

# -----------------------
# ASSIGN ASSESSMENT
# -----------------------

@app.route("/assign", methods=["POST"])
def assign():

    if session.get("role") != "admin":
        return redirect(url_for("login"))

    user_id = request.form["user_id"]
    mcq = request.form["mcq"]
    sql = request.form["sql"]
    coding = request.form["coding"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    UPDATE assignments
    SET mcq=?, sql=?, coding=?
    WHERE user_id=?
    """, (mcq, sql, coding, user_id))

    conn.commit()
    conn.close()

    flash("Assessments assigned successfully!", "success")

    return redirect(url_for("admin_dashboard"))
# -----------------------
# MCQ
# -----------------------

@app.route("/mcq")
def mcq():

    if "user_id" not in session:
        return redirect(url_for("login"))
    session.pop("mcq_answers", None)
    questions = load_questions("mcqquestions.json")

    saved_answers = session.get("mcq_answers", {})

    return render_template(
        "mcq.html",
        questions=questions,
        saved_answers=saved_answers
    )


@app.route("/save_mcq", methods=["POST"])
def save_mcq():

    answers = request.json

    session["mcq_answers"] = answers

    return jsonify({"status":"saved"})


@app.route("/submit_mcq", methods=["POST"])
def submit_mcq():

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # get max attempts
    cur.execute("SELECT mcq FROM assignments WHERE user_id=?", (user_id,))
    assigned = cur.fetchone()
    max_attempts = assigned["mcq"] if assigned else 0

    # current attempts
    cur.execute(
        "SELECT attempts FROM progress WHERE user_id=? AND assessment_type=?",
        (user_id, "mcq")
    )

    row = cur.fetchone()
    current_attempts = row["attempts"] if row else 0

    if current_attempts >= max_attempts:
        conn.close()
        return jsonify({"status":"max_attempts"})

    # insert/update progress
    cur.execute("""
    INSERT INTO progress(user_id,assessment_type,attempts,completed,score)
    VALUES(?,?,1,0,0)
    ON CONFLICT(user_id,assessment_type)
    DO UPDATE SET attempts = attempts + 1
    """,(user_id,"mcq"))

    conn.commit()
    conn.close()

    return jsonify({"status":"submitted"})

# -----------------------
# SQL
# -----------------------

@app.route("/sql")
def sql():

    if "user_id" not in session:
        return redirect(url_for("login"))
    session.pop("sql_answers", None)
    questions = load_questions("sqlquestions.json")

    conn = sqlite3.connect(SAMPLE_SQL_DB)
    cur = conn.cursor()

    cur.execute("SELECT * FROM Employee")
    rows = cur.fetchall()

    columns = [desc[0] for desc in cur.description]

    conn.close()

    return render_template(
        "sql.html",
        questions=questions,
        table_rows=rows,
        table_columns=columns
    )

@app.route("/run_sql", methods=["POST"])
def run_sql():

    data = request.get_json()
    query = data["query"]

    conn = sqlite3.connect(SAMPLE_SQL_DB)
    cur = conn.cursor()

    try:
        cur.execute(query)
        rows = cur.fetchall()

        return jsonify({"output": rows})

    except Exception as e:
        return jsonify({"error": str(e)})

@app.route("/save_sql_answer", methods=["POST"])
def save_sql_answer():

    data = request.get_json()

    saved = session.get("sql_answers", {})

    saved[str(data["id"])] = data["query"]

    session["sql_answers"] = saved

    return jsonify({"status": "saved"})
@app.route("/submit_sql", methods=["POST"])
def submit_sql():

    if "user_id" not in session:
        return jsonify({"status": "error"})

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    # Get max allowed attempts from assignments
    cur.execute("SELECT sql FROM assignments WHERE user_id=?", (user_id,))
    assigned = cur.fetchone()
    max_attempts = assigned["sql"] if assigned else 0

    # Get current attempts
    cur.execute(
        "SELECT attempts FROM progress WHERE user_id=? AND assessment_type=?",
        (user_id, "sql")
    )
    row = cur.fetchone()

    current_attempts = row["attempts"] if row else 0

    # Check attempt limit
    if current_attempts >= max_attempts:
        conn.close()
        return jsonify({"status": "max_attempts"})

    # Insert or update progress
    cur.execute("""
    INSERT INTO progress(user_id,assessment_type,attempts,completed,score)
    VALUES(?,?,1,0,0)
    ON CONFLICT(user_id,assessment_type)
    DO UPDATE SET attempts = attempts + 1
    """, (user_id, "sql"))

    conn.commit()
    conn.close()

    return jsonify({"status": "submitted"})
# -----------------------
# CODING
# -----------------------

@app.route("/coding")
def coding():

    if "user_id" not in session:
        return redirect(url_for("login"))
    session.pop("coding_answers", None)
    questions = load_questions("codingquestions.json")

    saved_answers = session.get("coding_answers", {})

    return render_template(
        "coding.html",
        questions=questions,
        saved_answers=saved_answers
    )
@app.route("/run_code", methods=["POST"])
def run_code():

    data = request.get_json()
    code = data["code"]
    input_data = data.get("input","")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
        f.write(code.encode())
        file = f.name

    try:

        result = subprocess.run(
            ["python", file],
            input=input_data,
            capture_output=True,
            text=True,
            timeout=5
        )

        output = result.stdout + result.stderr

    except Exception as e:
        output = str(e)

    os.remove(file)

    return jsonify({"output":output})
@app.route("/save_code", methods=["POST"])
def save_code():

    data = request.get_json()

    saved = session.get("coding_answers", {})

    saved[str(data["id"])] = data["code"]

    session["coding_answers"] = saved

    return jsonify({"status": "saved"})

@app.route("/submit_coding", methods=["POST"])
def submit_coding():

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO progress(user_id,assessment_type,attempts,completed,score)
    VALUES(?,?,1,0,0)
    ON CONFLICT(user_id,assessment_type)
    DO UPDATE SET attempts=attempts+1,
    """,(session["user_id"],"coding"))

    conn.commit()
    conn.close()

    return redirect(url_for("dashboard"))


# -----------------------
# FINAL RESULT
# -----------------------
@app.route("/final_submit")
def final_submit():

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()
    cur = conn.cursor()

    results = []

    # ---------------- MCQ ----------------
    mcq_score = 0
    mcq_total = 0

    mcq_answers = session.get("mcq_answers", {})
    mcq_questions = load_questions("mcqquestions.json")

    for q in mcq_questions:
        mcq_total += 5
        if str(q["id"]) in mcq_answers:
            if mcq_answers[str(q["id"])] == q["answer"]:
                mcq_score += 5

    results.append(("mcq", mcq_score, mcq_total))

    # ---------------- SQL ----------------
    sql_score = 0
    sql_total = 0

    sql_answers = session.get("sql_answers", {})
    sql_questions = load_questions("sqlquestions.json")

    sql_conn = sqlite3.connect(SAMPLE_SQL_DB)
    sql_cur = sql_conn.cursor()

    for q in sql_questions:
        sql_total += 5

        user_query = sql_answers.get(str(q["id"]))

        if user_query:
            try:
                sql_cur.execute(user_query)
                user_result = sql_cur.fetchall()

                # Convert tuples to lists
                user_result = [list(row) for row in user_result]

                if sorted(user_result) == sorted(q["expected_result"]):
                    sql_score += 5

            except:
                pass

    sql_conn.close()

    results.append(("sql", sql_score, sql_total))

    # ---------------- CODING ----------------
    coding_score = 0
    coding_total = 0

    coding_answers = session.get("coding_answers", {})
    coding_questions = load_questions("codingquestions.json")

    for q in coding_questions:

        coding_total += 5

        code = coding_answers.get(str(q["id"]))

        if code:

            passed_all = True

            for test in q["test_cases"]:

                try:

                    with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as f:
                        f.write(code.encode())
                        file = f.name

                    result = subprocess.run(
                        ["python", file],
                        input=test["input"],
                        capture_output=True,
                        text=True,
                        timeout=5
                    )

                    output = result.stdout.strip()

                    os.remove(file)

                    if output != test["expected_output"]:
                        passed_all = False
                        break

                except:
                    passed_all = False
                    break

            if passed_all:
                coding_score += 5

    results.append(("coding", coding_score, coding_total))

    # ---------------- STORE SCORES ----------------

    for assessment, score, total in results:

        cur.execute("""
        SELECT attempts FROM progress
        WHERE user_id=? AND assessment_type=?
        """, (user_id, assessment))

        row = cur.fetchone()

        if row:

            cur.execute("""
            UPDATE progress
            SET completed = 1,
                score = ?
            WHERE user_id=? AND assessment_type=?
            """, (score, user_id, assessment))

        else:

            cur.execute("""
            INSERT INTO progress(user_id,assessment_type,attempts,completed,score)
            VALUES(?,?,1,1,?)
            """, (user_id, assessment, score))

    conn.commit()
    conn.close()

    return render_template("final_result.html", results=results)

@app.route("/tab_switch", methods=["POST"])
def tab_switch():
    if "user_id" not in session:
        return jsonify({"status": "error"})

    user_id = session["user_id"]
    conn = get_db_connection()
    cur = conn.cursor()

    # List of all assessments
    assessments = ["mcq", "sql", "coding"]

    for a in assessments:
        # Check if progress exists
        cur.execute("SELECT * FROM progress WHERE user_id=? AND assessment_type=?", (user_id, a))
        row = cur.fetchone()
        if row:
            # Reset attempts and score, mark completed
            cur.execute("""
                UPDATE progress
                SET attempts=0, score=0, completed=1
                WHERE user_id=? AND assessment_type=?
            """, (user_id, a))
        else:
            # Insert row with attempts=0, score=0, completed=1
            cur.execute("""
                INSERT INTO progress(user_id, assessment_type, attempts, completed, score)
                VALUES(?,?,0,1,0)
            """, (user_id, a))
    conn.commit()
    conn.close()

    # Clear session answers if needed
    session.pop("mcq_answers", None)
    session.pop("sql_answers", None)
    session.pop("coding_answers", None)

    return jsonify({"status": "locked"})
# -----------------------
# LOGOUT
# -----------------------

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# -----------------------
# RUN
# -----------------------

if __name__ == "__main__":

    init_db()

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT * FROM users WHERE username='admin'")

    if not cur.fetchone():

        cur.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                    ("admin","admin123","admin"))

        admin_id = cur.lastrowid

        cur.execute("INSERT INTO assignments(user_id) VALUES(?)",(admin_id,))

        print("Admin created")

    conn.commit()
    conn.close()

    import os

    if __name__ == "__main__":

        init_db()

        conn = get_db_connection()
        cur = conn.cursor()

        cur.execute("SELECT * FROM users WHERE username='admin@xyz.com'")

        if not cur.fetchone():
            cur.execute("INSERT INTO users(username,password,role) VALUES(?,?,?)",
                        ("admin@xyz.com", "admin123", "admin"))
            admin_id = cur.lastrowid
            cur.execute("INSERT INTO assignments(user_id) VALUES(?)", (admin_id,))
            print("Admin created")

        conn.commit()
        conn.close()

        port = int(os.environ.get("PORT", 5000))
        app.run(host="0.0.0.0", port=port, debug=True)