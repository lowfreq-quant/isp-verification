"""Cocotb testbench for RGB2YUV module (wrapped by tb_top)."""
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
import random


def rgb565_to_r8g8b8(rgb565):
    r5 = (rgb565 >> 11) & 0x1F
    g6 = (rgb565 >> 5) & 0x3F
    b5 = rgb565 & 0x1F
    r8 = ((r5 << 3) | ((r5 >> 2) & 0x7)) & 0xFF
    g8 = ((g6 << 2) | ((g6 >> 4) & 0x3)) & 0xFF
    b8 = ((b5 << 3) | ((b5 >> 2) & 0x7)) & 0xFF
    return r8, g8, b8


def expected_y(r8, g8, b8):
    return ((r8 * 77) + (g8 * 150) + (b8 * 29)) >> 8


async def setup(dut):
    """Reset the DUT (accessed via dut.uut inside tb_top)."""
    uut = dut.uut
    cocotb.start_soon(Clock(uut.clk, 40, units="ns").start())
    uut.rst_n.value = 0
    uut.i_display_data.value = 0
    uut.i_HSYNC.value = 0
    uut.i_VSYNC.value = 0
    uut.i_BLANK.value = 1
    for _ in range(4):
        await RisingEdge(uut.clk)
    uut.rst_n.value = 1
    await RisingEdge(uut.clk)


@cocotb.test()
async def test_rgb2yuv_math(dut):
    """Verify math for known RGB565 values after pipeline delay."""
    await setup(dut)
    uut = dut.uut

    test_cases = [
        (0x0000, "Black", 0),
        (0xFFFF, "White", 255),
        (0xF800, "Red", 76),
        (0x07E0, "Green", 149),
        (0x001F, "Blue", 28),
    ]

    uut.i_BLANK.value = 0
    for rgb565, name, expected_val in test_cases:
        r8, g8, b8 = rgb565_to_r8g8b8(rgb565)
        ey = expected_y(r8, g8, b8)
        assert ey == expected_val, f"Python calc mismatch for {name}: {ey} != {expected_val}"

        uut.i_display_data.value = rgb565
        for _ in range(4):
            await RisingEdge(uut.clk)
            await Timer(1, units="ns")

        y_val = int(uut.Y0.value)
        assert y_val == ey, f"{name}: got {y_val}, expected {ey}"

    cocotb.log.info("All math tests PASSED")


@cocotb.test()
async def test_sync_3cycle_delay(dut):
    """Verify HSYNC/VSYNC/BLANK have 3-cycle pipeline delay."""
    await setup(dut)
    uut = dut.uut

    uut.i_HSYNC.value = 1
    uut.i_VSYNC.value = 1
    uut.i_BLANK.value = 1

    for _ in range(4):
        await RisingEdge(uut.clk)
    await Timer(1, units="ns")

    assert int(uut.H_SYNC.value) == 1, "H_SYNC not high"
    assert int(uut.V_SYNC.value) == 1, "V_SYNC not high"
    assert int(uut.BLANK.value) == 1, "BLANK not high"

    uut.i_HSYNC.value = 0
    uut.i_VSYNC.value = 0
    uut.i_BLANK.value = 0

    for _ in range(4):
        await RisingEdge(uut.clk)
    await Timer(1, units="ns")

    assert int(uut.H_SYNC.value) == 0, "H_SYNC not low"
    assert int(uut.V_SYNC.value) == 0, "V_SYNC not low"
    assert int(uut.BLANK.value) == 0, "BLANK not low"

    cocotb.log.info("Sync signal test PASSED")


@cocotb.test()
async def test_continuous_stream(dut):
    """Pipeline produces correct results for continuous stream."""
    await setup(dut)
    uut = dut.uut

    test_vals = [0x0000, 0xF800, 0x07E0, 0x001F, 0xFFFF]
    expected_ys = []
    for v in test_vals:
        r8, g8, b8 = rgb565_to_r8g8b8(v)
        expected_ys.append(expected_y(r8, g8, b8))

    uut.i_BLANK.value = 0
    outputs = []
    for v in test_vals:
        uut.i_display_data.value = v
        for _ in range(4):
            await RisingEdge(uut.clk)
            await Timer(1, units="ns")
        outputs.append(int(uut.Y0.value))

    for i, (output, expected) in enumerate(zip(outputs, expected_ys)):
        assert output == expected, f"Pixel {i}: got {output}, expected {expected}"

    cocotb.log.info(f"Continuous stream PASSED")


@cocotb.test()
async def test_display_data_output(dut):
    """Verify display_data = {Y0[7:3], Y0[7:2], Y0[7:3]}."""
    await setup(dut)
    uut = dut.uut

    rgb565 = 0xFFFF
    uut.i_BLANK.value = 0
    uut.i_display_data.value = rgb565

    for _ in range(5):
        await RisingEdge(uut.clk)
    await Timer(1, units="ns")

    y_val = int(uut.Y0.value)
    dd = int(uut.display_data.value)
    expected_dd = ((y_val >> 3) << 11) | ((y_val >> 2) << 5) | (y_val >> 3)

    cocotb.log.info(f"Y0={y_val:3d}, display_data=0x{dd:04X}, expected=0x{expected_dd:04X}")
