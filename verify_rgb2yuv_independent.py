"""
verify_rgb2yuv_independent.py
-----------------------------
INDEPENDENT cross-check of RGB2YUV.v against the BT.601 FLOATING-POINT standard.

Why this is not circular:
  The RTL computes, in fixed point,
        Y0 = (R*77 + G*150 + B*29)        >> 8
        U0 = (B*128 - R*43 - G*85 + 32768)>> 8        # == 128 + (...)
        V0 = (R*128 - G*107 - B*21 + 32768)>> 8
  with coefficients 77/150/29, 128/43/85, 128/107/21 baked into the Verilog.

  This script builds the reference from the BT.601 DEFINITION in floating point:
        Y  =  0.299 R + 0.587 G + 0.114 B
        Cb = -0.169 R - 0.331 G + 0.500 B + 128      (U)
        Cr =  0.500 R - 0.419 G - 0.081 B + 128      (V)
  rounded to nearest integer. It never imports the integer coefficients above.

  Two independent facts are then established:
    (A) The RTL's integer coefficients are the nearest-integer x256
        quantisation of the BT.601 floats  -> proves the "right constants".
    (B) Across ALL 65536 RGB565 inputs, RTL output agrees with the
        float-standard reference within a small quantization bound
        (<=2 LSB). A wrong coefficient would blow this up by ~100 LSB.

Usage:
    python sim/verify_rgb2yuv_independent.py
(expects sim/rgb2yuv_dump.txt produced by tb_rgb2yuv_dump.v)
"""
import os
import sys
import numpy as np

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rgb2yuv_dump.txt")

# ---- BT.601 floating-point reference (the standard, NOT the RTL) ----
# Y  = 0.299 R + 0.587 G + 0.114 B
# Cb = -0.169 R - 0.331 G + 0.500 B + 128   (U)
# Cr =  0.500 R - 0.419 G - 0.081 B + 128   (V)
YF  = np.array([0.299, 0.587, 0.114])
CBF = np.array([-0.169, -0.331, 0.500])
CRF = np.array([0.500, -0.419, -0.081])

# The RTL's integer coefficients (used ONLY to prove fact A, i.e. to show they
# equal round(std_float * 256)). They are not used to compute the reference.
RTL_Y_COEF  = np.array([77, 150, 29])
RTL_CB_COEF = np.array([-43, -85, 128])
RTL_CR_COEF = np.array([128, -107, -21])


def load_dump(path):
    """Return arrays rgb565(N,), Y0(N,) uint8, U0(N,) uint8, V0(N,) uint8.

    The dump file uses hex (%04h / %02h); parse as base-16. Lines starting
    with '#' are comments.
    """
    if not os.path.exists(path):
        print(f"ERROR: {path} not found. Run tb_rgb2yuv_dump.v first.")
        sys.exit(1)
    rows = []
    with open(path) as f:
        for line in f:
            s = line.strip()
            if not s or s.startswith("#"):
                continue
            parts = s.split()
            rows.append([int(p, 16) for p in parts])
    arr = np.array(rows, dtype=np.int64)
    rgb = arr[:, 0].astype(np.uint16)
    Y0  = arr[:, 1].astype(np.uint8)
    U0  = arr[:, 2].astype(np.uint8)
    V0  = arr[:, 3].astype(np.uint8)
    return rgb, Y0, U0, V0


def rgb565_to_rgb888(rgb, mode="rtl"):
    """Expand RGB565 -> RGB888.

    Two expansion methods exist and we support both so we can (a) test the
    YUV matrix fairly against the RTL, and (b) quantify how non-canonical
    the RTL's expansion is:

      mode="rtl"   ->  match RGB2YUV.v exactly:
                       R8 = {R5, R5[2:0]} = (R5<<3)|(R5&0x07)   [low-bit replication]
                       G8 = {G6, G6[1:0]} = (G6<<2)|(G6&0x03)
                       B8 = {B5, B5[2:0]}
      mode="canon" ->  the canonical RGB565->888 (high-bit replication):
                       R8 = (R5<<3)|(R5>>2),  G8 = (G6<<2)|(G6>>4),  B8 = (B5<<3)|(B5>>2)

    Expansion is the INPUT ENCODING (a wire-format choice), not the colour
    matrix under test. Using the RTL's own expansion isolates the matrix.
    """
    r5 = (rgb >> 11) & 0x1F
    g6 = (rgb >> 5)  & 0x3F
    b5 =  rgb       & 0x1F
    if mode == "rtl":
        r8 = (r5 << 3) | (r5 & 0x07)
        g8 = (g6 << 2) | (g6 & 0x03)
        b8 = (b5 << 3) | (b5 & 0x07)
    elif mode == "canon":
        r8 = (r5 << 3) | (r5 >> 2)
        g8 = (g6 << 2) | (g6 >> 4)
        b8 = (b5 << 3) | (b5 >> 2)
    else:
        raise ValueError(mode)
    return np.stack([r8, g8, b8], axis=1).astype(np.int64)   # (N,3)


