"""Cycle-exact Python model of the SDRAM write/read chain.

Replicates, cycle by cycle:
  - sdram_controller/sram_ctrl.v   (module sdram_ctrl): FSM, commands, acks
  - sdram_controller/fifo_ctrl.v   : request generation + address tracking
  - sim/ip/sdram_ip_wrappers.v     : FWFT wr_fifo / rd_fifo behaviour
  - a minimal SDRAM response (CL=3, burst of br_length) sufficient to
    reproduce rdata timing

The model prints one line per cycle in the SAME format as the RTL dump
(tb_sdram_loop_dump.v -> output/sdram_cycles_rtl.txt):

    time state state_cnt cmd(5b) addr(5h) bank(2b) wr_ack rd_ack wr_en
    wr_req rd_req sdram_wr_addr sdram_rd_addr rdata(4h)

Run `verify_sdram_loop.py` to compare both files (max_diff must be 0).
"""

# ---------------------------------------------------------------------------
# FWFT fifo model (mirrors wr_fifo in sdram_ip_wrappers.v)
# ---------------------------------------------------------------------------
class FwftFifo:
    def __init__(self, depth=1024):
        self.depth = depth
        self.mem = [0] * depth
        self.wr_ptr = 0
        self.rd_ptr = 0
        self.dout_reg = 0
        self.dout_valid = 0

    def count(self):
        # Occupancy reported to fifo_ctrl.  The behavioural wrapper exposes
        # (wr_ptr - rd_ptr) as the count, but its FWFT dout register holds an
        # extra word that the controller must also see, so include it.
        return ((self.wr_ptr - self.rd_ptr) % self.depth) + self.dout_valid

    def full(self):
        return self.count() >= self.depth

    def empty(self):
        return not self.dout_valid

    def dout(self):
        return self.dout_reg

    def clock(self, wr_en, din, rd_en):
        # RTL NBA semantics: the write port commits at the clock edge, but
        # the read/prefetch logic samples the PRE-EDGE pointers, so a word
        # written this cycle cannot be seen by the prefetch until the next.
        old_wr_ptr = self.wr_ptr
        old_rd_ptr = self.rd_ptr
        old_dout_valid = self.dout_valid

        # write side
        if wr_en and not self.full():
            self.mem[self.wr_ptr] = din
            self.wr_ptr = (self.wr_ptr + 1) % self.depth
        # read side (FWFT pre-fetch)
        if not old_dout_valid and old_wr_ptr != old_rd_ptr:
            self.dout_reg = self.mem[old_rd_ptr]
            self.rd_ptr = (old_rd_ptr + 1) % self.depth
            self.dout_valid = 1
        elif rd_en and old_dout_valid:
            if old_rd_ptr != old_wr_ptr:
                self.dout_reg = self.mem[old_rd_ptr]
                self.rd_ptr = (old_rd_ptr + 1) % self.depth
            else:
                self.dout_valid = 0


