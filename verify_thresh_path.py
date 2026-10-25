"""Verify the Sobel threshold->canny_in path and the Canny is_edge path.

Two white-box dump testbenches live in sim/:
  - tb_sobel_thresh.v  -> sobel_thresh_dump.txt
        columns: vid line col m11..m33 gx g sqrg phase thresh canny_in
                 tmin tmax hsync vsync blank rst
  - tb_canny_thresh.v  -> canny_thresh_dump.txt
        columns: vid line col m11..m33 is_edge hsync vsync blank rst

This script replays the exact TB stimulus through cycle-accurate Python
models (matrix_generator + sobel datapath / canny NMS+double-threshold) and
compares every dumped cycle field-by-field.

Canny is checked twice:
  1. "as-written" model replicates the RTL exactly, including the duplicated
     2'b10 case item that makes phase=2'b01 fall through (is_edge holds its
     previous value). Expect PASS against the unpatched RTL.
  2. "intended" model implements the missing 2'b01 (45-degree) branch
     (compare center magnitude against m13/m31). Expect FAIL only on
     weak+phase=01 windows, which proves the RTL case-item bug.

Usage:
    python sim/run_thresh.py          # compile TBs, run them, then verify
    python sim/verify_thresh_path.py  # requires the two *_dump.txt files
"""

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import verify_golden as vg  # noqa: E402  (FWFT_FIFO, MatrixGenerator, _sqrt20)


# ----------------------------- stimulus replay -----------------------------

def const_row(v):
    return [v] * 640


def step_row(v1, v2, sc):
    return [v1 if c < sc else v2 for c in range(640)]


def build_row(rv):
    if isinstance(rv, list):
        return rv
    kind = rv[0]
    if kind == "const":
        return const_row(rv[1])
    if kind == "step":
        return step_row(rv[1], rv[2], rv[3])
    raise ValueError(f"unknown row pattern {rv}")


# Exact vectors from tb_sobel_thresh.v (rows are {8-bit pixel} streams).
SOBEL_VECTORS = [
    (60, 120, [("const", 10), ("const", 10), ("const", 24), ("const", 24), ("const", 24)]),
    (60, 120, [("const", 10), ("const", 10), ("const", 25), ("const", 25), ("const", 25)]),
    (60, 120, [("const", 10), ("const", 10), ("const", 26), ("const", 26), ("const", 26)]),
    (60, 120, [("const", 10), ("const", 10), ("const", 40), ("const", 40), ("const", 40)]),
    (60, 120, [("const", 10), ("const", 10), ("const", 41), ("const", 41), ("const", 41)]),
    (60, 120, [("const", 41), ("const", 41), ("const", 10), ("const", 10), ("const", 10)]),
    (60, 120, [("const", 0), ("const", 0), ("const", 255), ("const", 255), ("const", 255)]),
    (60, 120, [("step", 100, 200, 320)] * 5),
    (60, 120, [("step", 100, 200, 320 + k) for k in range(6)]),
    (100, 100, [("const", 10), ("const", 10), ("const", 35), ("const", 35),
                ("const", 36), ("const", 36), ("const", 34), ("const", 34)]),
    (0, 2047, [("const", 10)] * 4),
    (60, 120, [("const", 10)] * 4),
]


def canny_pack(phase, thresh, mag):
    return (phase << 13) | (thresh << 11) | (mag & 0x7FF)


# Exact vectors from tb_canny_thresh.v: rows are {phase, thresh, mag} triples.
CANNY_VECTORS = [
    [(0, 2, 50), (0, 2, 100), (0, 2, 150), (0, 2, 200), (0, 2, 200)],
    [(0, 3, 100), (2, 3, 200), (1, 3, 300), (3, 3, 400), (0, 3, 500)],
    [(0, 1, 100), (1, 1, 200), (2, 1, 300), (3, 1, 400)],
    [(0, 2, 300)] * 5,
    [(2, 2, 500), (2, 2, 300)] * 3,
    [(0, 3, 500), (0, 3, 500), (1, 2, 300), (1, 2, 300), (1, 2, 300),
     (0, 1, 100), (1, 2, 300), (1, 2, 300), (1, 2, 300)],
    [(3, 2, 500), (3, 2, 300)] * 3,
    [("step", canny_pack(0, 2, 300), canny_pack(0, 2, 500), 320)] * 5,
]


