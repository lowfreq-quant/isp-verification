"""Cocotb cycle-accurate verification of LOG / EMBOSS / HISTOGRAM /
HISTOGRAM_EQ (tb_pointops_cocotb.v).

Alignment philosophy (this is what the Verilog-dump attempts could not pin):
for every clock cycle T the test
  1. drives the inputs that the DUTs sample at posedge T,
  2. reads every DUT output BEFORE that posedge (registered outputs are
     post-posedge-(T-1); combinational outputs reflect inputs T),
  3. runs the four as-written replicas from verify_pointops.py, whose
     cycle() returns exactly those pre-posedge values, and
  4. awaits the posedge.
So model-output(T) == RTL-output(T) must hold cycle after cycle with no
dump alignment heuristics.

After PART 1, PART 2 checks the functional intent on the model outputs
(valid because PART 1 proved model == RTL):
  LOG     : display == pack(lut[prev pixel]) on consecutive pixel cycles
  EMBOSS  : display == clamp(prev - cur + 150)
  HISTOGRAM: display == pack(stretch(prev-2 pixel, A/B = prev-frame min/max))
  HISTOGRAM_EQ: ram2 map after each frame vs intended pseudo-equalization
                (both the textbook scale 255*CDF/total and the RTL's own
                hardcoded scale 54/65536 which matches 640x480 frames)

Run with sim/run_pointops_cocotb.py.
"""

import os
import sys

SIM_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SIM_DIR)

import cocotb  # noqa: E402
from cocotb.clock import Clock  # noqa: E402
from cocotb.triggers import RisingEdge, Timer, ClockCycles  # noqa: E402

import verify_pointops as vp  # noqa: E402


W, H = vp.W, vp.H
# Frame protocol (matches real VGA timing, VGA_CTRL.v): the VSYNC falling
# edge fires at the frame head, followed by a frame-blank period long enough
# for HISTOGRAM_EQ's 256-cycle scan window and HISTOGRAM's min/max latch to
# settle BEFORE the first pixel arrives.  Frames are NOT reset in between
# (a real pipeline runs continuously; the "previous-frame statistics"
# intent of the pseudo-stretch / pseudo-equalization requires the state to
# survive across frames).
FRAME_BLANK = 320   # cycles between the frame-start VSYNC pulse and pixel 0
GAP = 40            # cycles after the last pixel of a frame
MASK32 = vp.MASK32


def rd(handle):
    """Read a signal as int; None when X/Z (unresolved)."""
    v = handle.value
    if v is None or not getattr(v, "is_resolvable", False) or not v.is_resolvable:
        return None
    return int(v)


def rd10(handle):
    """Read a signed 10-bit wire as its unsigned bit pattern."""
    v = handle.value
    if v is None or not getattr(v, "is_resolvable", False) or not v.is_resolvable:
        return None
    return v.integer & 0x3FF


