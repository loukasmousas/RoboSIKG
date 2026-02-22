from __future__ import annotations

import argparse
import os
from dataclasses import replace
from pathlib import Path
import sys
from typing import TYPE_CHECKING

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

if TYPE_CHECKING:
    from robosikg.agent.orchestrator import Orchestrator
    from robosikg.config import DemoConfig

DEFAULT_NIM_BASE_URL = os.getenv("ROBOSIKG_NIM_BASE_URL", "http://160.211.46.122:8000/v1")
DEFAULT_MODEL_NAME = os.getenv("ROBOSIKG_MODEL_NAME", "nvidia/cosmos-reason2-8b")


def build_config(args: argparse.Namespace):
    from robosikg.config import DemoConfig

    cfg = DemoConfig()
    ingest_cfg = replace(
        cfg.ingest,
        sample_fps=args.sample_fps,
        max_frames=args.max_frames,
    )
    perception_cfg = replace(
        cfg.perception,
        device=args.device,
        pretrained=args.pretrained,
        score_thresh=args.score_thresh,
        require_cuda=(args.device == "cuda"),
    )
    reasoning_cfg = replace(
        cfg.reasoning,
        mode=args.reasoning_mode,
        reason_every_n_frames=args.reason_every_n_frames,
        nim_base_url=args.nim_base_url,
        model_name=args.model_name,
        debug_capture=args.reasoning_debug,
    )
    return replace(cfg, ingest=ingest_cfg, perception=perception_cfg, reasoning=reasoning_cfg)


def parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mp4", required=True, help="Path to input MP4 file.")
    ap.add_argument("--out", default="out_demo", help="Output directory for artifacts.")
    ap.add_argument("--source-id", default="demo_video", help="Deterministic source identifier.")
    ap.add_argument("--reasoning-mode", choices=["auto", "nim", "mock"], default="auto")
    ap.add_argument("--device", choices=["cuda", "cpu"], default="cuda")
    ap.add_argument("--pretrained", action=argparse.BooleanOptionalAction, default=True)
    ap.add_argument("--score-thresh", type=float, default=0.5)
    ap.add_argument("--max-frames", type=int, default=500)
    ap.add_argument("--sample-fps", type=float, default=5.0)
    ap.add_argument("--reason-every-n-frames", type=int, default=50)
    ap.add_argument("--reasoning-debug", action=argparse.BooleanOptionalAction, default=False)
    ap.add_argument("--nim-base-url", default=DEFAULT_NIM_BASE_URL)
    ap.add_argument("--model-name", default=DEFAULT_MODEL_NAME)
    return ap.parse_args()


def main() -> None:
    args = parse_args()
    os.makedirs(args.out, exist_ok=True)

    cfg = build_config(args)
    from robosikg.agent.orchestrator import Orchestrator

    orch = Orchestrator(cfg=cfg, source_id=args.source_id, out_dir=args.out)
    summary = orch.run_mp4(args.mp4)

    print("Wrote artifacts:", summary["artifacts"])
    print("Reasoning backend:", summary["reasoning_backend"])
    print("Run summary:", os.path.join(args.out, "run_summary.json"))


if __name__ == "__main__":
    main()
