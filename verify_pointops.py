"""Golden-model verification for the four point-operation modules:
LOG, EMBOSS, HISTOGRAM (pseudo-stretch), HISTOGRAM_EQ (pseudo-equalization).

Two verification layers (same philosophy as verify_thresh_path.py):

  PART 1 - cycle-accurate replica: Python classes reproduce the RTL
           register-for-register (NBA semantics: all RHS sampled pre-edge,
           all LHS committed post-edge) and are compared against every cycle
           of pointops_dump.txt. Any mismatch => FAIL.

  PART 2 - functional intent: independent checks against the documented
           algorithms (README), NOT copies of the RTL:
             LOG        : ROM table == round(255*ln(1+r)/ln(256));
                          display output equals the table (incl. latency).
             EMBOSS     : display == clamp(r_prev - r + 150) packed RGB565.
             HISTOGRAM  : from frame 2 on, output == stretch with A/B being
                          the true min/max of the PREVIOUS frame (pseudo).
             HISTOGRAM_EQ: ram2 mapping vs the intended pseudo-equalization
                          map built from the true previous-frame histogram.
           PART 2 findings are reported; a deviation is printed as an RTL
           FINDING (the as-written replica of PART 1 still pins the RTL).

Requires sim/pointops_dump.txt produced by tb_pointops.v via run_pointops.py.
"""
import math
import os
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
DUMP = os.path.join(SIM_DIR, "pointops_dump.txt")
LUT_HEX = os.path.join(SIM_DIR, "ip", "log_lut.hex")

W, H = 640, 8
THRESHOLD = 150
MASK32 = 0xFFFFFFFF


def rgb565(g):
    return ((g >> 3) << 11) | ((g >> 2) << 5) | (g >> 3)


def log_table():
    c = 255.0 / math.log(256.0)
    return [int(round(c * math.log(1 + r))) for r in range(256)]


# ---------------------------------------------------------------------------
# Cycle-accurate models (as-written RTL replicas)
# ---------------------------------------------------------------------------

class LogModel:
    """LOG.v: blk_mem_gen_0 ROM, 1-cycle read latency; sync delayed 1 cycle."""

    def __init__(self, lut):
        self.lut = lut
        self.dout = 0
        self.hs = self.vs = self.bl = 0

    def reset(self):
        self.dout = 0
        self.hs = self.vs = self.bl = 0

    def cycle(self, y, h, v, b):
        # outputs = pre-edge register values
        out = (rgb565(self.dout), self.bl, self.hs, self.vs)
        # commit
        self.hs, self.vs, self.bl = h, v, b
        self.dout = self.lut[y]
        return out


class EmbossModel:
    """EMBOSS.v: emboss = r_Y0 - i_Y0 + threshold (signed), combinational out."""

    def __init__(self):
        self.ry = 0
        self.hs = self.vs = self.bl = 0

    def reset(self):
        self.ry = 0
        self.hs = self.vs = self.bl = 0

    def cycle(self, y, h, v, b):
        ev = self.ry - y + THRESHOLD          # signed, no overflow in range
        if ev > 255:
            disp = 0xFFFF
        elif ev < 0:
            disp = 0
        else:
            disp = rgb565(ev)
        out = (disp, self.bl, self.ry, ev & 0x3FF)
        self.ry = y
        self.hs, self.vs, self.bl = h, v, b
        return out