@cocotb.test()
async def pointops_cycle_exact(dut):
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())

    lut = vp.log_table()
    log = vp.LogModel(lut)
    emb = vp.EmbossModel()
    hist = vp.HistogramModel()
    eq = vp.HistEqModel()
    frames = vp.regen_frames()

    dut.rst_n.value = 0
    dut.i_Y0.value = 0
    dut.i_HSYNC.value = 0
    dut.i_VSYNC.value = 0
    dut.i_BLANK.value = 0
    await ClockCycles(dut.clk, 10)

    errs = {"log": 0, "emboss": 0, "histogram": 0, "eq": 0}
    first_err = {}
    n_x = 0
    n_cycles = 0
    model_events = []   # (vid, y, b, log_disp, emb_disp, hist_disp) per cycle
    ram2_snaps = {}     # vid -> model ram2 snapshot after the frame

    FIELD_NAMES = {
        "log": ("disp", "blank", "hsync", "vsync"),
        "emboss": ("disp", "blank", "r_Y0", "emboss_value"),
        "histogram": ("disp", "blank", "min", "max", "min_r", "max_r",
                      "numerator", "denominator", "Y0"),
        "eq": ("disp", "blank", "r_addr", "hvv", "hvvr", "hv", "heqv",
               "wea1", "addra1", "dina1", "w_cnt", "r_Y0", "r_i_BLANK",
               "doutb1", "doutb2"),
    }

    def check(key, model_vals, rtl_vals):
        nonlocal n_x
        for name, m, r in zip(FIELD_NAMES[key], model_vals, rtl_vals):
            if r is None:
                n_x += 1
                continue
            if m != r:
                errs[key] += 1
                if key not in first_err:
                    first_err[key] = (n_cycles, name, m, r)

    async def step(y, h, v, b):
        nonlocal n_cycles
        dut.i_Y0.value = y
        dut.i_HSYNC.value = h
        dut.i_VSYNC.value = v
        dut.i_BLANK.value = b
        await Timer(1, units="ps")   # let combinational logic settle

        rtl_log = (rd(dut.u_log.display_data), rd(dut.u_log.BLANK),
                   rd(dut.u_log.H_SYNC), rd(dut.u_log.V_SYNC))
        rtl_emb = (rd(dut.u_emboss.display_data), rd(dut.u_emboss.BLANK),
                   rd(dut.u_emboss.r_Y0), rd10(dut.u_emboss.emboss_value))
        rtl_hist = (rd(dut.u_hist.display_data), rd(dut.u_hist.BLANK),
                    rd(dut.u_hist.min), rd(dut.u_hist.max),
                    rd(dut.u_hist.min_r), rd(dut.u_hist.max_r),
                    rd(dut.u_hist.numerator), rd(dut.u_hist.denominator),
                    rd(dut.u_hist.Y0))
        rtl_eq = (rd(dut.u_eq.display_data), rd(dut.u_eq.BLANK),
                  rd(dut.u_eq.r_addr),
                  rd(dut.u_eq.histogram_value_valid),
                  rd(dut.u_eq.histogram_value_valid_r),
                  rd(dut.u_eq.histogram_value),
                  rd(dut.u_eq.histogram_eq_value),
                  rd(dut.u_eq.wea1), rd(dut.u_eq.addra1),
                  rd(dut.u_eq.dina1), rd(dut.u_eq.w_cnt),
                  rd(dut.u_eq.r_Y0), rd(dut.u_eq.r_i_BLANK),
                  rd(dut.u_eq.doutb1), rd(dut.u_eq.doutb2))

        ml = log.cycle(y, h, v, b)
        me = emb.cycle(y, h, v, b)
        mh = hist.cycle(y, h, v, b)
        mq = eq.cycle(y, h, v, b)

        check("log", ml, rtl_log)
        check("emboss", me, rtl_emb)
        check("histogram", mh, rtl_hist)
        check("eq", mq, rtl_eq)

        if 16318 <= n_cycles <= 16326:
            print(f"DBG c{n_cycles}: vid={vid} y={y} h={h} v={v} b={b}")
            for name, m, r in zip(FIELD_NAMES["eq"], mq, rtl_eq):
                print(f"   eq.{name:<8} model={m} rtl={r}")
            mram = [eq.ram1[i] for i in range(4)]
            rram = []
            for i in range(4):
                rv = rd(dut.u_eq.u_ram_1.mem[i])
                rram.append(rv)
            print(f"   ram1[0:4] model={mram} rtl={rram}")

        model_events.append((vid, y, b, ml[0], me[0], mh[0]))
        n_cycles += 1
        await RisingEdge(dut.clk)

    def reset_dut_and_models():
        dut.rst_n.value = 0
        log.reset()
        emb.reset()
        hist.reset()
        eq.reset()

    # Single reset at the very start; frames then run continuously, exactly
    # like a real VGA pipeline (no per-frame reset -- the pseudo-stretch /
    # pseudo-equalization intent requires histogram state to survive across
    # frames).  Each frame: VSYNC pulse at the frame head, then a frame-blank
    # period long enough for HISTOGRAM_EQ's 256-cycle scan window and
    # HISTOGRAM's min/max latch to settle BEFORE pixel 0 arrives.
    reset_dut_and_models()
    await ClockCycles(dut.clk, 8)
    dut.rst_n.value = 1

    for vid in range(1, 9):
        # frame-start VSYNC pulse cycle (i_BLANK=0)
        await step(0, 0, 1, 0)
        # frame blank: scan window + min/max latch settle (real VGA timing:
        # V_SYNC fires at v_cnt 0..1, pixels start at v_cnt 35+)
        for _ in range(FRAME_BLANK):
            await step(0, 0, 0, 0)
        # pixels: 8 rows x 640, i_HSYNC merged into the last pixel of each row
        img = frames[vid]
        for row in range(H):
            for col in range(W):
                await step(img[row][col], 1 if col == W - 1 else 0, 0, 1)
        # frame gap
        for _ in range(GAP):
            await step(0, 0, 0, 0)

        # cross-check the mapping RAM content (model vs RTL)
        ram_bad = 0
        for a in range(256):
            rv = rd(dut.u_eq.u_ram_2.mem[a])
            if rv is None:
                n_x += 1
            elif rv != eq.ram2[a]:
                ram_bad += 1
        if ram_bad:
            errs["eq"] += ram_bad
            if "eq" not in first_err:
                first_err["eq"] = (n_cycles, "ram2", "model", "rtl")
        ram2_snaps[vid] = list(eq.ram2)

    # ----------------------------- PART 1 report ---------------------------
    print(f"\nPART 1: cycle-accurate replica vs RTL ({n_cycles} cycles)")
    p1_ok = True
    for key in ("log", "emboss", "histogram", "eq"):
        if errs[key]:
            p1_ok = False
            i, name, m, r = first_err[key]
            print(f"  [{key.upper():<9}] FAIL: {errs[key]} field mismatches; "
                  f"first at cycle {i}: {name} model={m} rtl={r}")
        else:
            print(f"  [{key.upper():<9}] max_diff=0 over {n_cycles} cycles")
    if n_x:
        print(f"  (note: {n_x} reads were X/Z and skipped; mostly "
              f"histogram_eq_value before it flushes)")

    # ----------------------------- PART 2 -------------------------------
    print("\nPART 2: functional intent checks (on the cycle-exact models)")
    findings = []

    # 2a. LOG
    log_bad = checked = 0
    prev_y = prev_b = None
    for (vid, y, b, ld, _, _) in model_events:
        if b and prev_b:
            checked += 1
            if ld != vp.rgb565(lut[prev_y]):
                log_bad += 1
        prev_y, prev_b = y, b
    if log_bad == 0:
        print(f"  [LOG]        display == pack(lut[prev pixel]) over "
              f"{checked} pixel cycles: OK")
    else:
        findings.append(f"LOG display deviates from formula ({log_bad}/{checked})")

    # 2b. EMBOSS
    emb_bad = checked = 0
    prev_y = prev_b = None
    for (vid, y, b, _, ed, _) in model_events:
        if b and prev_b:
            checked += 1
            ev = prev_y - y + vp.THRESHOLD
            exp = 0xFFFF if ev > 255 else (0 if ev < 0 else vp.rgb565(ev))
            if ed != exp:
                emb_bad += 1
        prev_y, prev_b = y, b
    if emb_bad == 0:
        print(f"  [EMBOSS]     display == clamp(prev-cur+150) over "
              f"{checked} pixel cycles: OK")
    else:
        findings.append(f"EMBOSS deviates from formula ({emb_bad}/{checked})")

    # 2c. HISTOGRAM stretch: display(T) == pack(stretch(y(T-2))) with A/B the
    #     true min/max of the PREVIOUS frame.  vid1 has no previous frame
    #     (the reset latch yields min_r=255/max_r=0 -> output 255), so the
    #     check starts at vid2 where the documented prev-frame intent applies.
    stats = {}
    for vid in range(2, 9):
        flat = [p for row in frames[vid - 1] for p in row]
        stats[vid] = (min(flat), max(flat))
    stretch_bad = checked = 0
    cur_vid = 0
    win = []
    for (vid, y, b, _, _, hd) in model_events:
        if vid not in stats:
            continue
        if vid != cur_vid:
            win = []
            cur_vid = vid
        win.append((y, b))
        if len(win) > 3:
            win.pop(0)
        if len(win) == 3 and all(w[1] for w in win):
            # disp is the CURRENT cycle's display = stretch(y(T-2)); compare
            # it against the y latched 2 cycles earlier (win[0]).
            y_prev2 = win[0][0]
            disp = hd
            A, B = stats[vid]
            checked += 1
            exp = y_prev2 if A == B else (
                255 if y_prev2 > B else (
                    0 if y_prev2 < A else 255 * (y_prev2 - A) // (B - A)))
            if disp != vp.rgb565(exp):
                stretch_bad += 1
    if stretch_bad == 0:
        print(f"  [HISTOGRAM]  pseudo-stretch matches prev-frame min/max over "
              f"{checked} interior pixels: OK")
    else:
        findings.append(f"HISTOGRAM stretch deviates from intended mapping "
                        f"({stretch_bad}/{checked})")

    # 2d. HISTOGRAM_EQ ram2 vs intended pseudo-equalization map
    eq_bad_rtlscale = []
    eq_bad_textbook = []
    for vid in range(2, 9):
        img = frames[vid - 1]
        hist_true = [0] * 256
        for row in img:
            for p in row:
                hist_true[p] += 1
        cdf = 0
        cdf_list = []
        for k in range(256):
            cdf += hist_true[k]
            cdf_list.append(cdf)
        total = H * W
        snap = ram2_snaps[vid]
        # textbook scale for this frame size
        d_tb = sum(1 for k in range(256)
                   if snap[k] != min(255, cdf_list[k] * 255 // total))
        # RTL's hardcoded scale: add = hv*54, heqv = add>>16 (matches
        # 255/307200 for a 640x480 frame)
        d_rt = sum(1 for k in range(256)
                   if snap[k] != min(255, (cdf_list[k] * 54) >> 16))
        if d_rt:
            eq_bad_rtlscale.append((vid, d_rt))
        if d_tb:
            eq_bad_textbook.append((vid, d_tb))
    if not eq_bad_rtlscale:
        print("  [HIST_EQ]    ram2 == CDF scaled by the RTL's hardcoded "
              "x54>>16 (640x480 scale): OK")
    else:
        for vid, d in eq_bad_rtlscale:
            findings.append(f"HISTOGRAM_EQ ram2 deviates even at the RTL's own "
                            f"scale after vid{vid} ({d}/256 bins)")
    if eq_bad_textbook and not eq_bad_rtlscale:
        findings.append("HISTOGRAM_EQ scale x54>>16 assumes a 640x480 frame; "
                        "test frames are 640x8, so the textbook map "
                        "255*CDF/total does not match")

    if findings:
        print("\nRTL FINDINGS (deviations from documented intent; the "
              "as-written RTL is pinned by PART 1):")
        for f_ in findings:
            print(f"  - {f_}")

    overall = p1_ok
    print(f"\nOverall: {'PASS' if overall else 'FAIL'} "
          f"(cycle-accurate replica {'OK' if p1_ok else 'FAIL'}, "
          f"{len(findings)} functional findings)")
    assert overall, "PART 1 cycle-accurate comparison failed"
