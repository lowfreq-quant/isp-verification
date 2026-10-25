"""Verify Gaussian, Sobel, and Median filter RTL against cycle-accurate Python models.

The golden models are software replicas of matrix_generator + filter that mirror
Verilog's non-blocking assignment (NBA) semantics exactly: every registered
output is sampled before the clock edge, and combinational outputs read the
pre-edge registered values.

Usage:
    1. python sim/run_golden.py        # produces sim/rtl_dump.npz
    2. python sim/verify_golden.py

Test bench protocol (matches test_golden.py):
  - Each image: 1-cycle VSYNC pulse, then H*W pixels with i_BLANK=1.
  - HSYNC merged with the last pixel of each row (row = exactly W cycles).
  - 40-cycle blank gap between images.
  - Inter-image rst_n reset (8 cycles) so every frame starts clean.
"""
import os
import sys
import math
import numpy as np


# ----------------------------- FWFT FIFO -----------------------------------

class FWFT_FIFO:
    """First-Word-Fall-Through FIFO matching sim/ip/behavioral_fifo.v.

    step() returns the OLD dout (the value visible to matrix_generator at
    this posedge), then commits all register updates — mirroring Verilog
    non-blocking assignment semantics.
    """

    def __init__(self, depth=2048, data_width=8):
        self.depth = depth
        self.data_width = data_width
        self.mask = (1 << data_width) - 1
        self.reset()

    def reset(self):
        self.mem = [0] * self.depth
        self.wr_ptr = 0
        self.rd_ptr = 0
        self.count = 0
        self.dout_reg = 0
        self.dout_valid = False

    def step(self, din, wr_en, rd_en):
        old_dout = self.dout_reg
        old_dout_valid = self.dout_valid
        old_count = self.count
        old_wr_ptr = self.wr_ptr
        old_rd_ptr = self.rd_ptr

        new_wr_ptr = old_wr_ptr
        new_rd_ptr = old_rd_ptr
        new_dout_reg = old_dout
        new_dout_valid = old_dout_valid
        new_count = old_count

        if wr_en and old_count < self.depth:
            self.mem[old_wr_ptr] = din & self.mask
            new_wr_ptr = (old_wr_ptr + 1) % self.depth

        if not old_dout_valid and old_count > 0:
            new_dout_reg = self.mem[old_rd_ptr]
            new_rd_ptr = (old_rd_ptr + 1) % self.depth
            new_dout_valid = True
        elif rd_en and old_dout_valid:
            if old_rd_ptr != old_wr_ptr:
                new_dout_reg = self.mem[old_rd_ptr]
                new_rd_ptr = (old_rd_ptr + 1) % self.depth
            else:
                new_dout_valid = False

        if wr_en and not rd_en and old_count < self.depth:
            new_count = old_count + 1
        elif not wr_en and rd_en and old_dout_valid:
            new_count = old_count - 1

        self.wr_ptr = new_wr_ptr
        self.rd_ptr = new_rd_ptr
        self.dout_reg = new_dout_reg
        self.dout_valid = new_dout_valid
        self.count = new_count

        return old_dout


# --------------------- shared matrix_generator model -----------------------

