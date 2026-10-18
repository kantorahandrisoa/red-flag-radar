import { createContext, useContext, useEffect, useState } from "react";

export const ZONES = {
  probable: { label: "Probable match", icon: "▲", chip: "bg-red-50 text-red-800 ring-red-200", bar: "bg-red-600" },
  review: { label: "To review", icon: "●", chip: "bg-amber-50 text-amber-900 ring-amber-300", bar: "bg-amber-500" },
  cleared: { label: "Cleared", icon: "○", chip: "bg-slate-100 text-slate-600 ring-slate-200", bar: "bg-slate-400" },
};

export const REVIEW = {
  pending: { label: "Awaiting review", cls: "text-slate-700" },
  confirmed: { label: "Confirmed by reviewer", cls: "text-red-800 font-medium" },
  dismissed: { label: "Dismissed by reviewer", cls: "text-emerald-800 font-medium" },
  not_needed: { label: "—", cls: "text-slate-400" },
};

/** Status is always written out; color only reinforces it. */
export function ZoneChip({ zone, size = "sm" }) {
  const z = ZONES[zone] ?? ZONES.cleared;
  const pad = size === "lg" ? "px-3 py-1 text-sm" : "px-2 py-0.5 text-xs";
  return (
    <span className={`inline-flex items-center gap-1.5 whitespace-nowrap rounded-full font-medium ring-1 ring-inset ${pad} ${z.chip}`}>
      <span aria-hidden="true">{z.icon}</span>
      {z.label}
    </span>
  );
}

/** Calibrated probabilities are never certainties: show >99% rather than 100%. */
export const fmtScore = (score) => (score >= 0.995 ? ">99%" : `${Math.round(score * 100)}%`);

export function ScoreBar({ score, zone }) {
  const z = ZONES[zone] ?? ZONES.cleared;
  return (
    <div className="flex items-center gap-2" title={`Match probability ${(score * 100).toFixed(1)}%`}>
      <div className="h-1.5 w-20 overflow-hidden rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${z.bar}`} style={{ width: `${Math.max(score * 100, 2)}%` }} />
      </div>
      <span className="tabular-nums text-sm text-slate-700">{fmtScore(score)}</span>
    </div>
  );
}

export function Gauge({ score, zone, thresholds }) {
  const z = ZONES[zone] ?? ZONES.cleared;
  const pct = Math.round(score * 100);
  return (
    <div>
      <div className="flex items-baseline gap-2">
        <span className="text-4xl font-semibold tabular-nums">{fmtScore(score)}</span>
        <span className="text-sm text-slate-500">estimated probability of same person</span>
      </div>
      <div className="relative mt-3 h-2.5 rounded-full bg-slate-200">
        <div className={`h-full rounded-full ${z.bar}`} style={{ width: `${Math.max(pct, 1)}%` }} />
        {thresholds &&
          ["review", "probable"].map((k) => (
            <div key={k} className="absolute -top-1 h-4.5 w-0.5 bg-slate-700" style={{ left: `${thresholds[k] * 100}%`, height: 18 }}
                 title={`${ZONES[k].label} from ${Math.round(thresholds[k] * 100)}%`} />
          ))}
      </div>
      {thresholds && (
        <div className="relative mt-1 h-4 text-[11px] text-slate-500">
          <span className="absolute -translate-x-1/2" style={{ left: `${thresholds.review * 100}%` }}>review {Math.round(thresholds.review * 100)}%</span>
          <span className="absolute -translate-x-1/2" style={{ left: `${thresholds.probable * 100}%` }}>probable {Math.round(thresholds.probable * 100)}%</span>
        </div>
      )}
    </div>
  );
}

export function Loading({ what = "Loading" }) {
  return <div className="py-16 text-center text-sm text-slate-500">{what}…</div>;
}

export function ErrorBox({ error }) {
  if (!error) return null;
  return <div role="alert" className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">{String(error.message ?? error)}</div>;
}

const ReviewerCtx = createContext(["", () => {}]);

export function ReviewerProvider({ children }) {
  const [name, setName] = useState(() => {
    try { return localStorage.getItem("rfr-reviewer") ?? ""; } catch { return ""; }
  });
  useEffect(() => {
    try { localStorage.setItem("rfr-reviewer", name); } catch {}
  }, [name]);
  return <ReviewerCtx.Provider value={[name, setName]}>{children}</ReviewerCtx.Provider>;
}

export const useReviewer = () => useContext(ReviewerCtx);

export function useAsync(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const reload = () => {
    setState((s) => ({ ...s, loading: true }));
    fn().then((data) => setState({ data, error: null, loading: false }),
              (error) => setState({ data: null, error, loading: false }));
  };
  useEffect(reload, deps);
  return { ...state, reload };
}
