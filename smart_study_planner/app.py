import json
import os
import re
import sqlite3
import urllib.request
import urllib.error
from datetime import date, timedelta
from flask import Flask, jsonify, render_template, request

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(APP_DIR, "study_planner.db")
app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with db() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS subjects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            subject_id INTEGER,
            due_date TEXT,
            estimated_minutes INTEGER NOT NULL DEFAULT 30,
            priority TEXT NOT NULL DEFAULT 'Medium',
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(subject_id) REFERENCES subjects(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS study_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            exam_date TEXT,
            daily_hours INTEGER NOT NULL DEFAULT 3,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        count = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        if count == 0:
            conn.execute("INSERT INTO subjects(name) VALUES (?)", ("Maths",))
            conn.execute("INSERT INTO subjects(name) VALUES (?)", ("Physics",))
            conn.execute("INSERT INTO subjects(name) VALUES (?)", ("Computer",))
        task_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        if task_count == 0:
            rows = conn.execute("SELECT id, name FROM subjects").fetchall()
            subject_map = {r["name"]: r["id"] for r in rows}
            conn.execute(
                "INSERT INTO tasks(title, subject_id, due_date, estimated_minutes, priority) VALUES (?,?,?,?,?)",
                ("Revise one topic", subject_map.get("Maths"), (date.today() + timedelta(days=1)).isoformat(), 30, "High")
            )


def rows_to_dict(rows):
    return [dict(row) for row in rows]


def get_dashboard_data():
    with db() as conn:
        subjects = rows_to_dict(conn.execute(
            "SELECT id, name FROM subjects ORDER BY name"
        ).fetchall())
        tasks = rows_to_dict(conn.execute("""
            SELECT tasks.id, tasks.title, tasks.subject_id,
                   subjects.name AS subject, tasks.due_date,
                   tasks.estimated_minutes, tasks.priority, tasks.status
            FROM tasks LEFT JOIN subjects ON subjects.id = tasks.subject_id
            ORDER BY CASE tasks.status WHEN 'pending' THEN 0 ELSE 1 END,
                     CASE tasks.priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                     tasks.due_date IS NULL, tasks.due_date, tasks.id DESC
        """).fetchall())
        messages = rows_to_dict(conn.execute(
            "SELECT role, content FROM messages ORDER BY id DESC LIMIT 12"
        ).fetchall())
    messages.reverse()
    return subjects, tasks, messages


def ask_openai(user_text, context):
    """Optional AI connection. Keep the API key in an environment variable, never in frontend code."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None, "demo"

    system_text = (
        "You are StudyBuddy, a practical study-planning assistant. Reply in friendly, clear language. "
        "Help students break syllabus into realistic tasks, prioritize deadlines, and plan revision. "
        "Do not claim tasks were saved unless the application does that. If the user asks to create tasks, "
        "suggest concrete task titles and dates in your reply, but the student must add them using the task form. "
        "Respect the student's available study time and include breaks. Existing planner context: " + context
    )
    payload = {
        "model": os.environ.get("OPENAI_MODEL", "gpt-4.1-mini"),
        "input": [
            {"role": "system", "content": system_text},
            {"role": "user", "content": user_text}
        ],
        "max_output_tokens": 500
    }
    req = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            result = json.loads(response.read().decode("utf-8"))
        text_parts = []
        for item in result.get("output", []):
            if item.get("type") == "message":
                for part in item.get("content", []):
                    if part.get("type") == "output_text":
                        text_parts.append(part.get("text", ""))
        answer = "\n".join(text_parts).strip()
        return (answer or "I couldn't create a reply just now. Please try again."), "ai"
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, ValueError):
        return None, "demo"


def demo_reply(message):
    text = message.lower()
    if any(word in text for word in ["syllabus", "chapters", "chapter", "units", "unit"]):
        return (
            "Let's turn your syllabus into manageable pieces. Add each subject and chapter in the "
            "Syllabus section, then add a task with an estimated time and deadline. Start with prerequisite "
            "topics, then practice questions, and keep a revision slot before the exam."
        )
    if any(word in text for word in ["late", "missed", "reschedule", "behind", "pending"]):
        return (
            "We can reset the plan without losing your progress. Use “Reschedule pending tasks” to move "
            "unfinished tasks from today onward. The planner keeps completed tasks unchanged."
        )
    if any(word in text for word in ["plan", "timetable", "schedule", "exam", "study"]):
        return (
            "I can help organize your study plan. Tell me your exam date, subjects, chapters, and how many "
            "hours you can study each day. Then add the suggested tasks to the planner so they are saved. "
            "This first version is in demo chat mode until you add an OpenAI API key."
        )
    return (
        "Got it. I can help you break that into smaller study actions. For this first version, use the "
        "Add task and Add subject forms to save the exact items. Add an OpenAI API key to enable AI replies."
    )


@app.route("/")
def index():
    subjects, tasks, messages = get_dashboard_data()
    return render_template("index.html", subjects=subjects, tasks=tasks, messages=messages,
                           today=date.today().isoformat())


@app.post("/api/subjects")
def add_subject():
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify(error="Please enter a subject name."), 400
    try:
        with db() as conn:
            cur = conn.execute("INSERT INTO subjects(name) VALUES (?)", (name,))
            subject_id = cur.lastrowid
        return jsonify(id=subject_id, name=name)
    except sqlite3.IntegrityError:
        return jsonify(error="That subject already exists."), 409


@app.post("/api/tasks")
def add_task():
    data = request.json or {}
    title = str(data.get("title", "")).strip()
    if not title:
        return jsonify(error="Please enter a task title."), 400
    subject_id = data.get("subject_id") or None
    due_date = data.get("due_date") or None
    try:
        minutes = max(5, min(720, int(data.get("estimated_minutes", 30))))
    except (TypeError, ValueError):
        minutes = 30
    priority = data.get("priority", "Medium")
    if priority not in ("High", "Medium", "Low"):
        priority = "Medium"
    with db() as conn:
        if subject_id:
            exists = conn.execute("SELECT id FROM subjects WHERE id=?", (subject_id,)).fetchone()
            if not exists:
                subject_id = None
        cur = conn.execute(
            "INSERT INTO tasks(title, subject_id, due_date, estimated_minutes, priority) VALUES (?,?,?,?,?)",
            (title, subject_id, due_date, minutes, priority)
        )
        task_id = cur.lastrowid
    return jsonify(id=task_id, message="Task saved.")


@app.patch("/api/tasks/<int:task_id>")
def update_task(task_id):
    status = (request.json or {}).get("status")
    if status not in ("pending", "completed"):
        return jsonify(error="Invalid status."), 400
    with db() as conn:
        cur = conn.execute("UPDATE tasks SET status=? WHERE id=?", (status, task_id))
        if cur.rowcount == 0:
            return jsonify(error="Task not found."), 404
    return jsonify(message="Task updated.")


@app.delete("/api/tasks/<int:task_id>")
def delete_task(task_id):
    with db() as conn:
        cur = conn.execute("DELETE FROM tasks WHERE id=?", (task_id,))
        if cur.rowcount == 0:
            return jsonify(error="Task not found."), 404
    return jsonify(message="Task deleted.")


@app.post("/api/reschedule")
def reschedule():
    """Simple rule: spread pending tasks over the next 7 days, preserving completed tasks."""
    with db() as conn:
        pending = conn.execute("""
            SELECT id FROM tasks WHERE status='pending'
            ORDER BY CASE priority WHEN 'High' THEN 0 WHEN 'Medium' THEN 1 ELSE 2 END,
                     due_date IS NULL, due_date, id
        """).fetchall()
        start = date.today()
        for index, row in enumerate(pending):
            new_day = start + timedelta(days=index % 7)
            conn.execute("UPDATE tasks SET due_date=? WHERE id=?", (new_day.isoformat(), row["id"]))
    return jsonify(message=f"Rescheduled {len(pending)} pending task(s) across the next 7 days.")



@app.post("/api/plans")
def create_manual_plan():
    """Create a study plan manually and turn each chapter into a saved task."""
    data = request.json or {}
    plan_name = str(data.get("name", "")).strip()[:120]
    exam_date = str(data.get("exam_date", "")).strip() or None
    try:
        daily_hours = max(1, min(12, int(data.get("daily_hours", 3))))
    except (TypeError, ValueError):
        daily_hours = 3
    subject_name = str(data.get("subject", "")).strip()[:80]
    chapters_text = str(data.get("chapters", "")).strip()
    try:
        minutes_per_chapter = max(5, min(720, int(data.get("minutes_per_chapter", 45))))
    except (TypeError, ValueError):
        minutes_per_chapter = 45
    priority = data.get("priority", "Medium")
    if priority not in ("High", "Medium", "Low"):
        priority = "Medium"

    chapters = [line.strip().lstrip("-•* ").strip() for line in chapters_text.splitlines() if line.strip()]
    if not plan_name:
        return jsonify(error="Please enter a study plan name."), 400
    if not subject_name:
        return jsonify(error="Please enter a subject name."), 400
    if not chapters:
        return jsonify(error="Add at least one chapter or topic, one per line."), 400

    try:
        end_date = date.fromisoformat(exam_date) if exam_date else None
    except ValueError:
        return jsonify(error="Please choose a valid exam date."), 400
    if end_date and end_date < date.today():
        return jsonify(error="Exam date cannot be in the past."), 400

    with db() as conn:
        conn.execute(
            "INSERT INTO study_plans(name, exam_date, daily_hours) VALUES (?,?,?)",
            (plan_name, exam_date, daily_hours)
        )
        subject = conn.execute("SELECT id FROM subjects WHERE name=?", (subject_name,)).fetchone()
        if subject:
            subject_id = subject["id"]
        else:
            cur = conn.execute("INSERT INTO subjects(name) VALUES (?)", (subject_name,))
            subject_id = cur.lastrowid

        # Spread chapters over the available days before the exam, while keeping
        # a minimum of one day for a small plan. This is a simple first version.
        total_days = max(1, (end_date - date.today()).days) if end_date else max(1, (len(chapters) + daily_hours - 1) // daily_hours)
        for index, chapter in enumerate(chapters):
            due = date.today() + timedelta(days=min(total_days - 1, index * total_days // len(chapters)))
            conn.execute(
                """INSERT INTO tasks(title, subject_id, due_date, estimated_minutes, priority)
                   VALUES (?,?,?,?,?)""",
                (chapter, subject_id, due.isoformat(), minutes_per_chapter, priority)
            )

    return jsonify(message=f"Plan created! Saved {len(chapters)} chapter task(s) under {subject_name}.",
                   task_count=len(chapters), subject=subject_name)


@app.post("/api/chat")
def chat():
    message = (request.json or {}).get("message", "").strip()
    if not message:
        return jsonify(error="Write a message first."), 400
    with db() as conn:
        conn.execute("INSERT INTO messages(role, content) VALUES ('user', ?)", (message,))
        tasks_count = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
        subjects = conn.execute("SELECT name FROM subjects ORDER BY name").fetchall()
    context = f"Subjects: {', '.join(row['name'] for row in subjects)}. Current saved task count: {tasks_count}."
    answer, mode = ask_openai(message, context)
    if answer is None:
        answer, mode = demo_reply(message), "demo"
    with db() as conn:
        conn.execute("INSERT INTO messages(role, content) VALUES ('assistant', ?)", (answer,))
    return jsonify(reply=answer, mode=mode)


@app.post("/api/chat/clear")
def clear_chat():
    with db() as conn:
        conn.execute("DELETE FROM messages")
    return jsonify(message="Chat cleared.")


init_db()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
