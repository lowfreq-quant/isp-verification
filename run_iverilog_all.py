"""Unified standalone Icarus Verilog simulation runner.

Runs all standalone iverilog testbenches (no cocotb required):
  1. RGB2YUV waveform (tb_waveform.v)
  2. HISTOGRAM contrast stretch (tb_histogram.v)
  3. Filters standalone (tb_filters_standalone.v)
  4. ISP_TOP full system (ISP_TOP_tb.v)

Usage:
    python run_iverilog_all.py          # run all
    python run_iverilog_all.py 1 3      # run specific tests by number
"""
import subprocess
import os
import sys
import time

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))
IVERILOG = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "iverilog" + (".exe" if os.name == "nt" else ""))
VVP = os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "vvp" + (".exe" if os.name == "nt" else ""))

# Ensure output directory exists
os.makedirs(os.path.join(SIM_DIR, "output"), exist_ok=True)


def run_sim(name, top_module, sources, success_str, cwd=None, timeout=300):
    """Compile and run a single simulation. Returns (passed, elapsed, msg)."""
    if cwd is None:
        cwd = SIM_DIR
    vvp_file = os.path.join(SIM_DIR, f"{name}.vvp")

    # --- Compile ---
    cmd = [IVERILOG, "-o", vvp_file, "-g2012", "-s", top_module] + sources
    t0 = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if result.returncode != 0:
        elapsed = time.time() - t0
        return False, elapsed, f"Compile error:\n{result.stderr[:2000]}"

    # --- Run ---
    result = subprocess.run([VVP, vvp_file], capture_output=True, text=True,
                            cwd=cwd, timeout=timeout)
    elapsed = time.time() - t0
    output = result.stdout + result.stderr

    if success_str in output:
        return True, elapsed, ""
    else:
        # Show last 1000 chars for debugging
        return False, elapsed, f"Success string '{success_str}' not found.\nOutput tail:\n{output[-1000:]}"


# ===========================================================================
# Test definitions
# ===========================================================================

def test_rgb2yuv_waveform():
    sources = [
        os.path.join(PROJECT_ROOT, "image_processing", "RGB_to_YUV", "RGB2YUV.v"),
        os.path.join(SIM_DIR, "tb_waveform.v"),
    ]
    return run_sim("waveform_sim", "tb_waveform", sources,
                   "Waveform simulation complete")


def test_histogram():
    sources = [
        os.path.join(PROJECT_ROOT, "image_processing", "Histogram", "HISTOGRAM.v"),
        os.path.join(SIM_DIR, "tb_histogram.v"),
    ]
    return run_sim("histogram_sim", "tb_histogram", sources,
                   "Histogram stretch test complete")


def test_filters_standalone():
    sources = [
        os.path.join(SIM_DIR, "ip", "behavioral_fifo.v"),
        os.path.join(SIM_DIR, "ip", "behavioral_cordic.v"),
        os.path.join(SIM_DIR, "ip", "ip_wrappers.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Matrix_generator", "matrix_generator.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Gaussian_filter", "gaussian_filter.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Sobel_detection", "sobel.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Median_filter", "median_filter.v"),
        os.path.join(SIM_DIR, "tb_filters_standalone.v"),
    ]
    return run_sim("filters_standalone", "tb_filters_standalone", sources,
                   ">>> PASS")


def test_isp_top():
    sources = [
        os.path.join(SIM_DIR, "ip", "behavioral_fifo.v"),
        os.path.join(SIM_DIR, "ip", "behavioral_cordic.v"),
        os.path.join(SIM_DIR, "ip", "ip_wrappers.v"),
        os.path.join(SIM_DIR, "ip", "sdram_ip_wrappers.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Matrix_generator", "matrix_generator.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Gaussian_filter", "gaussian_filter.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Sobel_detection", "sobel.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Median_filter", "median_filter.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Canny_detection", "canny.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "RGB_to_YUV", "RGB2YUV.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Histogram", "HISTOGRAM.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Histogram", "HISTOGRAM_EQ.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "logarithmization", "LOG.v"),
        os.path.join(PROJECT_ROOT, "image_processing", "Emboss", "EMBOSS.v"),
        os.path.join(PROJECT_ROOT, "vga_controller", "VGA_CTRL.v"),
        os.path.join(PROJECT_ROOT, "sdram_controller", "sdram_top.v"),
        os.path.join(PROJECT_ROOT, "sdram_controller", "sdram_model.v"),
        os.path.join(PROJECT_ROOT, "sdram_controller", "fifo_ctrl.v"),
        os.path.join(PROJECT_ROOT, "sdram_controller", "sram_ctrl.v"),
        os.path.join(PROJECT_ROOT, "image_processing_top", "ISP_TOP.v"),
        os.path.join(PROJECT_ROOT, "ISP_testbench", "ISP_TOP_tb.v"),
    ]
    ok, elapsed, msg = run_sim("isp_top_tb", "ISP_TOP_tb", sources,
                               "ISP_TOP simulation complete", timeout=600)
    if not ok:
        return ok, elapsed, msg
    # Assert the data path actually delivered pixels: with ping-pong the
    # first frames read the empty half-plane (all zeros) — the FIRST frame
    # with real data is grey_out_3 or later.  Any of them being non-zero
    # proves SDRAM write->read->RGB2YUV works end to end.
    out_dir = os.path.join(SIM_DIR, "output")
    found_data = False
    for i in (3, 4, 5):
        p = os.path.join(out_dir, f"grey_out_{i}.txt")
        if not os.path.exists(p):
            continue
        with open(p) as fh:
            for line in fh:
                if line.strip() != "0000":
                    found_data = True
                    break
        if found_data:
            print(f"  [OK] grey_out_{i}.txt contains non-zero pixels (SDRAM path alive)")
            break
    if not found_data:
        print("  [FAIL] grey_out_3..5 all zero: SDRAM write/read path did not deliver data")
        return False, 0.0, "grey_out_3..5 all zero"
    return True, elapsed, ""


# ===========================================================================
# Main
# ===========================================================================

TESTS = [
    ("RGB2YUV waveform", test_rgb2yuv_waveform),
    ("HISTOGRAM stretch", test_histogram),
    ("Filters standalone", test_filters_standalone),
    ("ISP_TOP full system", test_isp_top),
]


def main():
    # Parse optional test numbers from command line
    if len(sys.argv) > 1:
        indices = [int(x) - 1 for x in sys.argv[1:]]
        selected = [(i, TESTS[i]) for i in indices if 0 <= i < len(TESTS)]
    else:
        selected = list(enumerate(TESTS))

    print("=" * 70)
    print("  Icarus Verilog Standalone Simulation Suite")
    print("=" * 70)

    results = []
    for idx, (name, func) in selected:
        print(f"\n[{idx+1}/{len(TESTS)}] {name} ...")
        try:
            passed, elapsed, msg = func()
        except subprocess.TimeoutExpired:
            passed, elapsed, msg = False, 0, "TIMEOUT"
        except Exception as e:
            passed, elapsed, msg = False, 0, str(e)

        status = "PASS" if passed else "FAIL"
        print(f"       {status}  ({elapsed:.1f}s)")
        if msg:
            print(f"       {msg[:500]}")
        results.append((name, status))

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)
    all_pass = True
    for name, status in results:
        print(f"  [{status}] {name}")
        if status != "PASS":
            all_pass = False
    print("=" * 70)
    print(f"  Overall: {'ALL PASS' if all_pass else 'SOME FAILED'}")
    print("=" * 70)
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
