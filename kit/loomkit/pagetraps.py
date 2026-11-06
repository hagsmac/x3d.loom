"""Page-traps witness: has this page code already cost us once?

The X3D traps witness (traps.py) reads scenes. This one reads the JavaScript that drives them, for the
runtime contracts x3d.STEM paid for (Loom law 32). It is a static, standard-library reader: each rule is
a narrow pattern with a named incident, tested on both sides in tests/test_gates.py. A clean result means
none of these known traps is present, not that the page is correct; the page's own browser evidence
remains the witness for behaviour.

Rules are labelled with the runtime they were observed on: a browser fact must not become a universal
prohibition (the same discipline as traps.py).

What it reads: .js files, and the inline <script> blocks of .html files (the Mashtots slide show keeps its
whole X_ITE driver inline in stage.html; a witness that read only app/*.js passed it while it measured
nothing, failure mode 93). A callback passed by name is resolved to its definition in the same source and
checked like an inline one. It reports an inventory (field callbacks and world loads seen) so a pass over
code that never touches X_ITE is visible as such.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class Hit:
    rule: str
    severity: str
    where: str
    detail: str


@dataclass
class Rule:
    id: str
    severity: str
    runtime: str
    origin: str


RULES = {
    "xite-callback-unguarded": Rule("xite-callback-unguarded", "error", "X_ITE 16.5.1",
        "One exception escaping a field callback left the routing guard set and froze every route in the scene "
        "(X_ITE teardown F02; reproduced on the Turing Garden page, 5 Nov; Loom failure mode 88). The callback body must start with try."),
    "xite-browser-currenttime": Rule("xite-browser-currenttime", "error", "X_ITE 16.5.1",
        "Browser.currentTime is undefined in X_ITE; a NaN TimeSensor startTime froze playback silently (Turing Garden, failure mode 72). Use getCurrentTime()."),
    "nav-before-scene": Rule("nav-before-scene", "error", "any (X_ITE pages)",
        "A hashchange listener registered before the scene loaded reached the case loader with no scene (Electron Cloud and Turing Garden, failure mode 78). "
        "Heuristic: the listener must appear after the loadURL call in the file."),
    "window-global-shadow": Rule("window-global-shadow", "error", "browsers (classic scripts)",
        "A top-level const named top collided with window.top and the page script never ran (Electron Cloud, failure mode 77)."),
    "js-syntax": Rule("js-syntax", "error", "Node.js syntax check (node --check)",
        "A hardening script left '}););' in the vortex page; the script never ran, yet every pattern rule passed it (5 Nov, failure mode 92). "
        "A page that does not parse trivially avoids every other trap, so syntax is checked first."),
    "sim-nonportable-math": Rule("sim-nonportable-math", "error", "ECMAScript (any engine); files marked // loom:sim",
        "A game whose proof of play is a replayed tape needs the same state hash in every JavaScript engine. ECMAScript leaves "
        "Math.sin, cos, exp, pow, atan2 and the ** operator implementation-approximated, so two engines may differ in the last bit "
        "and a tape recorded in one diverges in another; Math.random and clocks differ on every run. x3d.platformer's sim "
        "replaced them with a portable polynomial (engine/physics.js dsin, 6 Nov). Spec fact; a cross-engine divergence was not "
        "reproduced here (grade L). Only code that declares itself sim is held to it: render and audio code may use Math.sin."),
    "loadurl-unbudgeted": Rule("loadurl-unbudgeted", "warning", "X_ITE 16.6.1 (source reading)",
        "replaceWorld can leave its promise pending when an internal wait rejects (X_ITE teardown F01, L2; not reproduced here, failure mode 89). "
        "Give the world load a time budget (Promise.race with a timeout)."),
}

WINDOW_PROPS = {"top", "name", "status", "parent", "length", "origin", "self", "frames", "location", "history",
                "closed", "opener", "event", "external", "screen", "window", "document", "navigator"}


def _line(src: str, pos: int) -> int:
    return src.count("\n", 0, pos) + 1


def strip_comments(src: str) -> str:
    """Blank out // and /* */ comments (newlines kept, so line numbers hold), leaving strings, template
    literals and regex-free code intact. A comment that explains a trap must not trip it (the first run
    flagged the Electron Cloud page's own warning comment about Browser.currentTime)."""
    out, i, n = [], 0, len(src)
    while i < n:
        c = src[i]
        if c in "\"'`":
            j = i + 1
            while j < n and src[j] != c:
                j += 2 if src[j] == "\\" else 1
            out.append(src[i:j + 1]); i = j + 1
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i)); i = j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in src[i:j])); i = j
        else:
            out.append(c); i += 1
    return "".join(out)


