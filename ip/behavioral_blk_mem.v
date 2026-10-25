`timescale 1ns / 1ps
// Behavioral models for the Xilinx Block Memory Generator IPs used by the
// point-operation modules (LOG / HISTOGRAM_EQ).  Both are configured as
// WRITE-FIRST simple dual-port memories with a REGISTERED port-B read
// (1 cycle latency), matching the standard blk_mem_gen "Simple Dual Port
// RAM, registered output" configuration the RTL was written against.
//
// NOTE: the real design loads the LOG ROM content from log.mif (README:
// "a LUT is used by calculating the output value of 256 grey values in
// advance ... loaded into a rom").  The .mif is not checked into the
// repository, so for simulation the ROM is loaded from ip/log_lut.hex,
// which gen_pointops_lut.py generates from the documented formula
//     s = c * log(1 + r),  c chosen so that s(255) = 255.
// verify_pointops.py recomputes the same formula independently and checks
// the ROM dump against it, so the check is not circular w.r.t. the RTL
// datapath (address wiring, read latency, RGB565 packing).

// blk_mem_gen_0 : 256 x 8 single-port ROM (LOG lookup table)
module blk_mem_gen_0 (
    input             clka,
    input             ena,
    input      [7:0]  addra,
    output reg [7:0]  douta
);
    reg [7:0] mem [0:255];
    initial begin
        $readmemh("ip/log_lut.hex", mem);
        douta = 8'b0;
    end
    always @(posedge clka) begin
        if (ena) douta <= mem[addra];
    end
endmodule

// blk_mem_gen_1 : 256 x 32 simple dual-port RAM
//   port A: write (wea/addra/dina), port B: read (addrb -> doutb, 1 cycle)
module blk_mem_gen_1 (
    input             clka,
    input             ena,
    input             wea,
    input      [7:0]  addra,
    input      [31:0] dina,
    input             clkb,
    input             enb,
    input      [7:0]  addrb,
    output reg [31:0] doutb
);
    reg [31:0] mem [0:255];
    integer i;
    initial begin
        for (i = 0; i < 256; i = i + 1) mem[i] = 32'b0;
        doutb = 32'b0;
    end
    always @(posedge clka) begin
        if (ena && wea) mem[addra] <= dina;
    end
    always @(posedge clkb) begin
        if (enb) doutb <= mem[addrb];
    end
endmodule
