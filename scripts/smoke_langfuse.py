"""Run the bounded Langfuse Japan connectivity smoke without exposing secrets."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from src.infrastructure.config.settings import Settings
from src.observability import run_langfuse_smoke


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/phase2_1/langfuse/smoke_result.json"),
    )
    args = parser.parse_args()
    result = asdict(run_langfuse_smoke(Settings().langfuse))
    result["classification"] = result["classification"].value
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
