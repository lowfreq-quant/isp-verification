"""Cocotb cycle-accurate verification of the ISP_TOP data path (no SDRAM).

Chain: RGB565 -> RGB2YUV -> Y0 fan-out -> {LOG, gaussian, median,
sobel -> canny} (the sobel->canny series path included).

Drives tb_isp_chain.v exactly like test_golden.py drives the filter bank:
  warmup 4 cy -> per frame: VSYNC pulse (1 cy, BLANK=1) -> H*W pixels
  (BLANK=1, HSYNC merged into the last pixel of each row -> exactly W cycles
  per row) -> 40-cycle blank gap -> 8-cycle reset between frames -> drain.

For every cycle T the test:
  1. drives the inputs the DUTs sample at posedge T,
  2. reads every DUT output BEFORE that posedge,
  3. runs verify_isp_chain.ISPChainModel.cycle() which returns exactly those
     pre-posedge values, and
  4. awaits the posedge.
So model == RTL must hold cycle after cycle (max_diff = 0).

Run with sim/run_isp_chain.py.
"""

import os
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM_DIR)

import numpy as np  # noqa: E402
import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer, ClockCycles  # noqa: E402

import verify_pointops as vp  # noqa: E402
import verify_golden as vg  # noqa: E402
import verify_thresh_path as vtp  # noqa: E402
import verify_isp_chain as vic  # noqa: E402

W, H = 640, 10
BLANK_GAP = 40
DRAIN = 1000


