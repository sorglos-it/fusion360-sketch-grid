# -*- coding: utf-8 -*-
"""
SketchGrid - Fusion 360 add-in entry point.

Pick a sketch point, get a grid of shapes around it. Either a fixed number of
columns and rows, or as many as fit into an area you give it.

Scaffolded from fusion360-addin-template.
"""

import os
import sys
import math
import importlib

import adsk.core
import adsk.fusion

# --- module loading ---------------------------------------------------------
# Fusion caches imported modules, so an edited helper would keep serving its
# old version until Fusion restarts. Dropping it from sys.modules before the
# import makes "stop, run" pick up changes.
_CORE_MODULE = 'sketchgrid_core'

_DIR = os.path.dirname(os.path.abspath(__file__))
if _DIR not in sys.path:
    sys.path.insert(0, _DIR)
if _CORE_MODULE in sys.modules:
    del sys.modules[_CORE_MODULE]
core = importlib.import_module(_CORE_MODULE)


# ============================================================== CONFIGURE ====

CMD_ID = 'thwSketchGridCmd'
WORKSPACE_ID = 'FusionSolidEnvironment'
PANEL_IDS = ('SketchCreatePanel', 'SolidCreatePanel')

IN_POINT = 'sgPoint'
IN_MODE = 'sgMode'
IN_SHAPE = 'sgShape'
IN_SIDES = 'sgSides'
IN_REGULAR = 'sgRegular'
IN_CORNER = 'sgCorner'
IN_CORNER_SIZE = 'sgCornerSize'
IN_WIDTH = 'sgWidth'
IN_HEIGHT = 'sgHeight'
IN_GAP_X = 'sgGapX'
IN_GAP_Y = 'sgGapY'
IN_COLUMNS = 'sgColumns'
IN_ROWS = 'sgRows'
IN_AREA_WIDTH = 'sgAreaWidth'
IN_AREA_HEIGHT = 'sgAreaHeight'
IN_ANCHOR = 'sgAnchor'
IN_OFFSET_X = 'sgOffsetX'
IN_OFFSET_Y = 'sgOffsetY'
IN_INFO = 'sgInfo'

RESOURCE_FOLDER = os.path.join(_DIR, 'resources', 'SketchGrid')
LANG_DIR = os.path.join(_DIR, 'lang')

# How the count is arrived at. The stored value is the index in the drop-down,
# so it does not move when the interface language changes.
MODE_COUNT = 0
MODE_FILL = 1
MODE_KEYS = ('mode.count', 'mode.fill')

SHAPE_RECTANGLE = 0
SHAPE_ELLIPSE = 1
SHAPE_SLOT = 2
SHAPE_POLYGON = 3
SHAPE_KEYS = ('shape.rectangle', 'shape.ellipse', 'shape.slot', 'shape.polygon')

# What becomes of the four 90 degree corners of a rectangle. As with the mode
# and the shape, the stored value is the index in the drop-down.
CORNER_SHARP = 0
CORNER_ROUND = 1
CORNER_CHAMFER = 2
CORNER_KEYS = ('corner.sharp', 'corner.round', 'corner.chamfer')

# Where the picked point sits inside the grid, as a fraction of the bounding
# box: (0, 0) is the lower left corner, (0.5, 0.5) the middle.
ANCHOR_KEYS = ('anchor.center',
               'anchor.bottom_left', 'anchor.bottom_right',
               'anchor.top_left', 'anchor.top_right',
               'anchor.bottom_center', 'anchor.top_center',
               'anchor.left_center', 'anchor.right_center')
ANCHOR_FACTORS = ((0.5, 0.5),
                  (0.0, 0.0), (1.0, 0.0),
                  (0.0, 1.0), (1.0, 1.0),
                  (0.5, 0.0), (0.5, 1.0),
                  (0.0, 0.5), (1.0, 0.5))

MIN_SIDES = 3
MAX_SIDES = 24
# A runaway count in fill mode locks Fusion up for minutes. Refuse instead.
MAX_SHAPES = 2000
EPS = 1e-9

