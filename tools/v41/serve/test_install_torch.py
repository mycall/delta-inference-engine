"""PyTorch wheel selection checks; no downloads."""
import unittest
from unittest.mock import patch

import install_torch


class TorchInstallTests(unittest.TestCase):
    def test_arm64_python314_cpu_uses_available_vendor_wheel(self):
        self.assertEqual(install_torch.wheel_source("cpu", "win-arm64", (3, 14)),
                         ("torch==2.14.0+cu134", ["--extra-index-url", install_torch.NVIDIA_INDEX]))

    def test_arm64_python313_cpu_keeps_upstream_cpu_wheel(self):
        self.assertEqual(install_torch.wheel_source("cpu", "win-arm64", (3, 13)),
                         ("torch==2.14.1+cpu", ["--index-url", "https://download.pytorch.org/whl/cpu"]))

    def test_arm64_cuda_uses_vendor_index(self):
        for version in [(3, 13), (3, 14)]:
            self.assertEqual(install_torch.wheel_source("cuda", "win-arm64", version)[0],
                             "torch==2.14.0+cu134")

    def test_x64_interpreter_keeps_x64_wheels_even_on_arm_host(self):
        for device, variant in [("cpu", "cpu"), ("cuda", "cu130")]:
            self.assertEqual(install_torch.wheel_source(device, "win-amd64", (3, 14)),
                             (f"torch==2.14.1+{variant}",
                              ["--index-url", f"https://download.pytorch.org/whl/{variant}"]))

    def test_failed_resolution_does_not_uninstall_existing_torch(self):
        error = install_torch.subprocess.CalledProcessError(1, "pip")
        with patch.object(install_torch.subprocess, "run", side_effect=error) as run:
            with self.assertRaises(install_torch.subprocess.CalledProcessError):
                install_torch.install("cpu")
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0][1:4], ["-m", "pip", "install"])


if __name__ == "__main__":
    unittest.main()
