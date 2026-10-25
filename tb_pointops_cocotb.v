`timescale 1ns/1ps
// Point-ops cocotb top: LOG + EMBOSS + HISTOGRAM + HISTOGRAM_EQ sharing one
// stimulus (rebuilt 2026-09-19; original lost to a 404 overwrite).
// test_pointops.py drives dut.{clk,rst_n,i_Y0,i_HSYNC,i_VSYNC,i_BLANK} and
// probes dut.u_log / dut.u_emboss / dut.u_hist / dut.u_eq (incl.
// dut.u_eq.u_ram_1.mem / u_ram_2.mem), so instance names are load-bearing.
// NOTE: the file is tb_pointops_cocotb.v (ops); the stray tb_pointopts_cocotb.v
// (opts) that appeared during the 404 incident is not referenced anywhere.
module tb_pointops_cocotb(
    input               clk,
    input               rst_n,
    input               i_HSYNC,
    input               i_VSYNC,
    input               i_BLANK,
    input       [7:0]   i_Y0
);

    LOG u_log (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (),
        .V_SYNC         (),
        .BLANK          (),
        .display_data   ()
    );

    EMBOSS u_emboss (
        .clk            (clk),
        .shreshold      (8'd150),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (),
        .V_SYNC         (),
        .BLANK          (),
        .display_data   ()
    );

    HISTOGRAM u_hist (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (),
        .V_SYNC         (),
        .BLANK          (),
        .Y0             (),
        .display_data   ()
    );

    HISTOGRAM_EQ u_eq (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (),
        .V_SYNC         (),
        .BLANK          (),
        .display_data   ()
    );

endmodule