# ---------------------------------------------------------------------------
# fifo_ctrl model (mirrors fifo_ctrl.v)
# ---------------------------------------------------------------------------
class FifoCtrl:
    def __init__(self, ping_pong_en, wr_addr_max, wr_addr_min,
                 rd_addr_max, rd_addr_min, br_length):
        self.ping_pong_en = ping_pong_en
        self.wr_max = wr_addr_max
        self.wr_min = wr_addr_min
        self.rd_max = rd_addr_max
        self.rd_min = rd_addr_min
        self.br = br_length
        self.wr_ack_r = 0
        self.rd_ack_r = 0
        self.sdram_wr_addr = wr_addr_min
        self.sdram_rd_addr = (~rd_addr_min & 0x800000) if ping_pong_en else rd_addr_min
        self.wr_req = 0
        self.rd_req = 0

    def clock(self, wr_data_count, rd_data_count, wr_ack, rd_ack, rd_valid):
        # pos is combinational on the PREVIOUS shift-register value; the
        # address update (also posedge) samples it one cycle later, so the
        # address advances one cycle after the ack falls.
        wr_ack_pos = (self.wr_ack_r == 0b10)
        rd_ack_pos = (self.rd_ack_r == 0b10)
        self.wr_ack_r = ((self.wr_ack_r & 1) << 1) | (wr_ack & 1)
        self.rd_ack_r = ((self.rd_ack_r & 1) << 1) | (rd_ack & 1)

        # write address
        if wr_ack_pos:
            if self.sdram_wr_addr + self.br >= (
                    (self.sdram_wr_addr & 0x800000) | (self.wr_max & 0x7FFFFF)):
                if self.ping_pong_en:
                    self.sdram_wr_addr = ((~self.sdram_wr_addr) & 0x800000) | (self.wr_min & 0x7FFFFF)
                else:
                    self.sdram_wr_addr = self.wr_min
            else:
                self.sdram_wr_addr = self.sdram_wr_addr + self.br

        # read address
        if rd_ack_pos:
            if self.sdram_rd_addr + self.br >= (
                    (self.sdram_rd_addr & 0x800000) | (self.rd_max & 0x7FFFFF)):
                if self.ping_pong_en:
                    if ((self.sdram_wr_addr ^ self.sdram_rd_addr) & 0x800000):
                        self.sdram_rd_addr = (self.sdram_rd_addr & 0x800000) | (self.rd_min & 0x7FFFFF)
                    else:
                        self.sdram_rd_addr = ((~self.sdram_rd_addr) & 0x800000) | (self.rd_min & 0x7FFFFF)
                else:
                    self.sdram_rd_addr = self.rd_min
            else:
                self.sdram_rd_addr = self.sdram_rd_addr + self.br

        # requests
        self.wr_req = 1 if wr_data_count >= self.br else 0
        self.rd_req = 1 if (rd_data_count < self.br and rd_valid) else 0