# Last used values, kept for the duration of the Fusion session.
# Lengths are in cm - Fusion's internal unit - regardless of the display unit.
_last = {
    IN_MODE: MODE_COUNT,
    IN_SHAPE: SHAPE_RECTANGLE,
    IN_SIDES: 6,
    IN_REGULAR: False,
    IN_CORNER: CORNER_SHARP,
    IN_CORNER_SIZE: 0.1,    # 1 mm
    IN_WIDTH: 1.0,          # 10 mm
    IN_HEIGHT: 0.5,         # 5 mm
    IN_GAP_X: 0.2,          # 2 mm
    IN_GAP_Y: 0.2,          # 2 mm
    IN_COLUMNS: 8,
    IN_ROWS: 4,
    IN_AREA_WIDTH: 10.0,    # 100 mm
    IN_AREA_HEIGHT: 4.0,    # 40 mm
    IN_ANCHOR: 0,           # centre
    IN_OFFSET_X: 0.0,
    IN_OFFSET_Y: 0.0,
}

# =============================================================================

S = core.Strings(LANG_DIR)
S.load(core.FALLBACK_LANGUAGE)
_handlers = core.HandlerRegistry()
_control = None
_updating = False       # re-entrancy guard for inputChanged


def T(key, *args):
    return S.get(key, *args)


def fail(key, *args):
    raise core.AddInError(S, key, *args)


def mm(value):
    """Internal centimetres to millimetres, for messages and the info line."""
    return value * 10.0


# ============================================================ YOUR CODE HERE ==

def polygon_unit_points(sides, start=math.pi / 2.0):
    """Corners of a polygon on the unit circle, the first one pointing up."""
    step = 2.0 * math.pi / sides
    return [(math.cos(start + i * step), math.sin(start + i * step))
            for i in range(sides)]


def polygon_box(sides):
    """Bounding box of the unit polygon: (span_x, span_y, mid_x, mid_y).

    A polygon only has a vertex on every extreme when the corner count suits
    it, so the box is neither the circumcircle nor necessarily centred on it -
    a pentagon sits low in its own box. Everything else scales off this.
    """
    points = polygon_unit_points(sides)
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    return (max(xs) - min(xs), max(ys) - min(ys),
            (min(xs) + max(xs)) / 2.0, (min(ys) + max(ys)) / 2.0)


def shape_extent(shape, width, height, sides, regular):
    """How much room one drawn shape actually takes up.

    Rectangle, ellipse, slot and a stretched polygon all fill their cell, so
    this is simply length x depth. A regular polygon cannot fill a cell of the
    wrong proportions, so it reports its own footprint and the pitch follows
    that instead - otherwise the gap you ask for is not the gap you get.
    """
    if shape == SHAPE_POLYGON and regular:
        span_x, span_y, _mid_x, _mid_y = polygon_box(sides)
        radius = min(width, height) / 2.0
        return (span_x * radius, span_y * radius)
    return (width, height)


def corner_cut(shape, corner, size, width, height):
    """The radius, resp. the chamfer, actually applied to a rectangle's corners.

    Returns 0 for every other shape and for sharp corners, so the drawing code
    has one question to ask instead of three. Half the shorter edge is the
    limit: at exactly that the two cuts on that edge meet, and beyond it they
    would run past each other. More than that is refused rather than quietly
    trimmed - only rounding noise is absorbed.

    The cut changes nothing about the layout. The bounding box is still length
    x depth, so the pitch, the count and the gap stay as they were.
    """
    if shape != SHAPE_RECTANGLE or corner == CORNER_SHARP:
        return 0.0
    if size <= EPS:
        fail('err.corner_size')
    limit = min(width, height) / 2.0
    if size > limit + EPS:
        fail('err.corner_too_big', '%.2f' % mm(limit))
    return min(size, limit)