# ----------------------------- sobel model ---------------------------------

class SobelThreshModel:
    """Cycle-accurate replica of sobel.v (Canny_detection) fed by
    matrix_generator.  Mirrors NBA semantics: every registered output is
    computed from pre-posedge values; thresh / sqrg / canny_in are
    combinational.
    """

    def __init__(self):
        self.mg = vg.MatrixGenerator(data_width=8, fifo_depth=2048)
        self.reset()

    def reset(self):
        self.mg.reset()
        self.gx_1 = self.gx_3 = self.gy_1 = self.gy_3 = 0
        self.gx = self.gy = 0
        self.direction = 0
        # RTL has NO reset branch for `phase`; during reset, gx=gy=0 and
        # direction=0 make the tie-break select phase=2'b01.
        self.phase = 1
        self.g = 0

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC, tmin, tmax):
        m_old, _, _, _ = self.mg.clock(i_Y0, i_BLANK, i_VSYNC, i_HSYNC)

        # Stage 1 (committed this posedge): row/column convolutions
        ngx_1 = m_old[0] + 2 * m_old[1] + m_old[2]
        ngx_3 = m_old[6] + 2 * m_old[7] + m_old[8]
        ngy_1 = m_old[0] + 2 * m_old[3] + m_old[6]
        ngy_3 = m_old[2] + 2 * m_old[5] + m_old[8]

        # Stage 2 (committed this posedge): |gx|/|gy| + direction
        ogx_1, ogx_3, ogy_1, ogy_3 = self.gx_1, self.gx_3, self.gy_1, self.gy_3
        ngx = ogx_1 - ogx_3 if ogx_1 > ogx_3 else ogx_3 - ogx_1
        ngy = ogy_1 - ogy_3 if ogy_1 > ogy_3 else ogy_3 - ogy_1
        ndir = ((ogx_1 > ogx_3) << 1) | (ogy_1 > ogy_3)

        # Stage 3 (committed this posedge): phase from pre-edge gx/gy/direction
        ogx, ogy, odir = self.gx, self.gy, self.direction
        if ogx > 2 * ogy:
            nphase = 0
        elif ogy > 2 * ogx:
            nphase = 2
        elif (odir & 1) == ((odir >> 1) & 1):
            nphase = 1
        else:
            nphase = 3

        # Stage 4 (committed this posedge): g = gx^2 + gy^2 (20-bit truncate)
        ng = (ogx * ogx + ogy * ogy) & 0xFFFFF

        # behavioral_cordic.v is combinational: sqrg = f(g) same cycle.
        gx_beh = (ng >> 10) & 0x3FF
        gy_beh = ng & 0x3FF
        sq = (gx_beh * gx_beh + gy_beh * gy_beh) & 0xFFFFF
        nsqrg = vg.SobelPipeline._sqrt20(sq)

        # thresh / canny_in are combinational
        if nsqrg > tmax:
            nthresh = 3
        elif nsqrg < tmin:
            nthresh = 1
        else:
            nthresh = 2
        ncanny = (nphase << 13) | (nthresh << 11) | (nsqrg & 0x7FF)

        self.gx_1, self.gx_3, self.gy_1, self.gy_3 = ngx_1, ngx_3, ngy_1, ngy_3
        self.gx, self.gy, self.direction = ngx, ngy, ndir
        self.phase = nphase
        self.g = ng

        return {
            "line": self.mg.line_cnt,
            "col": self.mg.col_cnt,
            "m": list(self.mg.m),
            "gx": ngx,
            "g": ng,
            "sqrg": nsqrg,
            "phase": nphase,
            "thresh": nthresh,
            "canny_in": ncanny,
            "tmin": tmin,
            "tmax": tmax,
        }


