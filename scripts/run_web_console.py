from __future__ import annotations

from pathlib import Path
import sys

import uvicorn

if __package__ is None or __package__ == "":
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def main() -> None:
    uvicorn.run(
        "robosikg.web.app:create_app",
        factory=True,
        host="0.0.0.0",
        port=8080,
        reload=False,
    )


if __name__ == "__main__":
    main()
