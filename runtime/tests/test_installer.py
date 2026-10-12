"""Test suite for deployment installers and air-gapped DDIL execution."""

import os
import subprocess
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
INSTALL_SCRIPT = os.path.join(REPO_ROOT, "deploy", "install_runtime.sh")
GATEWAY_SCRIPT = os.path.join(REPO_ROOT, "deploy", "install_gateway.sh")


class TestDeployInstallers(unittest.TestCase):
    """Verify deployment scripts, airgap options, and bash syntax."""

    def test_installer_syntax(self):
        """Validate bash syntax for runtime, gateway, and runner scripts."""
        runner_script = os.path.join(REPO_ROOT, "scripts", "run_runtime.sh")
        for script in [INSTALL_SCRIPT, GATEWAY_SCRIPT, runner_script]:
            res = subprocess.run(
                ["bash", "-n", script],
                capture_output=True,
                text=True,
            )
            self.assertEqual(res.returncode, 0, f"Syntax error in {script}: {res.stderr}")

    def test_runtime_installer_help_flag(self):
        """Verify --help flag exits cleanly and displays airgap/gateway options."""
        res = subprocess.run(
            ["bash", INSTALL_SCRIPT, "--help"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 0)
        self.assertIn("--offline", res.stdout)
        self.assertIn("--airgap", res.stdout)
        self.assertIn("--skip-deps", res.stdout)
        self.assertIn("--gateway-ip", res.stdout)
        self.assertIn("--gateway-port", res.stdout)

    def test_runtime_installer_non_root_guard(self):
        """Verify non-root execution cleanly exits with error code 1."""
        res = subprocess.run(
            ["bash", INSTALL_SCRIPT, "--offline"],
            capture_output=True,
            text=True,
        )
        self.assertEqual(res.returncode, 1)
        self.assertIn("must be run as root", res.stderr)


if __name__ == "__main__":
    unittest.main()
