"""Validate the same entrypoint and HTTP routes used by Spaces, without API calls."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

import yaml

ROOT = Path(__file__).resolve().parents[1]


def main():
    metadata = yaml.safe_load((ROOT / 'README.md').read_text().split('---', 2)[1])
    assert metadata['sdk'] == 'gradio'
    colors = {'red', 'yellow', 'green', 'blue', 'indigo', 'purple', 'pink', 'gray'}
    assert metadata['colorFrom'] in colors and metadata['colorTo'] in colors
    assert metadata['app_file'] == 'hf_app.py'
    assert str(metadata['python_version']) == '3.12'
    assert metadata['sdk_version'] == importlib.metadata.version('gradio')
    env = dict(os.environ, GRADIO_ANALYTICS_ENABLED='False', GRADIO_SERVER_PORT='7860',
               GRADIO_SERVER_NAME='127.0.0.1')
    with tempfile.TemporaryFile(mode='w+') as log:
        process = subprocess.Popen([sys.executable, 'hf_app.py'], cwd=ROOT, env=env,
                                   stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 90
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError('Gradio exited during startup')
                try:
                    with urlopen('http://127.0.0.1:7860/config', timeout=2) as response:
                        config = json.load(response)
                    assert config['dependencies'], 'Missing evaluation event'
                    with urlopen('http://127.0.0.1:7860/', timeout=2) as response:
                        assert response.status == 200
                    print('Space metadata, Gradio startup, page and callback configuration passed.')
                    return
                except (OSError, ValueError):
                    time.sleep(1)
            raise RuntimeError('Gradio startup timed out')
        except Exception:
            log.seek(0)
            print(log.read())
            raise
        finally:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


if __name__ == '__main__':
    main()
