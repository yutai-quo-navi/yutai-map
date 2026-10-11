import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from official_api import collect_dnh, snapshot
if __name__=='__main__':snapshot('dnh',*collect_dnh())
