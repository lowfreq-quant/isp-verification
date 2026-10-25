"""Run the SDRAM write/read replay-chain verification.

Two checks in one flow:
  1. functional: 1024 words are written through the write FIFO, streamed
     into the SDRAM model and read back through the read FIFO; every word
     must match (tb_sdram_loop_dump.v self-check).
  2. cycle-exact: the per-cycle trace of the whole chain (sdram_ctrl FSM,
     command bus, FIFO handshakes, addresses, DQ/rdata) is compared against
     the Python replica in verify_sdram_loop.py; max_diff must be 0.

Usage:
    python run_sdram_loop.py
"""

import os
import subprocess
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
# RTL root = the image-processing checkout. Default: parent of this suite
# (in-tree layout <project>/sim/). Set RTL_ROOT for out-of-tree use.
RTL_ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))
IVERILOG = os.path.join(
    os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"),
    "iverilog" + (".exe" if os.name == "nt" else ""))
VVP = os.path.join(
    os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"),
    "vvp" + (".exe" if os.name == "nt" else ""))

SOURCES = [
    os.path.join(SIM_DIR, "ip", "sdram_ip_wrappers.v"),
    os.path.join(RTL_ROOT, "sdram_controller", "sdram_top.v"),
    os.path.join(RTL_ROOT, "sdram_controller", "sram_ctrl.v"),
    os.path.join(RTL_ROOT, "sdram_controller", "fifo_ctrl.v"),
    os.path.join(RTL_ROOT, "sdram_controller", "sdram_model.v"),
    os.path.join(SIM_DIR, "tb_sdram_loop_dump.v"),
]
OUT_VVP = os.path.join(SIM_DIR, "sdram_loop_dump.vvp")


def main():
    os.chdir(SIM_DIR)
    os.makedirs(os.path.join(SIM_DIR, "output"), exist_ok=True)

    print("=== compile tb_sdram_loop_dump ===")
    r = subprocess.run([IVERILOG, "-g2012", "-s", "tb_sdram_loop_dump",
                        "-o", OUT_VVP] + SOURCES, capture_output=True, text=True)
    if r.returncode != 0:
        print("Compile FAILED")
        print(r.stderr[:2000])
        print("Overall: FAIL")
        sys.exit(1)

    print("=== simulate: 1024-word write -> read round trip ===")
    r = subprocess.run([VVP, OUT_VVP], capture_output=True, text=True)
    out = (r.stdout or "") + (r.stderr or "")
    print(out[-1200:])
    ok_roundtrip = ">>> PASS: SDRAM write->read round trip preserves data" in out
    print(f"  round-trip: {'PASS' if ok_roundtrip else 'FAIL'}")

    print("=== compare per-cycle trace with the Python model ===")
    r = subprocess.run([sys.executable, "verify_sdram_loop.py"],
                       capture_output=True, text=True)
    print((r.stdout or "")[-1200:])
    ok_cycle = (r.returncode == 0 and
                ">>> PASS: cycle-exact match" in (r.stdout or ""))

    ok = ok_roundtrip and ok_cycle
    print(f"\nOverall: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