class MatrixGenerator:
    """Cycle-accurate model of matrix_generator.v (parameterized DATA_WIDTH)."""

    def __init__(self, data_width=8, fifo_depth=2048):
        self.data_width = data_width
        self.mask = (1 << data_width) - 1
        self.fifo_depth = fifo_depth
        self.reset()

    def reset(self):
        self.i_Y0_r = 0
        self.i_Y0_r2 = 0
        self.r_i_BLANK_0 = 0
        self.r_blank = [0] * 803
        self.r_hsync = [0] * 3
        self.r_vsync = [0] * 803
        self.line_cnt = 0
        self.col_cnt = 0
        self.m = [0] * 9
        self.fifo1 = FWFT_FIFO(self.fifo_depth, self.data_width)
        self.fifo2 = FWFT_FIFO(self.fifo_depth, self.data_width)

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC):
        # Save OLD matrix for output (RTL reads pre-posedge values)
        old_m = list(self.m)

        # Outputs produced by matrix_generator at the *previous* posedge
        o_HSYNC = self.r_hsync[2]
        o_VSYNC = self.r_vsync[802]
        o_BLANK = self.r_blank[802]

        # Save old r_blank[799] BEFORE shift (RTL data_valid uses pre-posedge value)
        old_r_blank_799 = self.r_blank[799]

        # Shift input sync / blank signals
        self.r_hsync = [i_HSYNC] + self.r_hsync[:-1]
        self.r_vsync = [i_VSYNC] + self.r_vsync[:-1]
        self.r_blank = [i_BLANK] + self.r_blank[:-1]

        data_valid = 1 if (i_BLANK or old_r_blank_799) else 0
        i_BLANK_neg = 1 if (data_valid == 0 and self.r_i_BLANK_0 == 1) else 0
        if i_BLANK_neg:
            fifo_din = i_Y0 | (self.i_Y0_r & self.mask)
        else:
            fifo_din = i_Y0

        wr_en1 = (self.line_cnt <= 479) and bool(data_valid or self.r_i_BLANK_0)
        wr_en2 = (self.line_cnt <= 478) and bool(data_valid or self.r_i_BLANK_0)
        rd_en1 = (self.line_cnt >= 1) and bool(data_valid or self.r_i_BLANK_0)
        rd_en2 = (self.line_cnt >= 2) and bool(data_valid or self.r_i_BLANK_0)

        dout1 = self.fifo1.step(fifo_din, wr_en1, rd_en1)
        dout2 = self.fifo2.step(fifo_din, wr_en2, rd_en2)

        m = self.m
        nm = list(m)
        lc, cc = self.line_cnt, self.col_cnt
        y0 = i_Y0 & self.mask
        if lc == 0:
            if cc == 0:
                nm = [y0] * 9
            elif cc == 639:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = y0
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = y0
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0
            else:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = y0
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = y0
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0
        elif lc == 1:
            if cc == 0:
                nm = [dout1] * 6 + [y0] * 3
            elif cc == 639:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = dout1
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = dout1
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0
            else:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = dout1
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = dout1
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0
        else:
            if cc == 0:
                nm = [dout2] * 3 + [dout1] * 3 + [y0] * 3
            elif cc == 639:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = dout2
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = dout1
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0
            else:
                nm[0] = m[1]; nm[1] = m[2]; nm[2] = dout2
                nm[3] = m[4]; nm[4] = m[5]; nm[5] = dout1
                nm[6] = m[7]; nm[7] = m[8]; nm[8] = y0

        self.i_Y0_r2 = self.i_Y0_r
        self.i_Y0_r = i_Y0 & self.mask
        self.r_i_BLANK_0 = data_valid
        # line_cnt 递增（cc==639 时，独立于 col_cnt 归零条件）
        if cc == 639:
            self.line_cnt = 0 if lc == 480 else lc + 1
        # col_cnt: HSYNC/VSYNC FALLING edge zeroes first (matches RTL:
        # low-active VGA syncs would keep i_HSYNC high most of the line and
        # the old `i_HSYNC or i_VSYNC` condition would pin col_cnt at 0),
        # then cc==639, then data_valid increments.
        hsync_fall = (self.r_hsync[1] == 1 and self.r_hsync[0] == 0)
        vsync_fall = (self.r_vsync[1] == 1 and self.r_vsync[0] == 0)
        if hsync_fall or vsync_fall:
            self.col_cnt = 0
        elif cc == 639:
            self.col_cnt = 0
        elif data_valid:
            self.col_cnt = cc + 1
        self.m = nm

        # Return OLD matrix (pre-posedge value visible to downstream filters)
        return old_m, o_HSYNC, o_VSYNC, o_BLANK


# --------------------- filter pipeline models ------------------------------

def rgb565_pack(y8):
    """Pack 8-bit grayscale into RGB565: {Y[7:3], Y[7:2], Y[7:3]}."""
    return ((y8 >> 3) << 11) | ((y8 >> 2) << 5) | (y8 >> 3)


def sort3(a, b, c):
    """Sort three 8-bit values descending: return (max, mid, min).

    Matches median_filter.v sort module: data1 >= data2 >= data3 ->
    max=data1, mid=data2, min=data3, with equality handled consistently.
    """
    if a >= b and b >= c:
        return a, b, c
    if a >= c and c >= b:
        return a, c, b
    if b >= a and a >= c:
        return b, a, c
    if b >= c and c >= a:
        return b, c, a
    if c >= a and a >= b:
        return c, a, b
    return c, b, a


