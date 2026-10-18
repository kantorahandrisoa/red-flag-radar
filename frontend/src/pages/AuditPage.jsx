import { Link } from "react-router-dom";
import { api } from "../api.js";
import { ErrorBox, Loading, REVIEW, useAsync } from "../components.jsx";

export default function AuditPage() {
  const { data, error, loading } = useAsync(() => api.audit(), []);
  if (loading) return <Loading what="Loading audit log" />;
  if (error) return <ErrorBox error={error} />;
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Audit log</h1>
        <p className="mt-1 text-sm text-slate-600">Every decision, newest first: who decided, when, on which evidence, with which model and list versions. Entries are never edited; a new decision is added instead.</p>
      </div>
      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50"><tr>
            <th className="th">When (UTC)</th><th className="th">Reviewer</th><th className="th">Investigator</th><th className="th">Decision</th>
            <th className="th">Comment</th><th className="th">Score</th><th className="th">Model / lists</th>
          </tr></thead>
          <tbody className="divide-y divide-slate-100">
            {data.map((d, i) => (
              <tr key={i}>
                <td className="td whitespace-nowrap tabular-nums text-slate-600">{d.decided_at.replace("T", " ").slice(0, 19)}</td>
                <td className="td">{d.reviewer}</td>
                <td className="td"><Link className="underline-offset-2 hover:underline" to={`/candidates/${d.candidate_id}`}>{d.candidate}</Link>
                  <div className="text-xs text-slate-500">{d.screening} · {d.sanction_id}</div></td>
                <td className={`td whitespace-nowrap ${REVIEW[d.decision].cls}`}>{d.decision === "confirmed" ? "Confirmed" : "Dismissed"}</td>
                <td className="td max-w-sm">{d.comment}</td>
                <td className="td tabular-nums">{(d.score * 100).toFixed(0)}%</td>
                <td className="td text-xs text-slate-500">{d.model_version}<br />{d.data_version}</td>
              </tr>
            ))}
            {data.length === 0 && <tr><td colSpan={7} className="td py-10 text-center text-slate-500">No decisions recorded yet.</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
