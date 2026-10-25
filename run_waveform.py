"""Standalone iverilog waveform simulation (no cocotb needed)."""
import subprocess
import os
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))
RGB2YUV_SRC = os.path.join(PROJECT_ROOT, "image_processing", "RGB_to_YUV", "RGB2YUV.v")
TB_SRC = os.path.join(SIM_DIR, "tb_waveform.v")
IVERILOG = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "iverilog" + (".exe" if os.name == "nt" else ""))
VVP = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "vvp" + (".exe" if os.name == "nt" else ""))
GTKWAVE = r"C:\iverilog\gtkwave\bin\gtkwave.exe"
OUTPUT_VVP = os.path.join(SIM_DIR, "waveform_sim.vvp")
WAVEFORM_VCD = os.path.join(SIM_DIR, "waveform.vcd")


def build():
    print("=== Compiling waveform testbench ===")
    cmd = [IVERILOG, "-o", OUTPUT_VVP, "-g2012", "-s", "tb_waveform", RGB2YUV_SRC, TB_SRC]
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
    # Remove old VCD if exists
    if os.path.exists(WAVEFORM_VCD):
        os.remove(WAVEFORM_VCD)

    print("\n=== Running waveform simulation ===")
    result = subprocess.run([VVP, OUTPUT_VVP], capture_output=True, text=True, cwd=SIM_DIR)
    print(result.stdout)
    if result.stderr:
        print("STDERR:", result.stderr[:1000])
    if result.returncode != 0:
        print(f"\nSimulation FAILED with code {result.returncode}")
        sys.exit(1)
    print("Simulation finished")


def open_gtkwave():
    if not os.path.exists(WAVEFORM_VCD):
        print(f"VCD file not found: {WAVEFORM_VCD}")
        sys.exit(1)

    size = os.path.getsize(WAVEFORM_VCD)
    print(f"\n=== Opening GTKWave with waveform.vcd ({size} bytes) ===")
    subprocess.Popen([GTKWAVE, WAVEFORM_VCD], creationflags=subprocess.CREATE_NEW_PROCESS_GROUP)


if __name__ == "__main__":
    build()
    run()
    open_gtkwave()
    print("\nGTKWave launched. Drag signals from the left panel to the waveform viewer.")
