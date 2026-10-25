`timescale 1ns/1ps
// Standalone RGB2YUV waveform TB (rebuilt 2026-09-19; original lost to a 404 overwrite).
// verify_vcd.py parses the resulting waveform.vcd by VCD identifier codes, so
// the declaration order below reproduces the original file's identifier
// assignment: display_data="!  Y0='"  V_SYNC="#  H_SYNC="$  BLANK="%  clk="&
// i_BLANK="'  i_HSYNC="(  i_VSYNC=")  i_display_data="*  rst_n="+.
module tb_waveform;
wire [15:0] display_data;
wire [7:0]  Y0;
wire        V_SYNC;
wire        H_SYNC;
wire        BLANK;
reg         clk;
reg         i_BLANK;
reg         i_HSYNC;
reg         i_VSYNC;
reg [15:0]  i_display_data;
reg         rst_n;

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

    initial clk = 0;
    always #20 clk = ~clk;   // 40 ns period

    // 10-step colour sequence that verify_vcd.py expects, in order:
    // Black, Red, Green, Blue, White, Red, Green, Blue, White, Black.
    // The leading Black lives in the t=0 dumpvars image; the other 9 are
    // driven 40 ns apart. Outputs pair with inputs by index, so the only
    // requirement is order preservation (pipeline is 1:1).
    initial begin
        $dumpfile("waveform.vcd");
        $dumpvars(0, tb_waveform);
        i_BLANK = 1; i_HSYNC = 0; i_VSYNC = 0; i_display_data = 16'h0000;
        rst_n = 0;
        #210 rst_n = 1;
        #30;                    // t = 240 ns : sync pulse
        i_VSYNC = 1; i_HSYNC = 1; i_BLANK = 0;
        #40;                    // t = 280 ns : pixels begin
        i_VSYNC = 0; i_HSYNC = 0; i_display_data = 16'hF800;  // Red
        #40 i_display_data = 16'h07E0;  // Green
        #40 i_display_data = 16'h001F;  // Blue
        #40 i_display_data = 16'hFFFF;  // White
        #40 i_display_data = 16'hF800;  // Red
        #40 i_display_data = 16'h07E0;  // Green
        #40 i_display_data = 16'h001F;  // Blue
        #40 i_display_data = 16'hFFFF;  // White
        #40 i_display_data = 16'h0000;  // Black
        #40;                    // t = 640 ns : trailer
        i_VSYNC = 0; i_HSYNC = 0; i_BLANK = 1;
        #200;
        $display("Waveform simulation complete");
        $finish;
    end

endmodule
