`timescale 1ns / 1ps
// Behavioral wrappers for Xilinx IPs used in sdram_top.v
// These replace the actual Xilinx IP cores for simulation.

// ============================================================================
// wr_fifo: Asynchronous FIFO (independent write/read clocks)
// Replaces Xilinx FIFO Generator in independent-clock mode.
// Simplified behavioral model: uses a shared memory with Gray-code pointers.
// For simulation, we use a simple dual-port model.
// ============================================================================
module wr_fifo (
    input  rst,
    input  wr_clk,
    input  rd_clk,
    input  [15:0] din,
    input  wr_en,
    input  rd_en,
    output [15:0] dout,
    output full,
    output empty,
    output [9:0] rd_data_count,
    output [9:0] wr_data_count,
    output wr_rst_busy,
    output rd_rst_busy
);
    parameter DEPTH = 1024;

    reg [15:0] mem [0:DEPTH-1];
    reg [9:0] wr_ptr;
    reg [9:0] rd_ptr;
    reg [15:0] dout_reg;
    reg dout_valid;

    // Same FWFT counting argument applies to the WRITE-side count: the
    // word prefetched into dout_reg is still readable, so the true
    // occupancy is (wr_ptr - rd_ptr) + dout_valid on BOTH sides.  The
    // pre-fix count_w omitted dout_valid, under-counting by 1, which made
    // fifo_ctrl's read-side `rd_data_count < br_length` threshold behave
    // erratically (it consumes rd_fifo.wr_data_count).
    wire [10:0] count_w = (wr_ptr - rd_ptr) + dout_valid;
    // FWFT counts: the word already prefetched into dout_reg is still
    // readable (it IS dout), so the real read-side occupancy is
    // (wr_ptr - rd_ptr) + dout_valid.  The pre-fix count omitted
    // dout_valid, under-counting by 1 exactly when dout_valid=1, which made
    // fifo_ctrl's `wr_data_count >= br_length` / `< br_length` thresholds
    // off by one and dead-locked the write path (full-ISP_TOP_tb dumps
    // all-zero because nothing ever gets written).
    wire [10:0] count_r = (wr_ptr - rd_ptr) + dout_valid;  // read-domain approx

    assign full  = (count_w >= DEPTH);
    assign empty = !dout_valid;
    assign dout  = dout_reg;
    assign rd_data_count = count_r[9:0];
    assign wr_data_count = count_w[9:0];
    assign wr_rst_busy = rst;
    assign rd_rst_busy = rst;

    // Write port
    always @(posedge wr_clk) begin
        if (rst) begin
            wr_ptr <= 0;
        end else if (wr_en && !full) begin
            mem[wr_ptr] <= din;
            wr_ptr <= wr_ptr + 1;
        end
    end

    // Read port (FWFT behavior)
    always @(posedge rd_clk) begin
        if (rst) begin
            rd_ptr   <= 0;
            dout_reg <= 0;
            dout_valid <= 0;
        end else begin
            if (!dout_valid && (wr_ptr != rd_ptr)) begin
                dout_reg   <= mem[rd_ptr];
                rd_ptr     <= rd_ptr + 1;
                dout_valid <= 1;
            end else if (rd_en && dout_valid) begin
                if (wr_ptr != rd_ptr) begin
                    dout_reg <= mem[rd_ptr];
                    rd_ptr   <= rd_ptr + 1;
                end else begin
                    dout_valid <= 0;
                end
            end
        end
    end
endmodule

// ============================================================================
// sdram_pll: Behavioral clock wizard replacement
// clk_out1 = input clock (SDRAM controller clock)
// clk_out2 = input clock (SDRAM interface clock, same freq for simulation)
// ============================================================================
module sdram_pll (
    output clk_out1,
    output clk_out2,
    input  reset,
    output locked,
    input  clk_in1
);
    assign clk_out1 = clk_in1;
    assign clk_out2 = clk_in1;
    assign locked   = !reset;
endmodule
