# ISP Verification Suite

[![regression](https://github.com/lowfreq-quant/isp-verification/actions/workflows/ci.yml/badge.svg)](https://github.com/lowfreq-quant/isp-verification/actions/workflows/ci.yml)

Cycle-accurate RTL verification for the FPGA image-processing (ISP) project
[ykqiu/Image-Processing](https://github.com/ykqiu/image-processing).

This repository contains **only the verification infrastructure** — testbenches,
Python cycle-accurate reference models, cocotb tests, runners and docs. The RTL
under test lives in the upstream repository; point `RTL_ROOT` at a checkout of
it (any checkout works, including a fork).

## What it verifies

The suite replicates the RTL **cycle by cycle in Python** (Verilog
non-blocking-assignment semantics: every registered output is sampled before
the clock edge, committed after it) and compares model vs. simulation on every
dumped cycle. A flow passes only when the difference is exactly zero over the
whole run (`max_diff = 0`).

| # | Flow | Entry point | Coverage |
|---|------|-------------|----------|
| 1 | Filter smoke tests | `run_filters.py` | Gaussian / median / Sobel operators |
| 2 | Golden model dump | `run_golden.py` | 6 deterministic test images |
| 3 | Golden model verify | `verify_golden.py` | cycle-accurate filter comparison |
| 4 | Probe test | `run_probe.py` | white-box 3x3 window probes |
| 5 | RGB2YUV (cocotb) | `run_sim.py` | RGB565 -> YUV, stream timing |
| 6 | RGB2YUV waveform | `run_waveform.py` | VCD waveform + protocol checks |
| 7 | HISTOGRAM waveform | `run_histogram.py` | contrast stretching |
| 8 | RGB2YUV independent | `verify_rgb2yuv_independent.py` | all 65536 RGB565 inputs vs. BT.601 floating point |
| 9 | VCD check | `verify_vcd.py` | waveform sanity |
| 10 | Sobel thresh -> Canny | `run_thresh.py` | threshold path + Canny `is_edge` |
| 11 | Point ops | `run_pointops_cocotb.py` | LOG / EMBOSS / HISTOGRAM / HISTOGRAM_EQ |
| 12 | ISP chain | `run_isp_chain.py` | RGB2YUV -> LOG -> Gaussian/median -> Sobel -> Canny |

`python run_all.py` runs all 12 flows and prints a PASS/FAIL summary.

## Requirements

- **Icarus Verilog 12.0** — the RTL uses SystemVerilog for the RGB2YUV
  conversion; `-g2012` is passed automatically by the runners.
- **Python 3.10+** with `cocotb >= 2.0` and `numpy`:

  ```bash
  python -m pip install cocotb numpy
  ```

- Tested on Windows with Icarus Verilog 12.0, Python 3.13 and cocotb 2.0.1.
  On Linux/macOS the executable names are currently Windows-oriented; set
  `IVERILOG_BIN` and adjust the `.exe` suffix if needed.

## Quick start

```bash
# 1. Get the RTL under test (upstream project, or any fork of it)
git clone https://github.com/ykqiu/image-processing

# 2. Get this suite
git clone https://github.com/lowfreq-quant/isp-verification
cd isp-verification

# 3. Point at the RTL checkout and run everything
export RTL_ROOT=../image-processing        # PowerShell: $env:RTL_ROOT = "..\image-processing"
export IVERILOG_BIN=/path/to/iverilog/bin  # Windows default: C:\iverilog\bin
python run_all.py
```

Run a single flow with its entry point, e.g. `python run_thresh.py`.

## Environment variables

| Variable | Default | Meaning |
|---|---|---|
| `RTL_ROOT` | parent of this repository | path to the `image-processing` RTL checkout |
| `IVERILOG_BIN` | `C:\iverilog\bin` | directory containing `iverilog(.exe)` and `vvp(.exe)` |

(When the suite is used in-tree, i.e. copied into `image-processing/sim/`, both
variables may be left unset.)

## Layout

```
ip/              behavioral models of the Xilinx IP cores used by the RTL
tb_*.v           Icarus Verilog testbenches (dumps consumed by the models)
run_*.py         one-shot runners (compile + simulate, or cocotb)
test_*.py        cocotb test modules (drive the DUT cycle by cycle)
verify_*.py      cycle-accurate Python reference models and comparators
gen_*.py         generators (log LUT, test images)
docs/HANDOFF.md  verification history and handoff notes
```

## Methodology notes

- Python models mirror Verilog non-blocking assignment semantics: values are
  sampled before the clock edge and committed after it, so model and RTL are
  compared on the same cycle.
- Alignment is fixed at the source (negedge dumps, posedge edge capture)
  instead of being "tuned" by hand, which keeps the comparison exact.
- The suite caught several real RTL bugs; the fixes live in the development
  fork: RGB565->RGB888 expansion, a missing Canny phase case, matrix-generator
  sync-edge handling and SDRAM write-data alignment.

## Status / known gaps

- **12/12 flows pass**; see `docs/HANDOFF.md` for the full verification history
  and the remaining open items.
- The SDRAM replay chain (`sdram_top` / `fifo_ctrl` / `sdram_ctrl`) is **not
  covered yet** — work in progress.
- `HISTOGRAM` / `HISTOGRAM_EQ` frame-boundary behaviour depends on the VGA
  blanking protocol; the details are documented in `docs/HANDOFF.md`.

## License

MIT — see [LICENSE](LICENSE). This covers the verification code in this
repository only. The RTL it targets
([ykqiu/Image-Processing](https://github.com/ykqiu/image-processing)) is **not**
included here and carries no license upstream; do not redistribute the RTL
without the original author's permission.
