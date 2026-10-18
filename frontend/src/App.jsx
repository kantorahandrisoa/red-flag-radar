import { NavLink, Route, Routes } from "react-router-dom";
import { ReviewerProvider, useReviewer } from "./components.jsx";
import ImportPage from "./pages/ImportPage.jsx";
import ResultsPage from "./pages/ResultsPage.jsx";
import AlertPage from "./pages/AlertPage.jsx";
import EvaluationPage from "./pages/EvaluationPage.jsx";
import AuditPage from "./pages/AuditPage.jsx";

function Logo() {
  return (
    <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="none" stroke="#b91c1c" strokeWidth="3" />
      <circle cx="16" cy="16" r="7" fill="none" stroke="#b91c1c" strokeWidth="2.5" />
      <path d="M16 16 L27 8" stroke="#b91c1c" strokeWidth="3" strokeLinecap="round" />
      <circle cx="16" cy="16" r="2.5" fill="#b91c1c" />
    </svg>
  );
}

function ReviewerBox() {
  const [name, setName] = useReviewer();
  return (
    <label className="flex items-center gap-2 text-sm text-slate-600">
      <span className="hidden sm:inline">Reviewing as</span>
      <input className="input w-40 py-1.5" placeholder="Your name" value={name} onChange={(e) => setName(e.target.value)} />
    </label>
  );
}

const link = ({ isActive }) =>
  `rounded-md px-3 py-1.5 text-sm font-medium ${isActive ? "bg-slate-900 text-white" : "text-slate-700 hover:bg-slate-100"}`;

export default function App() {
  return (
    <ReviewerProvider>
      <header className="sticky top-0 z-10 border-b border-slate-200 bg-white/90 backdrop-blur">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-x-6 gap-y-2 px-4 py-3">
          <NavLink to="/" className="flex items-center gap-2">
            <Logo />
            <span className="text-lg font-semibold tracking-tight">Red Flag Radar</span>
          </NavLink>
          <nav className="flex flex-wrap gap-1">
            <NavLink to="/" end className={link}>Screen</NavLink>
            <NavLink to="/evaluation" className={link}>Evaluation</NavLink>
            <NavLink to="/audit" className={link}>Audit log</NavLink>
          </nav>
          <div className="ml-auto"><ReviewerBox /></div>
        </div>
      </header>
      <main className="mx-auto max-w-7xl px-4 py-8">
        <Routes>
          <Route path="/" element={<ImportPage />} />
          <Route path="/screenings/:id" element={<ResultsPage />} />
          <Route path="/candidates/:id" element={<AlertPage />} />
          <Route path="/evaluation" element={<EvaluationPage />} />
          <Route path="/audit" element={<AuditPage />} />
        </Routes>
      </main>
      <footer className="mx-auto max-w-7xl px-4 pb-10 text-xs text-slate-500">
        A match is a lead to verify, never a verdict. Public sources: OIG LEIE and FDA Debarment List.
        Investigator data in the demo is synthetic.
      </footer>
    </ReviewerProvider>
  );
}
