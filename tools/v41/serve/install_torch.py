"""Install the pictures dependency for this Python's architecture and version."""
import argparse
import subprocess
import sys
import sysconfig


NVIDIA_INDEX = "https://pypi.nvidia.com/nvtorch_oot/"


def wheel_source(device, python_platform=None, python_version=None):
    """Select wheels for the interpreter, including x64 Python running on an ARM64 host."""
    python_platform = python_platform or sysconfig.get_platform()
    python_version = python_version or sys.version_info[:2]
    # The upstream CPU index has Windows ARM64 wheels through Python 3.13, but none for 3.14.
    # NVIDIA's stable Windows ARM64 build supports 3.14 and also runs CPU tensors.
    # https://github.com/NVIDIA/pytorch-windows-ci#install-built-wheels
    if python_platform == "win-arm64" and (device == "cuda" or python_version >= (3, 14)):
        return "torch==2.14.0+cu134", ["--extra-index-url", NVIDIA_INDEX]
    variant = "cu130" if device == "cuda" else "cpu"
    return f"torch==2.14.1+{variant}", ["--index-url", f"https://download.pytorch.org/whl/{variant}"]


def install(device):
    package, index = wheel_source(device)
    print(f"Installing {package} for {sysconfig.get_platform()}, Python {sys.version_info.major}."
          f"{sys.version_info.minor} from {index[1]} ...", flush=True)
    if index[1] == NVIDIA_INDEX and device == "cpu":
        print("Windows ARM64 Python 3.14 needs NVIDIA's CUDA-enabled wheel (~1.9 GB); "
              "pictures will still run on the CPU.", flush=True)
    # Let pip resolve and download before replacing an installed torch. An unavailable wheel should not
    # remove a working installation. Explicit local versions also allow a CPU -> CUDA replacement.
    subprocess.run([sys.executable, "-m", "pip", "install", "--disable-pip-version-check", package, *index],
                   check=True)
    check = ("import torch; x=torch.ones((2,2)); "
             "assert torch.equal(x @ x, torch.full((2,2), 2.)); "
             "print('PyTorch', torch.__version__, '- CPU tensor check passed')")
    if device == "cuda":
        check += ("; assert torch.cuda.is_available(), 'CUDA is unavailable in this PyTorch'; "
                  "x=x.cuda(); assert (x @ x).sum().item() == 8; "
                  "print('CUDA tensor check passed')")
    subprocess.run([sys.executable, "-c", check], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("device", choices=["cpu", "cuda"])
    args = parser.parse_args()
    try:
        install(args.device)
    except subprocess.CalledProcessError as error:
        return error.returncode or 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
