`timescale 1ns / 1ps
// Behavioral FIFO with FWFT (First Word Fall Through) behavior
// Matches Xilinx FIFO Generator FWFT mode: dout shows next data combinationally
module behavioral_fifo #(
    parameter DATA_WIDTH = 8,
    parameter FIFO_DEPTH = 1024
)(
    input  clk,
    input  rst,
    input  [DATA_WIDTH-1:0] din,
    input  wr_en,
    input  rd_en,
    output [DATA_WIDTH-1:0] dout,
    output full,
    output empty,
    output wr_rst_busy,
    output rd_rst_busy
);

    reg [DATA_WIDTH-1:0] mem [0:FIFO_DEPTH-1];
    reg [$clog2(FIFO_DEPTH):0] count;
    reg [$clog2(FIFO_DEPTH)-1:0] wr_ptr;
    reg [$clog2(FIFO_DEPTH)-1:0] rd_ptr;
    reg [DATA_WIDTH-1:0] dout_reg;
    reg dout_valid;

    assign full  = (count >= FIFO_DEPTH);
    assign empty = !dout_valid;
    assign dout  = dout_reg;
    assign wr_rst_busy = rst;
    assign rd_rst_busy = rst;

    always @(posedge clk) begin
        if (rst) begin
            count      <= 0;
            wr_ptr     <= 0;
            rd_ptr     <= 0;
            dout_reg   <= {DATA_WIDTH{1'b0}};
            dout_valid <= 1'b0;
        end else begin
            // Write
            if (wr_en && !full) begin
                mem[wr_ptr] <= din;
                wr_ptr <= wr_ptr + 1'b1;
            end

            // FWFT: if output register is empty but FIFO has data, fill it
            if (!dout_valid && count > 0) begin
                dout_reg   <= mem[rd_ptr];
                rd_ptr     <= rd_ptr + 1'b1;
                dout_valid <= 1'b1;
            end
            // Read: advance to next data when consumer reads
            else if (rd_en && dout_valid) begin
                if (rd_ptr != wr_ptr) begin
                    dout_reg <= mem[rd_ptr];
                    rd_ptr   <= rd_ptr + 1'b1;
                end else begin
                    dout_valid <= 1'b0;
                end
            end

            // Update count
            if (wr_en && !rd_en && !full)
                count <= count + 1'b1;
            else if (!wr_en && rd_en && dout_valid)
                count <= count - 1'b1;
            // Simultaneous read/write: count unchanged
        end
    end

endmodule
