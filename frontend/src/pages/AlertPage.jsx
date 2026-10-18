import { Fragment, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { ErrorBox, fmtScore, Gauge, Loading, REVIEW, useAsync, useReviewer, ZoneChip } from "../components.jsx";

const FIELD_STATUS = {
  match: { label: "Same", cls: "bg-emerald-50 text-emerald-900", mark: "=" },
  differs: { label: "Different", cls: "bg-red-50/60 text-red-900", mark: "≠" },
  partial: { label: "Partly the same", cls: "bg-amber-50 text-amber-900", mark: "≈" },
  missing: { label: "Not available", cls: "text-slate-400", mark: "?" },
};

function Comparison({ fields }) {
  return (
    <div className="overflow-x-auto">
      <table className="min-w-full text-sm">
        <thead>
          <tr className="border-b border-slate-200">
            <th className="th w-28">Field</th><th className="th">Investigator (your list)</th>
            <th className="th w-10 text-center" aria-label="Comparison"></th><th className="th">Sanction record</th>
          </tr>
        </thead>
        <tbody>
          {fields.map((f) => {
            const st = FIELD_STATUS[f.status];
            return (
              <tr key={f.field} className="border-b border-slate-100">
                <td className="td text-slate-500">{f.field}</td>
                <td className={`td font-medium ${["match", "partial"].includes(f.status) ? st.cls : ""}`}>{f.candidate || <span className="text-slate-400">—</span>}</td>
                <td className="td text-center text-slate-500" title={st.label}>
                  <span aria-label={st.label}>{st.mark}</span>
                </td>
                <td className={`td font-medium ${["match", "partial"].includes(f.status) ? st.cls : ""}`}>{f.record || <span className="text-slate-400">—</span>}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-2 text-xs text-slate-500">= same · ≈ partly the same · ≠ different · ? missing on one side. Values shown after normalization (case, accents, titles removed).</p>
    </div>
  );
}

function Reasons({ reasons }) {
  if (!reasons.length) return <p className="text-sm text-slate-500">No single factor stands out.</p>;
  return (
    <ul className="space-y-2">
      {reasons.map((r) => (
        <li key={r.feature} className="flex items-start gap-3 text-sm">
          <span className={`mt-0.5 inline-flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-xs font-bold ${r.direction === "raises" ? "bg-red-100 text-red-800" : "bg-emerald-100 text-emerald-800"}`}
                aria-hidden="true">{r.direction === "raises" ? "↑" : "↓"}</span>
          <span>
            <span className="font-medium">{r.text}</span>
            <span className="text-slate-500"> — {r.direction} the score</span>
          </span>
        </li>
      ))}
    </ul>
  );
}

function Record({ rec }) {
  const rows = [
    ["Source", rec.source], ["Sanction", rec.sanction_type], ["Severity", rec.severity === "high" ? "High (exclusion or debarment)" : rec.severity],
    ["Effective date", rec.sanction_date], ["Term", rec.end_term], ["Listed specialty", rec.specialty_raw],
    ["List retrieved", rec.fetched_at], ["List version", rec.import_version], ["Record id", rec.sanction_id],
  ].filter(([, v]) => v);
  return (
    <div>
      <dl className="grid grid-cols-[8rem_1fr] gap-x-3 gap-y-1.5 text-sm">
        {rows.map(([k, v]) => (
          <Fragment key={k}><dt className="text-slate-500">{k}</dt><dd className="break-words">{v}</dd></Fragment>
        ))}
      </dl>
      {rec.source_url && (
        <a href={rec.source_url} target="_blank" rel="noopener noreferrer" className="btn-secondary mt-4">
          Open the official source ↗
        </a>
      )}
    </div>
  );
}

function DecisionForm({ candidate, match, onDone }) {
  const [reviewer, setReviewer] = useReviewer();
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const valid = comment.trim().length >= 5 && reviewer.trim().length >= 2;

  const submit = async (decision) => {
    setBusy(true);
    setError(null);
    try {
      await api.decide(candidate.id, { decision, comment, reviewer, sanction_id: match?.record.sanction_id ?? "" });
      setComment("");
      onDone();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <label className="block text-sm">
        <span className="font-medium">Reviewer</span>
        <input className="input mt-1" value={reviewer} onChange={(e) => setReviewer(e.target.value)} placeholder="Your name" />
      </label>
      <label className="block text-sm">
        <span className="font-medium">Comment <span className="font-normal text-slate-500">(required)</span></span>
        <textarea className="input mt-1 h-24" value={comment} onChange={(e) => setComment(e.target.value)}
                  placeholder="What did you check? e.g. 'NPI confirmed with the site: different person.'" />
      </label>
      <div className="flex flex-wrap gap-2">
        <button className="btn bg-red-700 text-white hover:bg-red-800" disabled={!valid || busy} onClick={() => submit("confirmed")}>
          Confirm: same person
        </button>
        <button className="btn bg-emerald-700 text-white hover:bg-emerald-800" disabled={!valid || busy} onClick={() => submit("dismissed")}>
          Dismiss: different person
        </button>
      </div>
      {!valid && <p className="text-xs text-slate-500">Enter your name and a comment of at least 5 characters to record a decision.</p>}
      <ErrorBox error={error} />
    </div>
  );
}

export default function AlertPage() {
  const { id } = useParams();
  const { data: c, error, loading, reload } = useAsync(() => api.candidate(id), [id]);
  const [mi, setMi] = useState(0);

  if (loading && !c) return <Loading what="Loading alert" />;
  if (error) return <ErrorBox error={error} />;
  const m = c.matches[Math.min(mi, c.matches.length - 1)];
  const status = REVIEW[c.review_status];

  return (
    <div className="space-y-6">
      <div>
        <Link to={`/screenings/${c.screening_id}`} className="text-sm text-slate-500 hover:text-slate-800">← {c.screening_name}</Link>
        <div className="mt-1 flex flex-wrap items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
          <ZoneChip zone={c.zone} size="lg" />
          <span className={`text-sm ${status.cls}`}>{status.label}</span>
        </div>
        <p className="mt-1 text-sm text-slate-500">
          {[c.raw.specialty, [c.raw.city, c.raw.state].filter(Boolean).join(", "), c.raw.npi && `NPI ${c.raw.npi}`].filter(Boolean).join(" · ")}
          {" · "}row {c.candidate_id}
        </p>
      </div>

      {!m ? (
        <div className="card p-6 text-sm text-slate-600">No record on the sanction lists resembles this investigator.</div>
      ) : (
        <>
          {c.matches.length > 1 && (
            <div className="flex flex-wrap gap-2" role="tablist">
              {c.matches.map((x, i) => (
                <button key={x.match_id} role="tab" aria-selected={i === mi} onClick={() => setMi(i)}
                  className={`rounded-lg border px-3 py-1.5 text-sm ${i === mi ? "border-slate-800 bg-slate-900 text-white" : "border-slate-300 bg-white hover:bg-slate-100"}`}>
                  {x.record.display_name} · {fmtScore(x.score)}
                </button>
              ))}
            </div>
          )}

          <div className="grid gap-6 lg:grid-cols-3">
            <section className="card p-6 lg:col-span-2">
              <h2 className="font-semibold">Side by side</h2>
              <div className="mt-4"><Comparison fields={m.fields} /></div>
            </section>
            <section className="card p-6">
              <h2 className="font-semibold">Match score</h2>
              <div className="mt-4"><Gauge score={m.score} zone={m.zone} thresholds={c.thresholds} /></div>
              <h3 className="mt-6 text-sm font-semibold">Why this score</h3>
              <div className="mt-2"><Reasons reasons={m.reasons} /></div>
              {m.hint && <p className="mt-4 rounded-lg bg-sky-50 px-3 py-2 text-sm text-sky-900">💡 {m.hint}</p>}
            </section>
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <section className="card p-6 lg:col-span-2">
              <h2 className="font-semibold">Sanction record: {m.record.display_name}</h2>
              <div className="mt-4"><Record rec={m.record} /></div>
            </section>
            <section className="card p-6">
              <h2 className="font-semibold">Your decision</h2>
              <p className="mt-1 text-xs text-slate-500">Recorded with model {c.model_version} and lists {c.data_version}.</p>
              <div className="mt-4"><DecisionForm candidate={c} match={m} onDone={reload} /></div>
            </section>
          </div>
        </>
      )}

      {c.decisions.length > 0 && (
        <section className="card p-6">
          <h2 className="font-semibold">Decision history</h2>
          <ol className="mt-3 space-y-3">
            {[...c.decisions].reverse().map((d, i) => (
              <li key={i} className="border-l-2 border-slate-300 pl-3 text-sm">
                <div><strong>{d.reviewer}</strong> — <span className={REVIEW[d.decision].cls}>{d.decision === "confirmed" ? "confirmed: same person" : "dismissed: different person"}</span></div>
                <div className="text-slate-700">“{d.comment}”</div>
                <div className="text-xs text-slate-500">{d.decided_at.replace("T", " ")} UTC · record {d.sanction_id}</div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </div>
  );
}