class FilterPipeline:
    """Base class for filter-specific cycle-accurate models."""

    def __init__(self):
        self.mg = MatrixGenerator(data_width=8, fifo_depth=2048)

    def reset(self):
        self.mg.reset()

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC):
        raise NotImplementedError


class GaussianPipeline(FilterPipeline):
    """Software replica of matrix_generator + gaussian_filter."""

    def __init__(self):
        super().__init__()
        self.gs1 = 0
        self.gs2 = 0
        self.gs3 = 0
        self.gs_sum = 0
        self.gs_data = 0
        self.r_hsync = [0] * 3
        self.r_vsync = [0] * 3
        self.r_blank = [0] * 3

    def reset(self):
        super().reset()
        self.gs1 = 0
        self.gs2 = 0
        self.gs3 = 0
        self.gs_sum = 0
        self.gs_data = 0
        self.r_hsync = [0] * 3
        self.r_vsync = [0] * 3
        self.r_blank = [0] * 3

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC):
        m, o_HSYNC, o_VSYNC, o_BLANK = self.mg.clock(i_Y0, i_BLANK, i_VSYNC, i_HSYNC)

        # New gaussian stages from OLD registered values
        ngs1 = m[0] + 2 * m[1] + m[2]
        ngs2 = 2 * m[3] + 4 * m[4] + 2 * m[5]
        ngs3 = m[6] + 2 * m[7] + m[8]
        ngs_sum = self.gs1 + self.gs2 + self.gs3
        ngs_data = self.gs_sum >> 4

        # Combinational display_data from OLD gs_data
        disp = rgb565_pack(self.gs_data)

        # Commit filter-specific registers and sync delays.
        # NOTE: sync SHIFT direction and READ timing must match RTL
        # `r_* <= {r_*[N-2:0], in}` (new value enters bit 0) with the sync
        # output read BEFORE the shift (i.e. the value committed last
        # posedge).  The pre-fix code read r_hsync[2] AFTER the shift and
        # pushed the new value to the MSB - the sync outputs were never
        # compared by this verifier (only display_data was), so it went
        # unnoticed; the ISP-chain verifier (verify_isp_chain.py) compares
        # them and exposed it.
        H_SYNC = self.r_hsync[2]
        V_SYNC = self.r_vsync[2]
        BLANK = self.r_blank[2]
        self.gs1, self.gs2, self.gs3 = ngs1, ngs2, ngs3
        self.gs_sum = ngs_sum
        self.gs_data = ngs_data
        self.r_hsync = [o_HSYNC] + self.r_hsync[:-1]
        self.r_vsync = [o_VSYNC] + self.r_vsync[:-1]
        self.r_blank = [o_BLANK] + self.r_blank[:-1]

        return disp, H_SYNC, V_SYNC, BLANK


