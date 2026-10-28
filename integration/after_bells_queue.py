#!/usr/bin/env python3
"""GitHub-backed, single-writer story reservation and atomic draft delivery.

Only stage manuscripts for editorial approval; never approve or publish to AO3.
Requires Python 3.11+ and a fine-grained GitHub token with Contents: write
for remote claim, submit, or release. Validation requires no token.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

BASE = "stories/after-the-bells"
MANIFEST = f"{BASE}/manifest.json"
DEFAULT_REPO = "peterwjones334/ao3-fanfic-automation"
ALLOWED = {"planned", "generating", "draft", "approved", "published"}
LEASE_HOURS = 2
MIN_WORDS = 2000
MAX_WORDS = 5000


class QueueError(Exception):
    pass


class ApiError(QueueError):
    def __init__(self, code: int, message: str):
        self.code = code
        super().__init__(f"GitHub API {code}: {message[:500]}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def timestamp() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def utc_parse(s: str) -> datetime:
    result = datetime.fromisoformat(s.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise QueueError("timestamp has no timezone")
    return result.astimezone(timezone.utc)


def json_bytes(value: object) -> bytes:
    return (json.dumps(value, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def validate_manuscript(slot: dict, body: bytes, metadata: bytes) -> dict:
    if not body or b"\x00" in body:
        raise QueueError("empty/binary manuscript")
    try:
        text = body.decode("utf-8")
        md = json.loads(metadata.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QueueError(f"invalid UTF-8 or metadata JSON: {exc}") from exc
    if not isinstance(md, dict):
        raise QueueError("metadata must be an object")
    words = len(text.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        raise QueueError(f"manuscript has {words} words; expected {MIN_WORDS}–{MAX_WORDS}")
    number = slot["sequence"]
    if not re.search(rf"END OF STORY\s+(?:{number}|{number:02d})\s*[—–-]", text, re.I):
        raise QueueError(f"missing complete story {number} end marker")
    if md.get("work_id") != slot["work_id"]:
        raise QueueError("metadata work_id does not match reserved slot")
    if md.get("title") != slot["title"]:
        raise QueueError("metadata title does not match story slate")
    if md.get("chapter") != 1 or md.get("complete") is not True:
        raise QueueError("expected standalone complete chapter 1")
    if md.get("language") != "en":
        raise QueueError("metadata language must be 'en'")
    required = ("author", "chapter_title", "release_date", "rating", "warnings",
                "fandoms", "tags", "summary")
    if any(k not in md or not md[k] for k in required):
        raise QueueError("missing required AO3 metadata fields")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(md["release_date"])):
        raise QueueError("release_date must be YYYY-MM-DD")
    if not all(isinstance(md[k], list) for k in ("warnings", "fandoms", "tags")):
        raise QueueError("warnings/fandoms/tags must be arrays")
    return {"words": words, "sha256": hashlib.sha256(body).hexdigest()}


def validate_manifest(manifest: dict) -> list[dict]:
    slots = manifest.get("slots")
    if manifest.get("expected_count") != 10 or not isinstance(slots, list) or len(slots) != 10:
        raise QueueError("manifest must contain exactly ten slots")
    if [s.get("sequence") for s in slots] != list(range(1, 11)):
        raise QueueError("story sequence must be 1 through 10")
    for s in slots:
        n = s["sequence"]
        stem = f"story-{n:02d}"
        if s.get("work_id") != f"after-the-bells-{n:02d}":
            raise QueueError(f"invalid work ID in slot {n}")
        if s.get("markdown") != stem + ".md" or s.get("metadata") != stem + ".json":
            raise QueueError(f"invalid paths in slot {n}")
        if s.get("status") not in ALLOWED:
            raise QueueError(f"invalid status in slot {n}")
    return slots


def validate_local(root: Path) -> dict:
    data = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    slots = validate_manifest(data)
    completed = []
    for s in slots:
        md_path = root / s["markdown"]
        meta_path = root / s["metadata"]
        has_md, has_meta = md_path.is_file(), meta_path.is_file()
        if md_path.is_symlink() or meta_path.is_symlink():
            raise QueueError(f"story {s['sequence']}: source cannot be a symlink")
        if has_md != has_meta:
            raise QueueError(f"story {s['sequence']}: partial manuscript/metadata pair")
        if s["status"] in {"draft", "approved", "published"} and not has_md:
            raise QueueError(f"story {s['sequence']}: completed slot missing pair")
        if s["status"] in {"planned", "generating"} and has_md:
            raise QueueError(f"story {s['sequence']}: pair present but not committed as draft")
        if has_md:
            info = validate_manuscript(s, md_path.read_bytes(), meta_path.read_bytes())
            if s.get("sha256") != info["sha256"]:
                raise QueueError(f"story {s['sequence']}: stored hash mismatch")
            completed.append(s["sequence"])
    return {"validated": completed, "planned": 10 - len(completed), "expected": 10}


class GitHub:
    def __init__(self, repository: str, branch: str):
        self.repository = repository
        self.branch = branch
        self.token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not self.token:
            raise QueueError("Set GH_TOKEN or GITHUB_TOKEN (GitHub Contents:write).")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise QueueError("invalid repository")
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", branch) or ".." in branch:
            raise QueueError("invalid branch")

    def api(self, method: str, path: str, body: object | None = None) -> object:
        url = "https://api.github.com/repos/" + self.repository + "/" + path
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "after-bells-production-queue",
        }
        payload = None if body is None else json.dumps(body).encode("utf-8")
        if payload is not None:
            headers["Content-Type"] = "application/json"
        req = Request(url, data=payload, headers=headers, method=method)
        try:
            with urlopen(req, timeout=20) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ApiError(exc.code, details) from exc

    def snapshot(self) -> tuple[str, str, dict]:
        ref = self.api("GET", "git/ref/heads/" + quote(self.branch, safe="/"))
        head = ref["object"]["sha"]
        commit = self.api("GET", "git/commits/" + head)
        path = "contents/" + quote(MANIFEST, safe="/") + "?ref=" + quote(head, safe="")
        content = self.api("GET", path)
        raw = base64.b64decode(content["content"])
        manifest = json.loads(raw.decode("utf-8"))
        validate_manifest(manifest)
        return head, commit["tree"]["sha"], manifest

    def file_at(self, path: str, ref: str) -> bytes | None:
        try:
            payload = self.api("GET", "contents/" + quote(path, safe="/") +
                               "?ref=" + quote(ref, safe=""))
        except ApiError as exc:
            if exc.code == 404:
                return None
            raise
        return base64.b64decode(payload["content"])

    def commit_files(self, head: str, base_tree: str, files: dict[str, bytes], message: str):
        """One ref update makes all file changes visible atomically.

        A competing writer advancing HEAD makes our commit non-fast-forward.
        Never force; the caller must refetch manifest and retry or abort.
        """
        entries = []
        for name, data in files.items():
            blob = self.api("POST", "git/blobs",
                            {"content": base64.b64encode(data).decode("ascii"),
                             "encoding": "base64"})
            entries.append({"path": name, "mode": "100644", "type": "blob",
                            "sha": blob["sha"]})
        tree = self.api("POST", "git/trees",
                        {"base_tree": base_tree, "tree": entries})
        commit = self.api("POST", "git/commits",
                          {"message": message, "tree": tree["sha"],
                           "parents": [head]})
        self.api("PATCH", "git/refs/heads/" + quote(self.branch, safe="/"),
                 {"sha": commit["sha"], "force": False})
        return commit["sha"]


def claim(queue: GitHub) -> dict:
    for _ in range(5):
        head, tree, manifest = queue.snapshot()
        slots = manifest["slots"]
        chosen = None
        now = utc_now()
        for slot in slots:
            if slot["status"] == "planned":
                chosen = slot
                break
            if slot["status"] == "generating":
                try:
                    claimed = utc_parse(slot["claimed_at"])
                    if claimed + timedelta(hours=LEASE_HOURS) < now:
                        chosen = slot
                        break
                except (ValueError, KeyError):
                    chosen = slot
                    break
        if chosen is None:
            return {"status": "no_available_slot",
                    "drafts": sum(s["status"] in {"draft", "approved", "published"}
                                  for s in slots)}
        for path in (chosen["markdown"], chosen["metadata"]):
            if queue.file_at(BASE + "/" + path, head) is not None:
                raise QueueError(f"slot {chosen['sequence']}: source exists; reconcile manually")
        token = uuid4().hex
        chosen.update(status="generating", claimed_at=timestamp(),
                      claim_token=token, attempts=chosen.get("attempts", 0) + 1)
        try:
            sha = queue.commit_files(
                head, tree, {MANIFEST: json_bytes(manifest)},
                f"Reserve After the Bells story {chosen['sequence']:02d}")
        except ApiError as exc:
            if exc.code in (409, 422):
                continue
            raise
        return {"status": "claimed", "sequence": chosen["sequence"],
                "title": chosen["title"], "claim_token": token, "commit": sha}
    raise QueueError("concurrent claims prevented reservation; retry later")


def submit(queue: GitHub, token: str, sequence: int,
           manuscript: bytes, metadata: bytes) -> dict:
    head, tree, manifest = queue.snapshot()
    slot = manifest["slots"][sequence - 1]
    info = validate_manuscript(slot, manuscript, metadata)
    path_md = BASE + "/" + slot["markdown"]
    path_meta = BASE + "/" + slot["metadata"]
    existing_md = queue.file_at(path_md, head)
    existing_meta = queue.file_at(path_meta, head)
    if slot["status"] in {"draft", "approved", "published"}:
        if existing_md == manuscript and existing_meta == metadata:
            return {"status": "already_submitted", "sequence": sequence}
        raise QueueError("existing manuscript is different; use review PR, do not overwrite")
    if slot["status"] != "generating" or slot.get("claim_token") != token:
        raise QueueError("missing/mismatched reservation; submit refused")
    if existing_md is not None or existing_meta is not None:
        raise QueueError("partial or conflicting files; reconcile manually")
    slot.pop("claim_token", None)
    slot.pop("claimed_at", None)
    slot.update(status="draft", drafted_at=timestamp(),
                sha256=info["sha256"], word_count=info["words"])
    commit = queue.commit_files(
        head, tree, {MANIFEST: json_bytes(manifest),
                     path_md: manuscript, path_meta: metadata},
        f"Stage After the Bells story {sequence:02d} for editorial review")
    return {"status": "draft", "sequence": sequence, "commit": commit,
            "word_count": info["words"]}


def release(queue: GitHub, token: str, sequence: int) -> dict:
    head, tree, manifest = queue.snapshot()
    slot = manifest["slots"][sequence - 1]
    if slot["status"] != "generating" or slot.get("claim_token") != token:
        raise QueueError("cannot release another worker's reservation")
    for path in (slot["markdown"], slot["metadata"]):
        if queue.file_at(BASE + "/" + path, head) is not None:
            raise QueueError("source file exists; manual reconciliation required")
    slot.pop("claim_token", None)
    slot.pop("claimed_at", None)
    slot["status"] = "planned"
    commit = queue.commit_files(
        head, tree, {MANIFEST: json_bytes(manifest)},
        f"Release failed After the Bells story {sequence:02d} reservation")
    return {"status": "planned", "sequence": sequence, "commit": commit}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--branch", default="main")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--root", type=Path, default=Path(BASE))
    sub.add_parser("claim")
    s = sub.add_parser("submit")
    s.add_argument("--sequence", type=int, choices=range(1, 11), required=True)
    s.add_argument("--token", required=True)
    s.add_argument("--story", type=Path, required=True)
    s.add_argument("--metadata", type=Path, required=True)
    r = sub.add_parser("release")
    r.add_argument("--sequence", type=int, choices=range(1, 11), required=True)
    r.add_argument("--token", required=True)
    opts = parser.parse_args()
    try:
        if opts.command == "validate":
            result = validate_local(opts.root)
        else:
            queue = GitHub(opts.repo, opts.branch)
            if opts.command == "claim":
                result = claim(queue)
            elif opts.command == "submit":
                result = submit(queue, opts.token, opts.sequence,
                                opts.story.read_bytes(), opts.metadata.read_bytes())
            else:
                result = release(queue, opts.token, opts.sequence)
        print(json.dumps(result, ensure_ascii=False))
    except (QueueError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
