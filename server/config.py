import os
from pathlib import Path

CAMPAIGNS_ROOT = Path(os.environ.get("CAMPAIGNS_ROOT", Path(__file__).parent.parent / "campaigns"))