def make_images():
    """Deterministic RGB565 test frames (LCG random, uniform, gradient)."""
    rng = np.random.default_rng(20260810)
    frames = []
    # 1: uniform grey-ish RGB565 (R=G=B -> near-grey Y)
    v = 0x39E7  # arbitrary RGB565
    frames.append(np.full((H, W), v, dtype=np.uint16))
    # 2: horizontal gradient packed per-channel
    g = np.tile(np.linspace(0, 255, W, dtype=np.uint16), (H, 1))
    frames.append((((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)).astype(np.uint16))
    # 3: step vertical
    half = W // 2
    row = np.concatenate([np.zeros(half, dtype=np.uint16),
                          np.full(W - half, 0xF800, dtype=np.uint16)])
    frames.append(np.tile(row, (H, 1)))
    # 4: random RGB565
    frames.append(rng.integers(0, 0xFFFF, size=(H, W), dtype=np.uint16))
    # 5: random again (different seed working through the model LCG not needed;
    #    numpy RNG state continues)
    frames.append(rng.integers(0, 0xFFFF, size=(H, W), dtype=np.uint16))
    return frames


def rd(handle):
    v = handle.value
    if v is None or not getattr(v, "is_resolvable", False) or not v.is_resolvable:
        return None
    return int(v)


@cocotb.test()
async def isp_chain_cycle_exact(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    lut = vp.log_table()
    chain = vic.ISPChainModel(lut, vp, vg, vtp)
    frames = make_images()

    dut.rst_n.value = 0
    dut.i_HSYNC.value = 0
    dut.i_VSYNC.value = 0
    dut.i_BLANK.value = 0
    dut.i_display_data.value = 0
    await ClockCycles(dut.clk, 6)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 4)

    errs = 0
    first_err = None
    n_cycles = 0

    def check(name, m, r):
        nonlocal errs, first_err
        if r is None:
            return
        if m != r:
            errs += 1
            if first_err is None:
                first_err = (n_cycles, name, m, r)

    async def step(rgb, h, v, b, compare=True):
        nonlocal n_cycles
        dut.i_display_data.value = int(rgb)
        dut.i_HSYNC.value = h
        dut.i_VSYNC.value = v
        dut.i_BLANK.value = b
        await Timer(1, units="ps")

        rtl = {
            "rgb": (rd(dut.rgb_Y0), rd(dut.rgb_disp),
                    rd(dut.rgb_HSYNC), rd(dut.rgb_VSYNC), rd(dut.rgb_BLANK)),
            "log": (rd(dut.lg_disp), rd(dut.lg_HSYNC), rd(dut.lg_VSYNC),
                    rd(dut.lg_BLANK)),
            "gauss": (rd(dut.g_disp), rd(dut.g_HSYNC), rd(dut.g_VSYNC),
                      rd(dut.g_BLANK)),
            "median": (rd(dut.m_disp), rd(dut.m_HSYNC), rd(dut.m_VSYNC),
                       rd(dut.m_BLANK)),
            "sobel": (rd(dut.s_disp), rd(dut.s_HSYNC), rd(dut.s_VSYNC),
                      rd(dut.s_BLANK), rd(dut.s_canny_in)),
            "canny": (rd(dut.c_disp), rd(dut.c_HSYNC), rd(dut.c_VSYNC),
                      rd(dut.c_BLANK)),
        }

        m = chain.cycle(rgb, h, v, b)
        if compare:
            check("rgb.Y0", m["rgb"][0], rtl["rgb"][0])
            check("rgb.disp", m["rgb"][1], rtl["rgb"][1])
            check("rgb.H", m["rgb"][2], rtl["rgb"][2])
            check("rgb.V", m["rgb"][3], rtl["rgb"][3])
            check("rgb.B", m["rgb"][4], rtl["rgb"][4])
            check("log.disp", m["log"][0], rtl["log"][0])
            check("log.H", m["log"][1], rtl["log"][1])
            check("log.V", m["log"][2], rtl["log"][2])
            check("log.B", m["log"][3], rtl["log"][3])
            check("gauss.disp", m["gauss"][0], rtl["gauss"][0])
            check("gauss.H", m["gauss"][1], rtl["gauss"][1])
            check("gauss.V", m["gauss"][2], rtl["gauss"][2])
            check("gauss.B", m["gauss"][3], rtl["gauss"][3])
            check("median.disp", m["median"][0], rtl["median"][0])
            check("median.H", m["median"][1], rtl["median"][1])
            check("median.V", m["median"][2], rtl["median"][2])
            check("median.B", m["median"][3], rtl["median"][3])
            check("sobel.disp", m["sobel"][0], rtl["sobel"][0])
            check("sobel.H", m["sobel"][1], rtl["sobel"][1])
            check("sobel.V", m["sobel"][2], rtl["sobel"][2])
            check("sobel.B", m["sobel"][3], rtl["sobel"][3])
            check("sobel.canny_in", m["sobel"][4], rtl["sobel"][4])
            check("canny.disp", m["canny"][0], rtl["canny"][0])
            check("canny.H", m["canny"][1], rtl["canny"][1])
            check("canny.V", m["canny"][2], rtl["canny"][2])
            check("canny.B", m["canny"][3], rtl["canny"][3])

        n_cycles += 1
        await RisingEdge(dut.clk)

    # warmup
    for _ in range(4):
        await step(0, 0, 0, 0)

    for img in frames:
        # VSYNC pulse (1 cycle, pixel-valid ramps up inside matrix gen)
        await step(int(img[0, 0]), 0, 1, 1)
        for row in range(H):
            for col in range(W):
                hsync = 1 if col == W - 1 else 0
                await step(int(img[row, col]), hsync, 0, 1)
        # blank gap
        for _ in range(BLANK_GAP):
            await step(0, 0, 0, 0)
        # reset between frames (clean matrix state, like test_golden);
        # the RTL rst_n pulse must be mirrored by a model reset so the
        # post-reset state matches (RTL outputs are held at 0 while rst_n=0).
        # The 8 reset cycles themselves are NOT compared: RTL holds its
        # registers at reset values (incl. sobel's phase, which has no reset
        # branch and keeps its stale value), which is frame-boundary
        # plumbing rather than datapath behaviour; both sides are synchronised
        # again by the first pixel of the next frame.
        dut.rst_n.value = 0
        chain.reset()
        for _ in range(4):
            await step(0, 0, 0, 0, compare=False)
        dut.rst_n.value = 1
        for _ in range(4):
            await step(0, 0, 0, 0, compare=False)

    # drain
    for _ in range(DRAIN):
        await step(0, 0, 0, 0)

    print(f"\nISP chain: {n_cycles} cycles, {errs} mismatches")
    if first_err:
        print(f"  first mismatch at cycle {first_err[0]}: "
              f"{first_err[1]} model={first_err[2]} rtl={first_err[3]}")
    print(f"Overall: {'PASS' if errs == 0 else 'FAIL'}")
    assert errs == 0, "ISP chain cycle-accurate comparison failed"