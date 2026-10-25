"""Cocotb test: probe matrix + FIFO dout + gaussian pipeline at step_v transition."""
import numpy as np
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

W, H = 640, 10

@cocotb.test()
async def probe_matrix(dut):
    Clock(dut.clk, 10, unit="ns").start()
    dut.rst_n.value = 0
    dut.i_HSYNC.value = 0; dut.i_VSYNC.value = 0
    dut.i_BLANK.value = 0; dut.i_Y0.value = 0
    dut.thresh_min.value = 50; dut.thresh_max.value = 150
    await ClockCycles(dut.clk, 6)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 4)
    for _ in range(4):
        await RisingEdge(dut.clk)

    img = np.zeros((H, W), dtype=np.uint8)
    img[:, W//2:] = 220

    dut.i_BLANK.value = 1
    dut.i_VSYNC.value = 1
    await RisingEdge(dut.clk)
    dut.i_VSYNC.value = 0

    MG = dut.u_gaussian.U_MATRIX_GENERATOR_0
    cyc = 0
    results = []
    
    for row in range(H):
        for col in range(W):
            dut.i_Y0.value = int(img[row, col])
            if col == W - 1:
                dut.i_HSYNC.value = 1
            await RisingEdge(dut.clk)
            if col == W - 1:
                dut.i_HSYNC.value = 0
            cyc += 1
            
            if row == 5 and 318 <= col <= 326:
                m = [int(getattr(MG, f'o_matrix{i}{j}').value) for i in range(1,4) for j in range(1,4)]
                cc = int(MG.col_cnt.value)
                lc = int(MG.line_cnt.value)
                iyr = int(MG.i_Y0_r.value)
                iyr2 = int(MG.i_Y0_r2.value)
                # Probe FIFO outputs
                try:
                    d1 = int(MG.fifo_1.dout.value)
                    d2 = int(MG.fifo_2.dout.value)
                except:
                    d1 = -1; d2 = -1
                # Probe gaussian pipeline
                gs1 = int(dut.u_gaussian.gs_1.value)
                gs2 = int(dut.u_gaussian.gs_2.value)
                gs3 = int(dut.u_gaussian.gs_3.value)
                gss = int(dut.u_gaussian.gs_sum.value)
                gsd = int(dut.u_gaussian.gs_data.value)
                gdisp = int(dut.g_display.value)
                g6 = (gdisp >> 5) & 0x3F
                y_rec = (g6 << 2) | (g6 >> 4)
                results.append((col, cyc, cc, lc, m, iyr, iyr2, d1, d2, gs1, gs2, gs3, gss, gsd, gdisp, y_rec))

    print("\nFull pipeline probe at row 5:")
    hdr = f"{'col':>3} {'cc':>3} {'lc':>2} | {'m11':>3} {'m12':>3} {'m13':>3} {'m21':>3} {'m22':>3} {'m23':>3} {'m31':>3} {'m32':>3} {'m33':>3} | {'iYr':>3} {'iYr2':>3} {'d1':>3} {'d2':>3} | {'gs1':>4} {'gs2':>4} {'gs3':>4} {'gss':>4} {'gsd':>3} | {'disp':>5} {'Y':>3}"
    print(hdr)
    print("-"*len(hdr))
    for r in results:
        col,cyc,cc,lc,m,iyr,iyr2,d1,d2,gs1,gs2,gs3,gss,gsd,gd,y = r
        print(f"{col:>3} {cc:>3} {lc:>2} | {m[0]:>3} {m[1]:>3} {m[2]:>3} {m[3]:>3} {m[4]:>3} {m[5]:>3} {m[6]:>3} {m[7]:>3} {m[8]:>3} | {iyr:>3} {iyr2:>3} {d1:>3} {d2:>3} | {gs1:>4} {gs2:>4} {gs3:>4} {gss:>4} {gsd:>3} | {gd:>5} {y:>3}")
