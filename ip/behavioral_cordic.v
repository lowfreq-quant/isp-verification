`timescale 1ns / 1ps
// Behavioral CORDIC replacement for Xilinx IP "cordic_0"
// Computes magnitude (sqrt) from Cartesian coordinates
// Input:  {12'b0, gx[9:0], gy[9:0]}  (24-bit total, lower 20 bits valid)
// Output: sqrg[15:0] = round(sqrt(gx^2 + gy^2))
module behavioral_cordic (
    input  aclk,
    input  s_axis_cartesian_tvalid,
    input  [23:0] s_axis_cartesian_tdata,
    output m_axis_dout_tvalid,
    output [15:0]  m_axis_dout_tdata
);

    wire [19:0] val = s_axis_cartesian_tdata[19:0];
    wire [9:0]  gx  = val[19:10];
    wire [9:0]  gy  = val[9:0];
    wire [19:0] sq  = gx * gx + gy * gy;
    // Combinatorial sqrt: use bit-by-bit non-restoring algorithm
    wire [9:0] sqrt_val;
    gen_sqrt u_sqrt(.radicand(sq), .sqrt_result(sqrt_val));

    assign m_axis_dout_tdata  = {6'b0, sqrt_val};
    assign m_axis_dout_tvalid = s_axis_cartesian_tvalid;

endmodule

// Non-restoring square root for 20-bit input, 10-bit output
module gen_sqrt (
    input  [19:0] radicand,
    output [9:0]  sqrt_result
);
    reg [19:0] r_rad;
    reg [9:0]  r_res;
    reg [19:0] r_rem;
    integer i;
    reg [4:0]  r_shift;

    always @(*) begin
        r_rad = radicand;
        r_res = 10'b0;
        r_rem = 0;
        for (i = 0; i < 10; i = i + 1) begin
            r_rem = {r_rem[17:0], r_rad[19 - 2*i -: 2]};
            r_shift = {r_res[8:0], 1'b0} + 1;
            if (r_rem >= r_shift) begin
                r_rem = r_rem - r_shift;
                r_res[9 - i] = 1'b1;
            end
        end
    end
    assign sqrt_result = r_res;
endmodule