def syntax(src: str, path: str = "<page>", module: bool = False) -> list[Hit]:
    """Parse the page with node --check. Fails closed: without Node the check raises, it never passes.
    module=True parses as an ES module (<script type="module">)."""
    import shutil, subprocess, tempfile, os
    node = shutil.which("node")
    if not node:
        raise RuntimeError("PAGE_SYNTAX_UNCHECKED: node is not on PATH")
    with tempfile.NamedTemporaryFile("w", suffix=".mjs" if module else ".js", delete=False, encoding="utf-8") as f:
        f.write(src)
        tmp = f.name
    real = os.path.realpath(tmp)
    try:
        r = subprocess.run([node, "--check", tmp], capture_output=True, text=True, timeout=60)
    finally:
        os.unlink(tmp)
    if r.returncode == 0:
        return []
    msg = next((l for l in r.stderr.splitlines() if "Error" in l), r.stderr.strip()[:200])
    # node prints the real path (/private/var/... on macOS for a /var/... temp file): match either
    names = (tmp, real)
    line = next((l.rsplit(":", 1)[-1] for l in r.stderr.splitlines() if l.startswith(names)), "?")
    return [Hit("js-syntax", "error", f"{path}:{line}", msg[:200])]


_IDENT = r"[A-Za-z_$][\w$]*"
_ARG = r"""(?:"[^"]*"|'[^']*'|[\w$.]+)"""
_BY_NAME = re.compile(r"\s*" + _ARG + r"\s*,\s*" + _ARG + r"\s*,\s*(" + _IDENT + r")\s*\)")


def _named_body(src: str, name: str) -> str | None:
    """The text just after the opening brace of `name`'s definition in this source, or None."""
    n = re.escape(name)
    for pat in (r"(?:async\s+)?function\s+" + n + r"\s*\([^)]*\)\s*\{",
                r"(?:const|let|var)\s+" + n + r"\s*=\s*(?:async\s*)?(?:function\s*\([^)]*\)|\([^)]*\)\s*=>|" + _IDENT + r"\s*=>)\s*\{"):
        m = re.search(pat, src)
        if m:
            return src[m.end():]
    return None


_ESM = re.compile(r"^\s*(?:import\s*[\w${*\"']|export\s)", re.M)


def is_module(src: str) -> bool:
    """A .js file with top-level import or export can only load as a module, where top-level names stay out of window."""
    return bool(_ESM.search(src))


def patterns(src: str, path: str = "<page>", globals_shared: bool = True) -> list[Hit]:
    """The pattern rules, on comment-stripped source (line numbers preserved). globals_shared=False for module
    code: its top-level names do not reach window (the first HTML run flagged a module's `frames`, a false positive)."""
    hits: list[Hit] = []
    # 1. every field callback must open with try: inline functions, and functions passed by name that are
    #    defined in this same source (the Mashtots slide show passes its whole clock as `onFrame`)
    for m in re.finditer(r"addFieldCallback\s*\(", src):
        where = f"{path}:{_line(src, m.start())}"
        ref = _BY_NAME.match(src, m.end())
        if ref:
            body = _named_body(src, ref.group(1))
            if body is None:
                hits.append(Hit("xite-callback-unguarded", "warning", where,
                                f"callback {ref.group(1)} is defined elsewhere: put try/catch inside it (not checked here)"))
            elif not body.lstrip().startswith("try"):
                hits.append(Hit("xite-callback-unguarded", "error", where, f"callback {ref.group(1)} (passed by name) does not start with try"))
            continue
        tail = src[m.end():m.end() + 600]
        fn = re.search(r"(=>\s*\{|function\s*\([^)]*\)\s*\{)", tail)
        if not fn:
            hits.append(Hit("xite-callback-unguarded", "warning", where,
                            "callback passed by reference: put try/catch inside that function (not checked here)"))
            continue
        body = tail[fn.end():].lstrip()
        if not body.startswith("try"):
            hits.append(Hit("xite-callback-unguarded", "error", where, "callback body does not start with try"))
    # 2. Browser.currentTime
    for m in re.finditer(r"\b(?:B|browser|Browser|X3D\.getBrowser\([^)]*\))\.currentTime\b", src):
        hits.append(Hit("xite-browser-currenttime", "error", f"{path}:{_line(src, m.start())}", m.group(0)))
    # 3. navigation wired before the scene is loaded (file order)
    load = re.search(r"\.loadURL\s*\(", src)
    for m in re.finditer(r"addEventListener\s*\(\s*[\"']hashchange[\"']", src):
        if load is None or m.start() < load.start():
            hits.append(Hit("nav-before-scene", "error", f"{path}:{_line(src, m.start())}",
                            "hashchange listener appears before loadURL" if load else "hashchange listener but no loadURL in this file"))
    # 4. top-level declarations that shadow window properties (classic scripts share the global scope)
    for m in re.finditer(r"^(?:const|let|var|function)\s+([A-Za-z_$][\w$]*)", src, flags=re.M) if globals_shared else ():
        if m.group(1) in WINDOW_PROPS:
            hits.append(Hit("window-global-shadow", "error", f"{path}:{_line(src, m.start())}", f"top-level {m.group(1)}"))
    # 5. world loads without a time budget
    for m in re.finditer(r"await\s+[\w.]*loadURL\s*\(", src):
        window = src[max(0, m.start() - 200):m.start() + 300]
        if "Promise.race" not in window and "timeout" not in window.lower():
            hits.append(Hit("loadurl-unbudgeted", "warning", f"{path}:{_line(src, m.start())}", "await loadURL without a time budget"))
    return hits


