"""Compile and run the sobel/canny threshold-path testbenches, then verify.

Produces sim/sobel_thresh_dump.txt and sim/canny_thresh_dump.txt and
compares them against cycle-accurate Python models via verify_thresh_path.py.

Usage:
    python sim/run_thresh.py
"""

import os
import subprocess
import sys


SIM_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))
IVERILOG = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "iverilog.exe")
VVP = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "vvp.exe")

IP_SOURCES = [
    os.path.join(SIM_DIR, "ip", "behavioral_fifo.v"),
    os.path.join(SIM_DIR, "ip", "behavioral_cordic.v"),
    os.path.join(SIM_DIR, "ip", "ip_wrappers.v"),
]
MATRIX = os.path.join(ROOT, "image_processing", "Matrix_generator",
                      "matrix_generator.v")
SOBEL = os.path.join(ROOT, "image_processing", "Canny_detection", "sobel.v")
CANNY = os.path.join(ROOT, "image_processing", "Canny_detection", "canny.v")

TBS = [
    ("tb_sobel_thresh", [SOBEL, os.path.join(SIM_DIR, "tb_sobel_thresh.v")],
     "sobel_thresh.vvp"),
    ("tb_canny_thresh", [CANNY, os.path.join(SIM_DIR, "tb_canny_thresh.v")],
     "canny_thresh.vvp"),
]


def run(cmd, cwd):
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)
    return result.returncode == 0


def main():
    ok = True
    for top, extra, out_vvp in TBS:
        cmd = [IVERILOG, "-g2012", "-s", top, "-o", out_vvp,
               *IP_SOURCES, MATRIX, *extra]
        print(f"[compile] {' '.join(cmd)}")
        if not run(cmd, SIM_DIR):
            ok = False
            print(f"ERROR: compilation of {top} failed")
            continue
        print(f"[run] {VVP} {out_vvp}")
        if not run([VVP, out_vvp], SIM_DIR):
            ok = False
            print(f"ERROR: simulation of {top} failed")

    if not ok:
        sys.exit(1)

    print("\n[verify] python verify_thresh_path.py")
    verifier = os.path.join(SIM_DIR, "verify_thresh_path.py")
    r = subprocess.run([sys.executable, verifier], cwd=SIM_DIR,
                       capture_output=True, text=True)
    print(r.stdout)
    if r.stderr:
        print(r.stderr)
    sys.exit(r.returncode)


if __name__ == "__main__":
    main()
