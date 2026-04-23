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
                    gespann_number INTEGER NOT NULL,
                    time DOUBLE PRECISION,
                    faults INTEGER,
                    note TEXT DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'OK',
                    created_at TIMESTAMP NOT NULL,
                    processed INTEGER DEFAULT 0
                )
            """)

            c.execute("""
                ALTER TABLE results
                ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'OK'
            """)

            c.execute("""
                ALTER TABLE results
                ADD COLUMN IF NOT EXISTS gespann_number INTEGER
            """)


            c.execute("""
                ALTER TABLE results
                ALTER COLUMN gespann_number SET NOT NULL
            """)

            c.execute("""
                ALTER TABLE results
                ALTER COLUMN time DROP NOT NULL
            """)

            c.execute("""
                ALTER TABLE results
                ALTER COLUMN faults DROP NOT NULL
            """)


            c.execute("""
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1
                        FROM pg_constraint
                        WHERE conname = 'unique_obstacle_gespann'
                    ) THEN
                        ALTER TABLE results
                        ADD CONSTRAINT unique_obstacle_gespann
                        UNIQUE (obstacle, gespann_number);
                    END IF;
                END
                $$;
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
input, select, button { font-size: 20px; margin: 10px 0; width: 100%; padding: 10px; box-sizing: border-box; }
.error { color: #b00020; margin-top: 10px; }
.success { color: green; margin-top: 10px; }
</style>
</head>
<body>
<h2>Hindernis {{obstacle}}</h2>
<form method="post">
    <input name="gespann_number" placeholder="Gespannnummer" required>
    <input name="time" placeholder="Zeit (z.B. 41.83 oder 41,83)">
    <input name="faults" placeholder="Fehler">
    
    <select name="status" required>
        <option value="OK">Normal</option>
        <option value="RET">RET - aufgegeben</option>
        <option value="ELI">ELI - ausgeschieden</option>
    </select>

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
            gespann_number = int(request.form["gespann_number"].strip())
            status = request.form["status"].strip().upper()
            note = request.form.get("note", "").strip()

            time_raw = request.form.get("time", "").strip()
            faults_raw = request.form.get("faults", "").strip()

            if status not in ["OK", "RET", "ELI"]:
                raise ValueError("Ungültiger Status")

            if status == "OK":
                if not time_raw:
                    raise ValueError("Bei normalem Ergebnis muss eine Zeit eingegeben werden.")
                if not faults_raw:
                    raise ValueError("Bei normalem Ergebnis müssen Fehler eingegeben werden.")

            time_value = float(time_raw.replace(",", ".")) if time_raw else None
            faults = int(faults_raw) if faults_raw else None

            with get_conn() as conn:
                with conn.cursor() as c:
                    c.execute("""
                        INSERT INTO results
                        (obstacle, gespann_number, time, faults, note, status, created_at)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """, (
                        obstacle,
                        gespann_number,
                        time_value,
                        faults,
                        note,
                        status,
                        datetime.utcnow()
                    ))
                conn.commit()

            success = True

        except ValueError as e:
            error = str(e) if str(e) else "Bitte gültige Werte eingeben."
        except Exception as e:
            if "unique_obstacle_gespann" in str(e):
                error = "Für dieses Hindernis wurde diese Gespannnummer schon eingetragen."
            else:
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
                SELECT id, obstacle, gespann_number, time, faults, note, status, created_at, processed
                FROM results
                WHERE processed = 0
                ORDER BY id ASC
            """)
            rows = c.fetchall()

    data = [
        {
            "id": row[0],
            "obstacle": row[1],
            "gespann_number": row[2],
            "time": row[3],
            "faults": row[4],
            "note": row[5],
            "status": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "processed": row[8],
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
                SELECT id, obstacle, gespann_number, time, faults, note, status, created_at, processed
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
        <p>
            <a href="/alle_loeschen" style="color: red; font-weight: bold;">Alle Einträge löschen</a>
        </p>
        <table>
            <tr>
                <th>ID</th>
                <th>Hindernis</th>
                <th>Gespannnummer</th>
                <th>Zeit</th>
                <th>Fehler</th>
                <th>Bemerkung</th>
                <th>Status</th>
                <th>Erstellt</th>
                <th>Verarbeitet</th>
                <th>Bearbeiten</th>
                <th>Löschen</th>
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
                <td>{{ row[8] }}</td>
                <td><a href="/bearbeiten/{{ row[0] }}">Bearbeiten</a></td>
                <td><a href="/loeschen/{{ row[0] }}" style="color: red;">Löschen</a></td>
            </tr>
            {% endfor %}
        </table>
    </body>
    </html>
    """

    return render_template_string(html, rows=rows)

@app.route("/bearbeiten/<int:result_id>", methods=["GET", "POST"])
def bearbeiten(result_id):
    error = None
    success = False

    with get_conn() as conn:
        with conn.cursor() as c:
            if request.method == "POST":
                try:
                    gespann_number = int(request.form["gespann_number"].strip())
                    status = request.form["status"].strip().upper()
                    note = request.form.get("note", "").strip()

                    time_raw = request.form.get("time", "").strip()
                    faults_raw = request.form.get("faults", "").strip()

                    if status not in ["OK", "RET", "ELI"]:
                        raise ValueError("Ungültiger Status")

                    if status == "OK":
                        if not time_raw:
                            raise ValueError("Bei normalem Ergebnis muss eine Zeit eingegeben werden.")
                        if not faults_raw:
                            raise ValueError("Bei normalem Ergebnis müssen Fehler eingegeben werden.")

                    time_value = float(time_raw.replace(",", ".")) if time_raw else None
                    faults = int(faults_raw) if faults_raw else None

                    c.execute("""
                        UPDATE results
                        SET gespann_number = %s,
                            time = %s,
                            faults = %s,
                            note = %s,
                            status = %s,
                            processed = 0
                        WHERE id = %s
                    """, (
                        gespann_number,
                        time_value,
                        faults,
                        note,
                        status,
                        result_id
                    ))
                    conn.commit()
                    success = True

                except ValueError as e:
                    error = str(e) if str(e) else "Bitte gültige Werte eingeben."
                except Exception as e:
                    if "unique_obstacle_gespann" in str(e):
                        error = "Für dieses Hindernis gibt es diese Gespannnummer bereits."
                    else:
                        error = f"Serverfehler: {e}"

            c.execute("""
                SELECT id, obstacle, gespann_number, time, faults, note, status, created_at, processed
                FROM results
                WHERE id = %s
            """, (result_id,))
            row = c.fetchone()

    if not row:
        return "Eintrag nicht gefunden", 404

    html = """
    <!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Eintrag bearbeiten</title>
        <style>
            body { font-family: sans-serif; padding: 20px; }
            input, select, button { font-size: 20px; margin: 10px 0; width: 100%; padding: 10px; box-sizing: border-box; }
            .error { color: #b00020; margin-top: 10px; }
            .success { color: green; margin-top: 10px; }
            a { display: inline-block; margin-top: 15px; }
        </style>
    </head>
    <body>
        <h2>Eintrag bearbeiten</h2>
        <p><strong>ID:</strong> {{ row[0] }}</p>
        <p><strong>Hindernis:</strong> {{ row[1] }}</p>
        <p><strong>Erstellt:</strong> {{ row[7] }}</p>

        <form method="post">
            <input name="gespann_number" value="{{ row[2] }}" placeholder="Gespannnummer" required>

            <input name="time"
                   value="{{ '' if row[3] is none else row[3] }}"
                   placeholder="Zeit (z.B. 41.83 oder 41,83)">

            <input name="faults"
                   value="{{ '' if row[4] is none else row[4] }}"
                   placeholder="Fehler">

            <select name="status" required>
                <option value="OK" {% if row[6] == 'OK' %}selected{% endif %}>Normal</option>
                <option value="RET" {% if row[6] == 'RET' %}selected{% endif %}>RET - aufgegeben</option>
                <option value="ELI" {% if row[6] == 'ELI' %}selected{% endif %}>ELI - ausgeschieden</option>
            </select>

            <input name="note" value="{{ row[5] }}" placeholder="Bemerkung">

            <button type="submit">Änderungen speichern</button>
        </form>

        {% if success %}
        <p class="success">✅ Änderungen gespeichert</p>
        {% endif %}

        {% if error %}
        <p class="error">❌ {{ error }}</p>
        {% endif %}

        <a href="/uebersicht">Zurück zur Übersicht</a>
    </body>
    </html>
    """

    return render_template_string(html, row=row, success=success, error=error)


@app.route("/loeschen/<int:result_id>", methods=["GET", "POST"])
def loeschen(result_id):
    error = None

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute("""
                SELECT id, obstacle, gespann_number, time, faults, note, status, created_at, processed
                FROM results
                WHERE id = %s
            """, (result_id,))
            row = c.fetchone()

            if not row:
                return "Eintrag nicht gefunden", 404

            if request.method == "POST":
                confirm = request.form.get("confirm")

                if confirm != "yes":
                    error = "Bitte bestätige das Löschen mit dem Haken."
                else:
                    c.execute("DELETE FROM results WHERE id = %s", (result_id,))
                    conn.commit()
                    return """
                    <!doctype html>
                    <html>
                    <head>
                        <meta name="viewport" content="width=device-width, initial-scale=1">
                        <title>Gelöscht</title>
                    </head>
                    <body style="font-family: sans-serif; padding: 20px;">
                        <h2>Eintrag gelöscht</h2>
                        <p>Der Eintrag wurde erfolgreich gelöscht.</p>
                        <a href="/uebersicht">Zurück zur Übersicht</a>
                    </body>
                    </html>
                    """

    html = """
    <!doctype html>
    <html>
    <head>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>Eintrag löschen</title>
        <style>
            body { font-family: sans-serif; padding: 20px; }
            .box { border: 1px solid #ccc; padding: 15px; margin-bottom: 20px; }
            .error { color: #b00020; margin-top: 10px; }
            button { font-size: 18px; padding: 10px 15px; margin-top: 10px; }
            label { display: block; margin-top: 15px; }
        </style>
    </head>
    <body>
        <h2>Eintrag löschen</h2>

        <div class="box">
            <p><strong>ID:</strong> {{ row[0] }}</p>
            <p><strong>Hindernis:</strong> {{ row[1] }}</p>
            <p><strong>Gespann:</strong> {{ row[2] }}</p>
            <p><strong>Zeit:</strong> {{ row[3] }}</p>
            <p><strong>Fehler:</strong> {{ row[4] }}</p>
            <p><strong>Status:</strong> {{ row[6] }}</p>
        </div>

        <form method="post">
            <label>
                <input type="checkbox" name="confirm" value="yes">
                Ja, ich möchte diesen Eintrag wirklich löschen
            </label>

            <button type="submit">Eintrag endgültig löschen</button>
        </form>

        {% if error %}
        <p class="error">❌ {{ error }}</p>
        {% endif %}

        <p><a href="/uebersicht">Abbrechen und zurück</a></p>
    </body>
    </html>
    """

    return render_template_string(html, row=row, error=error)


if __name__ == "__main__":
    app.run(debug=True)