def report_diff(name, rtl, ref):
    diff = rtl.astype(np.int32) - ref.astype(np.int32)
    ad = np.abs(diff)
    print(f"\n--- {name} ---")
    print(f"  pixels           : {diff.size}")
    print(f"  max |diff|       : {int(ad.max())} LSB")
    print(f"  exact matches    : {int(np.sum(ad == 0))} "
          f"({100*np.sum(ad == 0)/diff.size:.2f}%)")
    print(f"  |diff| <= 1      : {int(np.sum(ad <= 1))} "
          f"({100*np.sum(ad <= 1)/diff.size:.2f}%)")
    print(f"  |diff| <= 2      : {int(np.sum(ad <= 2))} "
          f"({100*np.sum(ad <= 2)/diff.size:.2f}%)")
    vals, counts = np.unique(diff, return_counts=True)
    order = np.argsort(-counts)
    print("  diff histogram   : " +
          ", ".join(f"{int(v):+d}:{int(c)}" for v, c in
                    zip(vals[order][:6], counts[order][:6])))
    if ad.max() > 0:
        worst = np.argmax(ad)
        print(f"  worst pixel idx  : {worst}  diff={int(diff[worst]):+d}")
    return diff


def main():
    rgb, Y0, U0, V0 = load_dump(DUMP)
    N = rgb.size
    print(f"Loaded {N} dumped RTL samples from {os.path.basename(DUMP)}")

    # ===== Fact A : RTL integer coefs == round(BT.601 float * 256) =====
    print("\n" + "=" * 72)
    print(" Fact A : are RTL integer coefficients the x256 quantisation of")
    print("          the BT.601 floating-point standard?")
    print("=" * 72)
    factA = True
    for name, rtl_c, flt_c in [
        ("Y ", RTL_Y_COEF,  YF),
        ("Cb", RTL_CB_COEF, CBF),
        ("Cr", RTL_CR_COEF, CRF),
    ]:
        expected_int = np.round(flt_c * 256).astype(int)
        match = np.array_equal(rtl_c, expected_int)
        factA = factA and match
        print(f"  {name}: RTL={str(rtl_c):<18} round(float*256)={str(expected_int):<18} "
              f"{'MATCH' if match else '*** MISMATCH ***'}")
        if not match:
            print(f"       float coefs = {flt_c}")

    # ===== Fact B : per-pixel agreement across ALL inputs, both expansions =====
    # The expansion is INPUT ENCODING, not the colour matrix. After the fix the
    # RTL uses canonical (high-bit) replication, so it must match the BT.601
    # float reference built from CANONICAL expansion within 1 LSB. We also
    # report the old low-bit expansion to show the before/after clearly.
    print("\n" + "=" * 72)
    print(" Fact B : per-pixel RTL vs BT.601-float reference (all 65536 inputs)")
    print("   bar = |diff| <= 1 LSB (fixed-point floor vs float round).")
    print("   Both expansion modes tabulated; canonical is the post-fix spec.")
    print("=" * 72)

    summary = {}
    for mode in ("canon", "rtl"):
        rgb888_m = rgb565_to_rgb888(rgb, mode=mode)
        ry  = np.rint(rgb888_m @ YF ).astype(np.int32)
        rcb = np.rint(rgb888_m @ CBF + 128).astype(np.int32)
        rcr = np.rint(rgb888_m @ CRF + 128).astype(np.int32)
        mY = int(np.abs(Y0.astype(np.int32) - ry ).max())
        mU = int(np.abs(U0.astype(np.int32) - rcb).max())
        mV = int(np.abs(V0.astype(np.int32) - rcr).max())
        summary[mode] = (mY, mU, mV)
        tag = "canonical (high-bit) <-- spec" if mode == "canon" else "low-bit (pre-fix)"
        verdict = "<=1 LSB OK" if max(mY, mU, mV) <= 1 else "TOO LARGE"
        print(f"  [{tag}]  max|diff|  Y={mY}  Cb={mU}  Cr={mV}  -> {verdict}")

    # detailed histogram only for the spec (canonical) mode
    rgb888 = rgb565_to_rgb888(rgb, mode="canon")
    ref_y  = np.rint(rgb888 @ YF ).astype(np.int32)
    ref_cb = np.rint(rgb888 @ CBF + 128).astype(np.int32)
    ref_cr = np.rint(rgb888 @ CRF + 128).astype(np.int32)
    dY = report_diff("Y  (luma)   [canon]", Y0.astype(np.int32), ref_y)
    dU = report_diff("Cb (U, blue)[canon]", U0.astype(np.int32), ref_cb)
    dV = report_diff("Cr (V, red) [canon]", V0.astype(np.int32), ref_cr)
    factB = (np.abs(dY).max() <= 1 and np.abs(dU).max() <= 1
             and np.abs(dV).max() <= 1)
    # canonical must win (strictly smaller max) than low-bit -> proves the fix
    canon_wins = (max(summary["canon"]) < max(summary["rtl"]))
    print(f"\n  canonical expansion beats low-bit : {'YES (fix confirmed)' if canon_wins else 'NO'}")

    # ===== Observation : expansion is now canonical (confirmed via Fact B) ===
    print("\n" + "=" * 72)
    print(" Observation : RGB565->RGB888 expansion")
    print("   After the fix the RTL uses canonical HIGH-bit replication:")
    print("     R8 = {R5, R5[4:2]} = (R5<<3)|(R5>>2),  G8 = {G6, G6[5:4]},")
    print("     B8 = {B5, B5[4:2]}.  This is the standard expansion; it")
    print("     approximates linear scaling R5*255/31 to within 1 LSB")
    print("     (NOT exactly equal -- e.g. R5=3 -> 24 vs round=25).")
    print("   Proof of the fix: in Fact B the canonical-mode reference matches")
    print("   the RTL within 1 LSB while the old low-bit mode does not.")
    print("=" * 72)
    # property check on the canonical R-channel mapping
    r5_vals = np.arange(32)
    r8_canon = (r5_vals << 3) | (r5_vals >> 2)
    r8_linear = np.rint(r5_vals * 255.0 / 31.0).astype(int)
    dev = np.abs(r8_canon - r8_linear)
    print(f"  R5=0 -> R8={int(r8_canon[0])}, R5=31 -> R8={int(r8_canon[-1])}, "
          f"monotonic={bool(np.all(np.diff(r8_canon) >= 0))}")
    print(f"  max|R8_canon - round(R5*255/31)| over 32 : {int(dev.max())} "
          f"(canonical is a 1-LSB approximation, not exact)")

    # invariants that must hold exactly (independent of any coefficient choice)
    black = np.argmax(rgb == 0x0000)
    white = np.argmax(rgb == 0xFFFF)
    print("\n" + "=" * 72)
    print(" Independent invariants (must hold exactly):")
    print("=" * 72)
    inv_ok = ((Y0[black], U0[black], V0[black]) == (0, 128, 128) and
              (Y0[white], U0[white], V0[white]) == (255, 128, 128))
    print(f"  Black 0x0000 -> Y={int(Y0[black]):3d}, U={int(U0[black]):3d}, "
          f"V={int(V0[black]):3d}   (expect 0,128,128)  "
          f"{'OK' if (Y0[black],U0[black],V0[black])==(0,128,128) else 'FAIL'}")
    print(f"  White 0xFFFF -> Y={int(Y0[white]):3d}, U={int(U0[white]):3d}, "
          f"V={int(V0[white]):3d}   (expect 255,128,128) "
          f"{'OK' if (Y0[white],U0[white],V0[white])==(255,128,128) else 'FAIL'}")

    # ---- verdict ----
    print("\n" + "=" * 72)
    print(" VERDICT")
    print(f"   Fact A (coefs = BT.601 x256)          : {'CONFIRMED' if factA else 'FAIL'}")
    print(f"   Fact B (matrix vs float, <=1 LSB)     : {'CONFIRMED' if factB else 'FAIL'}")
    print(f"   Expansion = canonical (beats low-bit) : {'CONFIRMED' if canon_wins else 'FAIL'}")
    print(f"   Invariants (black/white gray point)   : {'CONFIRMED' if inv_ok else 'FAIL'}")
    overall = factA and factB and canon_wins and inv_ok
    print(f"   OVERALL (matrix + expansion)          : {'PASS' if overall else 'FAIL'}")
    print("=" * 72)
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