def corner_outline(width, height, cut, rounded):
    """The outline of a rectangle with its corners taken off, as segments.

    Each entry is ('line', start, end) or ('arc', start, through, end), the
    points relative to the centre of the shape and running counter-clockwise,
    so the end of one segment is the start of the next and the last closes back
    onto the first. No adsk calls, which is what lets tools/test_sketchgrid.py
    check the geometry - _draw_cut_rectangle only hands the result to Fusion.

    A cut of half an edge leaves no straight piece on that side, and such an
    edge is left out rather than emitted with zero length. Rounded on half of
    both edges is a circle and has no outline of this kind at all; that case
    belongs to the caller.
    """
    half_w, half_h = width / 2.0, height / 2.0
    inner_x, inner_y = half_w - cut, half_h - cut
    # The arc's third point sits on the diagonal out of the corner's centre.
    diagonal = cut * math.sqrt(0.5)

    # Each edge counter-clockwise from the bottom one, then the sign pair that
    # picks the corner ending it out of the four centres (+-inner_x, +-inner_y),
    # then where that corner comes out again.
    edges = (((-inner_x, -half_h), (inner_x, -half_h), (1.0, -1.0), (half_w, -inner_y)),
             ((half_w, -inner_y), (half_w, inner_y), (1.0, 1.0), (inner_x, half_h)),
             ((inner_x, half_h), (-inner_x, half_h), (-1.0, 1.0), (-half_w, inner_y)),
             ((-half_w, inner_y), (-half_w, -inner_y), (-1.0, -1.0), (-inner_x, -half_h)))

    out = []
    for start, end, (sign_x, sign_y), corner_end in edges:
        if abs(end[0] - start[0]) > EPS or abs(end[1] - start[1]) > EPS:
            out.append(('line', start, end))
        if rounded:
            out.append(('arc', end,
                        (sign_x * (inner_x + diagonal), sign_y * (inner_y + diagonal)),
                        corner_end))
        else:
            out.append(('line', end, corner_end))
    return out


def grid_layout(mode, width, height, gap_x, gap_y, columns, rows,
                area_width, area_height, anchor, offset_x=0.0, offset_y=0.0,
                shape=SHAPE_RECTANGLE, sides=6, regular=False):
    """Work out the grid without touching Fusion.

    Returns (columns, rows, pitch_x, pitch_y, total_width, total_height,
    origin_x, origin_y, extent_x, extent_y), where the origin places the lower left corner of the
    bounding box relative to the picked point. The anchor decides where the
    point sits in the grid; offset_x and offset_y then shift the whole thing
    away from it, which is how you keep a margin without moving the point.

    Kept free of adsk calls on purpose: this is the part worth testing, and
    tools/test_sketchgrid.py runs it without starting Fusion.
    """
    if width <= EPS:
        fail('err.width')
    if height <= EPS:
        fail('err.height')
    if gap_x < -EPS or gap_y < -EPS:
        fail('err.gap_negative')

    extent_x, extent_y = shape_extent(shape, width, height, sides, regular)
    pitch_x = extent_x + gap_x
    pitch_y = extent_y + gap_y

    if mode == MODE_FILL:
        if area_width <= EPS or area_height <= EPS:
            fail('err.area_positive')
        # n shapes need n widths and n-1 gaps, so n <= (area + gap) / pitch.
        columns = int(math.floor((area_width + gap_x) / pitch_x + 1e-9))
        rows = int(math.floor((area_height + gap_y) / pitch_y + 1e-9))
        if columns < 1 or rows < 1:
            fail('err.area_too_small', '%.2f' % mm(extent_x),
                 '%.2f' % mm(extent_y))
    else:
        if columns < 1:
            fail('err.columns')
        if rows < 1:
            fail('err.rows')

    if columns * rows > MAX_SHAPES:
        fail('err.too_many', str(columns * rows), str(MAX_SHAPES))

    total_width = columns * pitch_x - gap_x
    total_height = rows * pitch_y - gap_y

    factor_x, factor_y = ANCHOR_FACTORS[anchor]
    return (columns, rows, pitch_x, pitch_y, total_width, total_height,
            -factor_x * total_width + offset_x,
            -factor_y * total_height + offset_y,
            extent_x, extent_y)