# ---------------------------------------------------------------------------
# sram_ctrl model (mirrors sram_ctrl.v, module sdram_ctrl)
# ---------------------------------------------------------------------------
class SramCtrl:
    IDLE = 0; PRE_CHARGE = 1; T_PRE_CHARGE = 2; AUTO_REFRESH = 3
    T_AUTO_REFRESH = 4; MODE_REG_SET = 5; T_MODE_REG_SET = 6; ARBIT = 7
    W_AUTO_REFRESH = 8; T_W_AUTO_REFRESH = 9; ACTIVE = 10; WR_PRE = 11
    WRITE = 12; WD = 13; WR_TERM = 14; W_PRE_CHARGE = 15
    T_W_PRE_CHARGE = 16; READ = 17; R_CL = 18; RD = 19; RD_TERM = 20
    RD_POST = 21

    # states that zero state_cnt
    CNT_ZERO = {PRE_CHARGE, AUTO_REFRESH, MODE_REG_SET, W_AUTO_REFRESH,
                WRITE, W_PRE_CHARGE, READ}

    def __init__(self, br_length):
        self.br = br_length
        self.state = self.IDLE
        self.state_cnt = 0
        self.next_state = self.IDLE
        self.init_ar_cnt = 0
        self.arf_req = 0
        self.arf_ack = 0
        self.arf_cnt = 0
        self.init_done = 0
        self.sdram_cmd = 0b01111
        self.sdram_addr = 0x1FFF
        self.sdram_bank = 0b11
        self.wr_en = 0
        self.wr_ack = 0
        self.rd_ack = 0
        self.rd_post_d = 0
        self.rd_data_cnt = 0
        self.sdram_data_r = 0
        self.rdata = 0
        self.dq_is_z = False   # reset state: rdata=0000
        # external inputs
        self.wr_sys_addr = 0
        self.rd_sys_addr = 0

    def _next_state_logic(self):
        s = self.state
        c = self.state_cnt
        if s == self.IDLE:
            return self.PRE_CHARGE if c == 20000 - 1 else self.IDLE
        if s == self.PRE_CHARGE:
            return self.T_PRE_CHARGE
        if s == self.T_PRE_CHARGE:
            return self.AUTO_REFRESH if c == 2 else self.T_PRE_CHARGE
        if s == self.AUTO_REFRESH:
            return self.T_AUTO_REFRESH
        if s == self.T_AUTO_REFRESH:
            if c == 5:
                return self.MODE_REG_SET if self.init_ar_cnt == 8 else self.AUTO_REFRESH
            return self.T_AUTO_REFRESH
        if s == self.MODE_REG_SET:
            return self.T_MODE_REG_SET
        if s == self.T_MODE_REG_SET:
            return self.ARBIT if c == 5 else self.T_MODE_REG_SET
        if s == self.ARBIT:
            if self.arf_req:
                return self.W_AUTO_REFRESH
            if self.wr_req or self.rd_req:
                return self.ACTIVE
            return self.ARBIT
        if s == self.W_AUTO_REFRESH:
            return self.T_W_AUTO_REFRESH
        if s == self.T_W_AUTO_REFRESH:
            return self.ARBIT if c == 5 else self.T_W_AUTO_REFRESH
        if s == self.ACTIVE:
            return self.WR_PRE
        if s == self.WR_PRE:
            return self.WRITE if self.wr_req else self.READ
        if s == self.WRITE:
            return self.WR_TERM if self.br == 1 else self.WD
        if s == self.WD:
            return self.WR_TERM if c == self.br - 2 else self.WD
        if s == self.WR_TERM:
            return self.W_PRE_CHARGE
        if s == self.W_PRE_CHARGE:
            return self.T_W_PRE_CHARGE
        if s == self.T_W_PRE_CHARGE:
            return self.ARBIT if c == 2 else self.T_W_PRE_CHARGE
        if s == self.READ:
            return self.R_CL
        if s == self.R_CL:
            return self.RD if c == 1 else self.R_CL
        if s == self.RD:
            return self.RD_TERM if c == self.br - 2 else self.RD
        if s == self.RD_TERM:
            return self.RD_POST
        if s == self.RD_POST:
            return self.W_PRE_CHARGE if c == self.br + 1 else self.RD_POST
        return s

    def _cmd_logic(self, s=None):
        if s is None:
            s = self.state
        # default
        cmd, addr, bank = 0b10111, 0x1FFF, 0b11
        if s in (self.PRE_CHARGE, self.W_PRE_CHARGE):
            cmd = 0b10010
        elif s in (self.AUTO_REFRESH, self.W_AUTO_REFRESH):
            cmd = 0b10001
        elif s == self.MODE_REG_SET:
            cmd = 0b10000
            bank = 0b00
            addr = (0b000 << 10) | (0b0 << 9) | (0b00 << 7) | (0b011 << 4) | (0b0 << 3) | 0b111
        elif s == self.ACTIVE:
            cmd = 0b10011
            if self.wr_req:
                bank = (self.wr_sys_addr >> 22) & 0b11
                addr = (self.wr_sys_addr >> 9) & 0x1FFF
            else:
                bank = (self.rd_sys_addr >> 22) & 0b11
                addr = (self.rd_sys_addr >> 9) & 0x1FFF
        elif s == self.WRITE:
            cmd = 0b10100
            bank = (self.wr_sys_addr >> 22) & 0b11
            addr = self.wr_sys_addr & 0x1FF
        elif s == self.READ:
            cmd = 0b10101
            bank = (self.rd_sys_addr >> 22) & 0b11
            addr = self.rd_sys_addr & 0x1FF
        elif s in (self.WR_TERM, self.RD_TERM):
            cmd = 0b10110
        return cmd, addr, bank

    def clock(self, wr_sys_addr, rd_sys_addr, wr_req, rd_req, wdata,
              sdram_dq, # SDRAM-driven DQ value (or None if zzz)
              rd_valid, rst_n=1):
        if not rst_n:
            self.state = self.IDLE
            self.state_cnt = 0
            self.init_ar_cnt = 0
            self.arf_req = 0
            self.arf_ack = 0
            self.arf_cnt = 0
            self.init_done = 0
            self.sdram_cmd = 0b01111
            self.sdram_addr = 0x1FFF
            self.sdram_bank = 0b11
            self.wr_en = 0
            self.wr_ack = 0
            self.rd_ack = 0
            self.rd_post_d = 0
            self.rd_data_cnt = 0
            self.sdram_data_r = 0
            self.rdata = 0
            self.dq_is_z = False   # RTL: rdata 复位为 0000
            return
        self.wr_sys_addr = wr_sys_addr
        self.rd_sys_addr = rd_sys_addr
        self.wr_req = wr_req
        self.rd_req = rd_req

        # ALL combinational decisions use PRE-EDGE (old) values, exactly
        # like the RTL always blocks sample the pre-posedge state.
        s_old = self.state
        c_old = self.state_cnt

        # state (registered): next_state is a pure function of old state/cnt
        self.next_state = self._next_state_logic()
        self.state = self.next_state

        # state_cnt (registered, uses old state to decide zeroing)
        if s_old in self.CNT_ZERO:
            self.state_cnt = 0
        else:
            self.state_cnt = c_old + 1

        # arf_cnt / arf_req
        if self.arf_cnt == 250:
            self.arf_req = 1
            self.arf_cnt = 0
        else:
            self.arf_cnt = self.arf_cnt + 1
        if self.arf_ack:          # arf_ack is old value here (updated below)
            self.arf_req = 0

        # init_ar_cnt
        if s_old == self.AUTO_REFRESH:
            self.init_ar_cnt = self.init_ar_cnt + 1

        # arf_ack (registered)
        self.arf_ack = 1 if s_old == self.W_AUTO_REFRESH else 0

        # init_done (registered)
        if s_old == self.ARBIT:
            self.init_done = 1

        # cmd/addr/bank (registered; uses OLD state)
        cmd, addr, bank = self._cmd_logic(s_old)
        self.sdram_cmd = cmd
        self.sdram_addr = addr
        self.sdram_bank = bank

        # wr_en / wr_ack use OLD state and OLD state_cnt.
        # DQ (sdram_data) is driven by the PREVIOUS wr_en (register), so
        # save it before updating.
        wr_en_prev = self.wr_en
        s = s_old
        if s in (self.WR_PRE, self.WRITE) or (s == self.WD and c_old < self.br - 1):
            self.wr_en = 1
        else:
            self.wr_en = 0

        if self.br == 1:
            self.wr_ack = 1 if s == self.WRITE else 0
        elif self.br == 2:
            self.wr_ack = 1 if (s == self.WRITE or s == self.WD) else 0
        else:
            self.wr_ack = 1 if (s == self.WRITE or
                                (s == self.WD and c_old < self.br - 1)) else 0

        # rd_data_cnt (registered)
        dcnt_old = self.rd_data_cnt
        if s == self.READ:
            self.rd_data_cnt = 0
        else:
            self.rd_data_cnt = dcnt_old + 1

        # rd_post_d (samples OLD rd_data_cnt, like the RTL)
        if s == self.RD_POST:
            self.rd_post_d = 1
        elif dcnt_old >= 4 + self.br:
            self.rd_post_d = 0

        # rd_ack (samples OLD rd_data_cnt and OLD rd_post_d)
        if (s in (self.RD, self.RD_TERM, self.RD_POST) or self.rd_post_d) and \
                (3 <= dcnt_old < 3 + self.br):
            self.rd_ack = 1
        else:
            self.rd_ack = 0

        # sdram_data_r (rdata); DQ = wr_en ? wdata : sdram_dq (uses the
        # PREVIOUS cycle's wr_en, exactly like the RTL register)
        self.dq_is_z = (not wr_en_prev) and (sdram_dq is None)
        dq = wdata if wr_en_prev else (sdram_dq if sdram_dq is not None else 0)
        self.sdram_data_r = dq
        self.rdata = dq


