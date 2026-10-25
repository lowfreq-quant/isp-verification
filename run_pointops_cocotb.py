"""Run test_pointops.py via the cocotb runner.

Generates sim/ip/log_lut.hex first, compiles the four point-operation DUTs
with the behavioral block-memory models, and runs the cycle-accurate cocotb
verification (PART 1 + PART 2).

Usage:
    python sim/run_pointops_cocotb.py
"""

import os
from pathlib import Path
from cocotb_tools.runner import get_runner

import gen_pointops_lut


os.environ["PATH"] = os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin") + ";" + os.environ.get("PATH", "")
os.environ.setdefault("SIM", "icarus")

ROOT = Path(__file__).resolve().parent
# RTL root = the image-processing checkout. Default: parent of this suite
# (in-tree layout <project>/sim/). Set RTL_ROOT for out-of-tree use.
RTL_ROOT = Path(os.environ.get("RTL_ROOT", ROOT.parent))

gen_pointops_lut.main()

verilog_sources = [
    str(ROOT / "ip" / "behavioral_blk_mem.v"),
    str(RTL_ROOT / "image_processing" / "logarithmization" / "LOG.v"),
    str(RTL_ROOT / "image_processing" / "Emboss" / "EMBOSS.v"),
    str(RTL_ROOT / "image_processing" / "Histogram" / "HISTOGRAM.v"),
    str(RTL_ROOT / "image_processing" / "Histogram" / "HISTOGRAM_EQ.v"),
    str(ROOT / "tb_pointops_cocotb.v"),
]

runner = get_runner("icarus")
runner.build(
    verilog_sources=verilog_sources,
    hdl_toplevel="tb_pointops_cocotb",
    build_dir=str(ROOT / "build_pointops"),
    always=True,
    build_args=["-g2012"],
)
runner.test(
    test_module="test_pointops",
    hdl_toplevel="tb_pointops_cocotb",
    test_dir=str(ROOT),
)