def cell_centres(layout):
    """Centre of every cell, relative to the picked point, row by row."""
    (columns, rows, pitch_x, pitch_y, _total_width, _total_height,
     origin_x, origin_y, _extent_x, _extent_y) = layout
    out = []
    for row in range(rows):
        for column in range(columns):
            out.append((origin_x + column * pitch_x,
                        origin_y + row * pitch_y))
    return out


def _point(sketch_x, sketch_y):
    return adsk.core.Point3D.create(sketch_x, sketch_y, 0.0)


def _draw_rectangle(sketch, cx, cy, width, height,
                    corner=CORNER_SHARP, cut=0.0):
    if corner == CORNER_SHARP or cut <= EPS:
        sketch.sketchCurves.sketchLines.addTwoPointRectangle(
            _point(cx - width / 2.0, cy - height / 2.0),
            _point(cx + width / 2.0, cy + height / 2.0))
        return
    _draw_cut_rectangle(sketch, cx, cy, width, height, cut,
                        corner == CORNER_ROUND)


def _draw_cut_rectangle(sketch, cx, cy, width, height, cut, rounded):
    """Rectangle with all four corners taken off, as an arc or as a chamfer.

    `cut` is the fillet radius, resp. the leg length of the chamfer, and has
    already been measured against half the shorter edge by corner_cut().
    """
    # Rounded on half of both edges leaves nothing but the circle itself, and
    # a circle is not a chain of segments.
    if rounded and width - 2.0 * cut <= EPS and height - 2.0 * cut <= EPS:
        sketch.sketchCurves.sketchCircles.addByCenterRadius(_point(cx, cy), cut)
        return

    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs
    for segment in corner_outline(width, height, cut, rounded):
        points = [_point(cx + dx, cy + dy) for dx, dy in segment[1:]]
        if segment[0] == 'arc':
            arcs.addByThreePoints(*points)
        else:
            lines.addByTwoPoints(*points)


def _draw_ellipse(sketch, cx, cy, width, height):
    half_w, half_h = width / 2.0, height / 2.0
    centre = _point(cx, cy)
    if abs(half_w - half_h) <= EPS:
        sketch.sketchCurves.sketchCircles.addByCenterRadius(centre, half_w)
        return
    # The major axis point has to be on the longer axis, otherwise Fusion
    # rejects the ellipse.
    if half_w > half_h:
        major = _point(cx + half_w, cy)
        through = _point(cx, cy + half_h)
    else:
        major = _point(cx, cy + half_h)
        through = _point(cx + half_w, cy)
    sketch.sketchCurves.sketchEllipses.add(centre, major, through)


def _draw_slot(sketch, cx, cy, width, height):
    """Rectangle with semicircular ends, rounded on the shorter axis."""
    if abs(width - height) <= EPS:
        sketch.sketchCurves.sketchCircles.addByCenterRadius(
            _point(cx, cy), width / 2.0)
        return

    lines = sketch.sketchCurves.sketchLines
    arcs = sketch.sketchCurves.sketchArcs

    def at(dx, dy):
        return _point(cx + dx, cy + dy)

    if width > height:
        radius = height / 2.0
        straight = (width - height) / 2.0
        lines.addByTwoPoints(at(-straight, radius), at(straight, radius))
        arcs.addByThreePoints(at(straight, radius),
                              at(straight + radius, 0.0),
                              at(straight, -radius))
        lines.addByTwoPoints(at(straight, -radius), at(-straight, -radius))
        arcs.addByThreePoints(at(-straight, -radius),
                              at(-straight - radius, 0.0),
                              at(-straight, radius))
    else:
        radius = width / 2.0
        straight = (height - width) / 2.0
        lines.addByTwoPoints(at(radius, -straight), at(radius, straight))
        arcs.addByThreePoints(at(radius, straight),
                              at(0.0, straight + radius),
                              at(-radius, straight))
        lines.addByTwoPoints(at(-radius, straight), at(-radius, -straight))
        arcs.addByThreePoints(at(-radius, -straight),
                              at(0.0, -straight - radius),
                              at(radius, -straight))


