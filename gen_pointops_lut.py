"""Generate the LOG module's ROM content (sim/ip/log_lut.hex).

The RTL (LOG.v) instantiates blk_mem_gen_0 as a 256x8 ROM addressed by the
input grey value; the README specifies the transformation

    s = c * log(1 + r)

with c chosen so that s spans the full output range. This script generates
the table with c = 255 / log(256), i.e.

    lut[r] = round(255 * ln(1 + r) / ln(256))

so lut[0] = 0 and lut[255] = 255. verify_pointops.py recomputes the same
formula independently (Fact-A style, cf. verify_rgb2yuv_independent.py) to
check the ROM dump, so the verification is not a self-fulfilling copy.
"""
import math
import os


def log_lut():
    c = 255.0 / math.log(256.0)
    return [int(round(c * math.log(1 + r))) for r in range(256)]


def main():
    out = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "ip", "log_lut.hex")
    lut = log_lut()
    with open(out, "w") as f:
        for v in lut:
            f.write(f"{v:02x}\n")
    print(f"Wrote {out} ({len(lut)} entries, lut[0]={lut[0]}, lut[255]={lut[255]})")


if __name__ == "__main__":
    main()
