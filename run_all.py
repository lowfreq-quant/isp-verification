"""Run all production verification flows and print a unified PASS/FAIL report.

Usage:
    cd sim && python run_all.py

Flows executed:
  1. Filter smoke tests      (run_filters.py -> test_filters.py)
  2. Golden model dump       (run_golden.py  -> test_golden.py -> rtl_dump.npz)
  3. Golden model verify     (verify_golden.py)
  4. Probe test              (run_probe.py   -> test_probe.py)
  5. RGB2YUV cocotb tests    (run_sim.py     -> test_rgb2yuv.py)
  6. RGB2YUV waveform        (run_waveform.py, no GTKWave)
  7. Histogram waveform      (run_histogram.py, no GTKWave)
  8. RGB2YUV independent     (verify_rgb2yuv_independent.py)
  9. VCD check               (verify_vcd.py)
 10. Sobel thresh->canny     (run_thresh.py -> verify_thresh_path.py)
 11. Point-ops cocotb        (run_pointops_cocotb.py -> test_pointops.py)
 12. ISP chain (no SDRAM)    (run_isp_chain.py -> test_isp_chain.py)

The script returns exit code 0 only if every flow passes.
"""
import os
import subprocess
import sys
import shutil


SIM_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.environ.get("RTL_ROOT", os.path.dirname(SIM_DIR))


