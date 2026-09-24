"""Deployment gates: failures must not be reported as successful deployments."""
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from huggingface_hub import SpaceStage
from scripts.deploy_space import check_space_hardware, wait_for_space


class DeploymentTests(unittest.TestCase):
    def api(self, stage, sha='expected'):
        api = Mock()
        api.space_info.return_value = SimpleNamespace(sha=sha, host='https://example.test')
        api.get_space_runtime.return_value = SimpleNamespace(stage=stage)
        return api

    def test_zerogpu_is_rejected_without_changing_hardware(self):
        for current, requested in [('zero-a10g', None), ('cpu-basic', 'zero-a10g')]:
            api = Mock()
            api.get_space_runtime.return_value = SimpleNamespace(
                hardware=current, requested_hardware=requested)
            with self.assertRaisesRegex(RuntimeError, 'cannot run on ZeroGPU'):
                check_space_hardware(api, 'owner/space')
            api.request_space_hardware.assert_not_called()

    def test_cpu_or_pending_cpu_needs_no_change(self):
        for current, requested in [('cpu-basic', None), ('zero-a10g', 'cpu-basic')]:
            api = Mock()
            api.get_space_runtime.return_value = SimpleNamespace(
                hardware=current, requested_hardware=requested)
            check_space_hardware(api, 'owner/space')
            api.request_space_hardware.assert_not_called()

    def test_running_requires_http_health(self):
        with patch('scripts.deploy_space.urlopen') as request:
            request.return_value.__enter__.return_value.status = 200
            wait_for_space(self.api(SpaceStage.RUNNING), 'owner/space', 'expected')
            request.assert_called_once_with('https://example.test/config', timeout=15)

    def test_build_and_runtime_errors_fail(self):
        for stage in (SpaceStage.BUILD_ERROR, SpaceStage.RUNTIME_ERROR, 'CONFIG_ERROR', SpaceStage.PAUSED):
            with self.subTest(stage=stage), self.assertRaisesRegex(RuntimeError, 'Space failed'):
                wait_for_space(self.api(stage), 'owner/space', 'expected')

    def test_unexpected_revision_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'revision changed'):
            wait_for_space(self.api(SpaceStage.RUNNING, 'different'), 'owner/space', 'expected')

    def test_timeout_fails(self):
        with self.assertRaisesRegex(RuntimeError, 'did not become healthy'):
            wait_for_space(self.api(SpaceStage.BUILDING), 'owner/space', 'expected', timeout=0)
