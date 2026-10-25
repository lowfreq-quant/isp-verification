"""Generate a 640x480 RGB565 gradient test image for ISP_TOP_tb $readmemh.

Output: sim/test_image.hex  (307200 lines, one 16-bit hex value per line)

Pattern: horizontal R gradient + vertical G gradient + diagonal B gradient
         so that different color channels are visually distinguishable.
"""
import os

WIDTH = 640
HEIGHT = 480
TOTAL = WIDTH * HEIGHT  # 307200

def rgb565(r8, g8, b8):
    """Pack 8-bit RGB into RGB565."""
    return ((r8 >> 3) << 11) | ((g8 >> 2) << 5) | (b8 >> 3)

def main():
    here = os.path.dirname(os.path.abspath(__file__))
    out_path = os.path.join(here, "test_image.hex")

    with open(out_path, "w") as f:
        for row in range(HEIGHT):
            for col in range(WIDTH):
                r = (col * 255) // (WIDTH - 1)       # 0..255 left->right
                g = (row * 255) // (HEIGHT - 1)      # 0..255 top->bottom
                b = ((col + row) * 255) // (WIDTH + HEIGHT - 2)  # diagonal
                pixel = rgb565(r, g, b)
                f.write(f"{pixel:04x}\n")

    size = os.path.getsize(out_path)
    print(f"[OK] Generated {out_path} ({TOTAL} pixels, {size} bytes)")

if __name__ == "__main__":
    main()
