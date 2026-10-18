import { useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import Papa from "papaparse";
import { api } from "../api.js";
import { ErrorBox, useAsync, useReviewer } from "../components.jsx";

const EXPECTED = ["first_name", "last_name", "middle_name", "city", "state", "specialty", "npi"];

function checkColumns(fields) {
  const cols = fields.map((f) => f.trim().toLowerCase().replace(/ /g, "_"));
  const hasName = (cols.includes("first_name") && cols.includes("last_name")) || cols.includes("full_name");
  return {
    ok: hasName,
    found: EXPECTED.filter((c) => cols.includes(c)),
    missing: EXPECTED.filter((c) => !cols.includes(c)),
  };
}

export default function ImportPage() {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [reviewer] = useReviewer();
  const inputRef = useRef();
  const navigate = useNavigate();
  const health = useAsync(api.health, []);
  const past = useAsync(api.screenings, []);

  const pick = (f) => {
    setError(null);
    if (!f) return;
    if (!f.name.toLowerCase().endsWith(".csv")) return setError(new Error("Please choose a .csv file."));
    if (f.size > 2 * 1024 * 1024) return setError(new Error("File too large (max 2 MB)."));
    setFile(f);
    Papa.parse(f, {
      header: true, skipEmptyLines: true, preview: 6,
      complete: (res) => setPreview({ rows: res.data.slice(0, 5), fields: res.meta.fields ?? [], check: checkColumns(res.meta.fields ?? []) }),
      error: (e) => setError(e),
    });
  };

  const run = async (demo) => {
    setBusy(true);
    setError(null);
    try {
      const s = demo ? await api.demo(reviewer) : await api.upload(file, file.name, reviewer);
      navigate(`/screenings/${s.id}`);
    } catch (e) {
      setError(e);
      setBusy(false);
    }
  };

  const h = health.data;
  return (
    <div className="space-y-8">
      <section className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">Screen investigators against public sanction lists</h1>
        <p className="mt-2 text-slate-600">
          Upload the investigators you plan to work with. Each name is compared with the
          OIG exclusion list and the FDA debarment list. Every possible match gets a score, its reasons and
          a link to the official record. <strong className="font-semibold text-slate-800">You decide; the tool only points.</strong>
        </p>
        {h && (
          <p className="mt-3 text-xs text-slate-500">
            {Object.entries(h.sanction_records).map(([k, v]) => `${k}: ${v.toLocaleString()} records`).join(" · ")} ·
            lists {h.data_version} · model {h.model_version}
          </p>
        )}
      </section>

      <div className="grid gap-6 lg:grid-cols-3">
        <section className="card p-6 lg:col-span-2">
          <h2 className="font-semibold">1. Upload a candidate list (CSV)</h2>
          <div
            role="button" tabIndex={0}
            onClick={() => inputRef.current.click()}
            onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && inputRef.current.click()}
            onDragOver={(e) => { e.preventDefault(); setDrag(true); }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => { e.preventDefault(); setDrag(false); pick(e.dataTransfer.files[0]); }}
            className={`mt-4 flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed px-6 py-10 text-center transition ${drag ? "border-slate-700 bg-slate-100" : "border-slate-300 hover:border-slate-500"}`}
          >
            <svg className="h-8 w-8 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            <p className="mt-2 text-sm font-medium">{file ? file.name : "Drop a CSV here or click to choose"}</p>
            <p className="mt-1 text-xs text-slate-500">Columns: first_name, last_name (or full_name); optional middle_name, city, state, specialty, npi</p>
            <input ref={inputRef} type="file" accept=".csv,text/csv" className="hidden" onChange={(e) => pick(e.target.files[0])} />
          </div>

          {preview && (
            <div className="mt-5">
              <div className="flex flex-wrap items-center gap-2 text-sm">
                {preview.check.ok
                  ? <span className="font-medium text-emerald-800">✓ Name columns found</span>
                  : <span className="font-medium text-red-800">✗ Needs first_name and last_name (or full_name)</span>}
                {preview.check.missing.length > 0 && preview.check.ok && (
                  <span className="text-slate-500">· Not provided: {preview.check.missing.join(", ")} (matching will rely more on names)</span>
                )}
              </div>
              <div className="mt-3 overflow-x-auto rounded-lg border border-slate-200">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50"><tr>{preview.fields.map((f) => <th key={f} className="th">{f}</th>)}</tr></thead>
                  <tbody className="divide-y divide-slate-100">
                    {preview.rows.map((r, i) => (
                      <tr key={i}>{preview.fields.map((f) => <td key={f} className="td whitespace-nowrap">{r[f]}</td>)}</tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="mt-1 text-xs text-slate-500">First 5 rows</p>
            </div>
          )}

          <div className="mt-6 flex flex-wrap items-center gap-3">
            <button className="btn-primary" disabled={!file || !preview?.check.ok || busy} onClick={() => run(false)}>
              {busy ? "Screening…" : "Run screening"}
            </button>
            <span className="text-sm text-slate-500">or</span>
            <button className="btn-secondary" disabled={busy} onClick={() => run(true)}>
              Use the demo set (300 synthetic investigators)
            </button>
            <a className="text-sm text-slate-600 underline hover:text-slate-900" href="/api/demo.csv">Download demo CSV</a>
          </div>
          <div className="mt-4"><ErrorBox error={error} /></div>
        </section>

        <aside className="card p-6">
          <h2 className="font-semibold">How results are sorted</h2>
          <ul className="mt-3 space-y-3 text-sm text-slate-700">
            <li><strong className="text-red-800">▲ Probable match</strong> — strong evidence it is the same person. Check the source before acting.</li>
            <li><strong className="text-amber-900">● To review</strong> — similar name, but not enough to tell. Often a homonym.</li>
            <li><strong className="text-slate-600">○ Cleared</strong> — no meaningful match on the lists.</li>
          </ul>
          <p className="mt-4 text-xs text-slate-500">
            Confirming or dismissing an alert requires a comment. Every decision is logged with the reviewer,
            the time, and the model and list versions used.
          </p>
        </aside>
      </div>

      {past.data?.length > 0 && (
        <section>
          <h2 className="mb-3 font-semibold">Previous screenings</h2>
          <div className="card overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead className="bg-slate-50"><tr>
                <th className="th">Screening</th><th className="th">Run at (UTC)</th><th className="th">By</th>
                <th className="th">Investigators</th><th className="th">Probable</th><th className="th">To review</th>
              </tr></thead>
              <tbody className="divide-y divide-slate-100">
                {past.data.slice(0, 10).map((s) => (
                  <tr key={s.id} className="hover:bg-slate-50">
                    <td className="td"><Link className="font-medium underline-offset-2 hover:underline" to={`/screenings/${s.id}`}>{s.name}</Link></td>
                    <td className="td tabular-nums text-slate-600">{s.created_at.replace("T", " ").slice(0, 16)}</td>
                    <td className="td text-slate-600">{s.created_by || "—"}</td>
                    <td className="td tabular-nums">{s.n_candidates}</td>
                    <td className="td tabular-nums text-red-800">{s.zones.probable}</td>
                    <td className="td tabular-nums text-amber-900">{s.zones.review}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
