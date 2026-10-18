import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api.js";
import { ErrorBox, Loading, REVIEW, ScoreBar, useAsync, ZONES, ZoneChip } from "../components.jsx";

const COLUMNS = [
  { key: "name", label: "Investigator" },
  { key: "location", label: "Location" },
  { key: "match", label: "Possible record" },
  { key: "score", label: "Score" },
  { key: "zone", label: "Status" },
  { key: "review_status", label: "Review" },
];
const ZONE_ORDER = { probable: 0, review: 1, cleared: 2 };

function Counter({ zone, value, active, onClick }) {
  const z = ZONES[zone];
  return (
    <button onClick={onClick} aria-pressed={active}
      className={`card flex-1 p-4 text-left transition hover:shadow ${active ? "ring-2 ring-slate-800" : ""}`}>
      <div className="flex items-center justify-between"><ZoneChip zone={zone} /></div>
      <div className="mt-2 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-slate-500">{zone === "cleared" ? "no action needed" : "click to filter"}</div>
    </button>
  );
}

export default function ResultsPage() {
  const { id } = useParams();
  const { data, error, loading } = useAsync(() => api.screening(id), [id]);
  const [zone, setZone] = useState("alerts");
  const [source, setSource] = useState("all");
  const [q, setQ] = useState("");
  const [sort, setSort] = useState({ key: "score", dir: -1 });

  const rows = useMemo(() => {
    if (!data) return [];
    let r = data.candidates;
    if (zone === "alerts") r = r.filter((c) => c.zone !== "cleared");
    else if (zone !== "all") r = r.filter((c) => c.zone === zone);
    if (source !== "all") r = r.filter((c) => c.best_match?.source === source);
    if (q) {
      const s = q.toLowerCase();
      r = r.filter((c) => `${c.name} ${c.city} ${c.state} ${c.best_match?.name ?? ""}`.toLowerCase().includes(s));
    }
    const val = (c) => ({
      name: c.name.toLowerCase(), location: `${c.state} ${c.city}`, match: c.best_match?.name ?? "",
      score: c.score, zone: ZONE_ORDER[c.zone], review_status: c.review_status,
    })[sort.key];
    return [...r].sort((a, b) => (val(a) > val(b) ? 1 : val(a) < val(b) ? -1 : 0) * sort.dir);
  }, [data, zone, source, q, sort]);

  if (loading) return <Loading what="Loading results" />;
  if (error) return <ErrorBox error={error} />;
  const pending = data.candidates.filter((c) => c.review_status === "pending").length;
  const sources = [...new Set(data.candidates.map((c) => c.best_match?.source).filter(Boolean))];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <Link to="/" className="text-sm text-slate-500 hover:text-slate-800">← New screening</Link>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">{data.name}</h1>
          <p className="mt-1 text-sm text-slate-500">
            {data.n_candidates} investigators screened in {data.seconds}s · {data.created_at.replace("T", " ").slice(0, 16)} UTC ·
            model {data.model_version} · lists {data.data_version}
          </p>
        </div>
        <div className="flex gap-2">
          <a className="btn-secondary" href={`/api/screenings/${id}/export.csv`}>Export CSV</a>
          <a className="btn-secondary" href={`/api/screenings/${id}/export.pdf`}>Export PDF</a>
        </div>
      </div>

      <div className="flex flex-col gap-3 sm:flex-row">
        {["probable", "review", "cleared"].map((z) => (
          <Counter key={z} zone={z} value={data.zones[z]} active={zone === z} onClick={() => setZone(zone === z ? "alerts" : z)} />
        ))}
      </div>
      {pending > 0 && (
        <p className="text-sm text-slate-700"><strong>{pending}</strong> alert{pending > 1 ? "s" : ""} awaiting a decision.</p>
      )}

      <div className="flex flex-wrap items-center gap-3">
        <select className="input w-auto" value={zone} onChange={(e) => setZone(e.target.value)} aria-label="Status filter">
          <option value="alerts">Alerts only (probable + to review)</option>
          <option value="probable">Probable match</option>
          <option value="review">To review</option>
          <option value="cleared">Cleared</option>
          <option value="all">All investigators</option>
        </select>
        <select className="input w-auto" value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source filter">
          <option value="all">All sources</option>
          {sources.map((s) => <option key={s}>{s}</option>)}
        </select>
        <input className="input w-64" placeholder="Search name, city, state…" value={q} onChange={(e) => setQ(e.target.value)} />
        <span className="text-sm text-slate-500">{rows.length} shown</span>
      </div>

      <div className="card overflow-x-auto">
        <table className="min-w-full divide-y divide-slate-200">
          <thead className="bg-slate-50">
            <tr>
              {COLUMNS.map((c) => (
                <th key={c.key} className="th">
                  <button className="uppercase tracking-wide hover:text-slate-900"
                    onClick={() => setSort((s) => ({ key: c.key, dir: s.key === c.key ? -s.dir : c.key === "score" ? -1 : 1 }))}>
                    {c.label}{sort.key === c.key ? (sort.dir > 0 ? " ↑" : " ↓") : ""}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((c) => (
              <tr key={c.id} className="hover:bg-slate-50">
                <td className="td">
                  <Link to={`/candidates/${c.id}`} className="font-medium text-slate-900 underline-offset-2 hover:underline">{c.name}</Link>
                  <div className="text-xs text-slate-500">{c.candidate_id}{c.specialty ? ` · ${c.specialty}` : ""}</div>
                </td>
                <td className="td whitespace-nowrap text-slate-700">{[c.city, c.state].filter(Boolean).join(", ")}</td>
                <td className="td">
                  {c.best_match ? (
                    <>
                      <div>{c.best_match.name}</div>
                      <div className="text-xs text-slate-500">{c.best_match.source}</div>
                    </>
                  ) : <span className="text-slate-400">—</span>}
                </td>
                <td className="td"><ScoreBar score={c.score} zone={c.zone} /></td>
                <td className="td"><ZoneChip zone={c.zone} /></td>
                <td className={`td whitespace-nowrap text-sm ${REVIEW[c.review_status].cls}`}>{REVIEW[c.review_status].label}</td>
              </tr>
            ))}
            {rows.length === 0 && (
              <tr><td colSpan={6} className="td py-10 text-center text-slate-500">No investigators match these filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