# ---------------------------------------------------------------------------
# Minimal SDRAM response model (data plane only; CL=3)
# ---------------------------------------------------------------------------
class SdramResp:
    """Burst response: WRITE command latches the start address and samples
    DQ once per cycle (write latency 0); READ drives the stored word after
    CAS latency 3, one word per cycle for br_length cycles."""
    def __init__(self, br):
        self.br = br
        self.reading = False
        self.read_cnt = 0
        self.writing = False
        self.write_cnt = 0
        self.col = 0
        self.row = 0
        self.bank = 0
        self.mem = {}  # (bank,row,col) -> 16-bit value

    def clock(self, cmd, addr, bank, dq_from_ctrl, wdata, wr_en):
        """cmd/addr/bank: values on the SDRAM bus THIS cycle (already
        registered in sram_ctrl). Returns the DQ value the SDRAM drives
        (None = high-z)."""
        # ACTIVE: latches the ROW address (addr carries the row, bank carries
        # the bank) -- the row used by the following READ/WRITE burst
        if cmd == 0b10011:  # ACTIVE
            self.row = addr & 0x1FFF
            self.bank = bank
        # WRITE command: latch column, begin burst (DQ already holds word0)
        if cmd == 0b10100:  # WRITE
            self.col = addr & 0x1FF
            self.writing = True
            self.write_cnt = 0
        # READ command: latch column; data appears after CAS latency 3
        if cmd == 0b10101:  # READ
            self.col = addr & 0x1FF
            self.reading = True
            self.read_cnt = -3     # CL=3: 3 cycles until first word
        # write burst: one word per cycle sampled from DQ
        if self.writing:
            self.mem[(self.bank, self.row,
                      (self.col + self.write_cnt) & 0x1FF)] = \
                wdata if wr_en else 0
            self.write_cnt += 1
            if self.write_cnt >= self.br:
                self.writing = False
        # read burst: drive one word per cycle after CL
        if self.reading:
            if self.read_cnt < 0:       # still inside CAS latency
                self.read_cnt += 1
            elif self.read_cnt < self.br:
                v = self.mem.get((self.bank, self.row,
                                  (self.col + self.read_cnt) & 0x1FF), 0)
                self.read_cnt += 1
                return v
            else:
                self.reading = False
        return None