def run(cmd, cwd=SIM_DIR, env=None):
    """Run a command and return (ok, stdout, stderr)."""
    merged_env = os.environ.copy()
    merged_env["PATH"] = os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin") + os.pathsep + merged_env.get("PATH", "")
    if env:
        merged_env.update(env)
    result = subprocess.run(
        cmd,
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0, result.stdout, result.stderr


def run_python(script, args=None):
    cmd = [sys.executable, script]
    if args:
        cmd.extend(args)
    return run(cmd)


def run_filters():
    ok, out, err = run_python("run_filters.py")
    summary = "PASS" if ok and "FAIL=0" in out else "FAIL"
    return ok, "Filter smoke tests", summary, out, err


def run_golden():
    ok, out, err = run_python("run_golden.py")
    summary = "PASS" if ok and "FAIL=0" in out else "FAIL"
    return ok, "Golden model dump", summary, out, err


def verify_golden():
    ok, out, err = run_python("verify_golden.py")
    summary = "PASS" if ok and "Overall: PASS" in out else "FAIL"
    return ok, "Golden model verify", summary, out, err


def run_probe():
    ok, out, err = run_python("run_probe.py")
    summary = "PASS" if ok and "FAIL=0" in out else "FAIL"
    return ok, "Probe test", summary, out, err


def run_rgb2yuv_cocotb():
    ok, out, err = run_python("run_sim.py")
    summary = "PASS" if ok and "Simulation PASSED" in out else "FAIL"
    return ok, "RGB2YUV cocotb", summary, out, err


def run_waveform():
    # Import run_waveform but suppress GTKWave launch
    import run_waveform as rw
    rw.OUTPUT_VVP = os.path.join(SIM_DIR, "waveform_sim.vvp")
    rw.WAVEFORM_VCD = os.path.join(SIM_DIR, "waveform.vcd")
    try:
        rw.build()
        rw.run()
        ok = os.path.exists(rw.WAVEFORM_VCD)
        summary = "PASS" if ok else "FAIL"
        return ok, "RGB2YUV waveform", summary, "", ""
    except SystemExit as e:
        return False, "RGB2YUV waveform", "FAIL", "", str(e)


def run_histogram():
    import run_histogram as rh
    rh.OUTPUT_VVP = os.path.join(SIM_DIR, "histogram_sim.vvp")
    rh.WAVEFORM_VCD = os.path.join(SIM_DIR, "histogram_waveform.vcd")
    try:
        rh.build()
        rh.run()
        ok = os.path.exists(rh.WAVEFORM_VCD)
        summary = "PASS" if ok else "FAIL"
        return ok, "Histogram waveform", summary, "", ""
    except SystemExit as e:
        return False, "Histogram waveform", "FAIL", "", str(e)


def verify_rgb2yuv_independent():
    # Needs rgb2yuv_dump.txt, regenerated here from the current RTL.  The file
    # is tb_rgb_uv_dump.v (module name inside is tb_rgb2yuv_dump) -- referencing
    # it by module name silently failed to compile, and the flow then "passed"
    # against whatever stale rgb2yuv_dump.txt happened to be lying in sim/.
    stale = os.path.join(SIM_DIR, "rgb2yuv_dump.txt")
    if os.path.exists(stale):
        os.remove(stale)
    ok_dump, out_dump, err_dump = run(
        [os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "iverilog" + (".exe" if os.name == "nt" else "")), "-o", "rgb2yuv_dump.vvp", "-g2012", "-s", "tb_rgb2yuv_dump",
         os.path.join(PROJECT_ROOT, "image_processing", "RGB_to_YUV", "RGB2YUV.v"),
         "tb_rgb_uv_dump.v"],
        cwd=SIM_DIR
    )
    if not ok_dump:
        return False, "RGB2YUV independent", "FAIL (iverilog compile failed)", out_dump, err_dump
    run([os.path.join(os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin"), "vvp" + (".exe" if os.name == "nt" else "")), "rgb2yuv_dump.vvp"], cwd=SIM_DIR)
    ok, out, err = run_python("verify_rgb2yuv_independent.py")
    summary = "PASS" if ok and "PASS" in out else "FAIL"
    return ok, "RGB2YUV independent", summary, out, err


def verify_vcd():
    ok, out, err = run_python("verify_vcd.py")
    summary = "PASS" if ok and "PASS" in out else "FAIL"
    return ok, "VCD check", summary, out, err


def run_thresh_path():
    ok, out, err = run_python("run_thresh.py")
    summary = "PASS" if ok and "Overall: PASS" in out else "FAIL"
    return ok, "Sobel thresh->canny path", summary, out, err


def run_pointops_cocotb():
    ok, out, err = run_python("run_pointops_cocotb.py")
    summary = "PASS" if ok and "Overall: PASS" in out else "FAIL"
    return ok, "Point-ops cocotb (LOG/EMBOSS/HIST/EQ)", summary, out, err


def run_isp_chain():
    ok, out, err = run_python("run_isp_chain.py")
    summary = "PASS" if ok and "Overall: PASS" in out else "FAIL"
    return ok, "ISP chain (RGB2YUV+LOG+filter+sobel+canny)", summary, out, err


def main():
    os.chdir(SIM_DIR)
    print("=" * 70)
    print("IMAGE PROCESSING RTL - UNIFIED VERIFICATION")
    print("=" * 70 + "\n")

    flows = [
        run_filters,
        run_golden,
        verify_golden,
        run_probe,
        run_rgb2yuv_cocotb,
        run_waveform,
        run_histogram,
        verify_rgb2yuv_independent,
        verify_vcd,
        run_thresh_path,
        run_pointops_cocotb,
        run_isp_chain,
    ]

    results = []
    for flow in flows:
        print(f"Running {flow.__name__} ...", flush=True)
        ok, name, summary, out, err = flow()
        results.append((ok, name, summary, out, err))
        print(f"  -> {summary}\n")

    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    all_ok = True
    for ok, name, summary, out, err in results:
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name:<28} {summary}")
        if not ok:
            all_ok = False
    print("=" * 70)

    overall = "ALL PASS" if all_ok else "SOME FAILURES"
    print(f"\nOverall: {overall}")

    # Dump detailed logs for failures
    if not all_ok:
        print("\n--- Detailed failure logs ---")
        for ok, name, summary, out, err in results:
            if not ok:
                print(f"\n### {name} ###")
                if out:
                    print(out[-3000:])
                if err:
                    print(err[-2000:])
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
