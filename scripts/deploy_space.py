"""Upload only app files through the pinned SDK and wait for the Space to run."""
import os
from pathlib import Path
import time
from urllib.request import urlopen

from huggingface_hub import HfApi
from huggingface_hub.utils import validate_repo_id

ROOT = Path(__file__).resolve().parents[1]
APP_FILES = ['README.md', 'hf_app.py', 'requirements.txt', 'recruiterradar/*.py',
             'recruiterradar/providers/*.py']


def check_space_hardware(api, repo_id):
    """Validate hardware without changing the user's hosting plan or allocation."""
    runtime = api.get_space_runtime(repo_id)
    target = runtime.requested_hardware or runtime.hardware
    target = getattr(target, 'value', target)
    if target and target.startswith('zero-'):
        raise RuntimeError(
            'This API-backed app cannot run on ZeroGPU: it has no local GPU function. '
            'Select CPU hardware if your plan permits it, or use another Python host. '
            'CPU Basic has no hourly charge but compute Spaces may require a paid plan. '
            'No hardware changes were made.'
        )


def wait_for_space(api, repo_id, commit_sha, timeout=900):
    deadline = time.monotonic() + timeout
    last_stage = None
    while time.monotonic() < deadline:
        info = api.space_info(repo_id)
        runtime = api.get_space_runtime(repo_id)
        stage = getattr(runtime.stage, 'value', runtime.stage)
        if stage != last_stage:
            print(f'Space status: {stage}', flush=True)
            last_stage = stage
        if stage in {'BUILD_ERROR', 'RUNTIME_ERROR', 'CONFIG_ERROR', 'PAUSED'}:
            log_type = 'container' if stage == 'RUNTIME_ERROR' else 'build'
            raise RuntimeError(f'Space failed: {stage}. See https://huggingface.co/spaces/{repo_id}?logs={log_type}')
        if info.sha != commit_sha:
            raise RuntimeError('Space revision changed during deployment; inspect concurrent uploads.')
        if stage == 'RUNNING' and info.host:
            try:
                with urlopen(f"{info.host.rstrip('/')}/config", timeout=15) as response:
                    if response.status == 200:
                        print(f'Space is running: https://huggingface.co/spaces/{repo_id}')
                        return
            except OSError:
                pass
        time.sleep(15)
    raise RuntimeError(f'Space did not become healthy within {timeout}s. Inspect its build/runtime logs.')


def main():
    repo_id = os.environ.get('HF_SPACE_ID', '').strip()
    token = os.environ.get('HF_TOKEN', '').strip()
    if not repo_id or '/' not in repo_id:
        raise ValueError('Set GitHub Actions variable HF_SPACE_ID to attem03/RecruiterRadar.')
    validate_repo_id(repo_id)
    if not token:
        raise ValueError('Set GitHub Actions secret HF_TOKEN to a Hugging Face write token.')
    api = HfApi(token=token)
    info = api.space_info(repo_id)  # Verify access to the existing Space before upload.
    if info.sdk != 'gradio':
        raise ValueError('The target Space must use the Gradio SDK.')
    check_space_hardware(api, repo_id)
    commit = api.upload_folder(
        repo_id=repo_id, repo_type='space', folder_path=ROOT,
        allow_patterns=APP_FILES, ignore_patterns=['**/__pycache__/*', '*.pyc'],
        delete_patterns=['recruiterradar/*.py', 'recruiterradar/providers/*.py'],
        commit_message=f"Deploy GitHub {os.environ.get('GITHUB_SHA', 'manual')}",
    )
    # Restart also handles a no-change rerun of a previously failed deployment.
    api.restart_space(repo_id)
    time.sleep(15)
    wait_for_space(api, repo_id, commit.oid)


if __name__ == '__main__':
    main()
