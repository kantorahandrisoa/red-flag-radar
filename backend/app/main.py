"""Red Flag Radar API.

The model proposes; a person decides. Every screening stores the model and
list versions it used, and every decision is appended to an audit trail.
"""
import csv
import io
import json
import sqlite3
import time
from contextlib import asynccontextmanager

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from pipeline import sources
from pipeline.features import FEATURES, normalize_candidate
from pipeline.matcher import Bundle, Matcher
from pipeline.paths import DB_PATH, MODELS, REPORTS, SYNTH

from .db import Candidate, Decision, Match, Screening, SessionLocal, init_db

MAX_UPLOAD_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000
KNOWN_COLUMNS = {"candidate_id", "first_name", "middle_name", "last_name", "full_name", "city", "state",
                 "specialty", "npi"}
MAX_MATCHES_PER_CANDIDATE = 5


class Engine:
    """Model, sanction lists and versions, loaded once at startup."""

    def load(self) -> None:
        with sqlite3.connect(DB_PATH) as con:
            self.sanctions = pd.read_sql("SELECT * FROM sanctions", con).fillna("")
            self.data_version = con.execute(
                "SELECT data_version FROM imports ORDER BY id DESC LIMIT 1").fetchone()[0]
        self.by_id = self.sanctions.set_index("sanction_id", drop=False)
        self.bundle = Bundle.load(MODELS / "model.pkl")
        self.matcher = Matcher(self.bundle, self.sanctions, sources.load_surname_freq())
        self.card = json.loads((MODELS / "model_card.json").read_text())

    @property
    def thresholds(self) -> dict:
        return self.bundle.thresholds


engine = Engine()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    init_db()
    engine.load()
    yield


app = FastAPI(title="Red Flag Radar", version="1.0", lifespan=lifespan)


def get_db():
    with SessionLocal() as db:
        yield db


# --- helpers ----------------------------------------------------------------

def parse_candidates(content: bytes) -> pd.DataFrame:
    """Validate an uploaded candidate list (F4): size, encoding, columns, row count."""
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_BYTES // 1024} KB).")
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "File must be UTF-8 encoded CSV.")
    try:
        df = pd.read_csv(io.StringIO(text), dtype=str, keep_default_na=False)
    except Exception:
        raise HTTPException(422, "Could not read the file as CSV.")
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    if not ({"last_name", "first_name"} <= set(df.columns) or "full_name" in df.columns):
        raise HTTPException(422, "CSV needs first_name and last_name columns (or full_name).")
    if df.empty:
        raise HTTPException(422, "The file has no rows.")
    if len(df) > MAX_ROWS:
        raise HTTPException(422, f"Too many rows (max {MAX_ROWS}).")
    df = df[[c for c in df.columns if c in KNOWN_COLUMNS]]
    for col in KNOWN_COLUMNS - set(df.columns):
        df[col] = ""
    df["candidate_id"] = [cid or f"ROW-{i + 1:04d}" for i, cid in enumerate(df["candidate_id"])]
    return df.map(lambda v: str(v).strip()[:200])


def run_screening(db: Session, df: pd.DataFrame, name: str, user: str) -> Screening:
    t0 = time.perf_counter()
    rows = df.to_dict("records")
    pairs = engine.matcher.score(rows, min_prob=0.05)
    screening = Screening(name=name[:200], created_by=user[:100], model_version=engine.bundle.version,
                          data_version=engine.data_version, thresholds=engine.thresholds)
    by_cand = {ci: g.head(MAX_MATCHES_PER_CANDIDATE) for ci, g in pairs.groupby("cand_idx")}
    for i, r in enumerate(rows):
        cand = Candidate(row=i + 1, external_id=r["candidate_id"], raw=r, normalized=normalize_candidate(r))
        for _, p in by_cand.get(i, pd.DataFrame()).iterrows():
            feats = {f: (None if p[f] != p[f] else float(p[f])) for f in FEATURES}
            cand.matches.append(Match(sanction_id=p["sanction_id"], score=round(float(p["prob"]), 4),
                                      zone=engine.bundle.zone(float(p["prob"])), features=feats))
        if cand.matches:
            cand.best_score = max(m.score for m in cand.matches)
            cand.zone = engine.bundle.zone(cand.best_score)
        screening.candidates.append(cand)
    screening.seconds = round(time.perf_counter() - t0, 2)
    db.add(screening)
    db.commit()
    return screening


