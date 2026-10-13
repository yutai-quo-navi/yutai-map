import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ohsho_joyfull import collect_ohsho, snapshot
if __name__ == "__main__":
    snapshot("ohsho", *collect_ohsho())
