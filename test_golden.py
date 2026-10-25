"""Independent golden-model verification dump for tb_filters.

Drives a sequence of synthetic test images into tb_filters and dumps every
cycle's input/output signals to sim/rtl_dump.npz. Companion verify_golden.py
computes the numpy reference for each filter and reports per-pixel diff
against the RTL output.

Image protocol per image:
  1 cycle i_VSYNC=1 (frame start marker)
  H*W cycles of i_BLANK=1 (pixel valid):
    - W cycles of pixel data (i_Y0), with i_HSYNC=1 on the LAST cycle of each row
  BLANK_GAP_CYCLES cycles of i_BLANK=0 (frame gap / blanking)
After the last image: DRAIN_CYCLES of i_BLANK=0 so all RTL pipelines flush.

Note: matrix_generator.v has data_valid = i_BLANK | r_blank[799], so i_BLANK=1
means "pixel valid" (not the VGA-standard "blanking"). Driving i_BLANK=0
during pixel data leaves data_valid=0 forever and the matrix state machine
never advances -- which was the root cause of the previously-reported
"random full-image FAIL".
"""
import os
import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles


WIDTH = 640      # matrix_generator is hardcoded for VGA 640-wide, col_cnt==639
HEIGHT = 10      # enough rows so we can skip line_cnt 0..1 (boundary) and still have interior
BLANK_GAP_CYCLES = 40
DRAIN_CYCLES = 2000


def make_uniform(v):
    return np.full((HEIGHT, WIDTH), v, dtype=np.uint8)


def make_step_v():
    half = WIDTH // 2
    row = np.concatenate([np.zeros(half, dtype=np.uint8),
                          np.full(WIDTH - half, 220, dtype=np.uint8)])
    return np.tile(row, (HEIGHT, 1))


