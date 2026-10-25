"""Cycle-accurate model of the ISP_TOP data path (no SDRAM).

The ISP_TOP topology is *parallel*: RGB2YUV converts the RGB565 stream to
Y0, and the grey-scale Y0 is fanned out to every point op / filter; the
sobel -> canny pair is the only series connection.  This module provides
one Python model per ISP_TOP stage, reusing the already-verified
single-module models where possible:

  - RGB2YUVModel   : replica of RGB2YUV.v (3-stage pipeline, 3-cycle sync delay)
  - downstream models: reuse verify_pointops (LOG), verify_golden
    (matrix_generator + gaussian / median / sobel) and verify_thresh_path
    (canny).  Each consumes the grey Y0 stream and its own delayed sync.

All models follow the NBA convention used across this repo: cycle() takes
the inputs sampled at posedge T, returns the outputs as they appear AFTER
posedge T-1 (i.e. what the RTL presents during cycle T), and commits the
registered updates.  The cocotb driver (test_isp_chain.py) drives inputs,
reads outputs, then calls cycle() and awaits the posedge -- exactly the
alignment used by test_pointops.py / test_golden.py.
"""

import numpy as np


# ---------------------------------------------------------------------------
# RGB565 -> RGB888 expansion (canonical high-bit replication, RGB2YUV.v L48-50)
# ---------------------------------------------------------------------------

def rgb565_to_rgb888(rgb):
    """Return (R8, G8, B8) ints for a 16-bit RGB565 pixel."""
    r5 = (rgb >> 11) & 0x1F
    g6 = (rgb >> 5) & 0x3F
    b5 = rgb & 0x1F
    r8 = (r5 << 3) | (r5 >> 2)
    g8 = (g6 << 2) | (g6 >> 4)
    b8 = (b5 << 3) | (b5 >> 2)
    return r8, g8, b8


def rgb565_pack(y8):
    """Pack 8-bit grey into RGB565: {Y[7:3], Y[7:2], Y[7:3]} (same as
    verify_golden.rgb565_pack)."""
    return ((y8 >> 3) << 11) | ((y8 >> 2) << 5) | (y8 >> 3)


# ---------------------------------------------------------------------------
# RGB2YUV model (RGB2YUV.v)
# ---------------------------------------------------------------------------

