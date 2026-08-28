from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "src"))

from launchpilot.evaluation.task_dataset_cli import main

if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.argv.append(str(ROOT / "evals" / "datasets" / "marketing-ops-task-v1"))
    main()
