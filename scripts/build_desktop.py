"""Build a native one-folder application, distributable ZIP, and SHA-256 file."""

import argparse
import hashlib
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("dist"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    environment["PYINSTALLER_CONFIG_DIR"] = str(output / "build" / "pyinstaller-cache")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--distpath",
            str(output),
            "--workpath",
            str(output / "build"),
            str(root / "packaging" / "lottery.spec"),
        ],
        cwd=root,
        env=environment,
        check=True,
    )
    application = output / "PTACarnivalLottery"
    archive = output / f"PTACarnivalLottery-{platform.system()}-{platform.machine()}"
    zip_path = Path(
        shutil.make_archive(
            str(archive), "zip", root_dir=output, base_dir=application.name
        )
    )
    sha = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    zip_path.with_suffix(".zip.sha256").write_text(
        f"{sha}  {zip_path.name}\n", encoding="ascii"
    )
    print(zip_path)


if __name__ == "__main__":
    main()
