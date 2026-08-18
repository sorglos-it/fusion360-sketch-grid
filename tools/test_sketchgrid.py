# -*- coding: utf-8 -*-
"""Test the grid maths and the language files without running Fusion."""
import os
import re
import sys
import types
import xml.etree.ElementTree as ElementTree

# --- adsk stubs so the add-in can be imported outside of Fusion -------------
adsk = types.ModuleType('adsk')
core_stub = types.ModuleType('adsk.core')
fusion_stub = types.ModuleType('adsk.fusion')
for _name in ('CommandEventHandler', 'ValidateInputsEventHandler',
              'InputChangedEventHandler', 'CommandCreatedEventHandler'):
    setattr(core_stub, _name, type(_name, (object,), {}))
adsk.core = core_stub
adsk.fusion = fusion_stub
sys.modules['adsk'] = adsk
sys.modules['adsk.core'] = core_stub
sys.modules['adsk.fusion'] = fusion_stub

_HERE = os.path.dirname(os.path.abspath(__file__))
ADDIN = os.environ.get('SKETCHGRID_ADDIN_DIR') or os.path.join(
    os.path.dirname(_HERE), 'SketchGrid')
sys.path.insert(0, ADDIN)
import SketchGrid as sg  # noqa: E402

MM = 0.1  # 1 mm expressed in cm, Fusion's internal unit
failures = []


def check(condition, message):
    if condition:
        print('  ok   ', message)
    else:
        print('  FAIL ', message)
        failures.append(message)


def layout(mode=sg.MODE_COUNT, width=10 * MM, height=5 * MM, gap_x=2 * MM,
           gap_y=2 * MM, columns=8, rows=4, area_width=100 * MM,
           area_height=40 * MM, anchor=0, offset_x=0.0, offset_y=0.0):
    return sg.grid_layout(mode, width, height, gap_x, gap_y, columns, rows,
                          area_width, area_height, anchor, offset_x, offset_y)


def expect_error(key, label, **kwargs):
    try:
        layout(**kwargs)
        check(False, '%s -> should have raised "%s"' % (label, key))
    except sg.core.AddInError as err:
        check(err.key == key, '%s -> %s  "%s"' % (label, err.key, err))


print("1) The example from the brief: 10 x 5, gap 2, 8 columns, 4 rows")
columns, rows, pitch_x, pitch_y, total_w, total_h, off_x, off_y = layout()
check((columns, rows) == (8, 4), 'grid is 8 x 4 (%d x %d)' % (columns, rows))
check(abs(pitch_x - 12 * MM) < 1e-12 and abs(pitch_y - 7 * MM) < 1e-12,
      'pitch is 12 x 7 mm')
check(abs(total_w - 94 * MM) < 1e-12,
      'total width 8*10 + 7*2 = 94 mm (%.2f)' % (total_w * 10))
check(abs(total_h - 26 * MM) < 1e-12,
      'total height 4*5 + 3*2 = 26 mm (%.2f)' % (total_h * 10))
check(len(sg.cell_centres(layout())) == 32, '32 cells produced')

print('2) Every anchor entry has the factors its name promises')


def factors_from_name(key):
    """Derive the expected factors from the key, so a mismatch between the
    label and the maths cannot slip through unnoticed."""
    name = key.split('.', 1)[1]
    if name == 'center':
        return (0.5, 0.5)
    factor_x = factor_y = 0.5
    for part in name.split('_'):
        if part == 'left':
            factor_x = 0.0
        elif part == 'right':
            factor_x = 1.0
        elif part == 'bottom':
            factor_y = 0.0
        elif part == 'top':
            factor_y = 1.0
    return (factor_x, factor_y)


for index, key in enumerate(sg.ANCHOR_KEYS):
    check(sg.ANCHOR_FACTORS[index] == factors_from_name(key),
          '%s -> %s' % (key, sg.ANCHOR_FACTORS[index]))

# And the same again from the other end: where does the point actually land in
# the bounding box the grid occupies?
for index, key in enumerate(sg.ANCHOR_KEYS):
    result = layout(anchor=index)
    left, bottom = result[6], result[7]
    right, top = left + result[4], bottom + result[5]
    name = key.split('.', 1)[1]
    on_left = abs(left) < 1e-12
    on_right = abs(right) < 1e-12
    on_bottom = abs(bottom) < 1e-12
    on_top = abs(top) < 1e-12
    middle_x = abs(left + right) < 1e-12
    middle_y = abs(bottom + top) < 1e-12
    if 'left' in name:
        ok_x = on_left
    elif 'right' in name:
        ok_x = on_right
    else:
        ok_x = middle_x
    if 'bottom' in name:
        ok_y = on_bottom
    elif 'top' in name:
        ok_y = on_top
    else:
        ok_y = middle_y
    check(ok_x and ok_y,
          '%s: point at x %.0f..%.0f, y %.0f..%.0f mm'
          % (key, left * 10, right * 10, bottom * 10, top * 10))