def make_step_h():
    img = np.full((HEIGHT, WIDTH), 100, dtype=np.uint8)
    img[HEIGHT // 2:] = 220
    return img


def make_gradient():
    return np.tile(np.linspace(0, 255, WIDTH, dtype=np.uint8), (HEIGHT, 1))


def make_random():
    rng = np.random.default_rng(42)
    return rng.integers(0, 256, size=(HEIGHT, WIDTH), dtype=np.uint8)


@cocotb.test()
async def dump_for_golden(dut):
    Clock(dut.clk, 10, unit="ns").start()

    # ---- reset ----
    dut.rst_n.value = 0
    dut.i_HSYNC.value = 0
    dut.i_VSYNC.value = 0
    dut.i_BLANK.value = 0
    dut.i_Y0.value = 0
    dut.thresh_min.value = 50
    dut.thresh_max.value = 150
    await ClockCycles(dut.clk, 6)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 4)

    test_images = [
        ("uniform_050",  make_uniform(50)),
        ("uniform_200",  make_uniform(200)),
        ("step_v",       make_step_v()),
        ("step_h",       make_step_h()),
        ("gradient",     make_gradient()),
        ("random",       make_random()),
    ]
    image_data = np.stack([img for _, img in test_images])  # (N, H, W)
    N = len(test_images)
    image_names = np.array([n for n, _ in test_images])

    # ---- estimate total cycles ----
    per_image_data = HEIGHT * WIDTH
    total = (N * (1 + per_image_data + BLANK_GAP_CYCLES)) + DRAIN_CYCLES + 100
    total = int(total)

    cycles   = np.zeros(total, dtype=np.int32)
    in_blank = np.zeros(total, dtype=np.int8)
    in_hsync = np.zeros(total, dtype=np.int8)
    in_vsync = np.zeros(total, dtype=np.int8)
    in_y0    = np.zeros(total, dtype=np.uint8)
    g_blank  = np.zeros(total, dtype=np.int8)
    g_hsync  = np.zeros(total, dtype=np.int8)
    g_vsync  = np.zeros(total, dtype=np.int8)
    g_disp   = np.zeros(total, dtype=np.uint16)
    s_disp   = np.zeros(total, dtype=np.uint16)
    m_disp   = np.zeros(total, dtype=np.uint16)
    s_blank  = np.zeros(total, dtype=np.int8)
    s_hsync  = np.zeros(total, dtype=np.int8)
    s_vsync  = np.zeros(total, dtype=np.int8)
    m_blank  = np.zeros(total, dtype=np.int8)
    m_hsync  = np.zeros(total, dtype=np.int8)
    m_vsync  = np.zeros(total, dtype=np.int8)

    idx = 0

    async def snap():
        nonlocal idx
        cycles[idx]   = idx
        in_blank[idx] = int(dut.i_BLANK.value)
        in_hsync[idx] = int(dut.i_HSYNC.value)
        in_vsync[idx] = int(dut.i_VSYNC.value)
        in_y0[idx]    = int(dut.i_Y0.value)
        g_blank[idx]  = int(dut.g_BLANK.value)
        g_hsync[idx]  = int(dut.g_HSYNC.value)
        g_vsync[idx]  = int(dut.g_VSYNC.value)
        g_disp[idx]   = int(dut.g_display.value)
        s_disp[idx]   = int(dut.s_display.value)
        m_disp[idx]   = int(dut.m_display.value)
        s_blank[idx]  = int(dut.s_BLANK.value)
        s_hsync[idx]  = int(dut.s_HSYNC.value)
        s_vsync[idx]  = int(dut.s_VSYNC.value)
        m_blank[idx]  = int(dut.m_BLANK.value)
        m_hsync[idx]  = int(dut.m_HSYNC.value)
        m_vsync[idx]  = int(dut.m_VSYNC.value)
        idx += 1

    # small warm-up before vsync
    for _ in range(4):
        await RisingEdge(dut.clk); await snap()

    for img_i, (name, img) in enumerate(test_images):
        cocotb.log.info(f"Streaming image {img_i}: {name}")
        # pixel-valid throughout the frame (matrix_generator: data_valid=i_BLANK|r_blank[799])
        dut.i_BLANK.value = 1
        # vsync pulse
        dut.i_VSYNC.value = 1
        await RisingEdge(dut.clk); await snap()
        dut.i_VSYNC.value = 0

        for row in range(HEIGHT):
            for col in range(WIDTH):
                dut.i_Y0.value = int(img[row, col])
                # Merge HSYNC with last pixel: row = exactly W cycles
                if col == WIDTH - 1:
                    dut.i_HSYNC.value = 1
                await RisingEdge(dut.clk); await snap()
                if col == WIDTH - 1:
                    dut.i_HSYNC.value = 0

        # blank gap between images
        dut.i_BLANK.value = 0
        dut.i_Y0.value = 0
        for _ in range(BLANK_GAP_CYCLES):
            await RisingEdge(dut.clk); await snap()

        # Reset between images so each frame starts from clean state:
        # line_cnt=0, col_cnt=0, r_blank clear, FIFOs empty.
        # Without this, the short 40-cycle gap is << r_blank[799]'s 800-cycle
        # depth, causing col_cnt phase to drift across images.
        if img_i < len(test_images) - 1:
            dut.rst_n.value = 0
            for _ in range(4):
                await RisingEdge(dut.clk); await snap()
            dut.rst_n.value = 1
            for _ in range(4):
                await RisingEdge(dut.clk); await snap()

    # drain: keep blank low so RTL pipelines fully flush
    dut.i_BLANK.value = 0
    dut.i_Y0.value = 0
    for _ in range(DRAIN_CYCLES):
        await RisingEdge(dut.clk); await snap()

    # trim
    cycles = cycles[:idx]; in_blank = in_blank[:idx]; in_hsync = in_hsync[:idx]
    in_vsync = in_vsync[:idx]; in_y0 = in_y0[:idx]
    g_blank = g_blank[:idx]; g_hsync = g_hsync[:idx]; g_vsync = g_vsync[:idx]
    g_disp = g_disp[:idx]; s_disp = s_disp[:idx]; m_disp = m_disp[:idx]
    s_blank = s_blank[:idx]; s_hsync = s_hsync[:idx]; s_vsync = s_vsync[:idx]
    m_blank = m_blank[:idx]; m_hsync = m_hsync[:idx]; m_vsync = m_vsync[:idx]  

    out_path = os.path.join(os.path.dirname(__file__), "rtl_dump.npz")
    np.savez_compressed(
        out_path,
        cycles=cycles,
        in_blank=in_blank, in_hsync=in_hsync, in_vsync=in_vsync, in_y0=in_y0,
        g_blank=g_blank, g_hsync=g_hsync, g_vsync=g_vsync, g_disp=g_disp,
        s_blank=s_blank, s_hsync=s_hsync, s_vsync=s_vsync, s_disp=s_disp,
        m_blank=m_blank, m_hsync=m_hsync, m_vsync=m_vsync, m_disp=m_disp,
        image_data=image_data,
        image_names=image_names,
        width=WIDTH, height=HEIGHT,
    )
    cocotb.log.info(f"Dumped {idx} cycles to {out_path}")
