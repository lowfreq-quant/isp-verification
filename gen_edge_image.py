"""Generate a 640x480 RGB565 EDGE test image for ISP_TOP_tb $readmemh.

Output: sim/test_image.hex  (307200 lines, one 16-bit hex value per line)

Pattern: black/white checkerboard + fine stripes, so the default
sobel_en/canny_en ISP_TOP path has plenty of edges to detect (the smooth
gradient from gen_test_image.py yields an almost-all-zero canny display,
which is expected but not useful for end-to-end display verification).

Usage:
    python gen_edge_image.py            # overwrite sim/test_image.hex
    python gen_edge_image.py --restore  # restore the saved gradient image
"""
import os
import shutil

WIDTH = 640
HEIGHT = 480
TOTAL = WIDTH * HEIGHT  # 307200

BLACK = 0x0000
WHITE = 0xFFFF
GREY = 0x7BEF  # ~128 grey

def checker_pixel(row, col):
    """Large 4x3 checkerboard (cell 160x160) with a fine stripe overlay."""
    # base: 4 cols x 3 rows checkerboard
    cidx = col // 160
    ridx = row // 160
    base = WHITE if (cidx + ridx) % 2 == 0 else BLACK
    # fine stripes inside each cell (for dense edges)
    if (row % 32) < 8 or (col % 32) < 8:
        return GREY
    return base

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "test_image.hex")
    saved_path = os.path.join(here, "test_image.gradient.hex")

    if not os.path.exists(saved_path) and os.path.exists(out_path):
        shutil.copy(out_path, saved_path)
        print(f"[OK] Backed up current image to {saved_path}")

    with open(out_path, "w") as f:
        for row in range(HEIGHT):
            for col in range(WIDTH):
                f.write(f"{checker_pixel(row, col):04x}\n")

    size = os.path.getsize(out_path)
    print(f"[OK] Generated edge image {out_path} ({TOTAL} pixels, {size} bytes)")

if __name__ == "__main__":
    import sys
    if "--restore" in sys.argv:
        here = os.path.dirname(os.path.abspath(__file__))
        saved = os.path.join(here, "test_image.gradient.hex")
        out = os.path.join(here, "test_image.hex")
        if os.path.exists(saved):
            shutil.copy(saved, out)
            print(f"[OK] Restored gradient image from {saved}")
        else:
            print("[ERR] No saved gradient image found")
    else:
        main()