from flask import Flask, request, jsonify, render_template_string
import sqlite3
from datetime import datetime

app = Flask(__name__)

DB = "results.db"

def init_db():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            obstacle INTEGER,
            start_number INTEGER,
            time REAL,
            faults INTEGER,
            note TEXT,
            created_at TEXT,
            processed INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    conn.close()

init_db()

HTML_FORM = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: sans-serif; padding: 20px; }
input, button { font-size: 20px; margin: 10px 0; width: 100%; padding: 10px; }
</style>
</head>
<body>
<h2>Hindernis {{obstacle}}</h2>
<form method="post">
    <input name="start_number" placeholder="Startnummer" required>
    <input name="time" placeholder="Zeit (z.B. 41.83)" required>
    <input name="faults" placeholder="Fehler" required>
    <input name="note" placeholder="Bemerkung">
    <button type="submit">Senden</button>
</form>
{% if success %}
<p>✅ Gespeichert!</p>
{% endif %}
</body>
</html>
"""

@app.route("/eingabe/<int:obstacle>", methods=["GET", "POST"])
def eingabe(obstacle):
    success = False
    if request.method == "POST":
        conn = sqlite3.connect(DB)
        c = conn.cursor()
        c.execute("""
            INSERT INTO results 
            (obstacle, start_number, time, faults, note, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            obstacle,
            int(request.form["start_number"]),
            float(request.form["time"]),
            int(request.form["faults"]),
            request.form.get("note", ""),
            datetime.now().isoformat()
        ))
        conn.commit()
        conn.close()
        success = True

    return render_template_string(HTML_FORM, obstacle=obstacle, success=success)


@app.route("/api/results")
def get_results():
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.execute("SELECT * FROM results WHERE processed = 0")
    rows = c.fetchall()
    conn.close()

    return jsonify(rows)


@app.route("/api/mark_processed", methods=["POST"])
def mark_processed():
    ids = request.json.get("ids", [])
    conn = sqlite3.connect(DB)
    c = conn.cursor()
    c.executemany("UPDATE results SET processed=1 WHERE id=?", [(i,) for i in ids])
    conn.commit()
    conn.close()
    return {"status": "ok"}


if __name__ == "__main__":
    app.run()