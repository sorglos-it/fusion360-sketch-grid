# -*- coding: utf-8 -*-
"""Generate the toolbar icon for SketchGrid (standard library only).

    python tools/make_icon.py

A 3x3 grid of rounded-off cells with the anchor point marked in the middle,
which is exactly what the command does.
"""
import os
import zlib
import struct

_HERE = os.path.dirname(os.path.abspath(__file__))
ADDIN = os.environ.get('SKETCHGRID_ADDIN_DIR') or os.path.join(
    os.path.dirname(_HERE), 'SketchGrid')
OUT = os.path.join(ADDIN, 'resources', 'SketchGrid')

DARK = (0x2E, 0x3A, 0x45)
ACCENT = (0xE8, 0x8A, 0x1E)
SS = 4


def cell(col, row):
    """One grid cell as a polygon, in normalised coordinates (0..1, y up)."""
    pitch = 0.30
    size = 0.22
    x0 = 0.08 + col * pitch
    y0 = 0.08 + row * pitch
    return [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size)]


def cross(cx, cy, arm, thickness):
    """The anchor marker, drawn as two overlapping bars."""
    return [
        [(cx - arm, cy - thickness), (cx + arm, cy - thickness),
         (cx + arm, cy + thickness), (cx - arm, cy + thickness)],
        [(cx - thickness, cy - arm), (cx + thickness, cy - arm),
         (cx + thickness, cy + arm), (cx - thickness, cy + arm)],
    ]


SHAPES = []
for _row in range(3):
    for _col in range(3):
        if _row == 1 and _col == 1:
            continue                      # the middle cell holds the marker
        SHAPES.append((DARK, cell(_col, _row)))
for _bar in cross(0.50, 0.50, 0.13, 0.035):
    SHAPES.append((ACCENT, _bar))


def point_in_polygon(x, y, polygon):
    inside = False
    count = len(polygon)
    j = count - 1
    for i in range(count):
        xi, yi = polygon[i]
        xj, yj = polygon[j]
        if (yi > y) != (yj > y):
            crossing = xi + (y - yi) * (xj - xi) / (yj - yi)
            if x < crossing:
                inside = not inside
        j = i
    return inside


def render(size):
    buffer = bytearray(size * size * 4)
    for py in range(size):
        for px in range(size):
            red = green = blue = alpha = 0.0
            for colour, polygon in SHAPES:
                hits = 0
                for sy in range(SS):
                    for sx in range(SS):
                        gx = (px + (sx + 0.5) / SS) / size
                        gy = 1.0 - (py + (sy + 0.5) / SS) / size
                        if point_in_polygon(gx, gy, polygon):
                            hits += 1
                if not hits:
                    continue
                coverage = (hits / float(SS * SS)) * (1.0 - alpha)
                red += colour[0] * coverage
                green += colour[1] * coverage
                blue += colour[2] * coverage
                alpha += coverage

            if alpha <= 0.0:
                continue
            i = (py * size + px) * 4
            buffer[i] = int(round(red / alpha))
            buffer[i + 1] = int(round(green / alpha))
            buffer[i + 2] = int(round(blue / alpha))
            buffer[i + 3] = int(round(alpha * 255))
    return bytes(buffer)


def write_png(path, size, rgba):
    raw = b''.join(b'\x00' + rgba[y * size * 4:(y + 1) * size * 4]
                   for y in range(size))

    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data +
                struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    png = b'\x89PNG\r\n\x1a\n'
    png += chunk(b'IHDR', struct.pack('>IIBBBBB', size, size, 8, 6, 0, 0, 0))
    png += chunk(b'IDAT', zlib.compress(raw, 9))
    png += chunk(b'IEND', b'')
    with open(path, 'wb') as handle:
        handle.write(png)


def main():
    os.makedirs(OUT, exist_ok=True)
    for size in (16, 32, 64):
        path = os.path.join(OUT, '%dx%d.png' % (size, size))
        write_png(path, size, render(size))
        print('written:', path)


if __name__ == '__main__':
    main()
