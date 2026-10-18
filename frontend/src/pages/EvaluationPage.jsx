import { CartesianGrid, ComposedChart, Legend, Line, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { api } from "../api.js";
import { ErrorBox, Loading, useAsync, ZONES } from "../components.jsx";

const SERIES = {
  "LightGBM (calibrated)": { color: "#2a78d6", name: "Red Flag Radar (LightGBM)" },
  "Logistic regression": { color: "#eb6834", name: "Logistic regression" },
};
const pct = (v) => `${(v * 100).toFixed(1)}%`;

function Tile({ label, value, target, ok, note }) {
  return (
    <div className="card p-5">
      <div className="text-sm text-slate-600">{label}</div>
      <div className="mt-1 text-3xl font-semibold tabular-nums">{value}</div>
      <div className="mt-1 text-xs">
        <span className={ok ? "font-medium text-emerald-800" : "font-medium text-red-800"}>{ok ? "✓ meets" : "✗ misses"} target {target}</span>
        {note && <span className="text-slate-500"> · {note}</span>}
      </div>
    </div>
  );
}

function ChartTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const p = payload[0].payload;
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-xs shadow">
      <div className="font-semibold">{payload[0].name}</div>
      <div>Recall {pct(p.recall)} · Precision {pct(p.precision)}</div>
      {p.threshold !== undefined && <div className="text-slate-500">at score ≥ {p.threshold.toFixed(2)}</div>}
    </div>
  );
}