def replay_sobel():
    model = SobelThreshModel()
    recs = []
    last = 0  # i_Y0 is a free-running reg: it holds the previous value
    # during reset/VSYNC (0 before the first vector).
    for vid, (tmin, tmax, rows) in enumerate(SOBEL_VECTORS, start=1):
        model.reset()
        # VSYNC cycle IS dumped (dump_on is set before the VSYNC pulse).
        rec = model.clock(last, 1, 1, 0, tmin, tmax)
        rec.update(vid=vid, hsync=0, vsync=1, blank=1, rst=1)
        recs.append(rec)
        for rv in rows:
            row = build_row(rv)
            for col in range(640):
                rec = model.clock(row[col], 1, 0, 0, tmin, tmax)
                rec.update(vid=vid, hsync=0, vsync=0, blank=1, rst=1)
                recs.append(rec)
            last = row[639]
            rec = model.clock(row[639], 1, 0, 1, tmin, tmax)
            rec.update(vid=vid, hsync=1, vsync=0, blank=1, rst=1)
            recs.append(rec)
    return recs


# ----------------------------- canny model ---------------------------------

class CannyModel:
    """Cycle-accurate replica of canny.v: 15-bit matrix_generator + the
    registered is_edge unit (double-threshold + NMS).

    rtl_as_written=True  -> phase=2'b01 has no case item (holds old value),
                            matching the unpatched RTL.
    rtl_as_written=False -> phase=2'b01 compares against m13/m31 (intent).
    """

    def __init__(self, rtl_as_written=False):
        self.rtl_as_written = rtl_as_written
        self.mg = vg.MatrixGenerator(data_width=15, fifo_depth=2048)
        self.reset()

    def reset(self):
        self.mg.reset()
        self.is_edge = 0

    def _intended_edge(self, m):
        """Return (is_edge, center_phase, center_thresh) for window m."""
        c = m[4]
        phase = (c >> 13) & 0x3
        thresh = (c >> 11) & 0x3
        mag = c & 0x7FF
        mags = [x & 0x7FF for x in m]

        if thresh == 3:
            return 1, phase, thresh
        if thresh == 1:
            return 0, phase, thresh
        if thresh == 2:
            if phase == 0:
                return int(mag >= mags[3] and mag >= mags[5]), phase, thresh
            if phase == 2:
                return int(mag >= mags[1] and mag >= mags[7]), phase, thresh
            if phase == 1:
                # 45 degrees: compare against NE/SW neighbours (m13, m31)
                return int(mag >= mags[2] and mag >= mags[6]), phase, thresh
            return int(mag >= mags[0] and mag >= mags[8]), phase, thresh
        # thresh==2'b00 never produced by the sobel thresh block (only via
        # direct drive during reset); RTL has no branch -> hold.
        return self.is_edge, phase, thresh

    def clock(self, y15, i_BLANK, i_VSYNC, i_HSYNC):
        m_old, _, _, _ = self.mg.clock(y15, i_BLANK, i_VSYNC, i_HSYNC)

        if self.rtl_as_written:
            # Replicate the RTL exactly: case items are 00, 10, 10(dup), 11.
            c = m_old[4]
            phase = (c >> 13) & 0x3
            thresh = (c >> 11) & 0x3
            mag = c & 0x7FF
            mags = [x & 0x7FF for x in m_old]
            if thresh == 3:
                nedge = 1
            elif thresh == 1:
                nedge = 0
            elif thresh == 2:
                if phase == 0:
                    nedge = int(mag >= mags[3] and mag >= mags[5])
                elif phase == 2:
                    nedge = int(mag >= mags[1] and mag >= mags[7])
                elif phase == 3:
                    nedge = int(mag >= mags[0] and mag >= mags[8])
                else:  # phase==1: missing case -> hold
                    nedge = self.is_edge
            else:
                nedge = self.is_edge
        else:
            nedge, phase, thresh = self._intended_edge(m_old)

        self.is_edge = nedge
        return {
            "line": self.mg.line_cnt,
            "col": self.mg.col_cnt,
            "m": list(self.mg.m),
            "is_edge": nedge,
            "win_phase": phase,
            "win_thresh": thresh,
        }


