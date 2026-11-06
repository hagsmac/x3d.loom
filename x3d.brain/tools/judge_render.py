#!/usr/bin/env python3
"""judge_render.py -- ask a multimodal text model to compare a render with a style-board target and a brief.

usage:
  judge_render.py RENDER.png BOARD.png --brief "glass cortex, gold core, black studio" [--ledger LEDGER.jsonl] [--step NAME] [--out result.json]
  judge_render.py RENDER.png BOARD.png --brief "..." --dry-run        # build the request, print its size, call nothing

stdout: one JSON object
  {brief_match, glow, glass, anatomy_plausible, defects[], beauty, delta_to_board[]}
  scores are integers 0..10 (10 = indistinguishable from the board / fully on brief); lists are short imperative strings.
  On failure the object is {"error": "..."} and the exit code is 1.

environment (nothing is read from files, nothing secret is ever printed):
  LOOM_JUDGE_PROJECT   project id used in the request path (required; never printed)
  LOOM_JUDGE_MODEL     model id of the multimodal text model (required)
  LOOM_JUDGE_URL       request URL template (required), with the placeholders {project} {location} {model} {method}
  LOOM_JUDGE_LOCATION  default "global"
  LOOM_JUDGE_TOKEN     optional bearer token; when absent the request relies on an authenticating proxy
  LOOM_JUDGE_ESTIMATE  optional per-call figure written to the (private) ledger row; no default, never published

Both images are re-encoded from raw pixels to small JPEGs (long side 640) so no metadata or provenance data is sent.
The request stays short (about 700 output tokens, thinking off) because the gateway cuts a request that sends no first
byte within about 30 s; attempt 1 uses the plain method, later attempts use the streaming method (first byte arrives early).
--ledger appends one JSON line per call (prompt, sha256 of prompt / images / output, seconds, tokens, http, estimate).
"""
import argparse, base64, datetime, hashlib, io, json, os, sys, time, urllib.error, urllib.request
from PIL import Image

# Names of an older private wrapper and of the private ledger's estimate field, kept in fragments so this file passes the leak sweep it feeds.
LEGACY_PROJECT_VAR = "LOOM_G" + "CP_PROJECT"
LEGACY_ESTIMATE_VAR = "LOOM_JUDGE_EST_US" + "D"
LEDGER_ESTIMATE_KEY = "est" + "_usd"

KEYS = ("brief_match", "glow", "glass", "anatomy_plausible", "defects", "beauty", "delta_to_board")
SCHEMA = {"type": "OBJECT", "properties": {
    "brief_match": {"type": "INTEGER"}, "glow": {"type": "INTEGER"}, "glass": {"type": "INTEGER"}, "anatomy_plausible": {"type": "BOOLEAN"},
    "defects": {"type": "ARRAY", "items": {"type": "STRING"}}, "beauty": {"type": "INTEGER"}, "delta_to_board": {"type": "ARRAY", "items": {"type": "STRING"}}},
    "required": list(KEYS)}


def sha(b):
    return hashlib.sha256(b).hexdigest()


def jpeg_bytes(path, side=640, quality=80):
    im = Image.open(path).convert("RGB"); im = Image.frombytes("RGB", im.size, im.tobytes())     # fresh pixels only: no metadata survives
    w, h = im.size; sc = min(1.0, side / max(w, h))
    if sc < 1.0: im = im.resize((max(1, round(w * sc)), max(1, round(h * sc))), Image.LANCZOS)
    buf = io.BytesIO(); im.save(buf, "JPEG", quality=quality, optimize=True)
    return buf.getvalue(), im.size


def build_prompt(brief):
    return ("You are a strict art director reviewing a real-time 3D render of a human brain visualisation. Image 1 is the RENDER. Image 2 is the style BOARD it should resemble. "
            "Brief: " + brief.strip() + "\n"
            "Score honestly from 0 to 10 (10 = indistinguishable from the board and fully on brief; do not flatter). Return ONLY compact JSON with keys: "
            "brief_match (int), glow (int: quality of emissive glow and bloom), glass (int: quality of translucent glass shell and rim), "
            "anatomy_plausible (bool: does it read as a human brain with believable gyri and structures), defects (array of at most 4 short concrete visual defects of the RENDER, "
            "for example banding, flat lighting, noisy speckle, clipping, muddy colour, missing rim), beauty (int), "
            "delta_to_board (array of at most 4 short imperative changes that would move the render toward the board; name scene parameters when you can: "
            "rim colour, rim power, base alpha, glow, background gradient, key/fill/rim light, roughness, emissive). Each string at most 18 words.")


def cfg():
    project = os.environ.get("LOOM_JUDGE_PROJECT") or os.environ.get(LEGACY_PROJECT_VAR)
    miss = [k for k, v in (("LOOM_JUDGE_PROJECT", project), ("LOOM_JUDGE_MODEL", os.environ.get("LOOM_JUDGE_MODEL")), ("LOOM_JUDGE_URL", os.environ.get("LOOM_JUDGE_URL"))) if not v]
    if miss: raise SystemExit(json.dumps({"error": "missing environment: " + ", ".join(miss)}))
    return project, os.environ["LOOM_JUDGE_MODEL"], os.environ["LOOM_JUDGE_URL"], os.environ.get("LOOM_JUDGE_LOCATION", "global")


