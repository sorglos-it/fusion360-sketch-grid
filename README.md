# fusion360-sketch-grid

[![Fusion 360](https://img.shields.io/badge/Autodesk-Fusion%20360-F60?logo=autodesk&logoColor=white)](#requirements)
[![Type](https://img.shields.io/badge/type-add--in-0b7285.svg)](#installation)
[![Shapes](https://img.shields.io/badge/shapes-4-4c1.svg)](#shapes)
[![Languages](https://img.shields.io/badge/UI-DE%20%7C%20EN%20%7C%20ES%20%7C%20FR%20%7C%20IT-4c1.svg)](#languages)
[![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-0078D6?logo=windows&logoColor=white)](#requirements)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Donate](https://img.shields.io/badge/Donate-PayPal-00457C.svg?logo=paypal)](https://www.paypal.com/donate/?hosted_button_id=6CDEVZGJWTNQQ)

A Fusion 360 add-in that builds a **grid of shapes around a sketch point**. Click a point, say how big one cell is and how far apart they sit, and get the whole array in one go — rectangles, circles, slots or polygons.

Two ways to arrive at the count. Either you give **columns and rows** outright, or you give an **area** and it fits in as many as go in completely. A read-out under the dialog says what the current settings will produce before you commit to them.

See also **[fusion360-dovetail](https://github.com/sorglos-it/fusion360-dovetail)** — joinery on a sketch line — and **[fusion360-addin-template](https://github.com/sorglos-it/fusion360-addin-template)**, the scaffolding both were built from.

## Features

- **Two counting modes** — fixed columns and rows, or as many as fit into a given area
- **Four shapes** — rectangle, circle/ellipse, slot with rounded ends, regular polygon from 3 to 24 sides
- **Nine anchor positions** — the picked point can be the middle of the grid, any corner, or the middle of any edge
- **Offset X / Y** — shift the grid off the point to hold a margin, without moving the point
- **Separate gaps** for X and Y, zero allowed for shapes that touch
- **Live read-out** — *8 × 4 = 32 shapes, 94 × 26 mm overall*, updated as you type
- **Live preview** — the sketch updates while the dialog is open
- **Explained refusals** — an area too small for a single shape says how big it would have to be
- **A cap that saves you** — more than 2000 shapes is refused rather than locked up
- **Five languages** — German, English, Spanish, French, Italian, from the Fusion language setting
- **No dependencies** — pure Python standard library

## Requirements

- Autodesk Fusion 360 (Windows or macOS), any recent version
- Nothing else — the add-in uses only Python modules that ship with Fusion

## Installation

1. Download the latest `SketchGrid-*.zip` from **[Releases](https://github.com/sorglos-it/fusion360-sketch-grid/releases)** — or clone this repository and use the `SketchGrid` folder as it is.
2. Unpack it into the Fusion add-ins directory, so that `SketchGrid\SketchGrid.py` ends up one level below it:

   | OS | Path |
   |---|---|
   | Windows | `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\` |
   | macOS | `~/Library/Application Support/Autodesk/Autodesk Fusion 360/API/AddIns/` |

3. In Fusion: **Utilities → ADD-INS → Add-Ins**, select the entry, tick *Run on Startup*, press **Run**.
4. The button appears on the **SKETCH** tab in the **CREATE** panel, with the installed version in brackets after its name.

Replacing an older copy: stop the add-in in Fusion first, otherwise the running one stays in memory.

## Usage

1. Open or edit a sketch.
2. Click a point — the sketch origin, or any point you placed yourself.
3. Click the grid icon. The point you clicked is already filled into the dialog.
4. Set the values, read the result line, press **OK**.

Worked example, the one the add-in was built around: length 10 mm, depth 5 mm, gap 2 mm, 8 columns and 4 rows. That gives a pitch of 12 × 7 mm and a grid of 94 × 26 mm overall, 32 rectangles, centred on the point you picked.

## Dialog

| Field | Meaning |
|---|---|
| **Point** | The sketch point the grid is built around. Pre-filled from the current selection. |
| **Count from** | `Columns and rows` or `Fitting an area`. Switches which fields below are shown. |
| **Shape** | `Rectangle`, `Circle / ellipse`, `Slot`, `Polygon`. |
| **Sides** | Polygon only: 3 to 24. |
| **Length (X)** / **Depth (Y)** | The size of one cell. |
| **Gap X** / **Gap Y** | Space between neighbours. 0 makes them touch. |
| **Columns** / **Rows** | Fixed mode: the count outright. |
| **Area width** / **Area height** | Fill mode: the space to fill. |
| **Point sits** | Where the picked point is in the grid: middle, a corner, or the middle of an edge. |
| **Offset X** / **Offset Y** | Shifts the whole grid off the point, on top of the anchor. Negative goes the other way. |
| **Result** | Read-only: how many shapes and how big the grid comes out. |

## The two modes

**Columns and rows** is the direct one. `n` shapes span `n × size + (n−1) × gap`, so 8 columns of 10 mm with a 2 mm gap come to 94 mm, not 96.

**Fitting an area** turns that around: it fits in as many as go in *completely*, `floor((area + gap) / (size + gap))`. A partial shape at the edge is never drawn. Consequences worth knowing:

- 100 mm of width with 10 mm shapes and a 2 mm gap gives **8** columns (94 mm used, 6 mm left over). A ninth would need 106 mm.
- The leftover sits on the far side of the grid, not distributed. Use the anchor to decide which side that is.
- An area of exactly 94 mm gives 8. At 93.9 mm it drops to 7 — the arithmetic is exact, so a rounded-off number can cost you a whole column.

## Anchor

The field is called **Point sits in the grid**, and that is exactly what it says: where the point you clicked ends up *inside* the finished grid. It is not the direction the grid grows in — that is the opposite of each entry. A point sitting at the bottom left means the grid extends up and to the right of it.

Nine positions, here with a 3 × 2 grid, `X` the picked point and `#` the shapes:

```
  Bottom left          Left centre          Top right
  #####.#####.#####    #####.#####.#####    #####.#####.####X
  #####.#####.#####    #####.#####.#####    #####.#####.#####
  .................    X................    .................
  #####.#####.#####    #####.#####.#####    #####.#####.#####
  X####.#####.#####    #####.#####.#####    #####.#####.#####

  Bottom centre        In the middle        Right centre
  #####.#####.#####    #####.#####.#####    #####.#####.#####
  #####.#####.#####    #####.#####.#####    #####.#####.#####
  .................    ........X........    ................X
  #####.#####.#####    #####.#####.#####    #####.#####.#####
  #####.##X##.#####    #####.#####.#####    #####.#####.#####
```

`In the middle` is the default and grows the grid symmetrically in all four directions. For the 8 × 4 example that puts the lower left corner 47 mm left and 13 mm below the point. `Bottom left` puts the point exactly on the lower left corner, so the grid occupies the space up and to the right of it.

`tools/test_sketchgrid.py` derives the expected factors from each entry's own name and checks them both ways round, so a label that disagrees with the geometry fails the suite.

## Offset

The anchor puts the point somewhere in the grid; **Offset X** and **Offset Y** then move the whole grid off it. The two add up rather than replacing each other.

The case it exists for: your point sits at 0/0, but the grid should start 2 mm in from it because you want a margin at that edge. Without the offset you would have to move the point to 2/2 and lose it as a reference. With it, the point stays where it belongs and the grid sits where you want it — and the margin does not have to match the gap, so a safety zone of any size works.

Count, pitch and overall size are untouched by the offset, and in *fill an area* mode it does not change how many shapes fit — it only moves the result.

## Shapes

| Shape | Built from | Note |
|---|---|---|
| **Rectangle** | Length × depth | The plain case. |
| **Circle / ellipse** | Length and depth as the two axes | Equal values give a true circle, unequal an ellipse with the major axis on the longer side. |
| **Slot** | Rectangle with semicircular ends | Rounded on the shorter axis; the radius is half of it. Equal length and depth make a circle. |
| **Polygon** | Regular, first vertex pointing up | A regular polygon cannot fill a non-square cell, so it takes the **smaller** of the two dimensions as its diameter and sits centred. A 6-sided polygon in a 10 × 5 cell is 5 mm across, not 10. |

## How it works

1. The picked point gives an origin in sketch space. Everything is computed relative to it and only converted at the moment of drawing, so the grid does not care where in the sketch you are.
2. `grid_layout()` works out the count, the pitch, the overall size and the offset of the bounding box from the anchor factors. It touches no Fusion API at all, which is why `tools/test_sketchgrid.py` can check it without starting Fusion.
3. `cell_centres()` walks the cells row by row and yields their positions relative to the point.
4. Each shape is drawn into the sketch by its own small function. The polygon chains its segments through `endSketchPoint` so the outline comes out connected; the slot relies on coincident endpoints, which is enough for Fusion to detect a profile.
5. Drawing runs with `isComputeDeferred` set. With a few hundred cells that is the difference between instant and unusable.

## Notes & caveats

- **The count is capped at 2000.** Fill mode with a small shape and a large area produces four-figure counts easily, and Fusion takes minutes over that with the sketch solver awake. The cap refuses with a message rather than appearing to hang.
- **A polygon uses the smaller dimension.** In a wide, flat cell it looks lost, and that is honest: a regular polygon has one diameter. Use a rectangle or an ellipse when the cell is not roughly square.
- **The polygon's orientation is fixed** with a vertex pointing up. For flat-top hexagons, swap length and depth, or rotate the finished sketch.
- **Shapes are plain sketch geometry, not a Fusion pattern.** They are not associative — changing the source later does not update them. That is deliberate: the result is ordinary curves you can trim, constrain and extrude without a pattern feature in the way.
- **Gaps can be 0 but not negative.** Overlapping shapes would produce profiles that fight each other; if you want overlap, draw one grid and offset a second.
- **The leftover in fill mode is not centred.** The grid is laid out from the anchor, and whatever does not fit is left on the far side. Anchoring to the middle splits the leftover between both sides instead.
- **The sketch origin works as the point.** So does any point you place. What does not work is a vertex on a body — the selection filter is sketch points only.

## Development

The grid maths has no Fusion dependency and is tested from a normal Python installation. The test stubs the `adsk` modules, imports the add-in and checks the layout, the anchor factors, both counting modes, every error key and all five language files:

```bash
python tools/test_sketchgrid.py
```

The structural check from the template repository runs against it too — manifest, GUID, command id, icons:

```bash
python ../fusion360-addin-template/tools/test_addin.py --path SketchGrid
```

The icon is generated, not drawn by hand:

```bash
python tools/make_icon.py
```

Both scripts resolve paths relative to the repository. Set `SKETCHGRID_ADDIN_DIR` to point them at an installed copy instead.

Scaffolded from **[fusion360-addin-template](https://github.com/sorglos-it/fusion360-addin-template)**, which carries the translated-interface machinery, the handler registry and the panel lookup used here.

## Support this project ❤️

If this add-in saved you time, you can support further development:

[![Donate with PayPal](https://www.paypalobjects.com/en_US/i/btn/btn_donate_LG.gif)](https://www.paypal.com/donate/?hosted_button_id=6CDEVZGJWTNQQ)

**[➡️ Donate via PayPal](https://www.paypal.com/donate/?hosted_button_id=6CDEVZGJWTNQQ)**

## License

This project is licensed under the [MIT License](LICENSE) — © 2026 Thomas Weirich.
