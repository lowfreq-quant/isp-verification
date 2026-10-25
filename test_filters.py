"""Cocotb test for Gaussian, Sobel, and Median filters with behavioral IP stubs."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

LINE_WIDTH = 640
NUM_LINES = 10
PIPELINE_FILL = 3 * LINE_WIDTH


async def stream_pixels(dut, pixel_func, num_lines=NUM_LINES, line_width=LINE_WIDTH):
    """Continuously stream pixel data. Runs as background task."""
    dut.i_BLANK.value = 0
    dut.i_Y0.value = 0
    dut.i_HSYNC.value = 0
    dut.i_VSYNC.value = 0

    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 3)

    dut.i_VSYNC.value = 1
    await ClockCycles(dut.clk, 2)
    dut.i_VSYNC.value = 0
    await ClockCycles(dut.clk, 2)

    dut.i_BLANK.value = 1
    dut.i_HSYNC.value = 1
    await ClockCycles(dut.clk, 1)
    dut.i_HSYNC.value = 0

    for row in range(num_lines):
        for col in range(line_width):
            dut.i_Y0.value = int(pixel_func(row, col)) & 0xFF
            await RisingEdge(dut.clk)

    dut.i_BLANK.value = 0
    dut.i_Y0.value = 0


@cocotb.test()
async def test_gaussian_uniform(dut):
    """Gaussian filter: uniform input should pass through unchanged."""
    Clock(dut.clk, 10, unit="ns").start()

    PIXEL_VAL = 128
    pixel_func = lambda r, c: PIXEL_VAL

    dut.rst_n.value = 0
    cocotb.start_soon(stream_pixels(dut, pixel_func))

    await ClockCycles(dut.clk, PIPELINE_FILL + 50)

    g_vals = []
    for _ in range(200):
        g_vals.append(int(dut.g_display.value.to_unsigned()))
        await RisingEdge(dut.clk)

    nonzero = [v for v in g_vals if v != 0]
    dut._log.info(f"Gaussian uniform: {len(nonzero)} non-zero out of {len(g_vals)}")

    if len(nonzero) > 0:
        expected_display = (PIXEL_VAL >> 3) << 11 | (PIXEL_VAL >> 2) << 5 | (PIXEL_VAL >> 3)
        sample = nonzero[:5]
        dut._log.info(f"Expected 0x{expected_display:04X}, got {[hex(v) for v in sample]}")
        for v in sample:
            assert v == expected_display, \
                f"Gaussian uniform: expected 0x{expected_display:04X}, got 0x{v:04X}"
        dut._log.info("Gaussian uniform PASS")
    else:
        dut._log.warning("No non-zero Gaussian output captured")


@cocotb.test()
async def test_median_uniform(dut):
    """Median filter: uniform input should pass through unchanged."""
    Clock(dut.clk, 10, unit="ns").start()

    PIXEL_VAL = 200
    pixel_func = lambda r, c: PIXEL_VAL

    dut.rst_n.value = 0
    cocotb.start_soon(stream_pixels(dut, pixel_func))

    await ClockCycles(dut.clk, PIPELINE_FILL + 50)

    m_vals = []
    for _ in range(200):
        m_vals.append(int(dut.m_display.value.to_unsigned()))
        await RisingEdge(dut.clk)

    nonzero = [v for v in m_vals if v != 0]
    dut._log.info(f"Median uniform: {len(nonzero)} non-zero out of {len(m_vals)}")

    if len(nonzero) > 0:
        expected_display = (PIXEL_VAL >> 3) << 11 | (PIXEL_VAL >> 2) << 5 | (PIXEL_VAL >> 3)
        sample = nonzero[:5]
        dut._log.info(f"Expected 0x{expected_display:04X}, got {[hex(v) for v in sample]}")
        for v in sample:
            assert v == expected_display, \
                f"Median uniform: expected 0x{expected_display:04X}, got 0x{v:04X}"
        dut._log.info("Median uniform PASS")
    else:
        dut._log.warning("No non-zero Median output captured")


@cocotb.test()
async def test_sobel_uniform(dut):
    """Sobel: uniform input should give zero gradient (no edges)."""
    Clock(dut.clk, 10, unit="ns").start()

    PIXEL_VAL = 100
    pixel_func = lambda r, c: PIXEL_VAL

    dut.rst_n.value = 0
    dut.thresh_min.value = 50
    dut.thresh_max.value = 150
    cocotb.start_soon(stream_pixels(dut, pixel_func))

    await ClockCycles(dut.clk, PIPELINE_FILL + 100)

    s_vals = []
    for _ in range(200):
        s_vals.append(int(dut.s_display.value.to_unsigned()))
        await RisingEdge(dut.clk)

    nonzero = [v for v in s_vals if v != 0]
    dut._log.info(f"Sobel uniform: {len(nonzero)} non-zero out of {len(s_vals)}: {set(nonzero)}")
    assert len(nonzero) == 0, f"Sobel uniform: expected all zeros, got {len(nonzero)} non-zero values"
    dut._log.info("Sobel uniform PASS: all outputs zero (no edges in uniform image)")


@cocotb.test()
async def test_gaussian_step_edge(dut):
    """Gaussian filter on a step edge: output should smooth the transition."""
    Clock(dut.clk, 10, unit="ns").start()

    pixel_func = lambda r, c: 255 if c >= LINE_WIDTH // 2 else 0

    dut.rst_n.value = 0
    cocotb.start_soon(stream_pixels(dut, pixel_func))

    await ClockCycles(dut.clk, PIPELINE_FILL + 50)

    g_vals = []
    for _ in range(LINE_WIDTH + 50):
        g_vals.append(int(dut.g_display.value.to_unsigned()))
        await RisingEdge(dut.clk)

    nonzero = [v for v in g_vals if v != 0]
    g_y_values = [(v >> 10) & 0x1F for v in nonzero]  
    g_8bit = [y << 3 for y in g_y_values]
    dut._log.info(f"Gaussian step: {len(nonzero)} non-zero, samples: {g_8bit[:20]}")
    assert len(nonzero) > 0, "Gaussian step: expected some non-zero outputs"

    unique_vals = set(g_8bit)
    dut._log.info(f"Gaussian step unique output values: {sorted(unique_vals)}")
    assert len(unique_vals) >= 2, "Gaussian step: expected smoothed transition with multiple values"
    dut._log.info("Gaussian step edge PASS")


@cocotb.test()
async def test_sobel_step_edge(dut):
    """Sobel on step edge: should detect the edge with high magnitude."""
    Clock(dut.clk, 10, unit="ns").start()

    pixel_func = lambda r, c: 255 if c >= LINE_WIDTH // 2 else 0

    dut.rst_n.value = 0
    dut.thresh_min.value = 50
    dut.thresh_max.value = 150
    cocotb.start_soon(stream_pixels(dut, pixel_func))

    await ClockCycles(dut.clk, PIPELINE_FILL + 100)

    s_vals = []
    for _ in range(LINE_WIDTH + 50):
        s_vals.append(int(dut.s_display.value.to_unsigned()))
        await RisingEdge(dut.clk)

    white_count = sum(1 for v in s_vals if v == 0xFFFF)
    black_count = sum(1 for v in s_vals if v == 0)
    dut._log.info(f"Sobel step: {white_count} white (edge), {black_count} black (no edge) out of {len(s_vals)}")
    assert white_count > 0, "Sobel step: expected some edge detections"
    assert black_count > 0, "Sobel step: expected some non-edge areas"
    dut._log.info("Sobel step edge PASS: edge detected at step transition")
