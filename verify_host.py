"""Run on the Linux host before serving the app. No AI requests or charges."""

from pathlib import Path
import subprocess
import sys
import tempfile

from lesson_tools import render_environment, sandbox_command


def main():
    with tempfile.TemporaryDirectory(prefix="manim-check-") as temporary:
        directory = Path(temporary).resolve()
        code = """
import os, socket
from pathlib import Path
import manim
assert not Path('/app/.env').exists()
assert not Path('/app/app.py').exists()
assert not any('KEY' in name or 'TOKEN' in name for name in os.environ)
try:
    socket.create_connection(('1.1.1.1', 443), timeout=2)
except OSError:
    pass
else:
    raise RuntimeError('Network isolation failed')
print('Isolated Manim import passed')
"""
        result = subprocess.run(sandbox_command([sys.executable, "-c", code], directory),
                                env=render_environment(directory), capture_output=True, text=True, timeout=30)
        if result.returncode:
            print("Host isolation check failed. Do not disable the sandbox to deploy.")
            print(result.stderr[-2000:])
            raise SystemExit(1)
        print(result.stdout)


if __name__ == "__main__":
    main()
