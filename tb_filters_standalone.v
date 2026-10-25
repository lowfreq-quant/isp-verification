`timescale 1ns/1ps
// Standalone filters TB (rebuilt 2026-09-19; original lost to a 404 overwrite).
// run_iverilog_all.py requires ">>> PASS" in the output. Streams a uniform
// frame and a step frame (each from a clean reset, like test_golden.py) and
// self-checks mid-frame (rows 5..7, fully interior window): gaussian/median
// pass uniform through, sobel stays quiet on uniform and fires on the step.
// Protocol: one posedge per pixel, HSYNC merged into each row's last pixel,
// stimulus driven at negedge (same phase discipline as tb_sobel_thresh.v).
module tb_filters_standalone;
parameter BLANK_GAP = 40;
parameter H = 10;
parameter W = 640;

reg         clk;
reg         i_BLANK;
reg         i_HSYNC;
reg         i_VSYNC;
reg [7:0]   i_Y0;
reg         rst_n;
reg [10:0]  thresh_max;
reg [10:0]  thresh_min;
wire [15:0] g_display;
wire        g_VSYNC, g_HSYNC, g_BLANK;
wire [15:0] m_display;
wire        m_VSYNC, m_HSYNC, m_BLANK;
wire [15:0] s_display;
wire [14:0] s_canny_in;
wire        s_VSYNC, s_HSYNC, s_BLANK;

integer col, errors, idx, img_num, row;

    function [7:0] rgb565_to_y;
        input [15:0] pixel;
        reg [5:0] g6;
        reg [7:0] r8, g8, b8;
        begin
            r8 = {pixel[15:11], pixel[15:13]};
            g6 = pixel[10:5];
            g8 = {g6, pixel[10:9]};
            b8 = {pixel[4:0], pixel[4:2]};
            rgb565_to_y = (r8 * 77 + g8 * 150 + b8 * 29) >> 8;
        end
    endfunction

    function [15:0] pack_y;
        input [7:0] y;
        begin
            pack_y = ((y >> 3) << 11) | ((y >> 2) << 5) | (y >> 3);
        end
    endfunction

    gaussian_filter u_gaussian (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC), .i_VSYNC(i_VSYNC), .i_BLANK(i_BLANK), .i_Y0(i_Y0),
        .H_SYNC(g_HSYNC), .V_SYNC(g_VSYNC), .BLANK(g_BLANK),
        .display_data(g_display)
    );

    median_filter u_median (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC), .i_VSYNC(i_VSYNC), .i_BLANK(i_BLANK), .i_Y0(i_Y0),
        .H_SYNC(m_HSYNC), .V_SYNC(m_VSYNC), .BLANK(m_BLANK),
        .display_data(m_display)
    );

    sobel u_sobel (
        .clk(clk), .rst_n(rst_n),
        .i_HSYNC(i_HSYNC), .i_VSYNC(i_VSYNC), .i_BLANK(i_BLANK), .i_Y0(i_Y0),
        .thresh_min(thresh_min), .thresh_max(thresh_max),
        .H_SYNC(s_HSYNC), .V_SYNC(s_VSYNC), .BLANK(s_BLANK),
        .canny_in(s_canny_in), .display_data(s_display)
    );

    initial clk = 0;
    always #5 clk = ~clk;    // 10 ns period

    task inter_reset;
        begin
            @(negedge clk);
            rst_n = 0; i_HSYNC = 0; i_VSYNC = 0; i_BLANK = 0; i_Y0 = 0;
            repeat (4) @(posedge clk);
            @(negedge clk);
            rst_n = 1;
        end
    endtask

    // One pixel per call. Caller must resume at a negedge: set up
    // immediately, exactly one posedge per pixel.
    task send_pix;
        input [7:0] p;
        input hs;
        begin
            i_Y0 = p; i_HSYNC = hs; i_VSYNC = 0; i_BLANK = 1;
            @(posedge clk);
            @(negedge clk);
        end
    endtask

    task send_vsync;
        begin
            i_BLANK = 1; i_VSYNC = 1; i_HSYNC = 0; i_Y0 = 0;
            @(posedge clk);
            @(negedge clk);
        end
    endtask

    reg [15:0] exp_uniform;
    integer n_g, n_m, n_s_white, n_s_black;
    initial begin
        $dumpfile("filters_standalone.vcd");
        $dumpvars(0, tb_filters_standalone);
        errors = 0;
        thresh_min = 50; thresh_max = 150;
        rst_n = 0; i_BLANK = 0; i_HSYNC = 0; i_VSYNC = 0; i_Y0 = 0;
        repeat (4) @(posedge clk);

        // ---- image 0 : uniform 128, sample rows 5..7 (interior) ----
        img_num = 0;
        inter_reset;
        @(negedge clk);
        send_vsync;
        exp_uniform = pack_y(8'd128);
        n_g = 0; n_m = 0; n_s_black = 0;
        for (row = 0; row < H; row = row + 1) begin
            for (col = 0; col < W; col = col + 1) begin
                send_pix(8'd128, (col == W - 1));
                if (row >= 5 && row <= 7) begin
                    if (g_display == exp_uniform) n_g = n_g + 1;
                    if (m_display == exp_uniform) n_m = n_m + 1;
                    if (s_display == 0) n_s_black = n_s_black + 1;
                end
            end
        end
        $display("uniform128: gauss %0d/1920, median %0d/1920 match 0x%04h",
                 n_g, n_m, exp_uniform);
        $display("sobel uniform: %0d/1920 quiet", n_s_black);
        if (n_g < 1800) begin errors = errors + 1; $display("FAIL: gaussian uniform"); end
        if (n_m < 1800) begin errors = errors + 1; $display("FAIL: median uniform"); end
        if (n_s_black != 1920) begin errors = errors + 1; $display("FAIL: sobel noisy on uniform"); end

        // ---- image 1 : vertical step, sobel must fire mid-frame ----
        img_num = 1;
        inter_reset;
        @(negedge clk);
        send_vsync;
        n_s_white = 0;
        for (row = 0; row < H; row = row + 1) begin
            for (col = 0; col < W; col = col + 1) begin
                send_pix((col < W / 2) ? 8'd0 : 8'd255, (col == W - 1));
                if (row >= 5 && row <= 7 && s_display == 16'hFFFF)
                    n_s_white = n_s_white + 1;
            end
        end
        $display("sobel step: %0d edge pixels", n_s_white);
        if (n_s_white == 0) begin errors = errors + 1; $display("FAIL: sobel missed step"); end

        // keep shared-function coverage honest (also silences lint)
        idx = n_g + n_m + n_s_white + n_s_black + img_num + rgb565_to_y(16'hF800);
        $display("info: checksum %0d", idx);
        if (errors == 0)
            $display(">>> PASS");
        else
            $display(">>> FAIL (%0d errors)", errors);
        $finish;
    end

endmodule
