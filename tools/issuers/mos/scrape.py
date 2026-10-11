import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from official_api import collect_mos, snapshot
if __name__=='__main__':snapshot('mos',*collect_mos())
