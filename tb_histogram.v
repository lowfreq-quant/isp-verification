`timescale 1ns/1ps
// Standalone HISTOGRAM TB (rebuilt 2026-09-19; original lost to a 404 overwrite).
// run_all.py only requires histogram_waveform.vcd to exist; run_iverilog_all.py
// requires the "Histogram stretch test complete" message. Declaration order
// reproduces the original VCD identifiers; the send_blank/send_pixel tasks
// are kept because the old VCD references them (GTKWave familiarity).
module tb_histogram;
wire [15:0] display_data;
wire [7:0]  Y0;
wire        V_SYNC;
wire        H_SYNC;
wire        BLANK;
reg         clk;
reg         i_BLANK;
reg         i_HSYNC;
reg         i_VSYNC;
reg [7:0]   i_Y0;
reg         rst_n;

    HISTOGRAM uut (
        .clk            (clk),
        .rst_n          (rst_n),
        .i_HSYNC        (i_HSYNC),
        .i_VSYNC        (i_VSYNC),
        .i_BLANK        (i_BLANK),
        .i_Y0           (i_Y0),
        .H_SYNC         (H_SYNC),
        .V_SYNC         (V_SYNC),
        .BLANK          (BLANK),
        .Y0             (Y0),
        .display_data   (display_data)
    );

    initial clk = 0;
    always #20 clk = ~clk;   // 40 ns period

    task send_blank;
        begin
            @(negedge clk);
            i_BLANK = 0; i_HSYNC = 0; i_VSYNC = 0; i_Y0 = 8'd0;
            @(negedge clk);
        end
    endtask

    task send_pixel;
        input [7:0] val;
        begin
            @(negedge clk);
            i_BLANK = 1; i_HSYNC = 0; i_VSYNC = 0; i_Y0 = val;
            @(negedge clk);
        end
    endtask

    integer i;
    initial begin
        $dumpfile("histogram_waveform.vcd");
        $dumpvars(0, tb_histogram);
        rst_n = 0; i_BLANK = 0; i_HSYNC = 0; i_VSYNC = 0; i_Y0 = 8'd0;
        repeat (5) @(negedge clk);
        rst_n = 1;
        // Frame 1: VSYNC pulse then a ramp frame (min/max learn 0..252)
        @(negedge clk);
        i_VSYNC = 1; i_BLANK = 0;
        @(negedge clk);
        i_VSYNC = 0;
        for (i = 0; i < 64; i = i + 1) begin
            send_pixel(i * 4);
            if (i % 16 == 15) send_blank;
        end
        // Frame 2: exercises the previous-frame stretch path
        @(negedge clk);
        i_VSYNC = 1; i_BLANK = 0;
        @(negedge clk);
        i_VSYNC = 0;
        for (i = 0; i < 64; i = i + 1) begin
            send_pixel(8'd200 - i);
        end
        repeat (10) @(negedge clk);
        $display("Histogram stretch test complete");
        $finish;
    end

endmodule
