async function handle(res) {
  if (!res.ok) {
    let msg = `${res.status} ${res.statusText}`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") msg = body.detail;
      else if (Array.isArray(body.detail)) msg = body.detail.map((d) => `${d.loc?.at(-1)}: ${d.msg}`).join("; ");
    } catch {}
    throw new Error(msg);
  }
  return res.json();
}

export const api = {
  health: () => fetch("/api/health").then(handle),
  screenings: () => fetch("/api/screenings").then(handle),
  screening: (id) => fetch(`/api/screenings/${id}`).then(handle),
  candidate: (id) => fetch(`/api/candidates/${id}`).then(handle),
  evaluation: () => fetch("/api/evaluation").then(handle),
  audit: (sid) => fetch(`/api/audit${sid ? `?screening_id=${sid}` : ""}`).then(handle),
  upload: (file, name, user) => {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("name", name);
    fd.append("user", user);
    return fetch("/api/screenings", { method: "POST", body: fd }).then(handle);
  },
  demo: (user) => {
    const fd = new FormData();
    fd.append("user", user);
    return fetch("/api/screenings/demo", { method: "POST", body: fd }).then(handle);
  },
  decide: (cid, body) =>
    fetch(`/api/candidates/${cid}/decision`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }).then(handle),
};