def _draw_polygon(sketch, cx, cy, width, height, sides, regular):
    """Polygon with the first vertex pointing up, centred on its own box.

    Stretched so its bounding box is exactly the cell, unless `regular` is set,
    in which case the smaller of the two dimensions sets its size and it stays
    equilateral.
    """
    unit = polygon_unit_points(sides)
    span_x, span_y, mid_x, mid_y = polygon_box(sides)
    if regular:
        scale_x = scale_y = min(width, height) / 2.0
    else:
        scale_x = width / span_x
        scale_y = height / span_y
    corners = [_point(cx + (px - mid_x) * scale_x, cy + (py - mid_y) * scale_y)
               for px, py in unit]

    lines = sketch.sketchCurves.sketchLines
    first = lines.addByTwoPoints(corners[0], corners[1])
    previous = first
    for i in range(2, sides):
        previous = lines.addByTwoPoints(previous.endSketchPoint, corners[i])
    lines.addByTwoPoints(previous.endSketchPoint, first.startSketchPoint)


def _draw_shape(sketch, shape, cx, cy, width, height, sides, regular,
                corner=CORNER_SHARP, cut=0.0):
    if shape == SHAPE_ELLIPSE:
        _draw_ellipse(sketch, cx, cy, width, height)
    elif shape == SHAPE_SLOT:
        _draw_slot(sketch, cx, cy, width, height)
    elif shape == SHAPE_POLYGON:
        _draw_polygon(sketch, cx, cy, width, height, sides, regular)
    else:
        _draw_rectangle(sketch, cx, cy, width, height, corner, cut)


def read_inputs(inputs):
    selection = inputs.itemById(IN_POINT)
    point = None
    if selection.selectionCount == 1:
        entity = selection.selection(0).entity
        if entity and entity.objectType == adsk.fusion.SketchPoint.classType():
            point = entity

    mode_item = inputs.itemById(IN_MODE).selectedItem
    shape_item = inputs.itemById(IN_SHAPE).selectedItem
    anchor_item = inputs.itemById(IN_ANCHOR).selectedItem
    corner_item = inputs.itemById(IN_CORNER).selectedItem
    return dict(
        point=point,
        mode=mode_item.index if mode_item else MODE_COUNT,
        shape=shape_item.index if shape_item else SHAPE_RECTANGLE,
        anchor=anchor_item.index if anchor_item else 0,
        sides=inputs.itemById(IN_SIDES).value,
        regular=inputs.itemById(IN_REGULAR).value,
        corner=corner_item.index if corner_item else CORNER_SHARP,
        corner_size=inputs.itemById(IN_CORNER_SIZE).value,
        width=inputs.itemById(IN_WIDTH).value,
        height=inputs.itemById(IN_HEIGHT).value,
        gap_x=inputs.itemById(IN_GAP_X).value,
        gap_y=inputs.itemById(IN_GAP_Y).value,
        columns=inputs.itemById(IN_COLUMNS).value,
        rows=inputs.itemById(IN_ROWS).value,
        area_width=inputs.itemById(IN_AREA_WIDTH).value,
        area_height=inputs.itemById(IN_AREA_HEIGHT).value,
        offset_x=inputs.itemById(IN_OFFSET_X).value,
        offset_y=inputs.itemById(IN_OFFSET_Y).value,
    )


def cut_of(values):
    return corner_cut(values['shape'], values['corner'], values['corner_size'],
                      values['width'], values['height'])


def layout_of(values):
    return grid_layout(values['mode'], values['width'], values['height'],
                       values['gap_x'], values['gap_y'], values['columns'],
                       values['rows'], values['area_width'],
                       values['area_height'], values['anchor'],
                       values['offset_x'], values['offset_y'],
                       values['shape'], values['sides'], values['regular'])


