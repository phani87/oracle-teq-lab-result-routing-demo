import json
import os
from datetime import datetime, timezone

import oracledb
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

from db import get_connection

load_dotenv()

FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)

app = Flask(__name__, static_folder=FRONTEND_DIST, static_url_path="/")
CORS(app)

QUEUE_NAME = os.getenv("QUEUE_NAME", "LAB_RESULT_TEQ")


def parse_iso_ts(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def add_result_event(cur, result_id, stage_code, stage_label, stage_order, details=None):
    cur.execute(
        """
        INSERT INTO lab_result_event (
            result_id, stage_code, stage_label, stage_order, details, created_at
        )
        VALUES (
            :result_id, :stage_code, :stage_label, :stage_order, :details, SYSTIMESTAMP
        )
        """,
        {
            "result_id": result_id,
            "stage_code": stage_code,
            "stage_label": stage_label,
            "stage_order": stage_order,
            "details": details,
        },
    )


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/orders/open")
def get_open_orders():
    conn = get_connection()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                o.order_id,
                o.order_code,
                o.order_name,
                p.patient_name,
                p.patient_mrn,
                pr.provider_name,
                TO_CHAR(o.ordered_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS ordered_at
            FROM lab_order o
            JOIN patient p ON p.patient_id = o.patient_id
            JOIN provider pr ON pr.provider_id = o.ordering_provider_id
            WHERE o.order_status IN ('ORDERED', 'RESULTED')
            ORDER BY o.order_id DESC
            """
        )
        rows = cur.fetchall()
        return jsonify(
            [
                {
                    "order_id": r[0],
                    "order_code": r[1],
                    "order_name": r[2],
                    "patient_name": r[3],
                    "patient_mrn": r[4],
                    "provider_name": r[5],
                    "ordered_at": r[6],
                    "display_label": f"{r[3]} ({r[4]}) • {r[2]} • {r[5]}",
                }
                for r in rows
            ]
        )
    finally:
        conn.close()


@app.post("/api/results")
def submit_lab_result():
    body = request.get_json(force=True)

    required = [
        "order_id",
        "test_code",
        "test_name",
        "resulted_at",
        "abnormal_flag",
        "critical_flag",
    ]
    missing = [k for k in required if k not in body]
    if missing:
        return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

    conn = get_connection()
    try:
        cur = conn.cursor()

        resulted_at = parse_iso_ts(body["resulted_at"])
        result_id_var = cur.var(oracledb.NUMBER)

        cur.execute(
            """
            INSERT INTO lab_result (
                order_id,
                test_code,
                test_name,
                result_value_num,
                result_value_text,
                units,
                reference_low,
                reference_high,
                abnormal_flag,
                critical_flag,
                result_status,
                resulted_at,
                updated_at
            )
            VALUES (
                :order_id,
                :test_code,
                :test_name,
                :result_value_num,
                :result_value_text,
                :units,
                :reference_low,
                :reference_high,
                :abnormal_flag,
                :critical_flag,
                'RECEIVED',
                :resulted_at,
                SYSTIMESTAMP
            )
            RETURNING result_id INTO :result_id
            """,
            {
                "order_id": int(body["order_id"]),
                "test_code": body["test_code"],
                "test_name": body["test_name"],
                "result_value_num": body.get("result_value_num"),
                "result_value_text": body.get("result_value_text"),
                "units": body.get("units"),
                "reference_low": body.get("reference_low"),
                "reference_high": body.get("reference_high"),
                "abnormal_flag": body["abnormal_flag"],
                "critical_flag": body["critical_flag"],
                "resulted_at": resulted_at,
                "result_id": result_id_var,
            },
        )

        result_id = int(result_id_var.getvalue()[0])

        add_result_event(
            cur,
            result_id,
            "RECEIVED",
            "Result received by API",
            10,
            "Result payload accepted from UI",
        )

        payload = {
            "event_type": "LAB_RESULT_RECEIVED",
            "result_id": result_id,
        }

        queue = conn.queue(QUEUE_NAME)
        msg = conn.msgproperties(payload=json.dumps(payload).encode("utf-8"))
        queue.enqone(msg)

        add_result_event(
            cur,
            result_id,
            "ENQUEUED",
            "Queued in TEQ",
            25,
            f"Message enqueued to {QUEUE_NAME}",
        )

        cur.execute(
            """
            UPDATE lab_order
            SET order_status = 'RESULTED'
            WHERE order_id = :order_id
            """,
            {"order_id": int(body["order_id"])},
        )

        conn.commit()

        return jsonify({"result_id": result_id, "status": "RECEIVED"}), 202

    except Exception as e:
        conn.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@app.get("/api/results/<int:result_id>/progress")
def get_result_progress(result_id):
    conn = get_connection()
    try:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT result_id, test_name, result_status, route_reason
            FROM lab_result
            WHERE result_id = :result_id
            """,
            {"result_id": result_id},
        )
        row = cur.fetchone()
        if not row:
            return jsonify({"error": "Not found"}), 404

        cur.execute(
            """
            SELECT stage_code, stage_label, stage_order, details,
                   TO_CHAR(created_at, 'YYYY-MM-DD"T"HH24:MI:SS') AS created_at
            FROM lab_result_event
            WHERE result_id = :result_id
            ORDER BY stage_order, event_id
            """,
            {"result_id": result_id},
        )
        events = [
            {
                "stage_code": r[0],
                "stage_label": r[1],
                "stage_order": r[2],
                "details": r[3],
                "created_at": r[4],
            }
            for r in cur.fetchall()
        ]

        progress = max([e["stage_order"] for e in events], default=0)

        return jsonify(
            {
                "result_id": row[0],
                "test_name": row[1],
                "result_status": row[2],
                "route_reason": row[3],
                "progress_percent": progress,
                "events": events,
            }
        )
    finally:
        conn.close()


@app.route("/")
def serve_index():
    return send_from_directory(FRONTEND_DIST, "index.html")


@app.route("/<path:path>")
def serve_static(path):
    full_path = os.path.join(FRONTEND_DIST, path)
    if os.path.exists(full_path):
        return send_from_directory(FRONTEND_DIST, path)
    return send_from_directory(FRONTEND_DIST, "index.html")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
