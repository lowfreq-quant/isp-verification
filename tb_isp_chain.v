`timescale 1ns/1ps
// ISP_TOP data-path testbench (no SDRAM): RGB565 -> RGB2YUV -> Y0 fan-out ->
// {LOG, gaussian_filter, median_filter, sobel -> canny}.
//
// Layout mirrors ISP_TOP.v's parallel topology: RGB2YUV's Y0 and its
// registered syncs drive every downstream module; sobel -> canny is the only
// series connection (canny consumes sobel's canny_in and sobel's registered
// syncs, with canny's own internal 15-bit matrix_generator).
//
// HISTOGRAM / HISTOGRAM_EQ are intentionally NOT instantiated here: their
// pseudo-stretch/equalization needs a single-reset + frame-head-blank
// protocol (covered cycle-accurately by test_pointops.py), which conflicts
// with the per-frame-reset protocol used for the matrix filters.
//
// All stimulus is driven by test_isp_chain.py (cocotb); this file only
// instantiates the DUTs and exposes their outputs.
module tb_isp_chain(
    input               clk,
    input               rst_n,
    input               i_HSYNC,
    input               i_VSYNC,
    input               i_BLANK,
    input        [15:0] i_display_data,   // RGB565
    // RGB2YUV outputs
    output       [7:0]  rgb_Y0,
    output       [15:0] rgb_disp,
    output              rgb_HSYNC, rgb_VSYNC, rgb_BLANK,
    // LOG
    output       [15:0] lg_disp,
    output              lg_HSYNC, lg_VSYNC, lg_BLANK,
    // gaussian
    output       [15:0] g_disp,
    output              g_HSYNC, g_VSYNC, g_BLANK,
    // median
    output       [15:0] m_disp,
    output              m_HSYNC, m_VSYNC, m_BLANK,
    // sobel
    output       [15:0] s_disp,
    output              s_HSYNC, s_VSYNC, s_BLANK,
    output       [14:0] s_canny_in,
    // canny
    output       [15:0] c_disp,
    output              c_HSYNC, c_VSYNC, c_BLANK
);

    wire [7:0]  Y0_grey;
    wire [15:0] display_data_grey;
    wire        i_HSYNC_grey, i_VSYNC_grey, i_BLANK_grey;

    RGB2YUV u_rgb (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC), .i_VSYNC(i_VSYNC), .i_BLANK(i_BLANK),
        .i_display_data(i_display_data),
        .H_SYNC(i_HSYNC_grey), .V_SYNC(i_VSYNC_grey), .BLANK(i_BLANK_grey),
        .Y0(Y0_grey), .display_data(display_data_grey)
    );

    assign rgb_Y0    = Y0_grey;
    assign rgb_disp  = display_data_grey;
    assign rgb_HSYNC = i_HSYNC_grey;
    assign rgb_VSYNC = i_VSYNC_grey;
    assign rgb_BLANK = i_BLANK_grey;

    LOG u_log (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC_grey), .i_VSYNC(i_VSYNC_grey), .i_BLANK(i_BLANK_grey),
        .i_Y0(Y0_grey),
        .H_SYNC(lg_HSYNC), .V_SYNC(lg_VSYNC), .BLANK(lg_BLANK),
        .display_data(lg_disp)
    );

    gaussian_filter u_gauss (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC_grey), .i_VSYNC(i_VSYNC_grey), .i_BLANK(i_BLANK_grey),
        .i_Y0(Y0_grey),
        .H_SYNC(g_HSYNC), .V_SYNC(g_VSYNC), .BLANK(g_BLANK),
        .display_data(g_disp)
    );

    median_filter u_med (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC_grey), .i_VSYNC(i_VSYNC_grey), .i_BLANK(i_BLANK_grey),
        .i_Y0(Y0_grey),
        .H_SYNC(m_HSYNC), .V_SYNC(m_VSYNC), .BLANK(m_BLANK),
        .display_data(m_disp)
    );

    sobel u_sobel (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC_grey), .i_VSYNC(i_VSYNC_grey), .i_BLANK(i_BLANK_grey),
        .i_Y0(Y0_grey),
        .thresh_min(11'd60), .thresh_max(11'd120),
        .H_SYNC(s_HSYNC), .V_SYNC(s_VSYNC), .BLANK(s_BLANK),
        .canny_in(s_canny_in), .display_data(s_disp)
    );

    canny u_canny (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(s_HSYNC), .i_VSYNC(s_VSYNC), .i_BLANK(s_BLANK),
        .canny_in(s_canny_in),
        .H_SYNC(c_HSYNC), .V_SYNC(c_VSYNC), .BLANK(c_BLANK),
        .display_data(c_disp)
    );

endmodule