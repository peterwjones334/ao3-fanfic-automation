"""Validate and ingest GitHub-delivered After the Bells pairs; never publish."""
import argparse
import json
from pathlib import Path
from ao3_pipeline.models import Metadata
from ao3_pipeline.pipeline import Pipeline
from ao3_pipeline.store import Store

def load(root):
    pairs = []
    for number in range(1, 11):
        stem = f"story-{number:02d}"
        md, meta = root / (stem + ".md"), root / (stem + ".json")
        if not md.exists() and not meta.exists():
            continue
        if not md.is_file() or not meta.is_file() or md.is_symlink() or meta.is_symlink():
            raise ValueError(f"{stem}: require both regular source files")
        metadata = Metadata.model_validate_json(meta.read_text(encoding="utf-8"))
        if metadata.work_id != f"after-the-bells-{number:02d}" or metadata.chapter != 1 or not metadata.complete:
            raise ValueError(f"{stem}: require stable standalone work ID, chapter 1, complete")
        body = md.read_text(encoding="utf-8")
        if not body.strip():
            raise ValueError(f"{stem}: empty story")
        pairs.append((number, metadata, body))
    unexpected = [p.name for p in root.glob("story-*") if p.suffix in {".md", ".json"} and p.stem not in {f"story-{i:02d}" for i in range(1,11)}]
    if unexpected:
        raise ValueError(f"unexpected story files: {unexpected}")
    return pairs

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", type=Path, default=Path("stories/after-the-bells"))
    p.add_argument("--db", type=Path, help="Explicit local database; omit to validate only")
    args = p.parse_args()
    pairs = load(args.source)
    if not args.db:
        print(json.dumps({"validated": [n for n, _, _ in pairs], "expected": 10}))
        return
    pipe = Pipeline(Store(args.db))
    result = []
    for number, meta, body in pairs:
        revision = pipe.ingest(meta, body)
        result.append({"sequence": number, "revision": revision, "state": pipe.inspect(revision)["state"]})
    print(json.dumps(result))
if __name__ == "__main__":
    main()
