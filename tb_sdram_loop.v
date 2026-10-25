`timescale 1ns / 1ps
// Independent write->read round-trip test for sdram_top + sdram_model.
//
// Goal: show whether the SDRAM write/read path actually preserves data.
// The full ISP_TOP_tb dumps ALL-ZERO display output, so we isolate the
// SDRAM chain here:
//   - after init_done, write N=1024 words (value = index) via wr_fifo
//     (wr_en pulse, w_data_in = index),
//   - then read them back via rd_en / r_data_out and compare.
//
// Run: iverilog -g2012 -s tb_sdram_loop -o sdram_loop.vvp \
//          ip/sdram_ip_wrappers.v ../sdram_controller/sdram_top.v \
//          ../sdram_controller/sram_ctrl.v ../sdram_controller/fifo_ctrl.v \
//          ../sdram_controller/sdram_model.v tb_sdram_loop.v
module tb_sdram_loop;
    reg          clk;        // all clocks are the same frequency here
    reg          rst_n;
    reg          ping_pong_en;
    reg  [23:0]  sdram_wr_addr_max;
    reg  [23:0]  sdram_wr_addr_min;
    reg  [23:0]  sdram_rd_addr_max;
    reg  [23:0]  sdram_rd_addr_min;
    reg  [15:0]  w_data_in;
    reg          wr_en;
    reg          rd_en;
    wire [15:0]  r_data_out;
    reg  [9:0]   br_length;
    reg          rd_valid;

    wire         init_done;
    wire         sdram_clk, sdram_cke, sdram_cs_n, sdram_ras_n, sdram_cas_n;
    wire         sdram_we_n;
    wire  [1:0]  sdram_dqm, sdram_bank;
    wire  [12:0] sdram_addr;
    wire  [15:0] sdram_data;

    always #10 clk = ~clk;   // 50 MHz

    sdram_top dut (
        .clk(clk), .rst_n(rst_n),
        .wr_clk(clk), .rd_clk(clk),
        .ping_pong_en(ping_pong_en),
        .sdram_wr_addr_max(sdram_wr_addr_max),
        .sdram_wr_addr_min(sdram_wr_addr_min),
        .sdram_rd_addr_max(sdram_rd_addr_max),
        .sdram_rd_addr_min(sdram_rd_addr_min),
        .w_data_in(w_data_in), .wr_en(wr_en), .rd_en(rd_en),
        .r_data_out(r_data_out), .br_length(br_length), .rd_valid(rd_valid),
        .init_done(init_done),
        .sdram_clk(sdram_clk), .sdram_cke(sdram_cke),
        .sdram_cs_n(sdram_cs_n), .sdram_ras_n(sdram_ras_n),
        .sdram_cas_n(sdram_cas_n), .sdram_we_n(sdram_we_n),
        .sdram_dqm(sdram_dqm), .sdram_bank(sdram_bank),
        .sdram_addr(sdram_addr), .sdram_data(sdram_data)
    );

    sdram_model_plus um (
        .Addr(sdram_addr), .Ba(sdram_bank), .Clk(sdram_clk), .Cke(sdram_cke),
        .Cs_n(sdram_cs_n), .Ras_n(sdram_ras_n), .Cas_n(sdram_cas_n),
        .We_n(sdram_we_n), .Dqm(2'b00), .Debug(1'b0), .Dq(sdram_data)
    );

    parameter N = 1024;
    integer i;
    integer wr_cnt;
    integer rd_cnt;
    integer err_cnt;
    integer guard;
    reg [15:0] expv;

    initial begin
        clk = 0; rst_n = 0;
        ping_pong_en = 0;  // single-region round trip: read follows write
        sdram_wr_addr_max = 24'd12288;
        sdram_wr_addr_min = 24'd0;
        sdram_rd_addr_max = 24'd12288;
        sdram_rd_addr_min = 24'd0;
        w_data_in = 0; wr_en = 0; rd_en = 0;
        br_length = 10'd512;
        rd_valid = 0;
        wr_cnt = 0; rd_cnt = 0; err_cnt = 0; guard = 0;

        #100 rst_n = 1;

        // Wait for SDRAM init (IDLE 20000 cy + 8x refresh + mode set ~= 21k cy)
        wait (init_done == 1);
        #200;
        $display("[%0t] init_done high, starting write", $time);

        // ---- write N words: drive on NEGEDGE so signals settle before the
        //      posedge that wr_fifo samples (avoids delta-order races) ----
        for (i = 0; i < N; i = i + 1) begin
            @(negedge clk);
            w_data_in = i[15:0];
            wr_en = 1;
        end
        @(negedge clk);
        wr_en = 0;
        $display("[%0t] write beats fed, waiting for wr_fifo to drain", $time);

        // wait until wr_fifo is empty: poll count via hierarchical path
        wait (dut.u_wr_fifo.wr_ptr == dut.u_wr_fifo.rd_ptr);
        #500;
        $display("[%0t] wr_fifo drained, starting read", $time);

        // ---- read back: rd_valid=1 so fifo_ctrl requests reads; pull
        //      rd_en only when rd_fifo actually has a word (dout_valid),
        //      then compare r_data_out ----
        rd_valid = 1;
        while (rd_cnt < N && guard < N * 40) begin
            @(negedge clk);
            if (rd_cnt < N && !dut.u_rd_fifo.empty) begin
                rd_en = 1;
                expv = rd_cnt[15:0];
                if (r_data_out !== expv) begin
                    err_cnt = err_cnt + 1;
                    if (err_cnt <= 8)
                        $display("[%0t] MISMATCH rd_cnt=%0d got=%04h exp=%04h",
                                 $time, rd_cnt, r_data_out, expv);
                end
                rd_cnt = rd_cnt + 1;
            end
            guard = guard + 1;
        end
        rd_en = 0;
        rd_valid = 0;

        #200;
        $display("==============================================");
        $display("read %0d words, %0d mismatches", rd_cnt, err_cnt);
        if (rd_cnt == N && err_cnt == 0)
            $display(">>> PASS: SDRAM write->read round trip preserves data");
        else
            $display(">>> FAIL");
        $finish;
    end

    initial begin
        #10000000 $display(">>> TIMEOUT; read %0d words", (rd_cnt));
        $finish;
    end

endmodule