def sanction_dict(sid: str) -> dict:
    if sid not in engine.by_id.index:
        return {"sanction_id": sid, "display_name": "(record no longer on the list)"}
    s = engine.by_id.loc[sid]
    return {k: s[k] for k in ("sanction_id", "source", "display_name", "first", "middle", "last", "city",
                              "state", "specialty", "specialty_raw", "npi", "sanction_type", "severity",
                              "sanction_date", "end_term", "source_url", "fetched_at", "import_version")}


def review_status(cand: Candidate, decisions: list[Decision]) -> str:
    if decisions:
        return decisions[-1].decision
    return "not_needed" if cand.zone == "cleared" else "pending"


def candidate_name(raw: dict) -> str:
    if raw.get("full_name"):
        return raw["full_name"]
    return " ".join(x for x in (raw.get("first_name"), raw.get("middle_name"), raw.get("last_name")) if x)


def decisions_for(db: Session, candidate_ids: list[int]) -> dict[int, list[Decision]]:
    out: dict[int, list[Decision]] = {}
    if not candidate_ids:
        return out
    for d in db.scalars(select(Decision).where(Decision.candidate_id.in_(candidate_ids)).order_by(Decision.id)):
        out.setdefault(d.candidate_id, []).append(d)
    return out


def summary(s: Screening) -> dict:
    zones = {"probable": 0, "review": 0, "cleared": 0}
    for c in s.candidates:
        zones[c.zone] += 1
    return {"id": s.id, "name": s.name, "created_at": s.created_at, "created_by": s.created_by,
            "model_version": s.model_version, "data_version": s.data_version, "thresholds": s.thresholds,
            "seconds": s.seconds, "n_candidates": len(s.candidates), "zones": zones}


def get_screening(db: Session, sid: int) -> Screening:
    s = db.scalar(select(Screening).where(Screening.id == sid)
                  .options(selectinload(Screening.candidates).selectinload(Candidate.matches)))
    if not s:
        raise HTTPException(404, "Screening not found.")
    return s


def label(code: str) -> str:
    """FAMILY_MEDICINE -> Family Medicine, for display only."""
    return code.replace("_", " ").title() if code and "_" in code else code


def compare_fields(norm: dict, s: dict) -> list[dict]:
    def status(a, b):
        if not a or not b:
            return "missing"
        if a == b:
            return "match"
        return "partial" if set(a.split()) & set(b.split()) else "differs"
    middle = status(norm["middle"][:1], s.get("middle", "")[:1])
    return [
        {"field": "First name", "candidate": norm["first"], "record": s.get("first", ""),
         "status": status(norm["first"], s.get("first", ""))},
        {"field": "Middle", "candidate": norm["middle"], "record": s.get("middle", ""), "status": middle},
        {"field": "Last name", "candidate": norm["last"], "record": s.get("last", ""),
         "status": status(norm["last"], s.get("last", ""))},
        {"field": "City", "candidate": norm["city"], "record": s.get("city", ""),
         "status": status(norm["city"], s.get("city", ""))},
        {"field": "State", "candidate": norm["state"], "record": s.get("state", ""),
         "status": status(norm["state"], s.get("state", ""))},
        {"field": "Specialty", "candidate": label(norm["specialty"]), "record": label(s.get("specialty", "")),
         "status": status(norm["specialty"], s.get("specialty", ""))},
        {"field": "NPI", "candidate": norm["npi"], "record": s.get("npi", ""),
         "status": status(norm["npi"], s.get("npi", ""))},
    ]


def safe_cell(v) -> str:
    """Neutralize spreadsheet formulas in exported cells (CSV injection)."""
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


# --- routes -----------------------------------------------------------------

@app.get("/api/health")
def health():
    counts = engine.sanctions.groupby("source").size().to_dict()
    return {"status": "ok", "model_version": engine.bundle.version, "data_version": engine.data_version,
            "thresholds": engine.thresholds, "sanction_records": counts}


@app.get("/api/demo.csv")
def demo_csv():
    return FileResponse(SYNTH / "candidates_demo.csv", media_type="text/csv", filename="candidates_demo.csv")


@app.post("/api/screenings")
async def create_screening(file: UploadFile = File(...), name: str = Form(""), user: str = Form(""),
                           db: Session = Depends(get_db)):
    df = parse_candidates(await file.read(MAX_UPLOAD_BYTES + 1))
    s = run_screening(db, df, name or file.filename or "Screening", user)
    return summary(get_screening(db, s.id))


