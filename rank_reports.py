"""Load the project Skill's rank engine for the optional UI and showcase builder."""

import importlib.util
from pathlib import Path

path = Path(__file__).parent / ".agents/skills/amazon-seller-ops/scripts/track_keyword_ranks.py"
spec = importlib.util.spec_from_file_location("keyword_rank_engine", path)
engine = importlib.util.module_from_spec(spec)
spec.loader.exec_module(engine)

consolidate = engine.consolidate
load_observations = engine.load_observations
rank_workbook = engine.rank_workbook
HEADERS = engine.HEADERS
