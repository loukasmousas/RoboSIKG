from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", required=True, help="Path to run_summary.json")
    args = ap.parse_args()

    with open(args.run, "r", encoding="utf-8") as f:
        summary = json.load(f)

    counts = summary.get("counts", {})
    timing = summary.get("timing", {})
    report = {
        "source_id": summary.get("source_id"),
        "reasoning_backend": summary.get("reasoning_backend"),
        "reasoning_fallbacks": summary.get("reasoning_fallbacks", 0),
        "errors_count": len(summary.get("errors", [])),
        "frames_seen": counts.get("frames_seen"),
        "regions_added": counts.get("regions_added"),
        "tracks_seen": counts.get("tracks_seen"),
        "kg_triples": counts.get("kg_triples"),
        "vector_items": counts.get("vector_items"),
        "reasoning_invocations": counts.get("reasoning_invocations"),
        "effective_fps": timing.get("effective_fps"),
    }

    out = os.path.join(os.path.dirname(args.run), "eval_report.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, sort_keys=True)
    print("Wrote:", out)


if __name__ == "__main__":
    main()
