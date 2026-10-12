import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ramen_official import collect_yamaokaya, snapshot
if __name__ == '__main__':
    snapshot('yamaokaya', *collect_yamaokaya())