class SobelPipeline(FilterPipeline):
    """Software replica of matrix_generator + sobel."""

    def __init__(self, thresh_min=50, thresh_max=150):
        super().__init__()
        self.thresh_min = thresh_min
        self.thresh_max = thresh_max
        self.gx_1 = 0
        self.gx_3 = 0
        self.gy_1 = 0
        self.gy_3 = 0
        self.gx = 0
        self.gy = 0
        self.g = 0
        self.direction = 0
        # RTL has NO reset branch for `phase`; during reset, gx=gy=0 and
        # direction=0 make the tie-break select phase=2'b01 (mirrors
        # verify_thresh_path.SobelThreshModel).
        self.phase = 1
        self.phase_d = [0] * 22
        self.r_hsync = [0] * 14
        self.r_vsync = [0] * 14
        self.r_blank = [0] * 14

    def reset(self):
        super().reset()
        self.gx_1 = 0
        self.gx_3 = 0
        self.gy_1 = 0
        self.gy_3 = 0
        self.gx = 0
        self.gy = 0
        self.g = 0
        self.direction = 0
        self.phase = 1
        self.phase_d = [0] * 22
        self.r_hsync = [0] * 14
        self.r_vsync = [0] * 14
        self.r_blank = [0] * 14

    @staticmethod
    def _sqrt20(radicand):
        """Non-restoring sqrt matching gen_sqrt in behavioral_cordic.v exactly.

        Key RTL detail: r_shift is a 5-bit register, so
        r_shift = {r_res[8:0], 1'b0} + 1  is truncated to 5 bits.
        r_res bits are set individually at position (9-i).
        """
        r_rem = 0
        r_res = 0
        for i in range(10):
            # r_rem = {r_rem[17:0], r_rad[19-2*i -: 2]}
            bits = (radicand >> (18 - 2 * i)) & 0x3
            r_rem = ((r_rem & 0x3FFFF) << 2) | bits
            # r_shift = {r_res[8:0], 1'b0} + 1, truncated to 5 bits
            r_shift = (((r_res & 0x1FF) << 1) + 1) & 0x1F
            if r_rem >= r_shift:
                r_rem -= r_shift
                r_res |= (1 << (9 - i))
        return r_res

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC):
        m, o_HSYNC, o_VSYNC, o_BLANK = self.mg.clock(i_Y0, i_BLANK, i_VSYNC, i_HSYNC)

        # Stage 1: row/column convolutions (old values -> new regs)
        ngx_1 = m[0] + 2 * m[1] + m[2]
        ngx_3 = m[6] + 2 * m[7] + m[8]
        ngy_1 = m[0] + 2 * m[3] + m[6]
        ngy_3 = m[2] + 2 * m[5] + m[8]

        # Stage 2: absolute gradients and direction (old stage-1 -> new regs)
        ogx_1, ogx_3, ogy_1, ogy_3 = self.gx_1, self.gx_3, self.gy_1, self.gy_3
        ngx = ogx_1 - ogx_3 if ogx_1 > ogx_3 else ogx_3 - ogx_1
        ngy = ogy_1 - ogy_3 if ogy_1 > ogy_3 else ogy_3 - ogy_1
        ndirection = ((ogx_1 > ogx_3) << 1) | (ogy_1 > ogy_3)

        # Stage 3: phase is combinational registered from old gx/gy.
        # NOTE (verified by verify_thresh_path.py): the phase tie-break reads
        # the OLD direction register (direction(T-1)), not the new one just
        # computed this posedge.  The pre-fix code used ndirection here, which
        # only affects canny_in (display_data depends only on sqrg), so the
        # display-only verifier never noticed; the thresh-path verifier
        # exposed it and the corrected model matches RTL exactly.
        ogx, ogy = self.gx, self.gy
        odir = self.direction
        if ogx > 2 * ogy:
            nphase = 0
        elif ogy > 2 * ogx:
            nphase = 2
        elif (odir & 1) == ((odir >> 1) & 1):
            nphase = 1
        else:
            nphase = 3

        # Stage 4: g = gx*gx + gy*gy from old gx/gy
        ng = ogx * ogx + ogy * ogy

        # CORDIC sqrt: behavioral_cordic.v interprets g as {gx[9:0], gy[9:0]}
        # and computes sqrt(gx^2 + gy^2), NOT sqrt(g)
        gx_beh = (self.g >> 10) & 0x3FF
        gy_beh = self.g & 0x3FF
        sq = (gx_beh * gx_beh + gy_beh * gy_beh) & 0xFFFFF  # 20-bit truncation
        sqrg = self._sqrt20(sq)

        # thresh is combinational
        if sqrg > self.thresh_max:
            thresh = 3
        elif sqrg < self.thresh_min:
            thresh = 1
        else:
            thresh = 2

        # canny_in = {phase, thresh, sqrg[10:0]} -- phase is the REGISTERED
        # (previous-posedge) value, thresh/sqrg are combinational.  The
        # display-only verifier never compared canny_in, so using nphase here
        # went unnoticed; the ISP-chain verifier exposed it.
        ophase = self.phase
        canny_in = (ophase << 13) | (thresh << 11) | (sqrg & 0x7FF)

        # display_data is combinational
        disp = 0xFFFF if sqrg > 120 else 0

        # Commit
        self.gx_1, self.gx_3, self.gy_1, self.gy_3 = ngx_1, ngx_3, ngy_1, ngy_3
        self.gx, self.gy, self.direction = ngx, ngy, ndirection
        self.phase = nphase
        self.g = ng
        phase_d_int = 0
        for b in self.phase_d:
            phase_d_int = (phase_d_int << 1) | (b & 1)
        phase_d_int = ((phase_d_int & 0x3FFFFF) << 2) | (nphase & 0x3)
        self.phase_d = [(phase_d_int >> i) & 1 for i in range(21, -1, -1)]

        H_SYNC = self.r_hsync[13]
        V_SYNC = self.r_vsync[13]
        BLANK = self.r_blank[13]
        self.r_hsync = [o_HSYNC] + self.r_hsync[:-1]
        self.r_vsync = [o_VSYNC] + self.r_vsync[:-1]
        self.r_blank = [o_BLANK] + self.r_blank[:-1]

        return disp, H_SYNC, V_SYNC, BLANK, canny_in


