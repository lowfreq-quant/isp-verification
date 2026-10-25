`timescale 1ns/1ps
// Exhaustive RGB565 -> Y0/U0/V0 dump (rebuilt 2026-09-19; original lost).
// verify_rgb2yuv_independent.py expects sim/rgb2yuv_dump.txt with a '# ...'
// header line followed by 65536 lines of "%04h %02h %02h %02h" (rgb Y0 U0 V0).
// NOTE: the module MUST stay named tb_rgb2yuv_dump (with a 'y') even though
// the file is tb_rgb_uv_dump.v -- run_all.py compiles this file with
// "-s tb_rgb2yuv_dump".
module tb_rgb2yuv_dump;
reg         clk;
reg         i_BLANK;
reg         i_HSYNC;
reg         i_VSYNC;
reg [15:0]  i_display_data;
reg         rst_n;
wire [15:0] display_data;
wire [7:0]  Y0;
integer     fd;
integer     rgb;
integer     settled;

    RGB2YUV uut (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_display_data (i_display_data),
        .H_SYNC         (),
        .V_SYNC         (),
        .BLANK          (),
        .Y0             (Y0),
        .display_data   (display_data)
    );

    initial clk = 0;
    always #5 clk = ~clk;    // 10 ns period

    initial begin
        rst_n = 0; i_BLANK = 0; i_HSYNC = 0; i_VSYNC = 0; i_display_data = 0;
        repeat (4) @(posedge clk);
        rst_n = 1;
        repeat (2) @(posedge clk);
        fd = $fopen("rgb2yuv_dump.txt", "w");
        $fwrite(fd, "# rgb Y0 U0 V0   (exhaustive RGB565 sweep, 65536 lines)\n");
        // Hold each input steady for 5 cycles so the 3-stage pipeline fully
        // settles regardless of the exact stage count.
        for (rgb = 0; rgb < 65536; rgb = rgb + 1) begin
            @(negedge clk);
            i_display_data = rgb[15:0];
            i_BLANK = 1;
            repeat (5) @(posedge clk);
            @(negedge clk);
            settled = Y0;    // reference settled to quiet lint about unused
            $fwrite(fd, "%04h %02h %02h %02h\n", rgb[15:0], uut.Y0, uut.U0, uut.V0);
        end
        $fclose(fd);
        $display("RGB2YUV dump complete: 65536 lines");
        $finish;
    end

endmodule