def replay_canny(rtl_as_written):
    model = CannyModel(rtl_as_written=rtl_as_written)
    recs = []
    last = 0  # canny_in holds its previous value during reset/VSYNC.
    for vid, rows in enumerate(CANNY_VECTORS, start=1):
        model.reset()
        rec = model.clock(last, 1, 1, 0)
        rec.update(vid=vid, hsync=0, vsync=1, blank=1, rst=1)
        recs.append(rec)
        for rv in rows:
            if isinstance(rv, tuple) and len(rv) == 3:
                row = const_row(canny_pack(*rv))
            else:
                row = build_row(rv)
            for col in range(640):
                rec = model.clock(row[col], 1, 0, 0)
                rec.update(vid=vid, hsync=0, vsync=0, blank=1, rst=1)
                recs.append(rec)
            last = row[639]
            rec = model.clock(row[639], 1, 0, 1)
            rec.update(vid=vid, hsync=1, vsync=0, blank=1, rst=1)
            recs.append(rec)
    return recs


# ------------------------------ comparison ---------------------------------

def parse_dump(path):
    """Parse a dump file into a list of dicts keyed by the header names."""
    recs = []
    with open(path) as f:
        header = f.readline()
        cols = header.lstrip("#").split()
        for line in f:
            parts = line.split()
            if not parts:
                continue
            recs.append(dict(zip(cols, (int(p) for p in parts))))
    return recs


def _win(rec):
    return [rec[f"m{i}{j}"] for i in (1, 2, 3) for j in (1, 2, 3)]


def compare_sobel(model_recs, dump_recs):
    print("\n" + "=" * 72)
    print("PART 1: SOBEL thresh -> canny_in datapath")
    print("=" * 72)
    if len(model_recs) != len(dump_recs):
        print(f"LENGTH MISMATCH: model={len(model_recs)} dump={len(dump_recs)}")
        return False

    fields = ["line", "col", "gx", "g", "sqrg", "phase", "thresh",
              "canny_in", "tmin", "tmax", "hsync", "vsync", "blank", "rst"]
    ok = True
    for fld in fields:
        mx = 0
        nbad = 0
        first = []
        for i, (mr, dr) in enumerate(zip(model_recs, dump_recs)):
            diff = abs(mr[fld] - dr[fld])
            if diff > mx:
                mx = diff
            if diff:
                nbad += 1
                if len(first) < 6:
                    first.append((i, mr[fld], dr[fld]))
        status = "PASS" if mx == 0 else "FAIL"
        print(f"  {fld:<10} {status}  max_diff={mx:<6} mismatches={nbad}")
        for i, mv, dv in first:
            print(f"      cycle {i}: model={mv} rtl={dv}")
        if mx != 0:
            ok = False

    # Window equality (validates the 8-bit matrix_generator + FIFO path)
    win_bad = 0
    for i, (mr, dr) in enumerate(zip(model_recs, dump_recs)):
        if mr["m"] != _win(dr):
            win_bad += 1
            if win_bad <= 3:
                print(f"  window mismatch at cycle {i}: model={mr['m']} rtl={_win(dr)}")
    print(f"  {'m11..m33':<10} {'PASS' if win_bad == 0 else 'FAIL'}  mismatches={win_bad}")
    ok = ok and win_bad == 0

    print(f"\n  >>> {'PASS' if ok else 'FAIL'}: Sobel thresh path matches RTL cycle-by-cycle")
    return ok