print('2b) Anchor decides where the picked point sits')
for index, key in enumerate(sg.ANCHOR_KEYS):
    fx, fy = sg.ANCHOR_FACTORS[index]
    result = layout(anchor=index)
    check(abs(result[6] + fx * result[4]) < 1e-12
          and abs(result[7] + fy * result[5]) < 1e-12,
          '%s -> offset (%.1f, %.1f) mm' % (key, result[6] * 10, result[7] * 10))

centre = layout(anchor=0)
check(abs(centre[6] + 47 * MM) < 1e-12 and abs(centre[7] + 13 * MM) < 1e-12,
      'centred: grid starts 47 mm left and 13 mm below the point')
corner = layout(anchor=1)
check(abs(corner[6]) < 1e-12 and abs(corner[7]) < 1e-12,
      'bottom left: grid starts exactly at the point')

print('3) Cell positions')
cells = sg.cell_centres(layout(anchor=1))
check(abs(cells[0][0]) < 1e-12 and abs(cells[0][1]) < 1e-12,
      'first cell corner at the point')
check(abs(cells[1][0] - 12 * MM) < 1e-12,
      'second cell one pitch to the right (%.1f mm)' % (cells[1][0] * 10))
check(abs(cells[8][1] - 7 * MM) < 1e-12,
      'ninth cell is the start of row two (%.1f mm up)' % (cells[8][1] * 10))
check(abs(cells[-1][0] - 84 * MM) < 1e-12 and abs(cells[-1][1] - 21 * MM) < 1e-12,
      'last cell at 84 / 21 mm')
xs = sorted(set(round(c[0], 9) for c in cells))
ys = sorted(set(round(c[1], 9) for c in cells))
check(len(xs) == 8 and len(ys) == 4, '8 distinct columns, 4 distinct rows')

print('4) Fill mode counts what actually fits')
result = layout(mode=sg.MODE_FILL, area_width=100 * MM, area_height=40 * MM)
# 8 columns: 8*10 + 7*2 = 94 <= 100, a ninth would need 106.
# 6 rows: 6*5 + 5*2 = 40, exactly the height on offer.
check((result[0], result[1]) == (8, 6),
      '100 x 40 mm holds 8 x 6 (%d x %d)' % (result[0], result[1]))
check(result[4] <= 100 * MM + 1e-12 and result[5] <= 40 * MM + 1e-12,
      'the grid stays inside the area (%.1f x %.1f mm)'
      % (result[4] * 10, result[5] * 10))
check(layout(mode=sg.MODE_FILL, area_width=105 * MM, area_height=40 * MM)[0] == 8,
      'a ninth column needs 106 mm, so 105 still gives 8')
exact = layout(mode=sg.MODE_FILL, area_width=94 * MM, area_height=26 * MM)
check((exact[0], exact[1]) == (8, 4), 'an area of exactly 94 x 26 mm holds 8 x 4')
check(layout(mode=sg.MODE_FILL, area_width=93.9 * MM, area_height=26 * MM)[0] == 7,
      'one tenth of a millimetre short drops it to 7 columns')
check(layout(mode=sg.MODE_FILL, area_width=10 * MM, area_height=5 * MM)[0] == 1,
      'an area the size of one shape holds exactly one')
check(layout(mode=sg.MODE_FILL, gap_x=0.0, gap_y=0.0,
             area_width=100 * MM, area_height=50 * MM)[0] == 10,
      'without a gap, 100 mm holds 10 columns of 10 mm')

print('5) Failures report the right key')
expect_error('err.width', 'length of 0', width=0.0)
expect_error('err.height', 'depth of 0', height=0.0)
expect_error('err.gap_negative', 'negative gap', gap_x=-1 * MM)
expect_error('err.columns', 'no columns', columns=0)
expect_error('err.rows', 'no rows', rows=0)
expect_error('err.area_positive', 'area of 0',
             mode=sg.MODE_FILL, area_width=0.0)
expect_error('err.area_too_small', 'area smaller than one shape',
             mode=sg.MODE_FILL, area_width=9 * MM, area_height=40 * MM)
expect_error('err.too_many', 'more than the cap',
             columns=100, rows=100)
check(layout(columns=sg.MAX_SHAPES, rows=1)[0] == sg.MAX_SHAPES,
      'exactly %d shapes is still allowed' % sg.MAX_SHAPES)

print('6) Language files')
lang_dir = os.path.join(ADDIN, 'lang')
reference = {}
for node in ElementTree.parse(os.path.join(lang_dir, 'en.xml')).getroot().findall('string'):
    reference[node.get('key')] = node.text or ''
check(len(reference) > 40, 'en.xml holds %d keys' % len(reference))

