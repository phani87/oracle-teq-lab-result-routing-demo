import React, { useEffect, useMemo, useState } from "react";
import { getOpenOrders, submitResult, getResultProgress } from "./api";

const TEST_TEMPLATES = {
  K: {
    test_code: "K",
    test_name: "Potassium",
    units: "mmol/L",
    reference_low: 3.5,
    reference_high: 5.1
  },
  A1C: {
    test_code: "A1C",
    test_name: "Hemoglobin A1C",
    units: "%",
    reference_low: 4.0,
    reference_high: 5.6
  },
  LDL: {
    test_code: "LDL",
    test_name: "LDL Cholesterol",
    units: "mg/dL",
    reference_low: 0,
    reference_high: 100
  }
};

export default function App() {
  const [orders, setOrders] = useState([]);
  const [search, setSearch] = useState("");
  const [selectedOrder, setSelectedOrder] = useState(null);
  const [submittedResultId, setSubmittedResultId] = useState(null);
  const [progress, setProgress] = useState(null);
  const [submitting, setSubmitting] = useState(false);

  const [form, setForm] = useState({
    test_code: "K",
    test_name: "Potassium",
    result_value_num: "",
    result_value_text: "",
    units: "mmol/L",
    reference_low: 3.5,
    reference_high: 5.1,
    abnormal_flag: "N",
    critical_flag: "N",
    resulted_at: new Date().toISOString().slice(0, 16)
  });

  useEffect(() => {
    loadOrders();
  }, []);

  useEffect(() => {
    if (!submittedResultId) return;

    const timer = setInterval(async () => {
      const res = await getResultProgress(submittedResultId);
      setProgress(res.data);

      if (res.data.progress_percent >= 100) {
        clearInterval(timer);
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [submittedResultId]);

  async function loadOrders() {
    const res = await getOpenOrders();
    setOrders(res.data);
  }

  const filteredOrders = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return orders;
    return orders.filter((o) =>
      [
        o.patient_name,
        o.patient_mrn,
        o.provider_name,
        o.order_name,
        o.order_code
      ]
        .join(" ")
        .toLowerCase()
        .includes(q)
    );
  }, [orders, search]);

  function applyTemplate(code) {
    const template = TEST_TEMPLATES[code];
    setForm((prev) => ({
      ...prev,
      ...template
    }));
  }

  function onChange(e) {
    setForm((prev) => ({
      ...prev,
      [e.target.name]: e.target.value
    }));
  }

  async function onSubmit() {
    if (!selectedOrder) {
      alert("Please select an order first.");
      return;
    }

    setSubmitting(true);
    try {
      const payload = {
        order_id: selectedOrder.order_id,
        test_code: form.test_code,
        test_name: form.test_name,
        result_value_num: form.result_value_num === "" ? null : Number(form.result_value_num),
        result_value_text: form.result_value_text || null,
        units: form.units,
        reference_low: form.reference_low === "" ? null : Number(form.reference_low),
        reference_high: form.reference_high === "" ? null : Number(form.reference_high),
        abnormal_flag: form.abnormal_flag,
        critical_flag: form.critical_flag,
        resulted_at: new Date(form.resulted_at).toISOString()
      };

      const res = await submitResult(payload);
      setSubmittedResultId(res.data.result_id);

      const progressRes = await getResultProgress(res.data.result_id);
      setProgress(progressRes.data);
    } finally {
      setSubmitting(false);
    }
  }

  const currentStatus = progress?.result_status || "RECEIVED";

  return (
    <div className="app-shell">
      <div className="hero">
        <h1>Lab Result Routing Console</h1>
        <p>
          Select a patient order, submit a lab result, and watch TEQ move it through routing.
        </p>
      </div>

      <div className="layout">
        <div className="panel">
          <h2>1. Choose the lab order</h2>

          <input
            className="search-box"
            placeholder="Search by patient name, MRN, provider, or order"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />

          <div className="order-list">
            {filteredOrders.map((order) => (
              <div
                key={order.order_id}
                className={`order-card ${selectedOrder?.order_id === order.order_id ? "selected" : ""}`}
                onClick={() => setSelectedOrder(order)}
              >
                <div className="order-title">{order.patient_name} ({order.patient_mrn})</div>
                <div className="order-meta">
                  <div><b>Order:</b> {order.order_name} ({order.order_code})</div>
                  <div><b>Provider:</b> {order.provider_name}</div>
                  <div><b>Ordered:</b> {order.ordered_at}</div>
                </div>
              </div>
            ))}
            {filteredOrders.length === 0 && <div className="empty">No matching orders.</div>}
          </div>

          <h2 style={{ marginTop: 22 }}>2. Enter the result</h2>

          <div className="template-row">
            {Object.keys(TEST_TEMPLATES).map((code) => (
              <button
                key={code}
                type="button"
                className={`template-chip ${form.test_code === code ? "active" : ""}`}
                onClick={() => applyTemplate(code)}
              >
                {code} — {TEST_TEMPLATES[code].test_name}
              </button>
            ))}
          </div>

          <div className="grid-2">
            <div className="field">
              <label>Test code</label>
              <input name="test_code" value={form.test_code} onChange={onChange} />
            </div>
            <div className="field">
              <label>Test name</label>
              <input name="test_name" value={form.test_name} onChange={onChange} />
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label>Numeric result</label>
              <input name="result_value_num" value={form.result_value_num} onChange={onChange} />
            </div>
            <div className="field">
              <label>Units</label>
              <input name="units" value={form.units} onChange={onChange} />
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label>Reference low</label>
              <input name="reference_low" value={form.reference_low} onChange={onChange} />
            </div>
            <div className="field">
              <label>Reference high</label>
              <input name="reference_high" value={form.reference_high} onChange={onChange} />
            </div>
          </div>

          <div className="field">
            <label>Result note</label>
            <textarea
              name="result_value_text"
              value={form.result_value_text}
              onChange={onChange}
              placeholder="Optional text note from the lab"
            />
          </div>

          <div className="grid-2">
            <div className="field">
              <label>Abnormal?</label>
              <select name="abnormal_flag" value={form.abnormal_flag} onChange={onChange}>
                <option value="N">No</option>
                <option value="Y">Yes</option>
              </select>
            </div>
            <div className="field">
              <label>Critical?</label>
              <select name="critical_flag" value={form.critical_flag} onChange={onChange}>
                <option value="N">No</option>
                <option value="Y">Yes</option>
              </select>
            </div>
          </div>

          <div className="field">
            <label>Result timestamp</label>
            <input
              type="datetime-local"
              name="resulted_at"
              value={form.resulted_at}
              onChange={onChange}
            />
          </div>

          <div className="btn-row">
            <button className="btn btn-primary" onClick={onSubmit} disabled={submitting}>
              {submitting ? "Submitting..." : "Submit result to TEQ"}
            </button>
            <button className="btn btn-secondary" onClick={loadOrders}>
              Refresh orders
            </button>
          </div>
        </div>

        <div className="panel">
          <h2>Routing progress</h2>

          {selectedOrder ? (
            <div className="summary">
              <div><b>Patient:</b> {selectedOrder.patient_name} ({selectedOrder.patient_mrn})</div>
              <div><b>Order:</b> {selectedOrder.order_name}</div>
              <div><b>Provider:</b> {selectedOrder.provider_name}</div>
            </div>
          ) : (
            <div className="summary empty">Select an order to begin.</div>
          )}

          {progress ? (
            <>
              <div className="progress-wrap">
                <div className="progress-labels">
                  <span>API</span>
                  <span>TEQ</span>
                  <span>Worker</span>
                  <span>Complete</span>
                </div>

                <div className="progress-bar">
                  <div
                    className="progress-fill"
                    style={{ width: `${progress.progress_percent || 0}%` }}
                  />
                </div>

                <div className={`status-pill status-${currentStatus}`}>
                  {currentStatus}
                </div>

                <p style={{ marginTop: 12, color: "#64748b" }}>
                  {progress.route_reason || "Waiting for worker..."}
                </p>
              </div>

              <div className="timeline">
                {progress.events.map((event, idx) => (
                  <div key={`${event.stage_code}-${idx}`} className="timeline-item">
                    <div className="timeline-title">{event.stage_label}</div>
                    <div className="timeline-meta">{event.created_at}</div>
                    {event.details && (
                      <div className="timeline-meta" style={{ marginTop: 4 }}>
                        {event.details}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="empty">
              Submit a result and the app will show the TEQ lifecycle here.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}