def validate(values):
    if values['point'] is None:
        fail('err.no_point')
    if values['shape'] == SHAPE_POLYGON and not (
            MIN_SIDES <= values['sides'] <= MAX_SIDES):
        fail('err.sides', str(MIN_SIDES), str(MAX_SIDES))
    layout_of(values)
    cut_of(values)


def build_result(values):
    point = values['point']
    sketch = point.parentSketch
    origin = point.geometry
    layout = layout_of(values)
    cut = cut_of(values)
    # Centre each shape in its own footprint, which is the cell for everything
    # except a regular polygon.
    half_w, half_h = layout[8] / 2.0, layout[9] / 2.0

    # isComputeDeferred keeps the solver quiet until every shape is drawn -
    # with a few hundred cells that is the difference between instant and
    # unusable. Always reset it in a finally block.
    sketch.isComputeDeferred = True
    try:
        for dx, dy in cell_centres(layout):
            _draw_shape(sketch, values['shape'],
                        origin.x + dx + half_w, origin.y + dy + half_h,
                        values['width'], values['height'], values['sides'],
                        values['regular'], values['corner'], cut)
    finally:
        sketch.isComputeDeferred = False


def describe(values):
    """One line for the info box: how many, and how big the whole grid is."""
    try:
        layout = layout_of(values)
        cut_of(values)
    except core.AddInError as err:
        return str(err)
    columns, rows = layout[0], layout[1]
    return T('info.result', str(columns), str(rows), str(columns * rows),
             '%.2f' % mm(layout[4]), '%.2f' % mm(layout[5]))


def build_inputs(inputs):
    selection = inputs.addSelectionInput(IN_POINT, T('in.point'), T('in.point.prompt'))
    selection.addSelectionFilter('SketchPoints')
    selection.setSelectionLimits(1, 1)

    mode = inputs.addDropDownCommandInput(
        IN_MODE, T('in.mode'), adsk.core.DropDownStyles.TextListDropDownStyle)
    for index, key in enumerate(MODE_KEYS):
        mode.listItems.add(T(key), index == _last[IN_MODE])

    shape = inputs.addDropDownCommandInput(
        IN_SHAPE, T('in.shape'), adsk.core.DropDownStyles.TextListDropDownStyle)
    for index, key in enumerate(SHAPE_KEYS):
        shape.listItems.add(T(key), index == _last[IN_SHAPE])

    sides = inputs.addIntegerSpinnerCommandInput(
        IN_SIDES, T('in.sides'), MIN_SIDES, MAX_SIDES, 1, _last[IN_SIDES])
    sides.isVisible = _last[IN_SHAPE] == SHAPE_POLYGON

    regular = inputs.addBoolValueInput(IN_REGULAR, T('in.regular'), True, '',
                                       _last[IN_REGULAR])
    regular.tooltip = T('regular.tooltip')
    regular.isVisible = _last[IN_SHAPE] == SHAPE_POLYGON

    corner = inputs.addDropDownCommandInput(
        IN_CORNER, T('in.corner'), adsk.core.DropDownStyles.TextListDropDownStyle)
    for index, key in enumerate(CORNER_KEYS):
        corner.listItems.add(T(key), index == _last[IN_CORNER])
    corner.tooltip = T('corner.tooltip')
    corner.isVisible = _last[IN_SHAPE] == SHAPE_RECTANGLE

    corner_size = inputs.addValueInput(
        IN_CORNER_SIZE, T('in.corner_size'), 'mm',
        adsk.core.ValueInput.createByReal(_last[IN_CORNER_SIZE]))
    corner_size.tooltip = T('corner.tooltip')
    corner_size.isVisible = (_last[IN_SHAPE] == SHAPE_RECTANGLE
                             and _last[IN_CORNER] != CORNER_SHARP)

    inputs.addValueInput(IN_WIDTH, T('in.width'), 'mm',
                         adsk.core.ValueInput.createByReal(_last[IN_WIDTH]))
    inputs.addValueInput(IN_HEIGHT, T('in.height'), 'mm',
                         adsk.core.ValueInput.createByReal(_last[IN_HEIGHT]))
    inputs.addValueInput(IN_GAP_X, T('in.gap_x'), 'mm',
                         adsk.core.ValueInput.createByReal(_last[IN_GAP_X]))
    inputs.addValueInput(IN_GAP_Y, T('in.gap_y'), 'mm',
                         adsk.core.ValueInput.createByReal(_last[IN_GAP_Y]))

    columns = inputs.addIntegerSpinnerCommandInput(
        IN_COLUMNS, T('in.columns'), 1, MAX_SHAPES, 1, _last[IN_COLUMNS])
    rows = inputs.addIntegerSpinnerCommandInput(
        IN_ROWS, T('in.rows'), 1, MAX_SHAPES, 1, _last[IN_ROWS])
    area_width = inputs.addValueInput(
        IN_AREA_WIDTH, T('in.area_width'), 'mm',
        adsk.core.ValueInput.createByReal(_last[IN_AREA_WIDTH]))
    area_height = inputs.addValueInput(
        IN_AREA_HEIGHT, T('in.area_height'), 'mm',
        adsk.core.ValueInput.createByReal(_last[IN_AREA_HEIGHT]))

    fixed = _last[IN_MODE] == MODE_COUNT
    columns.isVisible = rows.isVisible = fixed
    area_width.isVisible = area_height.isVisible = not fixed

    anchor = inputs.addDropDownCommandInput(
        IN_ANCHOR, T('in.anchor'), adsk.core.DropDownStyles.TextListDropDownStyle)
    for index, key in enumerate(ANCHOR_KEYS):
        anchor.listItems.add(T(key), index == _last[IN_ANCHOR])

    offset_x = inputs.addValueInput(IN_OFFSET_X, T('in.offset_x'), 'mm',
                                    adsk.core.ValueInput.createByReal(_last[IN_OFFSET_X]))
    offset_y = inputs.addValueInput(IN_OFFSET_Y, T('in.offset_y'), 'mm',
                                    adsk.core.ValueInput.createByReal(_last[IN_OFFSET_Y]))
    offset_x.tooltip = offset_y.tooltip = T('offset.tooltip')

    inputs.addTextBoxCommandInput(IN_INFO, T('in.info'), '', 1, True)
    return selection


