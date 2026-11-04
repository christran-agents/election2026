#!/usr/bin/env python3
"""Fetch 2026 US general election results (NYT public results JSON) -> data.json.
Re-runnable; ~30-60s. Never invents numbers: missing data stays null."""
import os
import json, sys, time, datetime as dt, urllib.request, concurrent.futures as cf
B = "https://static01.nyt.com/elections-assets/pages/data/2026-11-03/"
UA = {"User-Agent": "Mozilla/5.0"}
STATES = ["alabama","alaska","arizona","arkansas","california","colorado","connecticut","delaware","florida","georgia","hawaii","idaho","illinois","indiana","iowa","kansas","kentucky","louisiana","maine","maryland","massachusetts","michigan","minnesota","mississippi","missouri","montana","nebraska","nevada","new-hampshire","new-jersey","new-mexico","new-york","north-carolina","north-dakota","ohio","oklahoma","oregon","pennsylvania","rhode-island","south-carolina","south-dakota","tennessee","texas","utah","vermont","virginia","washington","west-virginia","wisconsin","wyoming"]
SKIP_OFFICES = {"U.S. House","U.S. Senate","Governor","State House","State Senate","State Assembly","House of Delegates"}
EXIT_URLS = [B+"results-exit-polls.json", "https://politics.api.cnn.io/results/national-exit-polls/2026-HG.json"]
SGT = dt.timezone(dt.timedelta(hours=8))

def get(url, tries=2):
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as r:
                return json.load(r)
        except Exception as e:
            err = e
            time.sleep(1)
    print(f"WARN {url}: {err}", file=sys.stderr); return None

def pkey(p):
    return {"DEM": "D", "GOP": "R"}.get(p, "O")

def project(cands, eevp, total, expected):
    """SuperChief's estimate. Final margin = counted share c * current margin + (1-c) * remaining margin,
    remaining margin assumed within current margin +/- 20 pts (range) . Returns None with no votes."""
    if not total or len(cands) < 1 or eevp is None:
        return None
    s = sorted(cands, key=lambda c: -(c["votes"] or 0))
    m = (s[0]["pct"] or 0) - (s[1]["pct"] or 0) if len(s) > 1 else 100.0
    c = min(max(eevp / 100.0, 0), 1)
    half = 20.0 * (1 - c)
    lo, hi = m - half, m + half
    if eevp < 10: conf = "very low"
    elif lo > 0 and m >= 10: conf = "high"
    elif lo > 0: conf = "medium"
    else: conf = "low"
    return {"leader": s[0]["name"], "party": s[0]["party"], "margin": round(m, 1), "lo": round(lo, 1), "hi": round(hi, 1), "conf": conf}

def norm(r, page_url, fetched):
    tru = r.get("top_reporting_unit") or {}
    meta = r.get("candidate_metadata") or {}
    total = tru.get("total_votes") or 0
    cands = []
    for c in tru.get("candidates") or []:
        m = meta.get(c["nyt_id"], {})
        v = (c.get("votes") or {}).get("total")
        cands.append({"name": " ".join(x for x in [m.get("first_name"), m.get("last_name")] if x) or c["nyt_id"],
                      "party": pkey((m.get("party") or {}).get("nyt_id")), "inc": bool(m.get("incumbent")),
                      "votes": v, "pct": round(100.0 * v / total, 1) if total and v is not None else None})
    cands.sort(key=lambda c: -(c["votes"] or 0))
    out = r.get("outcome") or {}
    won = out.get("won") or []
    called = r.get("race_call_status") == "called" and bool(won)
    wparty = None
    if won:
        wm = meta.get(won[0], {}); wparty = pkey((wm.get("party") or {}).get("nyt_id"))
    inc = [c for c in cands if c["inc"]]
    eevp = tru.get("eevp")
    rec = {"id": r["nyt_id"], "state": tru.get("state_postal") or r["nyt_id"][:2], "office": r.get("office"),
           "seat": r.get("seat") or "", "rating": r.get("general_rating") or r.get("rating"),
           "uncontested": r.get("uncontested"), "cands": cands[:4], "totalVotes": total or None,
           "eevp": eevp, "called": called, "calledBy": [x.upper() for x in out.get("called_by") or []] if called else [],
           "winner": (meta.get(won[0], {}).get("last_name") if won else None), "winnerParty": wparty,
           "flip": bool(out.get("gained")) if called else None, "incParty": inc[0]["party"] if inc else None,
           "source": r.get("url") or page_url, "feed": page_url, "fetched": fetched}
    rec["proj"] = None if called else project(cands, eevp, total, tru.get("total_expected_vote"))
    if rec["proj"] and rec["incParty"] and rec["proj"]["party"] != rec["incParty"]:
        rec["projFlip"] = True
    return rec

def main():
    now = dt.datetime.now(dt.timezone.utc)
    fetched = now.astimezone(SGT).strftime("%-d %b %Y, %-I:%M %p SGT")
    urls = {"house": B+"results-house.json", "senate": B+"results-senate.json", "governor": B+"results-governor.json"}
    urls.update({s: B+f"results-{s}.json" for s in STATES})
    with cf.ThreadPoolExecutor(16) as ex:
        raw = dict(zip(urls, ex.map(get, urls.values())))
    data = {"fetchedAt": fetched, "fetchedUtc": now.isoformat(), "sources": {}, "senate": [], "governor": [], "statewide": [], "house": [], "control": {}, "exitPolls": []}
    for k in ("house", "senate", "governor"):
        d = raw[k]; data["sources"][urls[k]] = "ok" if d else "failed"
        if not d: continue
        data["resultsUpdatedAt"] = (d.get("resultsMeta") or {}).get("resultsUpdatedAt")
        data[k] = [norm(r, urls[k], fetched) for r in d["races"] if not r["nyt_id"].startswith("US-")]
        for pc in (d.get("partyControlData") or {}).get("results", []):
            for oid, o in (pc.get("offices") or {}).items():
                pb = o.get("party_balance") or {}
                data["control"][oid] = {"total": o.get("total"), "up": o.get("open_seats"), "called": o.get("num_races_called"),
                    "toWin": (o.get("to_win") or {}).get("DEM"), "current": o.get("current_control"),
                    "won": {pkey(p): v.get("seats") for p, v in pb.items()}, "noElection": {pkey(p): v.get("no_election") for p, v in pb.items()}}
    seen = set()
    for s in STATES:
        d = raw[s]; data["sources"][urls[s]] = "ok" if d else "failed"
        if not d: continue
        for r in d["races"]:
            if r.get("office") in SKIP_OFFICES or r.get("ballot_measure_text") or r["nyt_id"] in seen: continue
            if r.get("coverage") != "state" or r.get("seat") or "Court" in (r.get("office") or "") or "Board" in (r.get("office") or ""): continue
            if "Amendment" in (r.get("office") or "") or "Question" in (r.get("office") or "") or "Proposition" in (r.get("office") or ""): continue
            seen.add(r["nyt_id"]); data["statewide"].append(norm(r, urls[s], fetched))
    for u in EXIT_URLS:
        d = get(u, 1); data["sources"][u] = "ok" if d else "not available"
        if d: data["exitPolls"].append({"label": "Published network exit poll toplines", "source": u, "raw": d})
    json.dump(data, open(os.environ.get("EL_DIR","/workspace/election2026")+"/data.json", "w"))
    print(f"house={len(data['house'])} senate={len(data['senate'])} gov={len(data['governor'])} statewide={len(data['statewide'])} at {fetched}")
main()