def compare_canny(model_recs, dump_recs, label):
    print(f"\n  Canny model [{label}]")
    if len(model_recs) != len(dump_recs):
        print(f"  LENGTH MISMATCH: model={len(model_recs)} dump={len(dump_recs)}")
        return False, 0

    is_bad = 0
    phase01_bad = 0
    other_bad = 0
    win_bad = 0
    flag_bad = 0
    first = []
    for i, (mr, dr) in enumerate(zip(model_recs, dump_recs)):
        if mr["m"] != _win(dr):
            win_bad += 1
        for fld in ("hsync", "vsync", "blank", "rst"):
            if mr.get(fld) != dr[fld]:
                flag_bad += 1
        if mr["is_edge"] != dr["is_edge"]:
            is_bad += 1
            if len(first) < 8:
                first.append((i, mr["vid"], mr["win_phase"], mr["win_thresh"],
                              mr["is_edge"], dr["is_edge"]))
            if mr["win_phase"] == 1:
                phase01_bad += 1
            else:
                other_bad += 1

    print(f"  window mismatches        = {win_bad}")
    print(f"  hsync/vsync/blank/rst    = {flag_bad}")
    print(f"  is_edge mismatches       = {is_bad}")
    print(f"    at weak+phase=01 windows = {phase01_bad}")
    print(f"    at other windows         = {other_bad}")
    for i, vid, ph, th, mv, dv in first:
        print(f"      cycle {i} (vid {vid}, win phase={ph} thresh={th}): "
              f"model={mv} rtl={dv}")

    ok = win_bad == 0 and flag_bad == 0 and is_bad == 0
    return ok, phase01_bad


def main():
    sobel_dump = os.path.join(HERE, "sobel_thresh_dump.txt")
    canny_dump = os.path.join(HERE, "canny_thresh_dump.txt")
    for p in (sobel_dump, canny_dump):
        if not os.path.exists(p):
            print(f"ERROR: {p} not found. Run sim/run_thresh.py first.")
            sys.exit(1)

    print(f"sobel dump: {sobel_dump}")
    print(f"canny dump: {canny_dump}")

    ok_sobel = compare_sobel(replay_sobel(), parse_dump(sobel_dump))

    print("\n" + "=" * 72)
    print("PART 2: CANNY double-threshold + NMS is_edge")
    print("=" * 72)
    dump_c = parse_dump(canny_dump)
    ok_written, _ = compare_canny(replay_canny(rtl_as_written=True), dump_c,
                                  "as-written RTL (duplicated 2'b10)")
    ok_intent, p01_bad = compare_canny(replay_canny(rtl_as_written=False), dump_c,
                                       "intended (with 2'b01 branch)")

    # ------------------------------ report ---------------------------------
    print("\n" + "=" * 72)
    print("FINAL REPORT")
    print("=" * 72)
    print(f"  [{'PASS' if ok_sobel else 'FAIL'}] Sobel thresh->canny_in path")

    if ok_intent:
        print("  [PASS] Canny is_edge matches design intent (all phases, "
              "incl. 2'b01 45-degree branch)")
        if not ok_written:
            print("  [info] The as-written model (duplicated 2'b10, no 2'b01 "
                  "case) is the pre-fix RTL behavior;")
            print("         its mismatches at weak+phase=01 windows confirm "
                  "the 2'b01 case fix is in effect.")
        canny_issue = False
    elif ok_written and p01_bad > 0:
        print("  [BUG CONFIRMED] Canny RTL is missing the phase=2'b01 case item:")
        print("      '2'b10:' appears twice in canny.v; the intended 45-degree")
        print("      branch (compare against m13/m31) is absent, so weak 45-degree")
        print("      pixels hold a stale is_edge.")
        canny_issue = True
    else:
        print("  [UNEXPECTED] Canny mismatch pattern not explained by the "
              "missing 2'b01 case. Investigate.")
        canny_issue = True

    all_ok = ok_sobel and canny_issue is False
    print("=" * 72)
    print(f"\nOverall: {'PASS' if all_ok else 'see report'}")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
