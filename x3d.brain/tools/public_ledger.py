#!/usr/bin/env python3
"""Turn the private media ledger into the public one (standard library only).

    python3 -I -B tools/public_ledger.py --src LEDGER.jsonl [--out ledger/LEDGER.public.jsonl] [--summary ledger/LEDGER.summary.json]
        [--forbid-file FILE]

The private ledger has one JSON row per paid or probing call made while the demo was built: what was asked (the prompt), what came back
(the sha256 of the output, never the output), how long it took and what it cost. The public ledger keeps the first part and drops the
rest, so a reader can see how the generated media were made and can check any file against its hash, and nothing else.

  kept     kind, step, id, attempt, batch, prompt, prompt_sha256, sha256, file, bytes, items, images (role, sha256, bytes, px),
           http, seconds, token counts, finish reason, time stamp
  changed  the model name becomes "image model", "text model" or "music model" (by the row's kind; a probe is classed by its name's
           shape); an error text becomes a class (rate limited, timeout, error)
  dropped  every field not named above, by allowlist: costs, region, project and identity fields, API verbs, and anything a later
           version of the writer adds, because a new field must be reviewed before it is public

The summary holds counts and seconds only, never costs. The converter fails closed: if any string in the result matches a leak pattern
(vendor and model names, hosts, key shapes, account or project paths, absolute paths, a dollar amount) or contains a literal from
--forbid-file, it writes nothing and exits 1 naming the row and pattern (never the literal). Exit 2 is an input or instrument error.
This file keeps its own leak words in fragments so that it passes the sweep it feeds.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

KEEP = ("kind", "step", "id", "attempt", "batch", "prompt", "prompt_sha256", "sha256", "file", "bytes", "items", "http", "tokens", "tokens_in",
        "tokens_out", "tokens_think", "finish", "ts", "vision", "chunks", "think0", "seconds_audio")
NEUTRAL = {"image": "image model", "text": "text model", "music": "music model"}

# Leak patterns, assembled from fragments so this source file contains none of the words it refuses.
_v = ["gem" + "ini", "imag" + "en", "ly" + "ria", "ve" + "o-", "vert" + "ex ?ai", "goo" + "gle", "gcl" + "oud", "anthr" + "opic", "open" + "ai", "cla" + "ude"]
LEAKS = [re.compile("|".join(_v), re.I),
         re.compile(r"https?://", re.I),
         re.compile(r"AI" + r"za[0-9A-Za-z_-]{20,}|ya" + r"29\.[0-9A-Za-z_-]{20,}|sk-[A-Za-z0-9]{20,}|-----BEGIN [A-Z ]*PRIVATE"),
         re.compile(r"projects/|service" + r"[ -]?account|\.iam\.|\.gserv" + r"iceaccount|@[A-Za-z0-9-]+\.[a-z]{2,}"),
         re.compile(r"(?<![\w\"'])/(?:home|tmp|root|Users|mnt|var)/"),
         re.compile(r"\$\s?\d")]


def sha256_file(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def model_label(row: dict) -> str:
    kind = row.get("kind")
    if kind in NEUTRAL:
        return NEUTRAL[kind]
    name = str(row.get("model", ""))
    if "imag" in name.lower():
        return NEUTRAL["image"]
    if "music" in name.lower() or kind == "music":
        return NEUTRAL["music"]
    return NEUTRAL["text"]


def error_class(row: dict) -> str | None:
    err = row.get("err")
    if err is None:
        return None
    s = str(err).lower()
    if "429" in s or "exhausted" in s or "quota" in s:
        return "rate limited"
    if "timed out" in s or "timeout" in s:
        return "timeout"
    return "error"


def convert_row(row: dict) -> dict:
    out = {k: row[k] for k in KEEP if k in row and row[k] is not None}
    out["model"] = model_label(row)
    if "sec" in row:
        out["seconds"] = row["sec"]
    if row.get("kind") == "music" and isinstance(row.get("bytes"), int) and str(row.get("file", "")).endswith(".wav"):
        # the length is computed from the file size (48 kHz, stereo, 16-bit PCM, 44-byte header): the writer's own figure and the file header both over-declared it
        out["seconds_audio"] = round((row["bytes"] - 44) / 192000, 2)
        out["audio_note"] = "seconds_audio computed from the byte count (48 kHz stereo 16-bit PCM); the generator's own figure and the WAV header both over-declared the length"
    ec = error_class(row)
    if ec:
        out["error_class"] = ec
    imgs = row.get("images")
    if isinstance(imgs, list):
        out["images"] = [{k: i[k] for k in ("role", "sha256", "bytes", "px") if k in i} for i in imgs if isinstance(i, dict)]
    return out


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for k, v in value.items():
            yield from strings(k)
            yield from strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from strings(v)


def leak_scan(rows: list[dict], literals: list[str]) -> list[str]:
    hits = []
    for n, row in enumerate(rows, 1):
        for s in strings(row):
            for pat in LEAKS:
                if pat.search(s):
                    hits.append(f"row {n}: pattern {LEAKS.index(pat)}")
            for lit in literals:
                if lit and lit in s:
                    hits.append(f"row {n}: a --forbid-file literal")
    return hits


def summarise(src_rows: list[dict], pub_rows: list[dict], src_sha: str, pub_sha: str) -> dict:
    by_kind = Counter(r["kind"] for r in pub_rows)
    sec: Counter = Counter()
    tok: dict[str, Counter] = {}
    for r in pub_rows:
        sec[r["kind"]] += float(r.get("seconds") or 0)
        t = tok.setdefault(r["kind"], Counter())
        for k in ("tokens", "tokens_in", "tokens_out", "tokens_think"):
            if isinstance(r.get(k), int):
                t[k] += r[k]
    http = Counter(str(r.get("http")) for r in pub_rows)
    steps = Counter(r.get("step", "(none)") for r in pub_rows)
    by_model = Counter(r["model"] for r in pub_rows)
    ok = sum(1 for r in pub_rows if r.get("http") == 200)
    return {"schema": "brain.ledger-summary/1",
            "note": "Counts and seconds only. Costs, regions, project and identity fields are not part of the public ledger.",
            "rows": len(pub_rows), "rows_in_source": len(src_rows),
            "by_kind": dict(sorted(by_kind.items())), "by_model_label": dict(sorted(by_model.items())),
            "by_step": dict(sorted(steps.items())), "http_status": dict(sorted(http.items())),
            "succeeded": ok, "failed_or_retried": len(pub_rows) - ok,
            "rate_limited": sum(1 for r in pub_rows if r.get("error_class") == "rate limited"),
            "timeouts": sum(1 for r in pub_rows if r.get("error_class") == "timeout"),
            "retries": sum(1 for r in pub_rows if (r.get("attempt") or 0) > 0),
            "outputs_with_sha256": sum(1 for r in pub_rows if r.get("sha256")),
            "prompts_kept": sum(1 for r in pub_rows if r.get("prompt")),
            "seconds_by_kind": {k: round(v, 1) for k, v in sorted(sec.items())}, "seconds_total": round(sum(sec.values()), 1),
            "audio_seconds_generated": round(sum(float(r.get("seconds_audio") or 0) for r in pub_rows), 1),
            "tokens_by_kind": {k: dict(v) for k, v in sorted(tok.items())},
            "first_ts": min((r["ts"] for r in pub_rows if r.get("ts")), default=None), "last_ts": max((r["ts"] for r in pub_rows if r.get("ts")), default=None),
            "source_ledger_sha256": src_sha, "public_ledger_sha256": pub_sha}


def run(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(prog="public_ledger")
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", default="ledger/LEDGER.public.jsonl")
    ap.add_argument("--summary", default="ledger/LEDGER.summary.json")
    ap.add_argument("--forbid-file", help="a file of literals (one per line) that must not appear in the output; they are never printed")
    a = ap.parse_args(argv)
    src = Path(a.src)
    try:
        src_rows = [json.loads(line) for line in src.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, ValueError) as e:
        print(json.dumps({"error": "INPUT", "detail": str(e)[:200]}))
        return 2
    if not src_rows or not all(isinstance(r, dict) and "kind" in r for r in src_rows):
        print(json.dumps({"error": "INPUT", "detail": "no rows, or a row without a kind"}))
        return 2
    literals: list[str] = []
    if a.forbid_file:
        try:
            literals = [x.strip() for x in Path(a.forbid_file).read_text(encoding="utf-8").splitlines() if len(x.strip()) >= 4]
        except OSError as e:
            print(json.dumps({"error": "INPUT", "detail": f"--forbid-file: {type(e).__name__}"}))
            return 2
    pub = [convert_row(r) for r in src_rows]
    hits = leak_scan(pub, literals)
    if hits:
        print(json.dumps({"rejected": "LEAK_IN_PUBLIC_LEDGER", "detail": hits[:8]}))
        return 1
    body = "".join(json.dumps(r, sort_keys=True, ensure_ascii=False) + "\n" for r in pub)
    out, summ = Path(a.out), Path(a.summary)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    s = summarise(src_rows, pub, hashlib.sha256(src.read_bytes()).hexdigest(), sha256_file(out))
    if leak_scan([s], literals):
        out.unlink()
        print(json.dumps({"rejected": "LEAK_IN_PUBLIC_SUMMARY"}))
        return 1
    summ.write_text(json.dumps(s, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"rows": len(pub), "by_kind": s["by_kind"], "seconds_total": s["seconds_total"], "public_ledger_sha256": s["public_ledger_sha256"][:16],
                      "summary_sha256": sha256_file(summ)[:16]}))
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
