"""Run the real development verification suite from any working directory."""
from pathlib import Path
import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET


def escape(value):
    return value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')


def main():
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix='lottery-check-') as directory:
        report = Path(directory) / 'results.xml'
        result = subprocess.run([sys.executable, '-m', 'pytest', '-q', f'--junitxml={report}'], cwd=root)
        if result.returncode and os.environ.get('GITHUB_ACTIONS') == 'true' and report.exists():
            for case in ET.parse(report).iter('testcase'):
                for tag in ('failure', 'error'):
                    for failure in case.findall(tag):
                        name = escape(case.get('name', 'pytest'))
                        message = escape((failure.text or failure.get('message', 'Test failed'))[:20000])
                        print(f'::error title={name}::{message}', flush=True)
        return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())