for code in sg.core.SUPPORTED_LANGUAGES:
    path = os.path.join(lang_dir, '%s.xml' % code)
    check(os.path.isfile(path), '%s.xml exists' % code)
    if not os.path.isfile(path):
        continue
    root = ElementTree.parse(path).getroot()
    check(root.get('language') == code, '%s.xml declares language="%s"' % (code, code))
    values = {}
    for node in root.findall('string'):
        values[node.get('key')] = node.text or ''
    missing = sorted(set(reference) - set(values))
    unknown = sorted(set(values) - set(reference))
    check(not missing, '%s.xml complete%s'
          % (code, '' if not missing else ' - missing: %s' % missing))
    check(not unknown, '%s.xml has no unknown keys%s'
          % (code, '' if not unknown else ' - unknown: %s' % unknown))
    mismatched = [key for key in reference
                  if set(re.findall(r'\{\d+\}', reference[key]))
                  != set(re.findall(r'\{\d+\}', values.get(key, '')))]
    check(not mismatched, '%s.xml keeps every placeholder%s'
          % (code, '' if not mismatched else ' - differing: %s' % mismatched))
    check(all(value.strip() for value in values.values()),
          '%s.xml has no empty texts' % code)

print('7) Offset from the picked point')
base = layout(anchor=1)                       # bottom left, grid starts at the point
moved = layout(anchor=1, offset_x=2 * MM, offset_y=2 * MM)
check(abs(moved[6] - base[6] - 2 * MM) < 1e-12
      and abs(moved[7] - base[7] - 2 * MM) < 1e-12,
      'the whole grid moves by the offset (%.1f / %.1f mm)'
      % ((moved[6] - base[6]) * 10, (moved[7] - base[7]) * 10))
check(abs(moved[6] - 2 * MM) < 1e-12 and abs(moved[7] - 2 * MM) < 1e-12,
      'the case from the brief: point at 0/0, grid starts at 2/2')
check(moved[:6] == base[:6],
      'count, pitch and overall size are untouched by the offset')

negative = layout(anchor=1, offset_x=-3 * MM, offset_y=-1.5 * MM)
check(abs(negative[6] + 3 * MM) < 1e-12 and abs(negative[7] + 1.5 * MM) < 1e-12,
      'negative values go the other way (%.1f / %.1f mm)'
      % (negative[6] * 10, negative[7] * 10))

for anchor in range(len(sg.ANCHOR_KEYS)):
    plain = layout(anchor=anchor)
    shifted = layout(anchor=anchor, offset_x=7 * MM, offset_y=-4 * MM)
    check(abs(shifted[6] - plain[6] - 7 * MM) < 1e-12
          and abs(shifted[7] - plain[7] + 4 * MM) < 1e-12,
          '%s: the offset adds to the anchor rather than replacing it'
          % sg.ANCHOR_KEYS[anchor])

cells_plain = sg.cell_centres(layout(anchor=1))
cells_moved = sg.cell_centres(layout(anchor=1, offset_x=2 * MM, offset_y=2 * MM))
check(all(abs(b[0] - a[0] - 2 * MM) < 1e-12 and abs(b[1] - a[1] - 2 * MM) < 1e-12
          for a, b in zip(cells_plain, cells_moved)),
      'every one of the %d cells moves by the same amount' % len(cells_plain))

check(layout(mode=sg.MODE_FILL, offset_x=50 * MM)[0]
      == layout(mode=sg.MODE_FILL)[0],
      'in fill mode the offset does not change how many fit')

print('8) Every drop-down entry has a text of its own')
for key in ('in.offset_x', 'in.offset_y', 'offset.tooltip'):
    check(key in reference, '%s present' % key)
for label, keys in (('mode', sg.MODE_KEYS), ('shape', sg.SHAPE_KEYS),
                    ('anchor', sg.ANCHOR_KEYS)):
    missing = [key for key in keys if key not in reference]
    check(not missing, '%s: all %d entries present%s'
          % (label, len(keys), '' if not missing else ' - missing %s' % missing))
check(len(sg.ANCHOR_KEYS) == len(sg.ANCHOR_FACTORS),
      'every anchor entry has a factor pair')

print('9) Text catalogue')
for code in sg.core.SUPPORTED_LANGUAGES:
    sg.S.load(code)
    check(sg.S.code == code and sg.T('cmd.name') != 'cmd.name',
          '%s: cmd.name = "%s"' % (code, sg.T('cmd.name')))
sg.S.load('de')
line = sg.T('info.result', '8', '4', '32', '94.00', '26.00')
check('8' in line and '32' in line and '94.00' in line,
      'the info line fills every placeholder: "%s"' % line)
check(sg.S.load('klingon') == 'en', 'an unknown language falls back to English')
sg.S.load('it')
error = None
try:
    layout(width=0.0)
except sg.core.AddInError as exc:
    error = exc
check(error is not None and 'lunghezza' in str(error),
      'errors follow the language: "%s"' % error)
sg.S.load('en')

print()
if failures:
    print('%d FAILURES' % len(failures))
    sys.exit(1)
print('all tests passed')
