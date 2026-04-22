import json
import logging
import os
import time

import oracledb
from dotenv import load_dotenv

from db import get_connection

load_dotenv()

QUEUE_NAME = os.getenv("QUEUE_NAME", "LAB_RESULT_TEQ")
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "2"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
LOGGER = logging.getLogger(__name__)


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


def create_notification(cur, result_id, recipient_type, recipient_id, channel, message_text):
    cur.execute(
        """
        INSERT INTO result_notification (
            result_id, recipient_type, recipient_id,
            channel, notification_status, message_text,
            created_at, sent_at
        )
        VALUES (
            :result_id, :recipient_type, :recipient_id,
            :channel, 'SENT', :message_text,
            SYSTIMESTAMP, SYSTIMESTAMP
        )
        """,
        {
            "result_id": result_id,
            "recipient_type": recipient_type,
            "recipient_id": recipient_id,
            "channel": channel,
            "message_text": message_text,
        },
    )


def create_follow_up_task(cur, result_id, patient_id, provider_id, task_type, priority, task_notes, due_hours):
    cur.execute(
        """
        INSERT INTO follow_up_task (
            result_id, patient_id, provider_id,
            task_type, priority, task_status,
            due_at, task_notes, created_at, updated_at
        )
        VALUES (
            :result_id, :patient_id, :provider_id,
            :task_type, :priority, 'OPEN',
            SYSTIMESTAMP + NUMTODSINTERVAL(:due_hours, 'HOUR'),
            :task_notes,
            SYSTIMESTAMP, SYSTIMESTAMP
        )
        """,
        {
            "result_id": result_id,
            "patient_id": patient_id,
            "provider_id": provider_id,
            "task_type": task_type,
            "priority": priority,
            "task_notes": task_notes,
            "due_hours": due_hours,
        },
    )


def process_result(conn, result_id):
    cur = conn.cursor()

    add_result_event(
        cur,
        result_id,
        "DEQUEUED",
        "Dequeued from TEQ",
        40,
        f"Worker picked result {result_id} from {QUEUE_NAME}",
    )

    cur.execute(
        """
        SELECT
            r.result_id,
            r.test_code,
            r.test_name,
            r.abnormal_flag,
            r.critical_flag,
            r.result_status,
            o.patient_id,
            o.ordering_provider_id,
            p.patient_name,
            pr.provider_name,
            NVL(rule.release_policy, 'NORMAL_ONLY'),
            NVL(rule.create_followup_on_abnormal, 'Y'),
            NVL(rule.escalate_on_critical, 'Y'),
            NVL(rule.default_followup_type, 'PROVIDER_REVIEW')
        FROM lab_result r
        JOIN lab_order o ON o.order_id = r.order_id
        JOIN patient p ON p.patient_id = o.patient_id
        JOIN provider pr ON pr.provider_id = o.ordering_provider_id
        LEFT JOIN lab_test_rule rule ON rule.test_code = r.test_code
        WHERE r.result_id = :result_id
        FOR UPDATE
        """,
        {"result_id": result_id},
    )

    row = cur.fetchone()
    if not row:
        raise ValueError(f"Result {result_id} not found")

    (
        result_id,
        test_code,
        test_name,
        abnormal_flag,
        critical_flag,
        result_status,
        patient_id,
        provider_id,
        patient_name,
        provider_name,
        release_policy,
        create_followup_on_abnormal,
        escalate_on_critical,
        default_followup_type,
    ) = row

    if result_status in ("ROUTED", "RELEASED", "PROVIDER_REVIEW"):
        LOGGER.info("Result %s already processed", result_id)
        return

    add_result_event(
        cur,
        result_id,
        "RULES_EVALUATED",
        "Routing rules evaluated",
        55,
        f"Policy={release_policy}, abnormal={abnormal_flag}, critical={critical_flag}",
    )

    create_notification(
        cur,
        result_id,
        "PROVIDER",
        provider_id,
        "INBOX",
        f"{test_name} result posted for {patient_name}. Please review.",
    )

    final_status = "ROUTED"
    route_reason = "Provider notified"

    if critical_flag == "Y" and escalate_on_critical == "Y":
        create_follow_up_task(
            cur,
            result_id,
            patient_id,
            provider_id,
            default_followup_type,
            "CRITICAL",
            f"Critical {test_name} result requires immediate provider review.",
            1,
        )
        add_result_event(
            cur,
            result_id,
            "ACTIONS_CREATED",
            "Critical workflow created",
            80,
            "Provider inbox notification + critical follow-up task created",
        )
        final_status = "PROVIDER_REVIEW"
        route_reason = "Critical result routed to provider review; patient release withheld"

    elif abnormal_flag == "Y" and create_followup_on_abnormal == "Y":
        create_follow_up_task(
            cur,
            result_id,
            patient_id,
            provider_id,
            default_followup_type,
            "HIGH",
            f"Abnormal {test_name} result requires provider follow-up.",
            24,
        )

        if release_policy == "ALWAYS":
            create_notification(
                cur,
                result_id,
                "PATIENT",
                patient_id,
                "PORTAL",
                f"Your {test_name} result is now available in the patient portal.",
            )
            final_status = "RELEASED"
            route_reason = "Abnormal result released to patient and routed to provider"
            details = "Provider notification + follow-up task + patient portal release created"
        else:
            final_status = "PROVIDER_REVIEW"
            route_reason = "Abnormal result routed to provider review; patient release withheld"
            details = "Provider notification + follow-up task created"

        add_result_event(
            cur,
            result_id,
            "ACTIONS_CREATED",
            "Follow-up workflow created",
            80,
            details,
        )

    else:
        if release_policy in ("ALWAYS", "NORMAL_ONLY"):
            create_notification(
                cur,
                result_id,
                "PATIENT",
                patient_id,
                "PORTAL",
                f"Your {test_name} result is now available in the patient portal.",
            )
            final_status = "RELEASED"
            route_reason = "Normal result released to patient and provider notified"
            details = "Provider notification + patient portal release created"
        else:
            final_status = "PROVIDER_REVIEW"
            route_reason = "Normal result sent for provider review per rule"
            details = "Provider notification created"

        add_result_event(
            cur,
            result_id,
            "ACTIONS_CREATED",
            "Notifications/tasks created",
            80,
            details,
        )

    cur.execute(
        """
        UPDATE lab_result
        SET result_status = :result_status,
            route_reason = :route_reason,
            routed_at = SYSTIMESTAMP,
            updated_at = SYSTIMESTAMP
        WHERE result_id = :result_id
        """,
        {
            "result_status": final_status,
            "route_reason": route_reason,
            "result_id": result_id,
        },
    )

    add_result_event(
        cur,
        result_id,
        final_status,
        "Routing complete",
        100,
        route_reason,
    )

    LOGGER.info("Processed result_id=%s final_status=%s", result_id, final_status)


def run():
    conn = get_connection()
    queue = conn.queue(QUEUE_NAME)
    queue.deqoptions.wait = oracledb.DEQ_NO_WAIT

    LOGGER.info("Worker started on queue %s", QUEUE_NAME)

    while True:
        try:
            msg = queue.deqone()
            if msg is None:
                time.sleep(POLL_INTERVAL_SECONDS)
                continue

            payload = json.loads(msg.payload.decode("utf-8"))
            process_result(conn, int(payload["result_id"]))
            conn.commit()

        except Exception as exc:
            conn.rollback()
            LOGGER.exception("Worker error: %s", exc)
            time.sleep(POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