class HistogramModel:
    """HISTOGRAM.v pseudo-stretch, register-for-register."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.mn, self.mx = 255, 0
        self.mn_r, self.mx_r = 0, 0
        self.riv = 0b00
        self.num, self.den = 0, 255
        self.y0 = 0
        self.rh = self.rv = self.rb = 0b00

    def cycle(self, y, h, v, b):
        out = (rgb565(self.y0), self.rb >> 1 & 1,
               self.mn, self.mx, self.mn_r, self.mx_r,
               self.num, self.den, self.y0)
        vneg = (self.riv == 0b10)
        # RTL: Y0 <= numerator/denominator samples the PRE-edge values
        n_y0 = (self.num // self.den) & 0xFF
        old_mn, old_mx = self.mn, self.mx
        # min / max (i_BLANK takes priority over the VSYNC-neg reset)
        if b:
            if y < self.mn:
                self.mn = y
            if y > self.mx:
                self.mx = y
        elif vneg:
            self.mn, self.mx = 255, 0
        # numerator / denominator use PRE-edge min_r/max_r (RTL RHS pre-edge).
        # Width promotion pitfall: `numerator <= 255*(max_r - min_r)` with
        # numerator being reg [15:0] evaluates the subtraction at 16 bits
        # (0-255 = 65281, then 255*65281 mod 2^16 = 511), while
        # `denominator <= max_r - min_r` with denominator being reg [7:0]
        # wraps at 8 bits (0-255 = 1).  Mirror both widths exactly.
        if b:
            mnr, mxr = self.mn_r, self.mx_r
            if mnr == mxr:
                self.num = y
            elif y > mxr:
                self.num = (255 * ((mxr - mnr) & 0xFFFF)) & 0xFFFF
            elif y < mnr:
                self.num = 0
            else:
                self.num = (255 * ((y - mnr) & 0xFFFF)) & 0xFFFF
            self.den = 1 if mxr == mnr else ((mxr - mnr) & 0xFF)
        # latches: min_r <= min / max_r <= max with PRE-edge min/max
        if vneg:
            self.mn_r, self.mx_r = old_mn, old_mx
        # output divider commits Y0 from the pre-edge numerator/denominator
        self.y0 = n_y0
        # sync shifts
        self.rv = ((self.rv & 1) << 1) | v
        self.rh = ((self.rh & 1) << 1) | h
        self.rb = ((self.rb & 1) << 1) | b
        self.riv = ((self.riv & 1) << 1) | v
        return out


class HistEqModel:
    """HISTOGRAM_EQ.v, register-for-register incl. both blk_mem_gen_1 RAMs."""

    def __init__(self):
        self.ram1 = [0] * 256
        self.ram2 = [0] * 256
        self.heqv = 0
        self.reset()

    def reset(self):
        # NOTE: RAM content survives reset (matches behavioral model).
        # histogram_eq_value also survives reset: the RTL's second "reset"
        # branch actually writes histogram_value (multiple-driver bug), so
        # heqv has no reset and holds its value -- modelled by leaving
        # self.heqv untouched here (initialised to 0 in __init__).
        self.r_addr = 0
        self.hvv = 0
        self.hvvr = 0b0000
        self.hv = 0
        self.ls1 = 0
        self.ls2 = 0
        self.add = 0
        self.raddr_d = 0
        self.ry = 0
        self.rbl = 0
        self.riv = 0b00
        self.wcnt = 1
        # doutb1/doutb2 are registered RAM reads with NO reset: while rst_n=0
        # (i_Y0=0, r_addr=0) they re-read mem[0], so after reset release they
        # hold ram1[0]/ram2[0], not 0.
        self.doutb1 = self.ram1[0]
        self.doutb2 = self.ram2[0]
        self.hs = self.vs = self.bl = 0

    def cycle(self, y, h, v, b):
        out = (rgb565(self.doutb2 & 0xFF), self.bl,
               self.r_addr, self.hvv, self.hvvr, self.hv, self.heqv,
               None, None, None,      # wea1/addra1/dina1 filled below
               self.wcnt, self.ry, self.rbl, self.doutb1, self.doutb2)
        # {i_VSYNC, r_i_VSYNC[0]} == 2'b01 : VSYNC FALLING edge
        vneg = (v == 0) and ((self.riv & 1) == 1)
        vneg_d = (self.riv == 0b10)
        # {i_BLANK, r_i_BLANK} == 2'b01 : BLANK FALLING edge
        blank_neg = (b == 0) and (self.rbl == 1)

        # combinational
        addrb1 = y if b else self.r_addr
        wea1 = int(((self.ry != y) and self.rbl)
                   or blank_neg
                   or bool(self.hvv))
        addra1 = self.raddr_d & 0xFF if self.hvv else self.ry
        dina1 = (0 if self.hvv else (self.wcnt + self.doutb1)) & MASK32
        wea2 = (self.hvvr >> 3) & 1
        addra2 = (self.raddr_d >> 32) & 0xFF
        addrb2 = y
        out = out[:7] + (int(wea1), addra1, dina1) + out[10:]

        # RAM port-B reads: memory sampled pre-edge (read happens before any
        # same-cycle write commits, matching the two always blocks in the
        # behavioral model)
        new_doutb1 = self.ram1[addrb1]
        new_doutb2 = self.ram2[addrb2]
        # RAM port-A writes (post read sampling)
        if wea1:
            self.ram1[addra1] = dina1 & MASK32
        if wea2:
            self.ram2[addra2] = self.heqv & MASK32

        # registers -- all LHS committed from PRE-edge values (NBA)
        old_r_addr = self.r_addr
        old_hvv = self.hvv
        if vneg:
            self.r_addr = 0
        else:
            self.r_addr = (old_r_addr + 1) & 0xFF
        if vneg_d:
            self.hvv = 1
        elif old_r_addr == 0:
            self.hvv = 0
        old_hv = self.hv
        if old_hvv:
            self.hv = (old_hv + self.doutb1) & MASK32
        elif vneg:
            self.hv = 0

        # 3-stage heqv pipeline: ls1/ls2 <- PRE-edge hv, add <- pre-edge
        # ls1+ls2, heqv <- pre-edge add>>16
        n_ls1 = ((old_hv << 5) + (old_hv << 4)) & MASK32
        n_ls2 = ((old_hv << 2) + (old_hv << 1)) & MASK32
        n_add = (self.ls1 + self.ls2) & MASK32
        n_heqv = self.add >> 16
        self.ls1, self.ls2 = n_ls1, n_ls2
        self.add = n_add
        self.heqv = n_heqv

        # shifts sample the PRE-edge hvv / r_addr
        self.hvvr = ((self.hvvr & 0b111) << 1) | old_hvv
        self.raddr_d = ((self.raddr_d << 8) | old_r_addr) & ((1 << 40) - 1)
        old_rbl = self.rbl
        self.ry, self.rbl = y, b
        if vneg:
            self.wcnt = 1
        elif old_rbl:   # RTL: else if (r_i_BLANK) -- pre-edge value
            self.wcnt = 1 if wea1 else (self.wcnt + 1) & MASK32
        self.hs, self.vs, self.bl = h, v, b
        self.riv = ((self.riv & 1) << 1) | v
        self.doutb1, self.doutb2 = new_doutb1, new_doutb2
        return out


# ---------------------------------------------------------------------------
# Dump parsing
# ---------------------------------------------------------------------------

def parse_dump():
    cycles = []
    ram_snaps = {}
    with open(DUMP) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            t = line.split()
            if t[0] == "C":
                v = [int(x) for x in t[1:]]
                cycles.append(v)
            elif t[0] == "R2":
                vid, addr, val = int(t[1]), int(t[2]), int(t[3])
                ram_snaps.setdefault(vid, [0] * 256)[addr] = val
    return cycles, ram_snaps


VID_FRAMES = {
    1: ("uniform", 128, None),
    2: ("uniform", 40, None),
    3: ("gradient", None, None),
    4: ("random", 100, 110),
    5: ("random", 40, 170),
    6: ("random", 0, 255),
    7: ("uniform", 200, None),
    8: ("random", 0, 255),
}


def regen_frames():
    """Regenerate the exact stimulus the testbench feeds (LCG included)."""
    frames = {}
    lcg = 0x12345678

    def nxt():
        nonlocal lcg
        lcg = (1103515245 * lcg + 12345) & MASK32
        return (lcg >> 16) & 0xFF

    for vid, (kind, a, b) in VID_FRAMES.items():
        img = []
        for _r in range(H):
            row = []
            for col in range(W):
                if kind == "uniform":
                    row.append(a)
                elif kind == "gradient":
                    row.append((col >> 8) & 0xFF)
                else:
                    row.append(a + nxt() % (b - a + 1))
            img.append(row)
        frames[vid] = img
    return frames


def main():
    cycles, ram_snaps = parse_dump()
    lut = log_table()

    # ---- LUT file sanity (independent formula) ----
    file_lut = []
    with open(LUT_HEX) as f:
        for line in f:
            line = line.strip()
            if line:
                file_lut.append(int(line, 16))
    lut_ok = file_lut == lut
    print(f"LOG LUT file vs formula: {'MATCH' if lut_ok else 'MISMATCH'}")

    log = LogModel(lut)
    emb = EmbossModel()
    hist = HistogramModel()
    eq = HistEqModel()

    n = len(cycles)
    errs = {"log": 0, "emboss": 0, "histogram": 0, "eq": 0}
    first_err = {}

    frames = regen_frames()

    cur_vid = None
    for i, c in enumerate(cycles):
        vid = c[0]
        if vid != cur_vid:
            # The testbench resets the DUTs between vectors; dump rows during
            # rst_n==0 are gated out, so a vid change marks a reset boundary.
            # The tb sets i_VSYNC=1 immediately after releasing reset (posedge
            # drive, tb_sobel_thresh style), so the FIRST dumped row already
            # carries the frame-start VSYNC pulse; no extra undumped cycle
            # needs to be injected -- just reset the models.
            log.reset()
            emb.reset()
            hist.reset()
            eq.reset()
            cur_vid = vid
        (vid, y, hs, vs, b,
         lg_disp, lg_b, lg_h, lg_v,
         em_disp, em_b, em_ry, em_val,
         hs_disp, hs_b, h_mn, h_mx, h_mnr, h_maxr, h_num, h_den, h_y0,
         eq_disp, eq_b, eq_ra, eq_hvv, eq_hvvr, eq_hv, eq_heqv,
         eq_wea1, eq_addra1, eq_dina1, eq_wcnt, eq_ry, eq_rbl,
         eq_db1, eq_db2) = c

        lg = log.cycle(y, hs, vs, b)
        em = emb.cycle(y, hs, vs, b)
        hm = hist.cycle(y, hs, vs, b)
        qm = eq.cycle(y, hs, vs, b)

        def chk(key, got, exp, names):
            for g, e, nm in zip(got, exp, names):
                if g != e:
                    errs[key] += 1
                    if key not in first_err:
                        first_err[key] = (i, vid, nm, g, e)

        chk("log", lg, (lg_disp, lg_b, lg_h, lg_v),
            ("disp", "blank", "hsync", "vsync"))
        chk("emboss", em, (em_disp, em_b, em_ry, em_val),
            ("disp", "blank", "r_Y0", "emboss_value"))
        chk("histogram", hm,
            (hs_disp, hs_b, h_mn, h_mx, h_mnr, h_maxr, h_num, h_den, h_y0),
            ("disp", "blank", "min", "max", "min_r", "max_r",
             "numerator", "denominator", "Y0"))
        chk("eq", qm,
            (eq_disp, eq_b, eq_ra, eq_hvv, eq_hvvr, eq_hv, eq_heqv,
             eq_wea1, eq_addra1, eq_dina1, eq_wcnt, eq_ry, eq_rbl,
             eq_db1, eq_db2),
            ("disp", "blank", "r_addr", "hvv", "hvvr", "hv", "heqv",
             "wea1", "addra1", "dina1", "w_cnt", "r_Y0", "r_i_BLANK",
             "doutb1", "doutb2"))

    print("\nPART 1: cycle-accurate replica vs RTL dump "
          f"({n} cycles)")
    p1_ok = True
    for k in ("log", "emboss", "histogram", "eq"):
        if errs[k]:
            p1_ok = False
            i, vid, nm, g, e = first_err[k]
            print(f"  [{k.upper():<9}] FAIL: {errs[k]} field mismatches; "
                  f"first at row {i} vid {vid}: {nm} rtl={e} model={g}")
        else:
            print(f"  [{k.upper():<9}] max_diff=0 over {n} cycles")

    # ---- PART 2: functional intent (independent of RTL internals) ----
    print("\nPART 2: functional intent checks")
    findings = []

    # 2a. LOG: during pixel-valid cycles, display must equal the formula
    #     table applied to the input 1 cycle earlier.
    log_bad = 0
    prev_y = None
    prev_b = 0
    for c in cycles:
        vid, y, hs, vs, b = c[0], c[1], c[2], c[3], c[4]
        lg_disp = c[5]
        if b and prev_b and prev_y is not None:
            if lg_disp != rgb565(lut[prev_y]):
                log_bad += 1
        prev_y, prev_b = y, b
    if log_bad == 0:
        print("  [LOG]        display == round(255*ln(1+r)/ln(256)) packed "
              "RGB565: OK")
    else:
        findings.append(f"LOG display deviates from log formula ({log_bad})")

    # 2b. EMBOSS: display == clamp(prev - cur + 150)
    emb_bad = 0
    prev_y = None
    prev_b = 0
    for c in cycles:
        y, b, em_disp = c[1], c[4], c[9]
        if b and prev_b and prev_y is not None:
            ev = prev_y - y + THRESHOLD
            exp = 0xFFFF if ev > 255 else (0 if ev < 0 else rgb565(ev))
            if em_disp != exp:
                emb_bad += 1
        prev_y, prev_b = y, b
    if emb_bad == 0:
        print("  [EMBOSS]     display == clamp(r_prev-r+150) packed RGB565: OK")
    else:
        findings.append(f"EMBOSS deviates from formula ({emb_bad})")

    # 2c. HISTOGRAM stretch: from frame 2 on, min_r/max_r must equal the true
    #     min/max of the PREVIOUS frame, and pixels must map through the
    #     stretch formula with those A/B.
    order = sorted(ram_snaps.keys())
    prev_stats = None
    stretch_bad = 0
    stretch_checked = 0
    seg_prev = []
    cur_vid = None
    for c in cycles:
        vid, y, b, hs_disp = c[0], c[1], c[4], c[13]
        if vid != cur_vid:
            if seg_prev and prev_stats is not None:
                A, B = prev_stats
                for py, pd in seg_prev:
                    stretch_checked += 1
                    exp = py if A == B else (
                        255 if py > B else (0 if py < A else
                                            255 * (py - A) // (B - A)))
                    if pd != rgb565(exp):
                        stretch_bad += 1
            seg_prev = []
            cur_vid = vid
            if vid >= 2:
                img = frames[vid - 1]
                flat = [p for row in img for p in row]
                prev_stats = (min(flat), max(flat))
            else:
                prev_stats = None
        if b:
            seg_prev.append((y, hs_disp))
    if seg_prev and prev_stats is not None:
        A, B = prev_stats
        for py, pd in seg_prev:
            stretch_checked += 1
            exp = py if A == B else (
                255 if py > B else (0 if py < A else 255 * (py - A) // (B - A)))
            if pd != rgb565(exp):
                stretch_bad += 1
    if stretch_bad == 0:
        print(f"  [HISTOGRAM]  pseudo-stretch matches true prev-frame min/max "
              f"over {stretch_checked} pixels: OK")
    else:
        findings.append(f"HISTOGRAM stretch deviates from intended mapping "
                        f"({stretch_bad}/{stretch_checked})")

    # 2d. HISTOGRAM_EQ: intended pseudo-equalization map of the previous frame
    #     vs the ram2 snapshot taken after each frame.
    eq_bad_vids = []
    for vid in order:
        if vid == 1:
            continue  # first frame maps through all-zero ram2 (identity-ish 0)
        img = frames[vid - 1]
        hist_true = [0] * 256
        for row in img:
            for p in row:
                hist_true[p] += 1
        total = H * W
        cdf = 0
        intended = []
        for k in range(256):
            cdf += hist_true[k]
            intended.append(min(255, cdf * 255 // total))
        snap = ram_snaps[vid]
        diff = sum(1 for k in range(256) if snap[k] != intended[k])
        if diff:
            eq_bad_vids.append((vid, diff))
    if not eq_bad_vids:
        print("  [HIST_EQ]    ram2 mapping == intended pseudo-equalization: OK")
    else:
        for vid, diff in eq_bad_vids:
            findings.append(
                f"HISTOGRAM_EQ ram2 map deviates from intended "
                f"pseudo-equalization after vid{vid} ({diff}/256 bins)")

    if findings:
        print("\nRTL FINDINGS (deviations from documented intent; the "
              "as-written RTL is pinned by PART 1):")
        for f_ in findings:
            print(f"  - {f_}")

    overall = p1_ok and lut_ok
    print(f"\nOverall: {'PASS' if overall else 'FAIL'} "
          f"(cycle-accurate replica {'OK' if p1_ok else 'FAIL'}, "
          f"LUT {'OK' if lut_ok else 'FAIL'}, "
          f"{len(findings)} functional findings)")
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
