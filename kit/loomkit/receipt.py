"""Loom Receipt v1: one JSON per accepted artifact, written only after acceptance.

Joins the definition doc's "Loom Receipt v1 (proposal)" with what the other model's projects proved
necessary: the candidate digest (not the receipt) is the subject, every required witness record is
hashed, unrun witnesses stay visible, and the receipt links to the one it replaces (prev). It is
unsigned: it shows drift, it does not authenticate authorship (definition, Receipts; Loomsong v2).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from .core import canonical, need, sha256_bytes, sha256_file, utc_now

RECEIPT_SCHEMA = "loom.receipt/1"


def _output_keys(outputs: list[Path]) -> dict[str, Path]:
    """Name each output by its basename; when two share one (events/x.x3d and events-v2/x.x3d), name every output by
    its path below their common folder instead, so none is silently dropped. The same file twice is refused."""
    keys = {p.name: p for p in outputs}
    if len(keys) < len(outputs):
        common = Path(os.path.commonpath([str(p.resolve()) for p in outputs]))
        keys = {p.resolve().relative_to(common).as_posix(): p for p in outputs}
        need(len(keys) == len(outputs), "RECEIPT_OUTPUTS", "the same output file is listed twice")
    return keys


def build(subject: str, acceptance: dict, candidate_files: dict, outputs: list[Path], tools: dict,
          inputs: dict, not_run: list[dict], model_calls: list[dict], budget: dict,
          prev: Path | None, limitations: list[str]) -> dict:
    receipt = {
        "schema": RECEIPT_SCHEMA,
        "kind": "artifact",
        "subject": subject,
        "candidate_sha256": acceptance["subject_sha256"],
        "candidate_files": len(candidate_files),
        "profile": acceptance["profile"],
        "inputs": inputs,
        "tools": tools,
        "outputs": {k: {"bytes": p.stat().st_size, "sha256": sha256_file(p)} for k, p in _output_keys(outputs).items()},
        "witnesses": acceptance["witnesses"],
        "not_run": not_run,
        "model_calls": model_calls,
        "budget": budget,
        "limitations": limitations,
        "grade": "C",
        "written_at": utc_now(),
        "prev": sha256_file(prev) if prev else None,
        "signed": False,
    }
    receipt["sha256"] = sha256_bytes(canonical(receipt))
    return receipt


def write(receipt: dict, dest: Path, force: bool = False) -> Path:
    """Never overwrite a receipt unless told to (law 14: add layers, never replace)."""
    need(force or not dest.exists(), "RECEIPT_EXISTS", f"{dest} exists; write a new version or pass --force")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(receipt, sort_keys=True, indent=2) + "\n")
    return dest


def verify(dest: Path) -> dict:
    r = json.loads(Path(dest).read_text())
    need(r.get("schema") == RECEIPT_SCHEMA, "RECEIPT_SCHEMA")
    body = {k: v for k, v in r.items() if k != "sha256"}
    need(sha256_bytes(canonical(body)) == r.get("sha256"), "RECEIPT_DRIFT")
    return r