class MedianPipeline(FilterPipeline):
    """Software replica of matrix_generator + median_filter."""

    def __init__(self):
        super().__init__()
        # 7 sort stages; each registered output is a separate delay stage.
        self.sort1 = (0, 0, 0)
        self.sort2 = (0, 0, 0)
        self.sort3 = (0, 0, 0)
        self.sort4 = (0, 0, 0)
        self.sort5 = (0, 0, 0)
        self.sort6 = (0, 0, 0)
        self.sort7 = (0, 0, 0)
        self.r_hsync = [0] * 3
        self.r_vsync = [0] * 3
        self.r_blank = [0] * 3

    def reset(self):
        super().reset()
        self.sort1 = self.sort2 = self.sort3 = (0, 0, 0)
        self.sort4 = self.sort5 = self.sort6 = (0, 0, 0)
        self.sort7 = (0, 0, 0)
        self.r_hsync = [0] * 3
        self.r_vsync = [0] * 3
        self.r_blank = [0] * 3

    def clock(self, i_Y0, i_BLANK, i_VSYNC, i_HSYNC):
        m, o_HSYNC, o_VSYNC, o_BLANK = self.mg.clock(i_Y0, i_BLANK, i_VSYNC, i_HSYNC)

        # Stage 1: sort rows (registered outputs max1/mid1/min1 etc.)
        ns1 = sort3(m[0], m[1], m[2])
        ns2 = sort3(m[3], m[4], m[5])
        ns3 = sort3(m[6], m[7], m[8])

        # Stage 2: sort max/mid/min across rows
        ns4 = sort3(self.sort1[0], self.sort2[0], self.sort3[0])
        ns5 = sort3(self.sort1[1], self.sort2[1], self.sort3[1])
        ns6 = sort3(self.sort1[2], self.sort2[2], self.sort3[2])

        # Stage 3: final median
        ns7 = sort3(self.sort4[0], self.sort5[1], self.sort6[2])
        Y0 = self.sort7[1]

        disp = rgb565_pack(Y0)

        # Commit (sync read BEFORE shift, new value enters bit 0 -- same
        # convention as GaussianPipeline; see note there).
        self.sort1, self.sort2, self.sort3 = ns1, ns2, ns3
        self.sort4, self.sort5, self.sort6 = ns4, ns5, ns6
        self.sort7 = ns7

        H_SYNC = self.r_hsync[2]
        V_SYNC = self.r_vsync[2]
        BLANK = self.r_blank[2]
        self.r_hsync = [o_HSYNC] + self.r_hsync[:-1]
        self.r_vsync = [o_VSYNC] + self.r_vsync[:-1]
        self.r_blank = [o_BLANK] + self.r_blank[:-1]
        return disp, H_SYNC, V_SYNC, BLANK


# -------------------------- test bench driver ------------------------------

def run_testbench(pipeline, images, H, W, BLANK_GAP=40, DRAIN=2000):
    """Drive a pipeline exactly like test_golden.py and return all outputs."""
    all_disp = []
    all_vsync = []
    all_y0 = []
    all_canny_in = []

    for _ in range(4):
        out = pipeline.clock(0, 0, 0, 0)
        all_disp.append(out[0])
        all_vsync.append(0)
        all_y0.append(0)
        all_canny_in.append(out[4] if len(out) > 4 else 0)

    for img_idx, img in enumerate(images):
        out = pipeline.clock(0, 1, 1, 0)
        all_disp.append(out[0])
        all_vsync.append(1)
        all_y0.append(0)
        all_canny_in.append(out[4] if len(out) > 4 else 0)

        for row in range(H):
            for col in range(W):
                hsync = 1 if col == W - 1 else 0
                v = int(img[row, col])
                out = pipeline.clock(v, 1, 0, hsync)
                all_disp.append(out[0])
                all_vsync.append(0)
                all_y0.append(v)
                all_canny_in.append(out[4] if len(out) > 4 else 0)

        for _ in range(BLANK_GAP):
            out = pipeline.clock(0, 0, 0, 0)
            all_disp.append(out[0])
            all_vsync.append(0)
            all_y0.append(0)
            all_canny_in.append(out[4] if len(out) > 4 else 0)

        if img_idx < len(images) - 1:
            pipeline.reset()
            for _ in range(8):
                out = pipeline.clock(0, 0, 0, 0)
                all_disp.append(out[0])
                all_vsync.append(0)
                all_y0.append(0)
                all_canny_in.append(out[4] if len(out) > 4 else 0)

    for _ in range(DRAIN):
        out = pipeline.clock(0, 0, 0, 0)
        all_disp.append(out[0])
        all_vsync.append(0)
        all_y0.append(0)
        all_canny_in.append(out[4] if len(out) > 4 else 0)

    return (np.array(all_disp, dtype=np.uint16),
            np.array(all_vsync, dtype=np.int8),
            np.array(all_y0, dtype=np.uint8),
            np.array(all_canny_in, dtype=np.uint16))


