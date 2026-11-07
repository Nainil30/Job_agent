"""Static, dependency-free HTML dashboard (site/index.html), deployable to GitHub Pages for free."""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

from loguru import logger

from src.engine.models import JobRecord
from src.storage.health import SourceHealth
from src.utils import age_days, iso_now


def build_payload(records: list[JobRecord], health: list[SourceHealth], last_seen: dict[str, str]) -> dict:
    jobs = []
    for r in records:
        ev = r.evaluation
        first_seen = r.created_at[:10]
        jobs.append(
            {
                "id": r.hash_id[:10],
                "company": r.raw.company,
                "title": r.raw.title,
                "location": r.raw.location,
                "url": r.raw.url,
                "source": r.raw.source_ats,
                "score": r.score,
                "heuristic": ev.heuristic_score if ev else 0,
                "tier": ev.tier if ev else "Unscored",
                "scorer": ev.evaluator if ev else "",
                "summary": ev.summary if ev else "",
                "strengths": ev.key_alignment_reasons if ev else [],
                "gaps": ev.gap_analysis if ev else [],
                "bullets": ev.tailored_resume_bullets if ev else [],
                "posted": r.raw.posted_at or "",
                "first_seen": first_seen,
                "last_seen": last_seen.get(r.hash_id, first_seen),
                "is_new": (age_days(first_seen) or 0) <= 7,
                "status": r.status,
            }
        )
    jobs.sort(key=lambda j: j["score"], reverse=True)
    return {"generated_at": iso_now(), "jobs": jobs, "health": [asdict(h) for h in health]}


