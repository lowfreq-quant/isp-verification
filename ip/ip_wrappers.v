`timescale 1ns / 1ps
// Wrapper: matrix_fifo = 8-bit behavioral FIFO
// FIFO_DEPTH must be >= 2*WIDTH = 1280 for 640-wide images: matrix_generator
// writes lines 0..N into fifo_2 while reading starts at line 2, so fifo_2 must
// hold up to 2 full rows simultaneously. 1024 caused silent overflow during
// lines 0/1, losing 256 pixels of row 1 and corrupting every output row >= 3
// for column-varying images (step_h, random). 2048 leaves comfortable margin.
module matrix_fifo (
    input  clk,
    input  rst,
    input  [7:0] din,
    input  wr_en,
    input  rd_en,
    output [7:0] dout,
    output full,
    output empty,
    output wr_rst_busy,
    output rd_rst_busy
);
    behavioral_fifo #(.DATA_WIDTH(8), .FIFO_DEPTH(2048)) u (
        .clk(clk), .rst(rst), .din(din), .wr_en(wr_en),
        .rd_en(rd_en), .dout(dout), .full(full), .empty(empty),
        .wr_rst_busy(wr_rst_busy), .rd_rst_busy(rd_rst_busy)
    );
endmodule

// Wrapper: cordic_0 = Xilinx CORDIC IP, used as sqrt in Sobel
module cordic_0 (
    input  aclk,
    input  s_axis_cartesian_tvalid,
    input  [23:0] s_axis_cartesian_tdata,
    output m_axis_dout_tvalid,
    output [15:0]  m_axis_dout_tdata
);
    behavioral_cordic u (
        .aclk(aclk),
        .s_axis_cartesian_tvalid(s_axis_cartesian_tvalid),
        .s_axis_cartesian_tdata(s_axis_cartesian_tdata),
        .m_axis_dout_tvalid(m_axis_dout_tvalid),
        .m_axis_dout_tdata(m_axis_dout_tdata)
    );
endmodule

// Wrapper: fifo_15bit = 15-bit behavioral FIFO
// FIFO_DEPTH must be >= 2*640 = 1280, same reason as matrix_fifo above
// (fifo_2 buffers 2 full rows before reads start at line 2). Was 1024,
// which would silently overflow for 640-wide rows in the canny path.
module fifo_15bit (
    input  clk,
    input  rst,
    input  [14:0] din,
    input  wr_en,
    input  rd_en,
    output [14:0] dout,
    output full,
    output empty,
    output wr_rst_busy,
    output rd_rst_busy
);
    behavioral_fifo #(.DATA_WIDTH(15), .FIFO_DEPTH(2048)) u (
        .clk(clk), .rst(rst), .din(din), .wr_en(wr_en),
        .rd_en(rd_en), .dout(dout), .full(full), .empty(empty),
        .wr_rst_busy(wr_rst_busy), .rd_rst_busy(rd_rst_busy)
    );
endmodule
