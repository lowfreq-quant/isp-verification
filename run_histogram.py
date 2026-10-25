"""Standalone iverilog simulation for HISTOGRAM module (contrast stretching)."""
import subprocess
import os
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))
HIST_SRC = os.path.join(PROJECT_ROOT, "image_processing", "Histogram", "HISTOGRAM.v")
TB_SRC = os.path.join(SIM_DIR, "tb_histogram.v")
IVERILOG = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "iverilog.exe")
VVP = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "vvp.exe")
GTKWAVE = r"C:\iverilog\gtkwave\bin\gtkwave.exe"
OUTPUT_VVP = os.path.join(SIM_DIR, "histogram_sim.vvp")
WAVEFORM_VCD = os.path.join(SIM_DIR, "histogram_waveform.vcd")


def build():
    print("=== Compiling HISTOGRAM testbench ===")
    cmd = [IVERILOG, "-o", OUTPUT_VVP, "-g2012", "-s", "tb_histogram", HIST_SRC, TB_SRC]
    print(" ".join(cmd))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("STDERR:", result.stderr)
        print("STDOUT:", result.stdout)
        sys.exit(1)
    print("Compilation OK")
    if result.stderr.strip():
        print("Warnings:", result.stderr)


def run():
    if os.path.exists(WAVEFORM_VCD):
        os.remove(WAVEFORM_VCD)

    print("\n=== Running HISTOGRAM simulation ===")
    result = subprocess.run([VVP, OUTPUT_VVP], capture_output=True, text=True, cwd=SIM_DIR)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:2000])
    if result.returncode != 0:
        print(f"\nSimulation FAILED with code {result.returncode}")
        sys.exit(1)
    print("Simulation finished")


def open_gtkwave():
    if not os.path.exists(WAVEFORM_VCD):
        print(f"VCD file not found: {WAVEFORM_VCD}")
        sys.exit(1)

    size = os.path.getsize(WAVEFORM_VCD)
    print(f"\n=== Opening GTKWave with histogram_waveform.vcd ({size} bytes) ===")
    subprocess.Popen([GTKWAVE, WAVEFORM_VCD], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


if __name__ == "__main__":
    build()
    run()
    open_gtkwave()
    print("\nGTKWave launched.")