def write_dashboard(
    site_dir: str | Path, records: list[JobRecord], health: list[SourceHealth], last_seen: dict[str, str]
) -> Path:
    site = Path(site_dir)
    site.mkdir(parents=True, exist_ok=True)
    payload = build_payload(records, health, last_seen)
    data = json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
    (site / "jobs.json").write_text(json.dumps(payload, indent=1, ensure_ascii=False), encoding="utf-8")
    out = site / "index.html"
    out.write_text(TEMPLATE.replace("/*__DATA__*/null", data), encoding="utf-8")
    logger.info(f"Dashboard written: {out} ({len(records)} jobs)")
    return out


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Job Scout</title>
<style>
:root{--bg:#f7f7f5;--card:#fff;--ink:#1d1d1f;--muted:#6b6b70;--line:#e4e4e0;--accent:#2f6fde;--t1:#1a7f4b;--t2:#b26b00;--skip:#8a8a8f;--chip:#efefeb}
@media (prefers-color-scheme:dark){:root{--bg:#121214;--card:#1b1b1f;--ink:#ececef;--muted:#9a9aa2;--line:#2c2c32;--accent:#6c9cff;--t1:#3ccf86;--t2:#f0a83a;--skip:#77777f;--chip:#26262c}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
header{padding:24px 16px 8px;max-width:1200px;margin:auto}h1{margin:0;font-size:22px}header p{margin:4px 0 0;color:var(--muted)}
main{max-width:1200px;margin:auto;padding:0 16px 48px}
.stats{display:flex;gap:12px;flex-wrap:wrap;margin:16px 0}.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:120px}
.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
.controls{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:8px 0 12px}
input,select{background:var(--card);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:7px 10px;font:inherit}
input[type=search]{flex:1;min-width:200px}label{color:var(--muted);display:flex;gap:6px;align-items:center}
.job{background:var(--card);border:1px solid var(--line);border-radius:10px;margin:8px 0;overflow:hidden}
.row{display:grid;grid-template-columns:56px 1fr auto;gap:12px;align-items:center;padding:10px 14px;cursor:pointer}
.score{font-weight:700;font-size:18px;text-align:center;border-radius:8px;padding:4px 0}
.t1{color:var(--t1)}.t2{color:var(--t2)}.sk{color:var(--skip)}
.title{font-weight:600}.meta{color:var(--muted);font-size:12.5px}
.chip{display:inline-block;background:var(--chip);border-radius:999px;padding:1px 8px;font-size:11.5px;margin-left:6px;color:var(--muted)}
.new{background:var(--accent);color:#fff}
a.open{color:var(--accent);text-decoration:none;font-weight:600;white-space:nowrap}
.detail{display:none;padding:0 14px 14px 82px;border-top:1px solid var(--line)}.job.expanded .detail{display:block}
.detail h4{margin:12px 0 4px;font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}.detail ul{margin:0;padding-left:18px}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
td,th{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;font-size:13px}th{color:var(--muted);font-weight:600}
h2{font-size:16px;margin:28px 0 8px}.empty{color:var(--muted);padding:24px;text-align:center}
@media (max-width:640px){.row{grid-template-columns:44px 1fr}.row a.open{grid-column:2}.detail{padding-left:14px}.hide-sm{display:none}}
</style>
</head>
<body>
<header><h1>Job Scout</h1><p id="sub"></p></header>
<main>
<div class="stats" id="stats"></div>
<div class="controls">
  <input type="search" id="q" placeholder="Search title, company, location…">
  <select id="company"><option value="">All companies</option></select>
  <select id="tier"><option value="">All tiers</option><option>Tier 1: Apply Now</option><option>Tier 2: Review</option><option>Skip</option></select>
  <label>Min score <input type="number" id="min" value="60" min="0" max="100" style="width:64px"></label>
  <label><input type="checkbox" id="onlynew"> New (7d)</label>
</div>
<div id="list"></div>
<h2>Source health</h2>
<table><thead><tr><th>Source</th><th class="hide-sm">Tier</th><th>Status</th><th>Listings</th><th class="hide-sm">Kept</th><th class="hide-sm">Last success</th></tr></thead><tbody id="health"></tbody></table>
</main>
<script>
const DATA = /*__DATA__*/null;
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const cls = t => t.startsWith("Tier 1") ? "t1" : t.startsWith("Tier 2") ? "t2" : "sk";
const jobs = DATA.jobs;
$("#sub").textContent = `Updated ${new Date(DATA.generated_at).toLocaleString()} · finds and ranks roles — never auto-applies`;
[...new Set(jobs.map(j => j.company))].sort().forEach(c => $("#company").insertAdjacentHTML("beforeend", `<option>${esc(c)}</option>`));
const stat = (n, l) => `<div class="stat"><b>${n}</b><span>${l}</span></div>`;
$("#stats").innerHTML = stat(jobs.length, "open roles tracked") + stat(jobs.filter(j => j.tier.startsWith("Tier 1")).length, "apply now")
  + stat(jobs.filter(j => j.tier.startsWith("Tier 2")).length, "to review") + stat(jobs.filter(j => j.is_new).length, "new this week")
  + stat(new Set(jobs.map(j => j.company)).size, "companies");
const list = arr => arr && arr.length ? `<ul>${arr.map(x => `<li>${esc(x)}</li>`).join("")}</ul>` : "<p class='meta'>—</p>";
function render(){
  const q = $("#q").value.toLowerCase(), co = $("#company").value, tier = $("#tier").value, min = +$("#min").value || 0, nw = $("#onlynew").checked;
  const rows = jobs.filter(j => j.score >= min && (!co || j.company === co) && (!tier || j.tier === tier) && (!nw || j.is_new)
    && (!q || `${j.title} ${j.company} ${j.location}`.toLowerCase().includes(q)));
  $("#list").innerHTML = rows.length ? rows.map(j => `
   <div class="job"><div class="row">
     <div class="score ${cls(j.tier)}">${j.score}</div>
     <div><div class="title">${esc(j.title)}${j.is_new ? '<span class="chip new">new</span>' : ""}${j.status === "APPLIED" ? '<span class="chip">applied</span>' : ""}</div>
     <div class="meta">${esc(j.company)} · ${esc(j.location || "—")} · posted ${esc(j.posted || "?")} <span class="chip">${esc(j.source)}</span></div></div>
     <a class="open" href="${esc(j.url)}" target="_blank" rel="noopener">Open ↗</a></div>
     <div class="detail">${j.summary ? `<p>${esc(j.summary)}</p>` : ""}
       <h4>Why it fits</h4>${list(j.strengths)}<h4>Gaps to address</h4>${list(j.gaps)}
       ${j.bullets.length ? `<h4>Resume bullet ideas</h4>${list(j.bullets)}` : ""}
       <p class="meta">Scored by ${esc(j.scorer || "—")} · keyword score ${j.heuristic} · first seen ${esc(j.first_seen)} · last seen ${esc(j.last_seen)}</p></div></div>`).join("")
    : `<div class="empty">No roles match these filters.</div>`;
  document.querySelectorAll(".row").forEach(r => r.addEventListener("click", e => { if (e.target.tagName !== "A") r.parentElement.classList.toggle("expanded"); }));
}
["#q","#company","#tier","#min","#onlynew"].forEach(s => $(s).addEventListener("input", render));
const icon = {ok:"🟢",partial:"🟡",empty:"🟠",error:"🔴",skipped:"⚪"};
$("#health").innerHTML = DATA.health.map(h => `<tr><td>${esc(h.name)}</td><td class="hide-sm">${esc(h.tier)}</td><td title="${esc((h.errors||[]).join("\n"))}">${icon[h.status]||""} ${esc(h.status)}</td><td>${h.fetched}</td><td class="hide-sm">${h.kept}</td><td class="hide-sm">${esc((h.last_success||"never").slice(0,10))}</td></tr>`).join("");
render();
</script>
</body>
</html>
"""
