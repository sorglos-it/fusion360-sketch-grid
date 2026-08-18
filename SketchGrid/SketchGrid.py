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

def grid_layout(mode, width, height, gap_x, gap_y, columns, rows,
                area_width, area_height, anchor, offset_x=0.0, offset_y=0.0):
    """Work out the grid without touching Fusion.

    Returns (columns, rows, pitch_x, pitch_y, total_width, total_height,
    origin_x, origin_y), where the origin places the lower left corner of the
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

    pitch_x = width + gap_x
    pitch_y = height + gap_y

    if mode == MODE_FILL:
        if area_width <= EPS or area_height <= EPS:
            fail('err.area_positive')
        # n shapes need n widths and n-1 gaps, so n <= (area + gap) / pitch.
        columns = int(math.floor((area_width + gap_x) / pitch_x + 1e-9))
        rows = int(math.floor((area_height + gap_y) / pitch_y + 1e-9))
        if columns < 1 or rows < 1:
            fail('err.area_too_small', '%.2f' % mm(width), '%.2f' % mm(height))
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
            -factor_y * total_height + offset_y)


def cell_centres(layout):
    """Centre of every cell, relative to the picked point, row by row."""
    (columns, rows, pitch_x, pitch_y,
     _total_width, _total_height, origin_x, origin_y) = layout
    out = []
    for row in range(rows):
        for column in range(columns):
            out.append((origin_x + column * pitch_x,
                        origin_y + row * pitch_y))
    return out


def _point(sketch_x, sketch_y):
    return adsk.core.Point3D.create(sketch_x, sketch_y, 0.0)


def _draw_rectangle(sketch, cx, cy, width, height):
    sketch.sketchCurves.sketchLines.addTwoPointRectangle(
        _point(cx - width / 2.0, cy - height / 2.0),
        _point(cx + width / 2.0, cy + height / 2.0))


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


def _draw_polygon(sketch, cx, cy, width, height, sides):
    """Regular polygon, first vertex pointing up.

    A regular polygon cannot fill a non-square cell, so it takes the smaller of
    the two dimensions as its diameter and sits centred in the cell.
    """
    radius = min(width, height) / 2.0
    step = 2.0 * math.pi / sides
    start = math.pi / 2.0
    corners = [_point(cx + radius * math.cos(start + i * step),
                      cy + radius * math.sin(start + i * step))
               for i in range(sides)]

    lines = sketch.sketchCurves.sketchLines
    first = lines.addByTwoPoints(corners[0], corners[1])
    previous = first
    for i in range(2, sides):
        previous = lines.addByTwoPoints(previous.endSketchPoint, corners[i])
    lines.addByTwoPoints(previous.endSketchPoint, first.startSketchPoint)


def _draw_shape(sketch, shape, cx, cy, width, height, sides):
    if shape == SHAPE_ELLIPSE:
        _draw_ellipse(sketch, cx, cy, width, height)
    elif shape == SHAPE_SLOT:
        _draw_slot(sketch, cx, cy, width, height)
    elif shape == SHAPE_POLYGON:
        _draw_polygon(sketch, cx, cy, width, height, sides)
    else:
        _draw_rectangle(sketch, cx, cy, width, height)


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
    return dict(
        point=point,
        mode=mode_item.index if mode_item else MODE_COUNT,
        shape=shape_item.index if shape_item else SHAPE_RECTANGLE,
        anchor=anchor_item.index if anchor_item else 0,
        sides=inputs.itemById(IN_SIDES).value,
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


def layout_of(values):
    return grid_layout(values['mode'], values['width'], values['height'],
                       values['gap_x'], values['gap_y'], values['columns'],
                       values['rows'], values['area_width'],
                       values['area_height'], values['anchor'],
                       values['offset_x'], values['offset_y'])


def validate(values):
    if values['point'] is None:
        fail('err.no_point')
    if values['shape'] == SHAPE_POLYGON and not (
            MIN_SIDES <= values['sides'] <= MAX_SIDES):
        fail('err.sides', str(MIN_SIDES), str(MAX_SIDES))
    layout_of(values)


def build_result(values):
    point = values['point']
    sketch = point.parentSketch
    origin = point.geometry
    layout = layout_of(values)
    half_w, half_h = values['width'] / 2.0, values['height'] / 2.0

    # isComputeDeferred keeps the solver quiet until every shape is drawn -
    # with a few hundred cells that is the difference between instant and
    # unusable. Always reset it in a finally block.
    sketch.isComputeDeferred = True
    try:
        for dx, dy in cell_centres(layout):
            _draw_shape(sketch, values['shape'],
                        origin.x + dx + half_w, origin.y + dy + half_h,
                        values['width'], values['height'], values['sides'])
    finally:
        sketch.isComputeDeferred = False


def describe(values):
    """One line for the info box: how many, and how big the whole grid is."""
    try:
        layout = layout_of(values)
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
    inputs.itemById(IN_SIDES).isVisible = values['shape'] == SHAPE_POLYGON

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
