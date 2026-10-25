`timescale 1ns / 1ps
// Cycle-dump variant of tb_sdram_loop.v.
//
// Same stimulus as tb_sdram_loop.v (write N=1024 words through the wr_fifo,
// read them back through the rd_fifo), but instead of only self-checking it
// dumps one line per clock posedge for the cycle-exact Python model
// (verify_sdram_loop.py) to replay and compare:
//
//     time(ns) state state_cnt cmd addr bank wr_ack rd_ack wr_en
//     wr_req rd_req wr_addr rd_addr rdata
//
// (decimal fields; rdata is "zzzz" when the DQ bus is high-Z).
//
// Run from sim/:  python run_sdram_loop.py
module tb_sdram_loop_dump;
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

    // ---- per-posedge cycle dump (pre-NBA values, like the other dumps) ----
    integer dump_fd;
    initial dump_fd = $fopen("output/sdram_cycles_rtl.txt", "w");

    always @(posedge clk) begin
        if (dut.U_SDRAM_CTRL_0.sdram_data_r === 16'hzzzz)
            $fwrite(dump_fd, "%0d ns %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d zzzz\n",
                    $time,
                    dut.U_SDRAM_CTRL_0.state,
                    dut.U_SDRAM_CTRL_0.state_cnt,
                    dut.U_SDRAM_CTRL_0.sdram_cmd,
                    dut.U_SDRAM_CTRL_0.sdram_addr,
                    dut.U_SDRAM_CTRL_0.sdram_bank,
                    dut.U_SDRAM_CTRL_0.wr_ack,
                    dut.U_SDRAM_CTRL_0.rd_ack,
                    dut.U_SDRAM_CTRL_0.wr_en,
                    dut.U_FIFO_CTRL_0.wr_req,
                    dut.U_FIFO_CTRL_0.rd_req,
                    dut.U_FIFO_CTRL_0.sdram_wr_addr,
                    dut.U_FIFO_CTRL_0.sdram_rd_addr);
        else
            $fwrite(dump_fd, "%0d ns %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d\n",
                    $time,
                    dut.U_SDRAM_CTRL_0.state,
                    dut.U_SDRAM_CTRL_0.state_cnt,
                    dut.U_SDRAM_CTRL_0.sdram_cmd,
                    dut.U_SDRAM_CTRL_0.sdram_addr,
                    dut.U_SDRAM_CTRL_0.sdram_bank,
                    dut.U_SDRAM_CTRL_0.wr_ack,
                    dut.U_SDRAM_CTRL_0.rd_ack,
                    dut.U_SDRAM_CTRL_0.wr_en,
                    dut.U_FIFO_CTRL_0.wr_req,
                    dut.U_FIFO_CTRL_0.rd_req,
                    dut.U_FIFO_CTRL_0.sdram_wr_addr,
                    dut.U_FIFO_CTRL_0.sdram_rd_addr,
                    dut.U_SDRAM_CTRL_0.sdram_data_r);
    end

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

        for (i = 0; i < N; i = i + 1) begin
            @(negedge clk);
            w_data_in = i[15:0];
            wr_en = 1;
        end
        @(negedge clk);
        wr_en = 0;
        $display("[%0t] write beats fed, waiting for wr_fifo to drain", $time);

        wait (dut.u_wr_fifo.wr_ptr == dut.u_wr_fifo.rd_ptr);
        #500;
        $display("[%0t] wr_fifo drained, starting read", $time);

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
        $fclose(dump_fd);
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