# ------------------------------- utilities ---------------------------------

def rgb565_to_y(d16):
    """Recover 8-bit Y from RGB565. G channel (6-bit) is most precise."""
    g6 = (d16.astype(np.uint32) >> 5) & 0x3F
    return ((g6 << 2) | (g6 >> 4)).astype(np.uint8)


def compare_cycle_by_cycle(name, py_disp, rtl_disp):
    """Compare two display_data streams cycle-by-cycle and return (ok, max_diff, mismatches)."""
    min_len = min(len(py_disp), len(rtl_disp))
    diff = np.abs(py_disp[:min_len].astype(np.int32) - rtl_disp[:min_len].astype(np.int32))
    max_diff = int(diff.max())
    nz = int(np.count_nonzero(diff))
    print(f"\n{name} cycle-by-cycle diff over {min_len} cycles:")
    print(f"  max_diff   = {max_diff}")
    print(f"  mismatches = {nz}")
    if max_diff == 0:
        print(f"  >>> PASS: {name} Python model matches RTL exactly.")
        return True, 0, 0
    bad = np.where(diff > 0)[0]
    print(f"  First {min(8, len(bad))} divergences:")
    for c in bad[:8]:
        print(f"    cycle {c}: py=0x{py_disp[c]:04x}  rtl=0x{int(rtl_disp[c]):04x}")
    return False, max_diff, nz


def per_image_summary(name, py_disp, py_vsync, rtl_disp, rtl_vsync, image_names, H, W):
    """Print per-image interior max diff (informational, after cycle match)."""
    ROW0, ROW1 = 2, H - 2
    COL0, COL1 = 5, W - 2
    print(f"\n{name} per-image interior (rows [{ROW0}..{ROW1-1}], cols [{COL0}..{COL1-1}]):")
    print(f"  {'image':<14} | {'delay':>5} | {'max_diff':>9} | {'mismatches':>10}")
    print("  " + "-" * 60)
    for i, img_name in enumerate(image_names):
        rtl_loc = rtl_vsync[i]
        best_maxd = None
        best_delay = 0
        best_nz = 0
        for delay in range(0, 12):
            rtl_block = rtl_disp[rtl_loc + delay:rtl_loc + delay + H * W]
            if len(rtl_block) < H * W:
                continue
            rtl_y = rgb565_to_y(rtl_block).reshape(H, W)
            py_loc = py_vsync[i]
            py_block = py_disp[py_loc + delay:py_loc + delay + H * W]
            if len(py_block) < H * W:
                continue
            py_y = rgb565_to_y(py_block).reshape(H, W)
            d_block = np.abs(rtl_y[ROW0:ROW1, COL0:COL1].astype(np.int16)
                             - py_y[ROW0:ROW1, COL0:COL1].astype(np.int16))
            maxd = int(d_block.max())
            nz_block = int(np.count_nonzero(d_block))
            if best_maxd is None or maxd < best_maxd:
                best_maxd = maxd
                best_delay = delay
                best_nz = nz_block
        print(f"  {img_name:<14} | {best_delay:>5} | {best_maxd:>9} | {best_nz:>10}")


