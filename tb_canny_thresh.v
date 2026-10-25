`timescale 1ns/1ps
// Canny is_edge white-box dump TB (rebuilt 2026-09-19; original lost).
// Produces sim/canny_thresh_dump.txt for verify_thresh_path.py PART 2.
// Same negedge-drive / posedge-capture / negedge-dump protocol as
// tb_sobel_thresh.v. Vectors transcribed 1:1 from CANNY_VECTORS in
// verify_thresh_path.py; canny_pack = (phase<<13)|(thresh<<11)|(mag&0x7FF).
module tb_canny_thresh;
reg         clk;
reg         rst_n;
reg         i_HSYNC;
reg         i_VSYNC;
reg         i_BLANK;
reg [14:0]  c_in;
wire        H_SYNC;
wire        V_SYNC;
wire        BLANK;
wire [15:0] display_data;

reg d_hsync, d_vsync, d_blank, d_rst;
always @(posedge clk) begin
    d_hsync <= i_HSYNC;
    d_vsync <= i_VSYNC;
    d_blank <= i_BLANK;
    d_rst   <= rst_n;
end

    canny u_canny (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .canny_in       (c_in),
        .H_SYNC         (H_SYNC),
        .V_SYNC         (V_SYNC),
        .BLANK          (BLANK),
        .display_data   (display_data)
    );

    initial clk = 0;
    always #5 clk = ~clk;    // 10 ns period

    integer fd;
    integer vid, r, c;
    reg [14:0] last;

    function [14:0] pack3;
        input [1:0] ph, th;
        input [10:0] mag;
        begin
            pack3 = (ph << 13) | (th << 11) | (mag & 11'h7FF);
        end
    endfunction

    function [14:0] canny_pix;
        input integer v, rr, cc;
        begin
            case (v)
                1: case (rr)
                        0: canny_pix = pack3(0, 2, 50);
                        1: canny_pix = pack3(0, 2, 100);
                        2: canny_pix = pack3(0, 2, 150);
                        default: canny_pix = pack3(0, 2, 200);
                   endcase
                2: case (rr)
                        0: canny_pix = pack3(0, 3, 100);
                        1: canny_pix = pack3(2, 3, 200);
                        2: canny_pix = pack3(1, 3, 300);
                        3: canny_pix = pack3(3, 3, 400);
                        default: canny_pix = pack3(0, 3, 500);
                   endcase
                3: case (rr)
                        0: canny_pix = pack3(0, 1, 100);
                        1: canny_pix = pack3(1, 1, 200);
                        2: canny_pix = pack3(2, 1, 300);
                        default: canny_pix = pack3(3, 1, 400);
                   endcase
                4: canny_pix = pack3(0, 2, 300);
                5: canny_pix = (rr % 2 == 0) ? pack3(2, 2, 500) : pack3(2, 2, 300);
                6: case (rr)
                        0, 1: canny_pix = pack3(0, 3, 500);
                        2, 3, 4: canny_pix = pack3(1, 2, 300);
                        5: canny_pix = pack3(0, 1, 100);
                        default: canny_pix = pack3(1, 2, 300);
                   endcase
                7: canny_pix = (rr % 2 == 0) ? pack3(3, 2, 500) : pack3(3, 2, 300);
                default: canny_pix = (cc < 320) ? pack3(0, 2, 300)   // vid 8 step
                                                : pack3(0, 2, 500);
            endcase
        end
    endfunction

    function integer canny_rows;
        input integer v;
        begin
            case (v)
                3: canny_rows = 4;
                5, 7: canny_rows = 6;
                6: canny_rows = 9;
                default: canny_rows = 5;   // vids 1, 2, 4, 8
            endcase
        end
    endfunction

    task do_reset;
        begin
            @(negedge clk);
            rst_n = 0; i_HSYNC = 0; i_VSYNC = 0; i_BLANK = 0; c_in = 0;
            repeat (4) @(posedge clk);
            @(negedge clk);
            rst_n = 1;
        end
    endtask

    task do_cycle;
        input [14:0] pix;
        input hs, vs;
        input integer v;
        begin
            c_in = pix; i_HSYNC = hs; i_VSYNC = vs; i_BLANK = 1;
            @(posedge clk);
            @(negedge clk);
            $fwrite(fd, "%0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
                v,
                u_canny.U_MATRIX_GENERATOR_0.line_cnt,
                u_canny.U_MATRIX_GENERATOR_0.col_cnt,
                u_canny.o_matrix11, u_canny.o_matrix12, u_canny.o_matrix13,
                u_canny.o_matrix21, u_canny.o_matrix22, u_canny.o_matrix23,
                u_canny.o_matrix31, u_canny.o_matrix32, u_canny.o_matrix33,
                u_canny.is_edge,
                d_hsync, d_vsync, d_blank, d_rst);
        end
    endtask

    initial begin
        rst_n = 0; i_HSYNC = 0; i_VSYNC = 0; i_BLANK = 0; c_in = 0;
        fd = $fopen("canny_thresh_dump.txt", "w");
        $fwrite(fd, "# vid line col m11 m12 m13 m21 m22 m23 m31 m32 m33 is_edge hsync vsync blank rst\n");
        last = 0;
        for (vid = 1; vid <= 8; vid = vid + 1) begin
            do_reset;
            do_cycle(last, 0, 1, vid);   // VSYNC cycle
            for (r = 0; r < canny_rows(vid); r = r + 1) begin
                for (c = 0; c < 640; c = c + 1)
                    do_cycle(canny_pix(vid, r, c), 0, 0, vid);
                last = canny_pix(vid, r, 639);
                do_cycle(last, 1, 0, vid);   // HSYNC cycle
            end
        end
        $fclose(fd);
        $display("Canny thresh dump complete");
        $finish;
    end

endmodule
