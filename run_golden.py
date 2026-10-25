"""Run test_golden.py via cocotb runner; produces sim/rtl_dump.npz."""
import os
from pathlib import Path
from cocotb_tools.runner import get_runner

os.environ["PATH"] = os.environ.get("IVERILOG_BIN", r"C:\iverilog\bin") + ";" + os.environ.get("PATH", "")
os.environ.setdefault("SIM", "icarus")

ROOT = Path(__file__).resolve().parent
# RTL root = the image-processing checkout. Default: parent of this suite
# (in-tree layout <project>/sim/). Set RTL_ROOT for out-of-tree use.
RTL_ROOT = Path(os.environ.get("RTL_ROOT", ROOT.parent))

verilog_sources = [
    str(ROOT / "ip" / "behavioral_fifo.v"),
    str(ROOT / "ip" / "behavioral_cordic.v"),
    str(ROOT / "ip" / "ip_wrappers.v"),
    str(RTL_ROOT / "image_processing/Matrix_generator/matrix_generator.v"),
    str(RTL_ROOT / "image_processing/Gaussian_filter/gaussian_filter.v"),
    str(RTL_ROOT / "image_processing/Sobel_detection/sobel.v"),
    str(RTL_ROOT / "image_processing/Median_filter/median_filter.v"),
    str(ROOT / "tb_filters.v"),
]

runner = get_runner("icarus")
runner.build(
    verilog_sources=verilog_sources,
    hdl_toplevel="tb_filters",
    build_dir=str(ROOT / "build_golden"),
    always=True,
    build_args=["-g2012"],
)
runner.test(
    test_module="test_golden",
    hdl_toplevel="tb_filters",
    test_dir=str(ROOT),
)
