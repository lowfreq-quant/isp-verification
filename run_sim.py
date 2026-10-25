"""Cocotb + Icarus Verilog runner for RGB2YUV module."""
import subprocess
import os
import sys

PROJECT_ROOT = os.environ.get("RTL_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SIM_DIR = os.path.dirname(os.path.abspath(__file__))
VERILOG_SRC_RGB2YUV = os.path.join(PROJECT_ROOT, "image_processing", "RGB_to_YUV", "RGB2YUV.v")
VERILOG_SRC_TB = os.path.join(SIM_DIR, "tb_top.v")
IVERILOG_BIN = os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin")
IVERILOG = os.path.join(IVERILOG_BIN, "iverilog" + (".exe" if os.name == "nt" else ""))
VVP = os.path.join(IVERILOG_BIN, "vvp" + (".exe" if os.name == "nt" else ""))

import cocotb
COCOTB_DIR = os.path.dirname(cocotb.__file__)
COCOTB_LIBS = os.path.join(COCOTB_DIR, "libs")

OUTPUT = os.path.join(SIM_DIR, "sim.vvp")

# Fix: create hon313.dll -> python313.dll symlink/copy if needed
PYTHON_DIR = os.path.dirname(sys.executable)  # C:\Users\ty\anaconda3
HON313 = os.path.join(COCOTB_LIBS, "hon313.dll")
PY313 = os.path.join(PYTHON_DIR, "python313.dll")
if not os.path.exists(HON313) and os.path.exists(PY313):
    print(f"Creating hon313.dll -> python313.dll copy for embed.dll dependency")
    import shutil
    shutil.copy2(PY313, HON313)

def build():
    print("=== Compiling Verilog with iverilog ===")
    cmd = [
        IVERILOG,
        "-o", OUTPUT,
        "-g2012",
        "-s", "tb_top",
        VERILOG_SRC_RGB2YUV,
        VERILOG_SRC_TB
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        print("STDOUT:", result.stdout)
        sys.exit(1)
    print("Compilation OK")
    if result.stderr:
        print("Warnings:", result.stderr)

def run():
    print("\n=== Running cocotb simulation ===")
    env = os.environ.copy()
    # Add all relevant paths to PATH for DLL resolution
    env["PATH"] = os.pathsep.join([IVERILOG_BIN, COCOTB_LIBS, PYTHON_DIR, env['PATH']])
    env["MODULE"] = "test_rgb2yuv"
    env["COCOTB_TEST_MODULES"] = "test_rgb2yuv"
    env["TOPLEVEL"] = "tb_top"
    env["COCOTB_TOPLEVEL"] = "tb_top"
    env["TOPLEVEL_LANG"] = "verilog"
    env["COCOTB_SIM"] = "1"
    env["SIM"] = "icarus"
    env["COCOTB_LIB"] = COCOTB_LIBS
    env["PYGPI_PYTHON_BIN"] = sys.executable
    env["PYTHONPATH"] = SIM_DIR  # Add test directory to Python path
    env["COCOTB_VCD"] = os.path.join(SIM_DIR, "waveform.vcd")

    cmd = [
        VVP,
        "-M", COCOTB_LIBS,
        "-m", "cocotbvpi_icarus",
        OUTPUT
    ]
    print(" ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=SIM_DIR)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:3000])
    if result.returncode != 0:
        print(f"\nSimulation FAILED with code {result.returncode}")
        sys.exit(1)
    print("Simulation PASSED")

def clean():
    for f in [OUTPUT, os.path.join(SIM_DIR, "waveform.vcd"), HON313]:
        if os.path.exists(f):
            os.remove(f)
            print(f"Removed {f}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "clean":
        clean()
    else:
        build()
        run()