def remember(values):
    for key, name in ((IN_MODE, 'mode'), (IN_SHAPE, 'shape'),
                      (IN_ANCHOR, 'anchor'), (IN_SIDES, 'sides'),
                      (IN_REGULAR, 'regular'),
                      (IN_CORNER, 'corner'), (IN_CORNER_SIZE, 'corner_size'),
                      (IN_WIDTH, 'width'), (IN_HEIGHT, 'height'),
                      (IN_GAP_X, 'gap_x'), (IN_GAP_Y, 'gap_y'),
                      (IN_COLUMNS, 'columns'), (IN_ROWS, 'rows'),
                      (IN_AREA_WIDTH, 'area_width'),
                      (IN_AREA_HEIGHT, 'area_height'),
                      (IN_OFFSET_X, 'offset_x'), (IN_OFFSET_Y, 'offset_y')):
        _last[key] = values[name]


def refresh(inputs):
    """Show the fields that belong to the current mode and shape, and say what
    the settings will produce."""
    global _updating
    values = read_inputs(inputs)
    fixed = values['mode'] == MODE_COUNT

    inputs.itemById(IN_COLUMNS).isVisible = fixed
    inputs.itemById(IN_ROWS).isVisible = fixed
    inputs.itemById(IN_AREA_WIDTH).isVisible = not fixed
    inputs.itemById(IN_AREA_HEIGHT).isVisible = not fixed
    is_polygon = values['shape'] == SHAPE_POLYGON
    inputs.itemById(IN_SIDES).isVisible = is_polygon
    inputs.itemById(IN_REGULAR).isVisible = is_polygon
    is_rectangle = values['shape'] == SHAPE_RECTANGLE
    inputs.itemById(IN_CORNER).isVisible = is_rectangle
    inputs.itemById(IN_CORNER_SIZE).isVisible = (
        is_rectangle and values['corner'] != CORNER_SHARP)

    _updating = True
    try:
        inputs.itemById(IN_INFO).text = describe(values)
    finally:
        _updating = False


