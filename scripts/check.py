"""Run the real development verification suite from any working directory."""
from pathlib import Path
import subprocess
import sys

root = Path(__file__).resolve().parents[1]
raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q'], cwd=root))
