"""Run the native executable offline with no Python executable on PATH."""

import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("executable", type=Path)
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("--gui", action="store_true")
    args = parser.parse_args()
    executable, snapshot = args.executable.resolve(), args.snapshot.resolve()
    environment = dict(os.environ)
    # Keep OS DLL discovery, but remove Python and other development tools.
    system_root = environment.get("SystemRoot")
    environment["PATH"] = str(Path(system_root) / "System32") if system_root else ""
    for name in ("PYTHONHOME", "PYTHONPATH", "VIRTUAL_ENV", "UV_PROJECT_ENVIRONMENT"):
        environment.pop(name, None)
    environment.update(
        HTTP_PROXY="http://127.0.0.1:9",
        HTTPS_PROXY="http://127.0.0.1:9",
        ALL_PROXY="http://127.0.0.1:9",
        NO_PROXY="",
    )
    with tempfile.TemporaryDirectory(prefix="lottery-packaged-") as directory:
        output = Path(directory) / "result"
        subprocess.run(
            [
                str(executable),
                "--require-frozen",
                "--self-test",
                str(snapshot),
                "--output",
                str(output),
            ],
            cwd=directory,
            env=environment,
            check=True,
            timeout=180,
        )
        proof = (output / "smoke-passed.txt").read_text(encoding="utf-8")
        if "frozen=True\n" not in proof or "classes=22\n" not in proof:
            raise RuntimeError("Packaged smoke did not prove a frozen 22-class draw")
        print(proof)
        if args.gui:
            subprocess.run(
                [str(executable), "--require-frozen", "--gui-smoke"],
                cwd=directory,
                env=environment,
                check=True,
                timeout=60,
            )


if __name__ == "__main__":
    main()