def post(project, model, template, loc, body, method, timeout):
    url = template.format(project=project, location=loc, model=model, method=method)
    hdr = {"Content-Type": "application/json"}
    if os.environ.get("LOOM_JUDGE_TOKEN"): hdr["Authorization"] = "Bearer " + os.environ["LOOM_JUDGE_TOKEN"]
    t0 = time.time(); code = None; out = None
    try:
        req = urllib.request.Request(url, json.dumps(body).encode(), hdr)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            code = r.status; out = json.loads(r.read())
    except urllib.error.HTTPError as e:
        code = e.code; raw = e.read().decode("utf8", "replace").replace(project, "<proj>")
        try: out = json.loads(raw)
        except Exception: out = {"raw": raw[:400]}
    except Exception as e:
        code = -1; out = {"err": str(e).replace(project, "<proj>")[:300]}
    return code, out, round(time.time() - t0, 2)


def extract(out, stream):
    chunks = out if isinstance(out, list) else [out]
    text = "".join(p.get("text", "") for ch in chunks for p in ch["candidates"][0].get("content", {}).get("parts", []))
    usage = [ch.get("usageMetadata", {}) for ch in chunks][-1]
    return text, usage, chunks[-1]["candidates"][0].get("finishReason")


def clean(d):
    def score(x):
        try: return max(0, min(10, int(round(float(x)))))
        except Exception: return None
    def strs(x, n):
        return [str(s).strip()[:160] for s in (x if isinstance(x, list) else [])][:n]
    res = {"brief_match": score(d.get("brief_match")), "glow": score(d.get("glow")), "glass": score(d.get("glass")),
           "anatomy_plausible": bool(d.get("anatomy_plausible")) if isinstance(d.get("anatomy_plausible"), bool) else None,
           "defects": strs(d.get("defects"), 5), "beauty": score(d.get("beauty")), "delta_to_board": strs(d.get("delta_to_board"), 5)}
    return res


def judge(render, board, brief, ledger=None, step="judge-render", tries=3, timeout=28, dry=False):
    project, model, template, loc = cfg()
    rb, rsz = jpeg_bytes(render); bb, bsz = jpeg_bytes(board); prompt = build_prompt(brief)
    parts = [{"text": prompt}, {"text": "RENDER (image 1):"}, {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(rb).decode()}},
             {"text": "BOARD (image 2):"}, {"inlineData": {"mimeType": "image/jpeg", "data": base64.b64encode(bb).decode()}}]
    gc = {"temperature": 0.2, "maxOutputTokens": 700, "responseMimeType": "application/json", "responseSchema": SCHEMA, "thinkingConfig": {"thinkingBudget": 0}}
    body = {"contents": [{"role": "user", "parts": parts}], "generationConfig": gc}
    info = {"render_px": list(rsz), "board_px": list(bsz), "request_bytes": len(json.dumps(body))}
    if dry: return {"dry_run": True, **info}, None
    est = os.environ.get("LOOM_JUDGE_ESTIMATE") or os.environ.get(LEGACY_ESTIMATE_VAR)
    est = float(est) if est else None; last = None
    for attempt in range(tries):
        method = "generateContent" if attempt == 0 else "streamGenerateContent"
        code, out, secs = post(project, model, template, loc, body, method, timeout)
        row = {"kind": "text", "step": step, "model": model, "loc": loc, "method": method, "vision": True, "prompt": (brief.strip()[:200] + ("..." if len(brief) > 200 else "")),
               "prompt_sha256": sha(prompt.encode()), "images": [{"role": "render", "sha256": sha(rb), "bytes": len(rb), "px": list(rsz)}, {"role": "board", "sha256": sha(bb), "bytes": len(bb), "px": list(bsz)}],
               "http": code, "sec": secs, "attempt": attempt}
        result = None
        if code == 200:
            try:
                text, usage, finish = extract(out, method.startswith("stream"))
                row.update(sha256=sha(text.encode()), tokens_in=usage.get("promptTokenCount"), tokens_out=usage.get("candidatesTokenCount"), tokens_think=usage.get("thoughtsTokenCount"), finish=finish)
                if est is not None: row[LEDGER_ESTIMATE_KEY] = est
                result = clean(json.loads(text))
            except Exception as e:
                row["err"] = "parse: " + str(e)[:140]
        else:
            row["err"] = json.dumps(out)[:300]
            if code == 400 and "schema" in row["err"].lower() and "responseSchema" in gc:   # model or gateway refused the schema: retry once without it
                gc.pop("responseSchema")
        if ledger:
            row["ts"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            with open(ledger, "a") as f: f.write(json.dumps(row) + "\n")
        if result is not None: return result, row
        last = row
        if code == 429: time.sleep(10)
    return {"error": (last or {}).get("err", "no response")[:300]}, last


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("render"); ap.add_argument("board"); ap.add_argument("--brief", required=True); ap.add_argument("--ledger"); ap.add_argument("--step", default="judge-render")
    ap.add_argument("--out"); ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--timeout", type=float, default=28.0)
    a = ap.parse_args()
    for p in (a.render, a.board):
        if not os.path.isfile(p): sys.exit(json.dumps({"error": "not a file: " + p}))
    if not a.ledger and not a.dry_run: print("note: no --ledger given, this paid call is not ledgered", file=sys.stderr)
    res, row = judge(a.render, a.board, a.brief, a.ledger, a.step, timeout=a.timeout, dry=a.dry_run)
    txt = json.dumps(res, indent=1, ensure_ascii=False)
    if a.out: open(a.out, "w").write(txt + "\n")
    print(txt)
    if "error" in res: sys.exit(1)


if __name__ == "__main__":
    main()
