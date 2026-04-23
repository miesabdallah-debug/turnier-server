from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
import os
import psycopg

app = Flask(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL ist nicht gesetzt")

def get_conn():
    return psycopg.connect(DATABASE_URL)

def init_db():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS results (
                    id SERIAL PRIMARY KEY,
                    obstacle INTEGER NOT NULL,
                    start_number INTEGER NOT NULL,
                    time DOUBLE PRECISION NOT NULL,
                    faults INTEGER NOT NULL,
                    note TEXT DEFAULT '',
                    created_at TIMESTAMP NOT NULL,
                    processed INTEGER DEFAULT 0
                )
            """)
        conn.commit()

init_db()

HTML_FORM = """
<!doctype html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: sans-serif; padding: 20px; }
input, button { font-size: 20px; margin: 10px 0; width: 100%; padding: 10px; box-sizing: border-box; }
.error { color: #b00020; margin-top: 10px; }
.success { color: green; margin-top: 10px; }
</style>
</head>
<body>
<h2>Hindernis {{obstacle}}</h2>
<form method="post">
    <input name="start_number" placeholder="Startnummer" required>
    <input name="time" placeholder="Zeit (z.B. 41.83 oder 41,83)" required>
    <input name="faults" placeholder="Fehler" required>
    <input name="note" placeholder="Bemerkung">
    <button type="submit">Senden</button>
</form>

{% if success %}
<p class="success">✅ Gespeichert!</p>
{% endif %}

{% if error %}
<p class="error">❌ {{ error }}</p>
{% endif %}
</body>
</html>
"""

@app.route("/eingabe/<int:obstacle>", methods=["GET", "POST"])
def eingabe(obstacle):
    success = False
    error = None

    if request.method == "POST":
        try:
            start_number = int(request.form["start_number"].strip())
            time_value = float(request.form["time"].strip().replace(",", "."))
            faults = int(request.form["faults"].strip())
            note = request.form.get("note", "").strip()

            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        INSERT INTO results
                        (obstacle, start_number, time, faults, note, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        obstacle,
                        start_number,
                        time_value,
                        faults,
                        note,
                        datetime.utcnow()
                    ))
                conn.commit()

            success = True

        except ValueError:
            error = "Bitte gültige Zahlen eingeben."
        except Exception as e:
            error = f"Serverfehler: {e}"

    return render_template_string(
        HTML_FORM,
        obstacle=obstacle,
        success=success,
        error=error
    )

@app.route("/api/results")
def get_results():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT id, obstacle, start_number, time, faults, note, created_at, processed
                FROM results
                WHERE processed = 0
                ORDER BY id ASC
            """)
            rows = c.fetchall()

    data = [
        {
            "id": row[0],
            "obstacle": row[1],
            "start_number": row[2],
            "time": row[3],
            "faults": row[4],
            "note": row[5],
            "created_at": row[6].isoformat() if row[6] else None,
            "processed": row[7],
        }
        for row in rows
    ]
    return jsonify(data)

@app.route("/api/mark_processed", methods=["POST"])
def mark_processed():
    ids = request.json.get("ids", [])

    if not ids:
        return {"status": "ok", "updated": 0}

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "UPDATE results SET processed = 1 WHERE id = ANY(%s)",
                (ids,)
            )
        conn.commit()

    return {"status": "ok", "updated": len(ids)}

@app.route("/uebersicht")
def uebersicht():
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT id, obstacle, start_number, time, faults, note, created_at, processed
                FROM results
                ORDER BY id DESC
            """)
            rows = c.fetchall()

    html = """
    <!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Übersicht</title>
        <meta http-equiv="refresh" content="3">
        <style>
            body { font-family: sans-serif; padding: 20px; }
            h2 { margin-bottom: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ccc; padding: 8px; text-align: left; }
            th { background: #f2f2f2; }
            tr:nth-child(even) { background: #fafafa; }
        </style>
    </head>
    <body>
        <h2>Eingegangene Ergebnisse</h2>
        <table>
            <tr>
                <th>ID</th>
                <th>Hindernis</th>
                <th>Startnummer</th>
                <th>Zeit</th>
                <th>Fehler</th>
                <th>Bemerkung</th>
                <th>Erstellt</th>
                <th>Verarbeitet</th>
            </tr>
            {% for row in rows %}
            <tr>
                <td>{{ row[0] }}</td>
                <td>{{ row[1] }}</td>
                <td>{{ row[2] }}</td>
                <td>{{ row[3] }}</td>
                <td>{{ row[4] }}</td>
                <td>{{ row[5] }}</td>
                <td>{{ row[6] }}</td>
                <td>{{ row[7] }}</td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """

    return render_template_string(html, rows=rows)

if __name__ == "__main__":
    app.run(debug=True)