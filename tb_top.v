`timescale 1ns/1ps
// Cocotb wrapper for RGB2YUV (rebuilt 2026-09-19; original lost to a 404 overwrite).
// test_rgb2yuv.py drives everything through dut.uut, so the instance MUST be
// named uut and the top-level ports must mirror the DUT ports 1:1.
module tb_top(
    input               clk,
    input               rst_n,
    input               i_HSYNC,
    input               i_VSYNC,
    input               i_BLANK,
    input       [15:0]  i_display_data,
    output              H_SYNC,
    output              V_SYNC,
    output              BLANK,
    output      [7:0]   Y0,
    output      [15:0]  display_data
);

    RGB2YUV uut (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_display_data (i_display_data),
        .H_SYNC         (H_SYNC),
        .V_SYNC         (V_SYNC),
        .BLANK          (BLANK),
        .Y0             (Y0),
        .display_data   (display_data)
    );

endmodule