class RGB2YUVModel:
    """3-stage fixed-point pipeline:  {r0,g0,b0} -> {y0,u0,v0} -> {Y0,U0,V0},
    sync delayed by 3 cycles (r_hsync/r_vsync/r_blank [2])."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.r0 = self.g0 = self.b0 = 0
        self.r1 = self.g1 = self.b1 = 0
        self.r2 = self.g2 = self.b2 = 0
        self.y0 = self.u0 = self.v0 = 0
        self.Y0 = self.U0 = self.V0 = 0
        self.r_hsync = [0, 0, 0]
        self.r_vsync = [0, 0, 0]
        self.r_blank = [0, 0, 0]

    def cycle(self, rgb, h, v, b):
        """rgb: 16-bit RGB565. Returns (Y0, display_data, H_SYNC, V_SYNC, BLANK)
        as they appear during this cycle (post-previous-posedge)."""
        # outputs (registered values, sampled pre-posedge)
        Y0 = self.Y0
        disp = rgb565_pack(Y0)
        o_h = self.r_hsync[2]
        o_v = self.r_vsync[2]
        o_b = self.r_blank[2]

        r8, g8, b8 = rgb565_to_rgb888(rgb)

        # stage 1: coefficients (16-bit products truncate)
        nr0 = (r8 * 77) & 0xFFFF
        ng0 = (g8 * 150) & 0xFFFF
        nb0 = (b8 * 29) & 0xFFFF
        nr1 = (r8 * 43) & 0xFFFF
        ng1 = (g8 * 85) & 0xFFFF
        nb1 = (b8 * 128) & 0xFFFF
        nr2 = (r8 * 128) & 0xFFFF
        ng2 = (g8 * 107) & 0xFFFF
        nb2 = (b8 * 21) & 0xFFFF

        # stage 2
        ny0 = (self.r0 + self.g0 + self.b0) & 0xFFFF
        nu0 = (self.b1 - self.r1 - self.g1 + 32768) & 0xFFFF
        nv0 = (self.r2 - self.g2 - self.b2 + 32768) & 0xFFFF

        # stage 3
        nY0 = (self.y0 >> 8) & 0xFF
        # U0/V0 not used downstream but kept for completeness
        _nU0 = (self.u0 >> 8) & 0xFF
        _nV0 = (self.v0 >> 8) & 0xFF

        # commit
        self.r0, self.g0, self.b0 = nr0, ng0, nb0
        self.r1, self.g1, self.b1 = nr1, ng1, nb1
        self.r2, self.g2, self.b2 = nr2, ng2, nb2
        self.y0, self.u0, self.v0 = ny0, nu0, nv0
        self.Y0, self.U0, self.V0 = nY0, _nU0, _nV0
        self.r_hsync = [h] + self.r_hsync[:2]
        self.r_vsync = [v] + self.r_vsync[:2]
        self.r_blank = [b] + self.r_blank[:2]

        return Y0, disp, o_h, o_v, o_b


# ---------------------------------------------------------------------------
# Downstream stages (wrappers around the already-verified single-module models)
# ---------------------------------------------------------------------------

class LogStage:
    """LOG.v: 1-cycle ROM read of the grey Y0; display = pack(lut[Y0])."""

    def __init__(self, lut):
        self.lut = lut
        self.dout = 0
        self.hs = self.vs = self.bl = 0

    def reset(self):
        self.dout = 0
        self.hs = self.vs = self.bl = 0

    def cycle(self, y, h, v, b):
        disp = rgb565_pack(self.dout)
        o_h, o_v, o_b = self.hs, self.vs, self.bl
        self.hs, self.vs, self.bl = h, v, b
        self.dout = self.lut[y]
        return disp, o_h, o_v, o_b


class HistogramStage:
    """HISTOGRAM.v on the grey Y0: pseudo-stretch datapath (reuses
    verify_pointops.HistogramModel) plus the 3-cycle sync delay chain
    (H_SYNC/V_SYNC/BLANK = r_*[1] of RGB2YUV's downstream view)."""

    def __init__(self, vp):
        self.m = vp.HistogramModel()

    def reset(self):
        self.m.reset()

    def cycle(self, y, h, v, b):
        # RTL: H_SYNC = r_hsync[1], V_SYNC = r_vsync[1], BLANK = r_blank[1]
        # (2-bit shift registers).  HistogramModel maintains the same chain
        # and returns blank in out[1]; recover H/V from the pre-update chain.
        out = self.m.cycle(y, h, v, b)
        disp = out[0]
        H = (self.m.rh >> 1) & 1
        V = (self.m.rv >> 1) & 1
        B = (self.m.rb >> 1) & 1
        return disp, H, V, B


class CannyStage:
    """Canny.v consuming sobel's canny_in (15-bit).  display_data is
    combinational on is_edge; H/V/B sync is a 1-cycle delay of the internal
    15-bit matrix_generator's sync outputs (RTL L128-131)."""

    def __init__(self, vtp, rtl_as_written=False):
        self.m = vtp.CannyModel(rtl_as_written=rtl_as_written)
        # RTL: H_SYNC/V_SYNC/BLANK <= o_HSYNC/o_VSYNC/o_BLANK (1-cycle delay)
        self.r_h = self.r_v = self.r_b = 0

    def reset(self):
        self.m.reset()
        self.r_h = self.r_v = self.r_b = 0

    def cycle(self, y15, h, v, b):
        # matrix_generator sync outputs as of this cycle (pre-posedge):
        # o_HSYNC = r_hsync[2], o_VSYNC = r_vsync[802], o_BLANK = r_blank[802]
        mg = self.m.mg
        o_h = mg.r_hsync[2]
        o_v = mg.r_vsync[802]
        o_b = mg.r_blank[802]
        # CannyModel.clock returns the NEW is_edge (aligned to its own
        # negedge-sampling dump); for this chain's pre-posedge protocol we
        # must present the OLD (registered) is_edge, i.e. self.m.is_edge
        # before the update.
        old_edge = self.m.is_edge
        rec = self.m.clock(y15, b, v, h)
        disp = 0xFFFF if old_edge else 0
        # canny's registered syncs sample the matrix outputs at this posedge
        H = self.r_h
        V = self.r_v
        B = self.r_b
        self.r_h, self.r_v, self.r_b = o_h, o_v, o_b
        return disp, H, V, B, rec


# ---------------------------------------------------------------------------
# Composite ISP chain model
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Sobel (display + canny_in) via verify_golden.SobelPipeline.
#
# NOTE: verify_golden's models return PREVIOUS-posedge values (matching the
# cocotb "read before posedge" protocol used here), while
# verify_thresh_path.SobelThreshModel returns the CURRENT-posedge value
# (it was aligned to a negedge-sampling Verilog dump).  For this chain we
# need the pre-posedge convention, so SobelPipeline is the right model.
# Its phase tie-break was fixed to read the OLD direction (see
# verify_golden.py note); display and canny_in both follow from sqrg.
# ---------------------------------------------------------------------------

class SobelStage:
    """sobel.v: matrix_generator + sobel (display + canny_in + 14-bit sync)."""

    def __init__(self, vg):
        self.m = vg.SobelPipeline(thresh_min=60, thresh_max=120)

    def reset(self):
        self.m.reset()

    def cycle(self, y, h, v, b):
        # SobelPipeline.clock(i_Y0, i_BLANK, i_VSYNC, i_HSYNC) ->
        # (disp, H, V, B, canny_in), all pre-posedge values.
        return self.m.clock(y, b, v, h)


class ISPMatrixPipeline:
    """Wraps a verify_golden FilterPipeline (matrix_generator + one filter)
    so its clock() returns what the chain needs: (disp, H, V, B)."""

    def __init__(self, pipe):
        self.pipe = pipe

    def reset(self):
        self.pipe.reset()

    def cycle(self, y, h, v, b):
        out = self.pipe.clock(y, b, v, h)
        # filter models return (disp, H_SYNC, V_SYNC, BLANK)
        return out


class ISPChainModel:
    """Full grey path: RGB565 -> RGB2YUV -> Y0 fan-out ->
    {LOG, HISTOGRAM, GAUSSIAN, MEDIAN, SOBEL->CANNY}.

    Each stage models what the RTL presents during cycle T (post-posedge
    values of T-1), so the cocotb driver can compare directly.
    """

    def __init__(self, lut, vp, vg, vtp):
        self.vp = vp
        self.vg = vg
        self.vtp = vtp
        self.rgb = RGB2YUVModel()
        self.log = LogStage(lut)
        self.hist_s = HistogramStage(vp)
        self.gauss = ISPMatrixPipeline(vg.GaussianPipeline())
        self.median = ISPMatrixPipeline(vg.MedianPipeline())
        self.sobel = SobelStage(vg)
        self.canny = CannyStage(vtp, rtl_as_written=False)

    def reset(self):
        self.rgb.reset()
        self.log.reset()
        self.hist_s.reset()
        self.gauss.reset()
        self.median.reset()
        self.sobel.reset()
        self.canny.reset()

    def cycle(self, rgb, h, v, b):
        """rgb: 16-bit RGB565. Returns dict of every stage's outputs.
        Order of operations mirrors RTL: downstream stages consume the
        REGISTERED Y0/sync of RGB2YUV, i.e. the values produced one cycle
        earlier; in the RTL this is exactly what the downstream modules see
        on their inputs during this cycle."""
        # RGB2YUV outputs (post-posedge T-1)
        Y0, disp_rgb, hh, vv, bb = self.rgb.cycle(rgb, h, v, b)

        # Downstream consume Y0 + the sync RGB2YUV presented last cycle:
        # i_Y0 = Y0, i_HSYNC/V_SYNC/BLANK = RGB2YUV's registered syncs.
        log_out = self.log.cycle(Y0, hh, vv, bb)
        hist_out = self.hist_s.cycle(Y0, hh, vv, bb)
        gauss_out = self.gauss.cycle(Y0, hh, vv, bb)
        med_out = self.median.cycle(Y0, hh, vv, bb)
        # sobel consumes Y0; its sync inputs are RGB2YUV's registered syncs
        sob_out = self.sobel.cycle(Y0, hh, vv, bb)

        # sobel -> canny: canny consumes sobel's canny_in; canny's own
        # matrix_generator is 15-bit and its sync chain is driven by sobel's
        # registered sync outputs (sobel pipeline's r_*[13]).
        canny_in = sob_out[4]
        canny_out = self.canny.cycle(canny_in, sob_out[1], sob_out[2],
                                     sob_out[3])

        return {
            "rgb": (Y0, disp_rgb, hh, vv, bb),
            "log": log_out,
            "hist": hist_out,
            "gauss": gauss_out,
            "median": med_out,
            "sobel": sob_out,
            "canny": canny_out,
        }