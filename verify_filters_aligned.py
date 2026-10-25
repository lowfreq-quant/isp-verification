"""
verify_filters_aligned.py
-------------------------
Authoritative filter verification with the EMPIRICALLY-correct pipeline delay.

Background: verify_golden.py uses a hardcoded delay=5 to slice RTL output, which
misaligns RTL vs golden by 2 cycles and causes spurious FAIL on step/random
images. diagnose_step_alignment.py proved the true delay is 7 (the RTL step
response lines up exactly with golden at delay=7).

This script applies delay=7 to ALL 6 test images and all 3 filters and reports
per-image pixel diffs. RGB565 display_data is compared directly (no lossy Y
recovery). Sobel is binary.

Golden models are the SAME standard operators as verify_golden.py
(Gaussian [1 2 1;2 4 2;1 2 1]/16, median, Sobel sqrg>120) -- these are textbook
definitions, not copied from RTL coefficients, so the check is not circular.
"""
import os
import numpy as np

DUMP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rtl_dump.npz")
DELAY = 7
ROW_BORDER = 2          # matrix_generator line_cnt 0/1 is a 1D slide, skip
COL_BORDER_L = 1        # col 0..0 boundary; one warm-up col
COL_BORDER_R = 1


def gaussian_y(img):
    p = np.pad(img.astype(np.int32), 1, mode='edge')
    return (p[:-2,:-2]+2*p[:-2,1:-1]+p[:-2,2:]
            +2*p[1:-1,:-2]+4*p[1:-1,1:-1]+2*p[1:-1,2:]
            +p[2:,:-2]+2*p[2:,1:-1]+p[2:,2:])//16

def median_y(img):
    p = np.pad(img, 1, mode='edge')
    w = np.stack([p[:-2,:-2],p[:-2,1:-1],p[:-2,2:],
                  p[1:-1,:-2],p[1:-1,1:-1],p[1:-1,2:],
                  p[2:,:-2],p[2:,1:-1],p[2:,2:]])
    return np.median(w, axis=0).astype(np.uint8)

def sobel_bin(img):
    p = np.pad(img.astype(np.int32), 1, mode='edge')
    gx1=p[:-2,:-2]+2*p[:-2,1:-1]+p[:-2,2:]; gx3=p[2:,:-2]+2*p[2:,1:-1]+p[2:,2:]
    gy1=p[:-2,:-2]+2*p[1:-1,:-2]+p[2:,:-2]; gy3=p[:-2,2:]+2*p[1:-1,2:]+p[2:,2:]
    gx=np.abs(gx1-gx3); gy=np.abs(gy1-gy3)
    return (gx*gx+gy*gy>120).astype(np.uint8)

def y_to_565(y):
    y = y.astype(np.uint16)
    return ((y>>3)<<11) | ((y>>2)<<5) | (y>>3)

def extract(payload, vsync, n, h, w, delay):
    imgs=[]
    for loc in vsync[:n]:
        s = loc + delay
        block = payload[s:s+h*(w+1)].reshape(h, w+1)
        imgs.append(block[:, :w])
    return np.stack(imgs)

def interior(a):
    r0, r1 = ROW_BORDER, max(ROW_BORDER, a.shape[-2]-ROW_BORDER)
    return a[..., r0:r1, COL_BORDER_L:a.shape[-1]-COL_BORDER_R]


def main():
    d = np.load(DUMP, allow_pickle=True)
    vsync = np.where(d['in_vsync']==1)[0]
    image_data = d['image_data']
    names = list(d['image_names'])
    N, H, W = len(names), int(d['height']), int(d['width'])

    rtl_g = extract(d['g_disp'], vsync, N, H, W, DELAY)
    rtl_s = extract(d['s_disp'], vsync, N, H, W, DELAY)
    rtl_m = extract(d['m_disp'], vsync, N, H, W, DELAY)

    gold_g = np.stack([y_to_565(gaussian_y(im)) for im in image_data])
    gold_m = np.stack([y_to_565(median_y(im))   for im in image_data])
    gold_s = np.stack([np.where(sobel_bin(im)==1, 0xFFFF, 0).astype(np.uint16)
                       for im in image_data])

    print(f"=== Filter verification, pipeline delay = {DELAY}, 6 images {H}x{W} ===")
    print(f"{'image':<14}| {'Gauss: 565 mismatch / interior':<32}| "
          f"{'Median: 565 mismatch':<26}| {'Sobel: bin mismatch'}")
    print("-"*100)
    overall = True
    for i, name in enumerate(names):
        ig = interior(np.abs(rtl_g[i].astype(int)-gold_g[i].astype(int)))
        im_ = interior(np.abs(rtl_m[i].astype(int)-gold_m[i].astype(int)))
        is_ = interior(np.abs(rtl_s[i].astype(int)-gold_s[i].astype(int)))
        ng = int((ig!=0).sum()); nm = int((im_!=0).sum()); ns = int((is_!=0).sum())
        igsize = ig.size
        ok_g = ng==0; ok_m = nm==0; ok_s = ns==0
        if not (ok_g and ok_m and ok_s): overall = False
        print(f"{str(name):<14}| gauss mism={ng:5d}/{igsize:<6d} {'OK' if ok_g else 'FAIL':<8}| "
              f"median mism={nm:5d}/{igsize:<6d} {'OK' if ok_m else 'FAIL':<8}| "
              f"sobel mism={ns:5d} {'OK' if ok_s else 'FAIL'}")
    print("-"*100)
    print(f"OVERALL (delay={DELAY}): {'PASS' if overall else 'FAIL'}")
    print("Note: golden = textbook operators (Gaussian [1 2 1;2 4 2;1 2 1]/16,")
    print("median of 9, Sobel sqrg>120). NOT copied from RTL coefficients.")
    print("Compare: verify_golden.py with delay=5 reports FAIL on step/random")
    print("due to a 2-cycle misalignment; this uses the empirically-found delay=7.")
    sys = __import__('sys')
    sys.exit(0 if overall else 1)


if __name__ == "__main__":
    main()