SIM_MARKER = re.compile(r"^\s*//\s*loom:sim\b")
_SIM_FORBIDDEN = re.compile(
    r"\bMath\.(sin|cos|tan|asin|acos|atan|atan2|sinh|cosh|tanh|asinh|acosh|atanh|exp|expm1|log|log1p|log2|log10|pow|cbrt|hypot|random)\b"
    r"|\bDate\.now\b|\bnew\s+Date\b|\bperformance\.now\b|\bgetRandomValues\b|(?<![*/])\*\*(?![*/=])")


def is_sim(src: str) -> bool:
    """Code declares itself part of a deterministic simulation with a `// loom:sim` line among its first five lines."""
    lines = [l for l in src.splitlines() if l.strip()][:5]
    return any(SIM_MARKER.match(l) for l in lines)


def sim_math(code: str, path: str = "<page>") -> list[Hit]:
    """On comment-stripped sim code: every call whose result is not exactly specified, or not repeatable."""
    return [Hit("sim-nonportable-math", "error", f"{path}:{_line(code, m.start())}",
                f"{m.group(0).strip()} in sim code: use a portable polynomial (dsin/dcos) or the tick counter")
            for m in _SIM_FORBIDDEN.finditer(code)]


def inventory(src: str) -> dict:
    """What the witness saw: a pass over code with no field callbacks and no world loads measured nothing about them."""
    src = strip_comments(src)
    return {"field_callbacks": len(re.findall(r"addFieldCallback\s*\(", src)),
            "world_loads": len(re.findall(r"\.(?:loadURL|replaceWorld|createX3DFromURL)\s*\(", src))}


def check(src: str, path: str = "<page>") -> list[Hit]:
    code = strip_comments(src)
    return (syntax(src, path) + patterns(code, path, globals_shared=not is_module(code))
            + (sim_math(code, path) if is_sim(src) else []))


_JS_TYPES = {"", "module", "text/javascript", "application/javascript"}


def inline_scripts(html: str) -> list[tuple[int, int, bool]]:
    """(start, end, is_module) spans of inline JavaScript bodies in an HTML file. Scripts with src= and non-JS
    types (shaders, JSON) are skipped. Limitation: a literal '</script>' inside a script string ends the block."""
    out = []
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script\s*>", html, flags=re.S | re.I):
        attrs = m.group(1)
        if re.search(r"\bsrc\s*=", attrs, flags=re.I):
            continue
        t = re.search(r"""\btype\s*=\s*["']?([^"'\s>]*)""", attrs, flags=re.I)
        typ = (t.group(1).lower() if t else "")
        if typ not in _JS_TYPES:
            continue
        out.append((m.start(2), m.end(2), typ == "module"))
    return out


def scripts_view(html: str, which: str = "all") -> str:
    """The HTML with everything outside inline script bodies blanked (newlines kept), so pattern rules see
    all the page's inline code at once and report HTML line numbers. which: "all", "classic" or "module"."""
    keep = [False] * len(html)
    for a, b, module in inline_scripts(html):
        if which == "all" or (which == "module") == module:
            keep[a:b] = [True] * (b - a)
    return "".join(c if k or c == "\n" else " " for c, k in zip(html, keep))


def check_html(html: str, path: str = "<page>") -> list[Hit]:
    hits: list[Hit] = []
    for a, b, module in inline_scripts(html):
        pad = "\n" * html.count("\n", 0, a)                  # syntax errors report the HTML line
        hits += syntax(pad + html[a:b], path, module=module)
    hits += patterns(strip_comments(scripts_view(html)), path, globals_shared=False)
    shared = [h for h in patterns(strip_comments(scripts_view(html, "classic")), path) if h.rule == "window-global-shadow"]
    for a, b, _ in inline_scripts(html):                     # an inline script may declare itself sim
        if is_sim(html[a:b]):
            only = "".join(c if a <= i < b or c == "\n" else " " for i, c in enumerate(html))
            shared += sim_math(strip_comments(only), path)
    return hits + shared