@app.post("/api/screenings/demo")
def create_demo_screening(user: str = Form(""), db: Session = Depends(get_db)):
    df = parse_candidates((SYNTH / "candidates_demo.csv").read_bytes())
    s = run_screening(db, df, "Demo — 300 synthetic investigators", user)
    return summary(get_screening(db, s.id))


@app.get("/api/screenings")
def list_screenings(db: Session = Depends(get_db)):
    ss = db.scalars(select(Screening).order_by(Screening.id.desc())
                    .options(selectinload(Screening.candidates))).all()
    return [summary(s) for s in ss]


@app.get("/api/screenings/{sid}")
def screening_detail(sid: int, db: Session = Depends(get_db)):
    s = get_screening(db, sid)
    decs = decisions_for(db, [c.id for c in s.candidates])
    rows = []
    for c in s.candidates:
        best = c.matches[0] if c.matches else None
        rec = sanction_dict(best.sanction_id) if best and c.zone != "cleared" else None
        rows.append({
            "id": c.id, "row": c.row, "candidate_id": c.external_id, "name": candidate_name(c.raw),
            "city": c.raw.get("city", ""), "state": c.raw.get("state", ""),
            "specialty": c.raw.get("specialty", ""), "npi": c.raw.get("npi", ""),
            "score": c.best_score, "zone": c.zone,
            "best_match": {"sanction_id": rec["sanction_id"], "name": rec["display_name"],
                           "source": rec.get("source", ""), "severity": rec.get("severity", ""),
                           "sanction_type": rec.get("sanction_type", "")} if rec else None,
            "review_status": review_status(c, decs.get(c.id, [])),
        })
    return {**summary(s), "candidates": rows}


@app.get("/api/candidates/{cid}")
def candidate_detail(cid: int, db: Session = Depends(get_db)):
    c = db.get(Candidate, cid)
    if not c:
        raise HTTPException(404, "Candidate not found.")
    s = c.screening
    decs = decisions_for(db, [c.id]).get(c.id, [])
    matches = []
    for m in c.matches:
        if m.zone == "cleared" and matches:
            continue  # show the best match always, others only when they matter
        rec = sanction_dict(m.sanction_id)
        feats = {k: (float("nan") if v is None else v) for k, v in m.features.items()}
        hint = None
        if not c.normalized.get("npi") and rec.get("npi"):
            hint = "The sanction record has an NPI: ask the site for the investigator's NPI to settle this."
        matches.append({"match_id": m.id, "score": m.score, "zone": m.zone, "record": rec,
                        "fields": compare_fields(c.normalized, rec),
                        "reasons": engine.matcher.explain(feats), "hint": hint})
    return {
        "id": c.id, "screening_id": s.id, "screening_name": s.name, "candidate_id": c.external_id,
        "name": candidate_name(c.raw), "raw": c.raw, "normalized": c.normalized,
        "score": c.best_score, "zone": c.zone, "review_status": review_status(c, decs),
        "model_version": s.model_version, "data_version": s.data_version, "thresholds": s.thresholds,
        "matches": matches,
        "decisions": [{"decision": d.decision, "comment": d.comment, "reviewer": d.reviewer,
                       "decided_at": d.decided_at, "sanction_id": d.sanction_id} for d in decs],
    }


class DecisionIn(BaseModel):
    decision: str = Field(pattern="^(confirmed|dismissed)$")
    comment: str = Field(min_length=5, max_length=2000)
    reviewer: str = Field(min_length=2, max_length=100)
    sanction_id: str = ""


@app.post("/api/candidates/{cid}/decision")
def decide(cid: int, body: DecisionIn, db: Session = Depends(get_db)):
    c = db.get(Candidate, cid)
    if not c:
        raise HTTPException(404, "Candidate not found.")
    sid = body.sanction_id or (c.matches[0].sanction_id if c.matches else "")
    score = next((m.score for m in c.matches if m.sanction_id == sid), 0.0)
    d = Decision(candidate_id=c.id, sanction_id=sid, decision=body.decision, comment=body.comment.strip(),
                 reviewer=body.reviewer.strip(), score=score, model_version=c.screening.model_version,
                 data_version=c.screening.data_version)
    db.add(d)
    db.commit()
    return {"ok": True, "decided_at": d.decided_at}