def on_input_changed(inputs, changed):
    if changed.id != IN_INFO:
        refresh(inputs)


# ========================================================= END OF TEMPLATE ====

def _run_command(inputs):
    values = read_inputs(inputs)
    validate(values)
    build_result(values)
    return values


class ExecuteHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        ui = adsk.core.Application.get().userInterface
        try:
            remember(_run_command(args.firingEvent.sender.commandInputs))
        except core.AddInError as err:
            ui.messageBox(str(err), T('cmd.name'))
        except Exception:
            core.report(ui, S, 'msg.exec_failed')


class PreviewHandler(adsk.core.CommandEventHandler):
    def notify(self, args):
        try:
            _run_command(args.firingEvent.sender.commandInputs)
            args.isValidResult = False
        except Exception:
            # Fires on every keystroke, including half-typed values.
            # validateInputs is what reports the problem.
            pass


class ValidateHandler(adsk.core.ValidateInputsEventHandler):
    def notify(self, args):
        try:
            validate(read_inputs(args.firingEvent.sender.commandInputs))
            args.areInputsValid = True
        except Exception:
            args.areInputsValid = False


class InputChangedHandler(adsk.core.InputChangedEventHandler):
    def notify(self, args):
        if _updating:
            return
        try:
            changed = args.input
            on_input_changed(changed.parentCommand.commandInputs, changed)
        except Exception:
            pass


class CommandCreatedHandler(adsk.core.CommandCreatedEventHandler):
    def notify(self, args):
        ui = adsk.core.Application.get().userInterface
        try:
            command = args.command
            command.isRepeatable = True
            inputs = command.commandInputs

            preselected = []
            for i in range(ui.activeSelections.count):
                entity = ui.activeSelections.item(i).entity
                if entity and entity.objectType == adsk.fusion.SketchPoint.classType():
                    preselected.append(entity)

            selection = build_inputs(inputs)
            if preselected and selection and selection.selectionCount == 0:
                selection.addSelection(preselected[0])
            refresh(inputs)

            _handlers.add(command.execute, ExecuteHandler())
            _handlers.add(command.executePreview, PreviewHandler())
            _handlers.add(command.validateInputs, ValidateHandler())
            _handlers.add(command.inputChanged, InputChangedHandler())
        except Exception:
            core.report(ui, S, 'msg.dialog_failed')


def run(context):
    global _control
    ui = None
    try:
        ui = adsk.core.Application.get().userInterface
        S.load(core.detect_language())

        stale = ui.commandDefinitions.itemById(CMD_ID)
        if stale:
            stale.deleteMe()

        icons = RESOURCE_FOLDER if os.path.isdir(RESOURCE_FOLDER) else ''
        definition = ui.commandDefinitions.addButtonDefinition(
            CMD_ID,
            core.display_name(T('cmd.name'), core.read_version(_DIR, 'SketchGrid')),
            T('cmd.tooltip'), icons)
        _handlers.add(definition.commandCreated, CommandCreatedHandler())

        panel = core.find_panel(ui, WORKSPACE_ID, PANEL_IDS)
        if not panel:
            ui.messageBox(T('msg.panel_missing'), T('cmd.name'))
            return
        _control = core.add_button(ui, panel, definition)
    except Exception:
        if ui:
            core.report(ui, S, 'msg.run_failed')


def stop(context):
    global _control
    ui = None
    try:
        ui = adsk.core.Application.get().userInterface
        core.remove_button(ui, WORKSPACE_ID, PANEL_IDS, CMD_ID)
        _control = None
        _handlers.clear()
    except Exception:
        if ui:
            core.report(ui, S, 'msg.stop_failed')
