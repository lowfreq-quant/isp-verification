`timescale 1ns/1ps
// Sobel thresh->canny_in white-box dump TB (rebuilt 2026-09-19; original lost).
// Produces sim/sobel_thresh_dump.txt for verify_thresh_path.py PART 1.
// Protocol (matches verify_thresh_path.replay_sobel exactly):
//   per vector vid: reset (4 cycles, not dumped) -> 1 VSYNC cycle
//   (i_Y0 = last pixel of previous vector, BLANK=1, VSYNC=1) ->
//   per row: 640 pixel cycles (BLANK=1) + 1 HSYNC cycle (i_Y0 = row[639]).
// Sampling: stimulus is driven at negedge; input flags are captured at
// posedge into d_* (avoids the old posedge+#1 race); the dump happens at the
// following negedge, i.e. every record holds post-posedge RTL outputs paired
// with the flags sampled at that same posedge. Reset release also happens at
// negedge so no half-cycle ghost appears.
// Vectors are transcribed 1:1 from SOBEL_VECTORS in verify_thresh_path.py.
module tb_sobel_thresh;
reg         clk;
reg         rst_n;
reg         i_HSYNC;
reg         i_VSYNC;
reg         i_BLANK;
reg [7:0]   i_Y0;
reg [10:0]  thresh_min;
reg [10:0]  thresh_max;
wire        H_SYNC;
wire        V_SYNC;
wire        BLANK;
wire [14:0] canny_in;
wire [15:0] display_data;

// Input flags captured at posedge (what the RTL actually sampled)
reg d_hsync, d_vsync, d_blank, d_rst;
always @(posedge clk) begin
    d_hsync <= i_HSYNC;
    d_vsync <= i_VSYNC;
    d_blank <= i_BLANK;
    d_rst   <= rst_n;
end

    sobel u_sobel (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .thresh_min     (thresh_min),
        .thresh_max     (thresh_max),
        .H_SYNC         (H_SYNC),
        .V_SYNC         (V_SYNC),
        .BLANK          (BLANK),
        .canny_in       (canny_in),
        .display_data   (display_data)
    );

    initial clk = 0;
    always #5 clk = ~clk;    // 10 ns period

    integer fd;
    integer vid, r, c;
    reg [7:0] last;
    integer tmin, tmax;

    function [7:0] sob_pix;
        input integer v, rr, cc;
        begin
            case (v)
                1: sob_pix = (rr < 2) ? 8'd10 : 8'd24;
                2: sob_pix = (rr < 2) ? 8'd10 : 8'd25;
                3: sob_pix = (rr < 2) ? 8'd10 : 8'd26;
                4: sob_pix = (rr < 2) ? 8'd10 : 8'd40;
                5: sob_pix = (rr < 2) ? 8'd10 : 8'd41;
                6: sob_pix = (rr < 2) ? 8'd41 : 8'd10;
                7: sob_pix = (rr < 2) ? 8'd0  : 8'd255;
                8: sob_pix = (cc < 320) ? 8'd100 : 8'd200;
                9: sob_pix = (cc < (320 + rr)) ? 8'd100 : 8'd200;
                10: case (rr)
                        0, 1:    sob_pix = 8'd10;
                        2, 3:    sob_pix = 8'd35;
                        4, 5:    sob_pix = 8'd36;
                        default: sob_pix = 8'd34;
                     endcase
                default: sob_pix = 8'd10;   // vids 11, 12
            endcase
        end
    endfunction

    function integer sob_rows;
        input integer v;
        begin
            case (v)
                9:  sob_rows = 6;
                10: sob_rows = 8;
                11, 12: sob_rows = 4;
                default: sob_rows = 5;   // vids 1..8
            endcase
        end
    endfunction

    task do_reset;
        begin
            @(negedge clk);
            rst_n = 0; i_HSYNC = 0; i_VSYNC = 0; i_BLANK = 0; i_Y0 = 0;
            repeat (4) @(posedge clk);
            @(negedge clk);
            rst_n = 1;
        end
    endtask

    // Drive one dumped cycle: the caller always resumes at a negedge
    // (right after the previous dump, or right after reset release), so set
    // up the inputs immediately -- exactly ONE posedge per dumped record.
    // d_* (captured at that posedge) then equal the driven inputs, and the
    // negedge dump holds post-posedge RTL outputs, matching model.clock().
    task do_cycle;
        input [7:0] pix;
        input hs, vs;
        input integer v;
        begin
            i_Y0 = pix; i_HSYNC = hs; i_VSYNC = vs; i_BLANK = 1;
            @(posedge clk);
            @(negedge clk);
            $fwrite(fd, "%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
                v,
                u_sobel.U_MATRIX_GENERATOR_0.line_cnt,
                u_sobel.U_MATRIX_GENERATOR_0.col_cnt,
                u_sobel.o_matrix11, u_sobel.o_matrix12, u_sobel.o_matrix13,
                u_sobel.o_matrix21, u_sobel.o_matrix22, u_sobel.o_matrix23,
                u_sobel.o_matrix31, u_sobel.o_matrix32, u_sobel.o_matrix33,
                u_sobel.gx, u_sobel.g, u_sobel.sqrg,
                u_sobel.phase, u_sobel.thresh, u_sobel.canny_in,
                thresh_min, thresh_max,
                d_hsync, d_vsync, d_blank, d_rst);
        end
    endtask

    initial begin
        rst_n = 0; i_HSYNC = 0; i_VSYNC = 0; i_BLANK = 0; i_Y0 = 0;
        thresh_min = 0; thresh_max = 0;
        fd = $fopen("sobel_thresh_dump.txt", "w");
        $fwrite(fd, "# vid line col m11 m12 m13 m21 m22 m23 m31 m32 m33 gx g sqrg phase thresh canny_in tmin tmax hsync vsync blank rst\n");
        last = 0;
        for (vid = 1; vid <= 12; vid = vid + 1) begin
            case (vid)
                10: begin tmin = 100; tmax = 100; end
                11: begin tmin = 0;   tmax = 2047; end
                default: begin tmin = 60; tmax = 120; end
            endcase
            thresh_min = tmin; thresh_max = tmax;
            do_reset;
            // VSYNC cycle carries the previous vector's last pixel
            do_cycle(last, 0, 1, vid);
            for (r = 0; r < sob_rows(vid); r = r + 1) begin
                for (c = 0; c < 640; c = c + 1)
                    do_cycle(sob_pix(vid, r, c), 0, 0, vid);
                last = sob_pix(vid, r, 639);
                do_cycle(last, 1, 0, vid);   // HSYNC cycle
            end
        end
        $fclose(fd);
        $display("Sobel thresh dump complete");
        $finish;
    end

endmodule
