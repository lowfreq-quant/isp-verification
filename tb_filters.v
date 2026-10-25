`timescale 1ns/1ps
// Combined filters top for cocotb (rebuilt 2026-09-19; original lost to a 404 overwrite).
// Consumers: test_filters.py, test_golden.py, test_probe.py.
//   - test_filters drives dut.{clk,rst_n,i_BLANK,i_Y0,i_HSYNC,i_VSYNC,
//     thresh_min,thresh_max} and reads dut.{g,m,s}_display.
//   - test_golden additionally reads dut.{g,s,m}_{BLANK,HSYNC,VSYNC}.
//   - test_probe reaches into dut.u_gaussian.U_MATRIX_GENERATOR_0.o_matrix*
//     and dut.u_gaussian.{gs_1,gs_2,gs_3,gs_sum,gs_data}, so the gaussian
//     instance MUST be named u_gaussian (U_MATRIX_GENERATOR_0 comes from
//     gaussian_filter.v itself).
module tb_filters(
    input               clk,
    input               rst_n,
    input               i_HSYNC,
    input               i_VSYNC,
    input               i_BLANK,
    input       [7:0]   i_Y0,
    input       [10:0]  thresh_min,
    input       [10:0]  thresh_max,
    output              g_HSYNC,
    output              g_VSYNC,
    output              g_BLANK,
    output      [15:0]  g_display,
    output              s_HSYNC,
    output              s_VSYNC,
    output              s_BLANK,
    output      [15:0]  s_display,
    output              m_HSYNC,
    output              m_VSYNC,
    output              m_BLANK,
    output      [15:0]  m_display
);

    gaussian_filter u_gaussian (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (g_HSYNC),
        .V_SYNC         (g_VSYNC),
        .BLANK          (g_BLANK),
        .display_data   (g_display)
    );

    // Sobel_detection variant (display = sqrg>120 binary; canny_in unused here)
    sobel u_sobel (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .thresh_min     (thresh_min),
        .thresh_max     (thresh_max),
        .H_SYNC         (s_HSYNC),
        .V_SYNC         (s_VSYNC),
        .BLANK          (s_BLANK),
        .canny_in       (),
        .display_data   (s_display)
    );

    median_filter u_median (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (m_HSYNC),
        .V_SYNC         (m_VSYNC),
        .BLANK          (m_BLANK),
        .display_data   (m_display)
    );

endmodule