def run_model():
    """Drive the Python model exactly like tb_sdram_loop.v and emit one line
    per cycle in the RTL dump format.  Returns list of lines."""
    N = 1024
    br = 512
    wr_max = 12288
    wr_min = 0
    rd_max = 12288
    rd_min = 0

    wr_fifo = FwftFifo()
    rd_fifo = FwftFifo()
    fc = FifoCtrl(ping_pong_en=False, wr_addr_max=wr_max, wr_addr_min=wr_min,
                  rd_addr_max=rd_max, rd_addr_min=rd_min, br_length=br)
    sc = SramCtrl(br)
    sd = SdramResp(br)

    lines = []
    t = 0          # ns
    clk = 0        # first toggles to 1 at t=10 (posedge), like RTL
    rst_n = 0      # tb: rst_n=0 until t=100ns
    w_data_in = 0
    wr_en_ext = 0
    rd_en_ext = 0
    rd_valid = 0

    phase = "init"        # init -> write -> drain -> read -> done
    fed = 0               # words fed to wr_fifo
    rd_cnt = 0
    guard = 0
    init_done_t = None    # time init_done first asserted (tb waits #200)
    drain_t = None        # time wr_fifo became empty (tb waits #500)
    finish_t = None       # time last word read (tb waits #200 before $finish)

    def posedge_sample():
        """One posedge of clk: FIRST record pre-edge state (the RTL dump
        $fwrite runs in parallel with the FSM always-blocks, so it sees the
        pre-NBA values), THEN clock all blocks."""
        nonlocal rd_valid, rst_n, init_done_t
        # --- record pre-edge values (matches RTL dump semantics) ---
        rd_s = "zzzz" if sc.dq_is_z else ("%0d" % sc.rdata)
        lines.append("%0d ns %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %0d %s" % (
            t, sc.state, sc.state_cnt, sc.sdram_cmd, sc.sdram_addr,
            sc.sdram_bank, sc.wr_ack, sc.rd_ack, sc.wr_en,
            fc.wr_req, fc.rd_req, fc.sdram_wr_addr, fc.sdram_rd_addr,
            rd_s))
        # --- now clock everything (pre-edge values propagate) ---
        # NOTE: sram_ctrl's FSM samples wr_req/rd_req with their PRE-EDGE
        # values (same posedge updates both), so pass the values captured
        # before fifo_ctrl's registers update.  Likewise wdata is the
        # combinational wr_fifo.dout BEFORE this posedge's fifo pop, and
        # rd_fifo's din is rdata BEFORE this posedge's update.
        wr_req_old = fc.wr_req
        rd_req_old = fc.rd_req
        wdata_old = wr_fifo.dout()
        rdata_old = sc.rdata
        wc = wr_fifo.count()
        rc = rd_fifo.count()
        wr_ack_s = sc.wr_ack
        rd_ack_s = sc.rd_ack
        fc.clock(wc, rc, wr_ack_s, rd_ack_s, rd_valid)

        # SDRAM response sees the registered cmd/addr/bank
        cmd = sc.sdram_cmd
        addr = sc.sdram_addr
        bank = sc.sdram_bank
        dq = sd.clock(cmd, addr, bank, None, wdata_old, sc.wr_en)

        wr_fifo.clock(wr_en_ext, w_data_in, sc.wr_ack)
        sc.clock(fc.sdram_wr_addr, fc.sdram_rd_addr, wr_req_old, rd_req_old,
                 wdata_old, dq, rd_valid, rst_n)
        rd_fifo.clock(rd_ack_s, rdata_old, rd_en_ext)

    # main loop: one 20ns clock period per iteration; stimulus is applied
    # on the NEGEDGE (tb drives @(negedge clk)), FSM samples on the POSEDGE.
    def stimulus():
        nonlocal rst_n, phase, fed, wr_en_ext, w_data_in, rd_en_ext, rd_valid, init_done_t, rd_cnt, drain_t, finish_t
        if phase == "init":
            if t == 100:
                rst_n = 1
            if sc.init_done and init_done_t is None:
                init_done_t = t
            # transition to write on the SAME cycle (RTL tb falls straight
            # into the write loop after #200 + @(negedge))
            if init_done_t is not None and t >= init_done_t + 200:
                phase = "write"
                w_data_in = 0
                wr_en_ext = 1
                fed = 1
                return True
        elif phase == "write":
            if fed < N:
                w_data_in = fed
                wr_en_ext = 1
                fed += 1
            else:
                wr_en_ext = 0
        elif phase == "read":
            if rd_cnt < N:
                if not rd_fifo.empty():
                    rd_en_ext = 1
                    rd_cnt += 1
                    if rd_cnt == N:
                        # tb exits the while loop on this same negedge and
                        # immediately drops rd_en/rd_valid, then #200
                        rd_en_ext = 0
                        rd_valid = 0
                        if finish_t is None:
                            finish_t = t
                else:
                    rd_en_ext = 0
            else:
                rd_en_ext = 0
                rd_valid = 0
                # tb keeps running 200 ns after the last word (before $finish)
                if t >= finish_t + 200:
                    return False
                return True
        return True

    while True:
        clk = ~clk & 1
        t += 10
        # absolute-time check: rd_valid rises #500 after wr_fifo drains,
        # exactly like the RTL tb (not aligned to any clock edge)
        if phase == "write" and drain_t is not None and t >= drain_t + 500                 and not rd_valid:
            phase = "read"
            rd_valid = 1
        if clk == 1:     # posedge: FSM samples
            posedge_sample()
            # tb's wait(wr_ptr==rd_ptr) resolves right after the posedge
            # that pops the last word; record that instant
            if phase == "write" and fed >= N                     and wr_fifo.wr_ptr == wr_fifo.rd_ptr and drain_t is None:
                drain_t = t
        else:            # negedge: tb drives inputs
            if not stimulus():
                break
        if t > 600000:
            print("MODEL TIMEOUT at", t)
            break
    return lines


def main():
    rtl = open("output/sdram_cycles_rtl.txt").read().splitlines()
    model = run_model()
    open("output/sdram_cycles_model.txt", "w").write(chr(10).join(model) + chr(10))

    print(f"RTL   lines: {len(rtl)}")
    print(f"MODEL lines: {len(model)}")
    n = min(len(rtl), len(model))
    mism = 0
    for i in range(n):
        if rtl[i] != model[i]:
            mism += 1
            if mism <= 10:
                print(f"MISMATCH line {i}:")
                print(f"  RTL  : {rtl[i]}")
                print(f"  MODEL: {model[i]}")
    if mism == 0 and len(rtl) == len(model):
        print(">>> PASS: cycle-exact match (max_diff = 0)")
    else:
        print(f">>> FAIL: {mism} mismatching lines of {n} compared")
        if len(rtl) != len(model):
            print(f"    length differs: RTL={len(rtl)} model={len(model)}")


if __name__ == "__main__":
    main()