# ------------------------------- main --------------------------------------

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    npz_path = os.path.join(here, "rtl_dump.npz")
    if not os.path.exists(npz_path):
        print(f"ERROR: {npz_path} not found. Run sim/run_golden.py first.")
        sys.exit(1)

    d = np.load(npz_path, allow_pickle=True)
    image_names = d['image_names']
    image_data = d['image_data']
    in_vsync = d['in_vsync']
    in_y0 = d['in_y0']
    g_disp = d['g_disp']
    s_disp = d['s_disp']
    m_disp = d['m_disp']
    H, W = int(d['height']), int(d['width'])
    N = image_data.shape[0]

    # ---- sanity: dumped input reconstructs exactly ----
    vsync_locs = np.where(in_vsync == 1)[0]
    if len(vsync_locs) < N:
        print(f"ERROR: expected {N} i_VSYNC pulses, found {len(vsync_locs)}")
        sys.exit(1)
    for i, loc in enumerate(vsync_locs[:N]):
        rtl_in = in_y0[loc + 1:loc + 1 + H * W].reshape(H, W)
        if not np.array_equal(rtl_in, image_data[i]):
            diffs = np.where(rtl_in != image_data[i])
            print(f"ERROR: input image {i} ({image_names[i]}) mismatches "
                  f"image_data, {len(diffs[0])} pixels")
            sys.exit(1)
    print(f"[OK] Dumped {N} input images ({H}x{W}) reconstruct exactly")

    results = {}

    # ---- Gaussian ----
    print("\n" + "=" * 70)
    print("GAUSSIAN FILTER")
    print("=" * 70)
    pipe_g = GaussianPipeline()
    py_g, py_g_vsync, _, _ = run_testbench(pipe_g, image_data, H, W)
    print(f"  Python: {len(py_g)} cycles, VSYNC at {np.where(py_g_vsync==1)[0][:N].tolist()}")
    print(f"  RTL:    {len(g_disp)} cycles, VSYNC at {vsync_locs[:N].tolist()}")
    ok_g, _, _ = compare_cycle_by_cycle("Gaussian", py_g, g_disp)
    py_g_vsync_locs = np.where(py_g_vsync == 1)[0]
    per_image_summary("Gaussian", py_g, py_g_vsync_locs, g_disp, vsync_locs, image_names, H, W)
    results['Gaussian'] = ok_g

    # ---- Sobel ----
    print("\n" + "=" * 70)
    print("SOBEL FILTER")
    print("=" * 70)
    pipe_s = SobelPipeline(thresh_min=50, thresh_max=150)
    py_s, py_s_vsync, _, _ = run_testbench(pipe_s, image_data, H, W)
    print(f"  Python: {len(py_s)} cycles, VSYNC at {np.where(py_s_vsync==1)[0][:N].tolist()}")
    print(f"  RTL:    {len(s_disp)} cycles, VSYNC at {vsync_locs[:N].tolist()}")
    ok_s, _, _ = compare_cycle_by_cycle("Sobel", py_s, s_disp)
    py_s_vsync_locs = np.where(py_s_vsync == 1)[0]
    per_image_summary("Sobel", py_s, py_s_vsync_locs, s_disp, vsync_locs, image_names, H, W)
    results['Sobel'] = ok_s

    # ---- Median ----
    print("\n" + "=" * 70)
    print("MEDIAN FILTER")
    print("=" * 70)
    pipe_m = MedianPipeline()
    py_m, py_m_vsync, _, _ = run_testbench(pipe_m, image_data, H, W)
    print(f"  Python: {len(py_m)} cycles, VSYNC at {np.where(py_m_vsync==1)[0][:N].tolist()}")
    print(f"  RTL:    {len(m_disp)} cycles, VSYNC at {vsync_locs[:N].tolist()}")
    ok_m, _, _ = compare_cycle_by_cycle("Median", py_m, m_disp)
    py_m_vsync_locs = np.where(py_m_vsync == 1)[0]
    per_image_summary("Median", py_m, py_m_vsync_locs, m_disp, vsync_locs, image_names, H, W)
    results['Median'] = ok_m

    # ---- final report ----
    print("\n" + "=" * 70)
    print("FINAL REPORT")
    print("=" * 70)
    all_ok = True
    for name, ok in results.items():
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {name}")
        if not ok:
            all_ok = False
    print("=" * 70)
    print(f"\nOverall: {'PASS' if all_ok else 'FAIL'}")
    sys.exit(0 if all_ok else 1)


if __name__ == '__main__':
    main()