export default function EvaluationPage() {
  const { data, error, loading } = useAsync(api.evaluation, []);
  if (loading) return <Loading what="Loading evaluation" />;
  if (error) return <ErrorBox error={error} />;

  const main = data.models["LightGBM (calibrated)"];
  const base = data.models["Exact name baseline"];
  const curves = Object.entries(data.pr_curves).map(([k, c]) => ({
    key: k, ...SERIES[k], ap: c.ap, points: [...c.points].sort((a, b) => a.recall - b.recall),
  }));
  const kinds = { true_positive: "Sanctioned", homonym: "Innocent homonyms", clean: "Others" };

  return (
    <div className="space-y-8">
      <section className="max-w-3xl">
        <h1 className="text-2xl font-semibold tracking-tight">Does it work? Measured on a labeled test set</h1>
        <p className="mt-2 text-slate-600">
          {data.n_candidates} synthetic investigators: {data.truth.true_positive} real sanctioned people whose names were altered
          (typos, initials, swapped names, nicknames), {data.truth.homonym} innocent doctors who share a sanctioned person’s name,
          and {data.truth.clean} others. The model never saw this set during training.
        </p>
      </section>

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Tile label="Sanctioned people found (recall)" value={pct(main.recall_alert)} target="≥ 95%" ok={main.recall_alert >= 0.95}
              note={`exact-name check: ${pct(base.recall_alert)}`} />
        <Tile label="“Probable match” that are right (precision)" value={pct(main.precision_probable)} target="≥ 90%" ok={main.precision_probable >= 0.9}
              note={`exact-name check: ${pct(base.precision_probable)}`} />
        <Tile label="Innocent homonyms marked “probable”" value={main.homonyms_probable} target="0" ok={main.homonyms_probable === 0}
              note={`exact-name check: ${base.homonyms_probable}`} />
        <Tile label="Time to screen 300 investigators" value={`${main.seconds_for_300}s`} target="< 60s" ok={main.seconds_for_300 < 60} />
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        <section className="card p-6 lg:col-span-3">
          <h2 className="font-semibold">Precision vs recall at every score threshold</h2>
          <p className="mt-1 text-sm text-slate-600">Higher and further right is better. The black dot is a plain exact-name check.</p>
          <div className="mt-4 h-80">
            <ResponsiveContainer width="100%" height="100%">
              <ComposedChart margin={{ top: 10, right: 20, bottom: 25, left: 5 }}>
                <CartesianGrid stroke="#e2e8f0" strokeDasharray="3 3" />
                <XAxis type="number" dataKey="recall" domain={[0, 1]} tickFormatter={(v) => `${v * 100}%`} stroke="#64748b" fontSize={12}
                       label={{ value: "Recall: share of sanctioned people found", position: "insideBottom", offset: -15, fill: "#475569", fontSize: 12 }} />
                <YAxis type="number" dataKey="precision" domain={[0, 1]} tickFormatter={(v) => `${v * 100}%`} stroke="#64748b" fontSize={12}
                       label={{ value: "Precision", angle: -90, position: "insideLeft", fill: "#475569", fontSize: 12 }} />
                <Tooltip content={<ChartTooltip />} />
                <Legend verticalAlign="top" height={30} wrapperStyle={{ fontSize: 12 }} />
                {curves.map((c) => (
                  <Line key={c.key} data={c.points} dataKey="precision" name={`${c.name} (AP ${c.ap.toFixed(2)})`} stroke={c.color}
                        strokeWidth={2} dot={false} activeDot={{ r: 5 }} type="stepAfter" isAnimationActive={false} />
                ))}
                <Scatter data={[{ recall: base.recall_probable, precision: base.precision_probable }]} name="Exact-name check"
                         fill="#0f172a" shape="circle" isAnimationActive={false} />
              </ComposedChart>
            </ResponsiveContainer>
          </div>
        </section>

        <section className="card p-6 lg:col-span-2">
          <h2 className="font-semibold">Where each investigator landed</h2>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead><tr className="border-b border-slate-200">
                <th className="th">Ground truth</th>
                {["probable", "review", "cleared"].map((z) => (
                  <th key={z} className="px-2 py-2 text-left text-xs font-semibold text-slate-600">
                    <span aria-hidden="true">{ZONES[z].icon}</span> {ZONES[z].label}
                  </th>
                ))}
              </tr></thead>
              <tbody>
                {Object.entries(main.confusion).map(([k, row]) => (
                  <tr key={k} className="border-b border-slate-100">
                    <td className="td font-medium">{kinds[k]}</td>
                    {["probable", "review", "cleared"].map((z) => (
                      <td key={z} className={`td tabular-nums ${((k === "true_positive" && z === "cleared") || (k !== "true_positive" && z === "probable")) && row[z] > 0 ? "font-semibold text-red-800" : ""}`}>
                        {row[z]}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Homonyms in “To review” are expected: a shared name deserves a look, not an accusation.
            Thresholds: probable ≥ {data.thresholds.probable}, review ≥ {data.thresholds.review} (chosen on training data).
          </p>
        </section>
      </div>

      <section className="card p-6">
        <h2 className="font-semibold">Compared with simpler approaches</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead><tr className="border-b border-slate-200">
              <th className="th">Method</th><th className="th">Recall (alerts)</th><th className="th">Precision (probable)</th>
              <th className="th">Homonyms probable</th><th className="th">Homonyms alerted</th><th className="th">Others alerted</th>
            </tr></thead>
            <tbody>
              {Object.entries(data.models).map(([k, m]) => (
                <tr key={k} className="border-b border-slate-100">
                  <td className="td font-medium">{SERIES[k]?.name ?? k}</td>
                  <td className="td tabular-nums">{pct(m.recall_alert)}</td>
                  <td className="td tabular-nums">{pct(m.precision_probable)}</td>
                  <td className="td tabular-nums">{m.homonyms_probable}</td>
                  <td className="td tabular-nums">{m.homonyms_alert}</td>
                  <td className="td tabular-nums">{m.clean_alert}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {data.robustness?.length > 0 && (
        <section className="card p-6">
          <h2 className="font-semibold">Stability on fresh test sets</h2>
          <p className="mt-1 text-sm text-slate-600">Three more sets of 300, generated with new seeds and never inspected while building the rules.</p>
          <div className="mt-4 overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead><tr className="border-b border-slate-200">
                <th className="th">Seed</th><th className="th">Recall</th><th className="th">Precision (probable)</th>
                <th className="th">Homonyms probable</th><th className="th">Homonyms alerted</th><th className="th">Others alerted</th>
              </tr></thead>
              <tbody>
                {data.robustness.map((r) => (
                  <tr key={r.seed} className="border-b border-slate-100">
                    <td className="td">{r.seed}</td><td className="td tabular-nums">{pct(r.recall_alert)}</td>
                    <td className="td tabular-nums">{pct(r.precision_probable)}</td><td className="td tabular-nums">{r.homonyms_probable}</td>
                    <td className="td tabular-nums">{r.homonyms_alert}</td><td className="td tabular-nums">{r.clean_alert}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      <section className="card p-6 text-sm text-slate-700">
        <h2 className="font-semibold text-slate-900">How the model works, and its limits</h2>
        <ul className="mt-3 list-disc space-y-1.5 pl-5">
          <li>Candidate pairs are found by sound-alike surnames (Double Metaphone) and name prefixes, then scored by a gradient-boosted model on {data.model_card.features.length} features: name similarity, nickname and swapped-name detection, NPI, state, city, specialty, middle initial and how rare the surname is (US Census 2010).</li>
          <li>Scores are calibrated (isotonic) so 90% means roughly 9 in 10 such matches are the same person. Matching evidence can only raise the score (monotone constraints).</li>
          <li>Trained on {data.model_card.n_pairs.toLocaleString()} labeled pairs built from a separate pool of sanction records with a different random seed.</li>
          <li>Limits: the investigator side is synthetic; FDA records carry names only, so an FDA match rests on name evidence alone (full name, middle initial, surname rarity); only 10% of LEIE records list an NPI. A true namesake with the same middle initial, state and specialty cannot be told apart without an NPI.</li>
        </ul>
        <p className="mt-3 text-xs text-slate-500">Model {data.model_card.model_version} · lists {data.model_card.data_version}</p>
      </section>
    </div>
  );
}
