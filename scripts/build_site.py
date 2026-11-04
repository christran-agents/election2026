#!/usr/bin/env python3
"""data.json -> site/data.json for the public board. Keeps call history in calls.json for the ticker."""
import os
import json, datetime, pathlib
B = pathlib.Path(os.environ.get("EL_DIR","/workspace/election2026"))
d = json.load(open(B/"data.json"))
hist_p = pathlib.Path(os.environ.get("EL_CALLS", str(B/"calls.json")))
hist = json.load(open(hist_p)) if hist_p.exists() else {}
now = d["fetchedAt"]
GOV_NOT_UP = {"DE":"D","KY":"D","NJ":"D","NC":"D","VA":"D","WA":"D","IN":"R","LA":"R","MS":"R","MO":"R","MT":"R","ND":"R","UT":"R","WV":"R"}
def lab(r, kind):
    if kind == "H": return f'{r["state"]}-{"AL" if "Large" in r["seat"] else r["seat"].replace("District ","")}'
    if kind == "S": return r["state"] + (" special" if "S_W" in r["id"] else "")
    if kind == "G": return r["state"]
    return f'{r["state"]} {r["office"]}'
def row(r, kind):
    c = [{"n": x["name"], "p": x["party"], "i": 1 if x.get("inc") else 0, "v": x.get("votes"), "pc": x.get("pct")} for x in (r["cands"] or [])[:3]]
    k = lab(r, kind)
    if r["called"] and k not in hist: hist[k] = d.get("fetchedUtc") or now
    pr = r.get("proj") or {}
    return {"k": k, "s": r["state"], "c": c if r["totalVotes"] else [{"n": x["n"], "p": x["p"], "i": x["i"]} for x in c],
            "tv": r["totalVotes"], "ev": None if r["eevp"] is None else round(r["eevp"], 1),
            "cl": 1 if r["called"] else 0, "by": "/".join(r["calledBy"]), "wp": r["winnerParty"] or "", "w": r["winner"] or "",
            "fl": 1 if r.get("flip") else 2 if r.get("projFlip") else 0, "ip": r.get("incParty") or "",
            "rt": r.get("rating") or "", "u": 1 if r.get("uncontested") else 0, "src": r.get("source", ""),
            "pj": {"p": pr.get("party"), "m": pr.get("margin"), "lo": pr.get("lo"), "hi": pr.get("hi"), "cf": pr.get("conf")} if pr else None,
            "ct": hist.get(k)}
out = {"at": now, "utc": d.get("fetchedUtc"), "control": d["control"], "govNotUp": GOV_NOT_UP,
       "S": [row(r, "S") for r in d["senate"]], "G": [row(r, "G") for r in d["governor"]],
       "H": [row(r, "H") for r in d["house"]], "O": [row(r, "O") for r in d["statewide"]],
       "exit": len(d["exitPolls"])}
json.dump(hist, open(hist_p, "w"))
s = json.dumps(out, separators=(",", ":"), ensure_ascii=False)
(B/"site_data.json").write_text(s); print("site bytes", len(s))
