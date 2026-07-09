import { listMyPayments, listPayments } from "../api/payments";
import { useAsync } from "../hooks/useAsync";
import StatusBadge from "../components/StatusBadge";

export default function PaymentSummaryPage({
  mode,
}: {
  mode: "manager" | "annotator";
}) {
  const { data, loading, error } = useAsync(
    mode === "manager" ? listPayments : listMyPayments,
    [mode],
  );

  const rows = data ?? [];
  const total = rows
    .filter((p) => p.status !== "cancelled")
    .reduce((s, p) => s + Number(p.amount), 0);

  // Manager view: group by annotator.
  const byAnnotator = new Map<string, number>();
  rows.forEach((p) => {
    byAnnotator.set(
      p.annotator_username,
      (byAnnotator.get(p.annotator_username) ?? 0) + Number(p.amount),
    );
  });

  return (
    <>
      <h1>{mode === "manager" ? "Payments" : "My Payments"}</h1>
      {error && <div className="error">{error}</div>}

      <div className="grid">
        <div className="card">
          <div className="muted">Records</div>
          <div className="stat">{rows.length}</div>
        </div>
        <div className="card">
          <div className="muted">Estimated total</div>
          <div className="stat">${total.toFixed(2)}</div>
        </div>
      </div>

      {mode === "manager" && byAnnotator.size > 0 && (
        <div className="card">
          <h3>By annotator</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Annotator</th>
                  <th>Estimated total</th>
                </tr>
              </thead>
              <tbody>
                {[...byAnnotator.entries()].map(([name, amt]) => (
                  <tr key={name}>
                    <td>{name}</td>
                    <td>${amt.toFixed(2)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <div className="card">
        <h3>Records</h3>
        {loading ? (
          <p className="muted">Loading…</p>
        ) : rows.length === 0 ? (
          <p className="muted">No payment records yet.</p>
        ) : (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Project</th>
                  {mode === "manager" && <th>Annotator</th>}
                  <th>Amount</th>
                  <th>Status</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <td>#{p.task}</td>
                    <td>{p.project_title}</td>
                    {mode === "manager" && <td>{p.annotator_username}</td>}
                    <td>${p.amount}</td>
                    <td>
                      <StatusBadge value={p.status} />
                    </td>
                    <td>{new Date(p.created_at).toLocaleDateString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </>
  );
}