@app.get("/api/audit")
def audit(screening_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Decision, Candidate, Screening).join(Candidate, Decision.candidate_id == Candidate.id) \
        .join(Screening, Candidate.screening_id == Screening.id).order_by(Decision.id.desc())
    if screening_id:
        q = q.where(Screening.id == screening_id)
    return [{"decided_at": d.decided_at, "reviewer": d.reviewer, "decision": d.decision, "comment": d.comment,
             "candidate": candidate_name(c.raw), "candidate_id": c.id, "screening": s.name,
             "screening_id": s.id, "sanction_id": d.sanction_id, "score": d.score,
             "model_version": d.model_version, "data_version": d.data_version}
            for d, c, s in db.execute(q)]


@app.get("/api/screenings/{sid}/export.csv")
def export_csv(sid: int, db: Session = Depends(get_db)):
    s = get_screening(db, sid)
    decs = decisions_for(db, [c.id for c in s.candidates])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["candidate_id", "name", "city", "state", "specialty", "npi", "zone", "score",
                "match_source", "match_name", "sanction_type", "sanction_date", "source_url",
                "review_status", "reviewer", "comment", "decided_at", "model_version", "data_version"])
    for c in s.candidates:
        best = c.matches[0] if c.matches and c.zone != "cleared" else None
        rec = sanction_dict(best.sanction_id) if best else {}
        last = decs.get(c.id, [None])[-1]
        w.writerow([safe_cell(v) for v in (
            c.external_id, candidate_name(c.raw), c.raw.get("city"), c.raw.get("state"), c.raw.get("specialty"),
            c.raw.get("npi"), c.zone, f"{c.best_score:.3f}", rec.get("source"), rec.get("display_name"),
            rec.get("sanction_type"), rec.get("sanction_date"), rec.get("source_url"),
            review_status(c, decs.get(c.id, [])), last and last.reviewer, last and last.comment,
            last and last.decided_at, s.model_version, s.data_version)])
    return StreamingResponse(iter([buf.getvalue()]), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="screening-{sid}.csv"'})


@app.get("/api/screenings/{sid}/export.pdf")
def export_pdf(sid: int, db: Session = Depends(get_db)):
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    s = get_screening(db, sid)
    decs = decisions_for(db, [c.id for c in s.candidates])
    sm = summary(s)
    styles = getSampleStyleSheet()
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=landscape(A4), title=f"Red Flag Radar — {s.name}")
    story = [Paragraph(f"Red Flag Radar — screening report: {s.name}", styles["Title"]),
             Paragraph(f"Run {s.created_at} · model {s.model_version} · lists {s.data_version} · "
                       f"{sm['n_candidates']} investigators: {sm['zones']['probable']} probable match, "
                       f"{sm['zones']['review']} to review, {sm['zones']['cleared']} cleared.", styles["Normal"]),
             Paragraph("A match is a lead to verify, never a verdict. Decisions below were made by the "
                       "named reviewers.", styles["Italic"]), Spacer(1, 10)]
    data = [["Investigator", "State", "Status", "Score", "Possible record", "Source", "Review", "Reviewer / comment"]]
    for c in sorted(s.candidates, key=lambda c: -c.best_score):
        if c.zone == "cleared":
            continue
        rec = sanction_dict(c.matches[0].sanction_id)
        last = decs.get(c.id, [None])[-1]
        data.append([candidate_name(c.raw)[:40], c.raw.get("state", ""),
                     {"probable": "Probable match", "review": "To review"}[c.zone], f"{c.best_score:.2f}",
                     rec.get("display_name", "")[:35], rec.get("source", ""), review_status(c, decs.get(c.id, [])),
                     Paragraph(f"{last.reviewer}: {last.comment}" if last else "—", styles["BodyText"])])
    t = Table(data, repeatRows=1, colWidths=[120, 40, 85, 40, 120, 105, 70, 200])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2937")),
                           ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("FONTSIZE", (0, 0), (-1, -1), 8),
                           ("GRID", (0, 0), (-1, -1), 0.25, colors.grey), ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(t)
    doc.build(story)
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="screening-{sid}.pdf"'})


@app.get("/api/evaluation")
def evaluation():
    path = REPORTS / "eval.json"
    if not path.exists():
        raise HTTPException(404, "Run `make eval` first.")
    return {**json.loads(path.read_text()), "model_card": engine.card}
