"""End-to-end API flow on a copy of the database."""
from pipeline.paths import SYNTH


def test_health(client):
    h = client.get("/api/health").json()
    assert h["status"] == "ok" and h["sanction_records"]["OIG LEIE"] > 1000


def test_rejects_bad_csv(client):
    r = client.post("/api/screenings", files={"file": ("x.csv", b"foo,bar\n1,2\n", "text/csv")})
    assert r.status_code == 422 and "first_name" in r.json()["detail"]


def test_full_flow(client):
    content = (SYNTH / "candidates_demo.csv").read_bytes()
    s = client.post("/api/screenings", files={"file": ("demo.csv", content, "text/csv")},
                    data={"name": "test", "user": "tester"}).json()
    assert s["n_candidates"] == 300 and s["seconds"] < 60
    assert s["zones"]["probable"] > 0

    detail = client.get(f"/api/screenings/{s['id']}").json()
    alert = next(c for c in detail["candidates"] if c["zone"] == "probable")
    assert alert["best_match"]["source"] and alert["review_status"] == "pending"

    cand = client.get(f"/api/candidates/{alert['id']}").json()
    top = cand["matches"][0]
    assert top["record"]["source_url"].startswith("https://")
    assert 1 <= len(top["reasons"]) <= 5 and all(r["text"] for r in top["reasons"])

    bad = client.post(f"/api/candidates/{alert['id']}/decision",
                      json={"decision": "confirmed", "comment": "", "reviewer": "QA"})
    assert bad.status_code == 422  # a comment is mandatory
    ok = client.post(f"/api/candidates/{alert['id']}/decision",
                     json={"decision": "dismissed", "comment": "Different NPI confirmed by site", "reviewer": "QA"})
    assert ok.status_code == 200

    log = client.get("/api/audit", params={"screening_id": s["id"]}).json()
    assert log[0]["reviewer"] == "QA" and log[0]["model_version"] and log[0]["data_version"]

    csv_text = client.get(f"/api/screenings/{s['id']}/export.csv").text
    assert "dismissed" in csv_text and csv_text.count("\n") == 301
    pdf = client.get(f"/api/screenings/{s['id']}/export.pdf")
    assert pdf.content[:4] == b"%PDF"
