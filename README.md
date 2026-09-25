# FigureForge

Build a Matplotlib figure in a local web app using data from your Python script.
Choose plotting functions, bind their inputs to dictionary keys, style the plots,
and export ordinary Python / Matplotlib code.

## Use from a script

```python
import numpy as np
import figureforge

x = np.linspace(0, 2 * np.pi, 100)
data = {
    "time": x,
    "signal": np.sin(x),
    "reference": np.cos(x),
    "image": np.outer(np.sin(x), np.cos(x)),
}

fig = figureforge.run(data)
# Click Done editing in the browser to return the constructed figure.
fig.savefig("figure.png", dpi=200)
```

`run(data, *, port=0, open_browser=True)` accepts a dictionary with string keys.
Values can be NumPy arrays, lists, or other data accepted by the chosen Matplotlib
function. Data is copied for the editing session and is not modified. Only key
names and shape/type descriptions are sent to the browser; arrays stay in Python.

This replaces the earlier `run(fig)` workflow: you no longer need to construct a
figure before opening the editor. The function blocks until **Done editing** or
Ctrl+C, then returns the figure. Closing the browser tab does not stop the server.
The returned figure uses an Agg canvas and can be saved directly.

See [examples/data_builder.py](examples/data_builder.py) for a runnable example.

## Build a plot

1. Choose a function in the **Plot function** dropdown.
2. Select dictionary keys for its data inputs. Required inputs are marked `*`.
3. Click **Add plot**. Add more plots to overlay them on the same axes.
4. Select a plot to change its bindings, set its styling, or remove it.
5. Select **Labels & axes** for the title, x/y labels, legend, grid, scales, and limits.
   Set each plot's `label` parameter to give it a legend entry.
6. Select **Figure** for size, DPI, background colors, and layout.

Supported functions:

| Function | Data inputs |
| --- | --- |
| `plot` | `y`, optional `x` (otherwise sample indices) |
| `scatter` | `x`, `y`; optional size `s` and color `c` arrays |
| `imshow` | `X`, a 2D array or RGB/RGBA image |
| `hist` | `x`; optional `weights` |
| `bar` / `barh` | positions and heights/widths; optional widths/heights, baseline, errors |
| `step` | `x`, `y` |
| `errorbar` | `x`, `y`; optional `xerr`, `yerr` |
| `fill_between` | `x`, `y1`; optional `y2`, `where` |
| `contour` / `contourf` | `Z`, a 2D array using index coordinates |
| `pcolormesh` | `C`, a 2D array using index coordinates |

Optional inputs can use a dictionary entry or a literal parameter value. For
example, bind scatter `s` to a sizes array, or set `s` to `40` in its parameter
panel. Setting a literal replaces that input's data binding, and vice versa.

Text/number edits update the preview automatically. Arrays, dictionaries, and
nullable values use JSON. **Use Matplotlib default** removes a parameter override.
Invalid shapes, missing keys, or invalid styles leave the last valid figure and
export unchanged. Undo and reset cover plots, bindings, styling, and rcParams.

## Global rcParams

The separate **Global Matplotlib rcParams** widget provides searchable defaults.
For example, change `font.size`, `lines.linewidth`, or `axes.facecolor`. Every edit
rebuilds the figure in an isolated rc context, so defaults apply at construction
time. Explicit plot settings take precedence. The caller's rcParams are unchanged.

`axes.prop_cycle` accepts a JSON dictionary such as
`{"color": ["#6366f1", "#14b8a6"]}`. Backend/runtime controls and parameters requiring
custom Python objects are read-only. Export-only rcParams may not affect the PNG
preview.

## Export Python

**Download .py** produces a `make_figure(data)` function. For example:

```python
import matplotlib.pyplot as plt


def make_figure(data):
    with plt.rc_context({"font.size": 12}):
        fig, ax = plt.subplots(layout="constrained")
        ax.plot(data["time"], data["signal"], label="Signal", linewidth=2)
        ax.scatter(data["time"], data["reference"], s=30)
        ax.set_title("Measurements")
        ax.set_xlabel("Time (s)")
        ax.legend()
        fig.canvas.draw()
    return fig
```

Call the exported function with your dictionary; FigureForge is not needed:

```python
from make_figure import make_figure
fig = make_figure(data)
fig.savefig("figure.png")
```

The export references dictionary keys instead of embedding arrays, so it can be
reused with new data under the same keys. It records explicit rcParams and plotting
arguments; unspecified values inherit the active Matplotlib defaults. PNG download
and code copying are also available.

## Start with sample data

```sh
uv sync
uv run figureforge
# Or print the URL without opening a browser:
uv run figureforge --no-browser --port 8765
```

Calling `figureforge.run()` without an argument also supplies sample arrays. The
figure starts empty so you can choose which plots to create. An empty dictionary
is accepted but no data plots can be added until you start a session with data.

The server listens only on `127.0.0.1`. Open the complete printed URL, including its
session token after `#`. No frontend build or external web assets are required.
PNG previews are limited to 5,000 pixels per side and 16 megapixels.

## Checks

```sh
uv run python -m unittest discover -s tests -v
node --check src/figureforge/static/app.js
```

Tests include every plotting function, data binding/rebinding, plot removal,
labels, rcParams, rollback, undo/reset, and pixel-identical Python export replay.
The socket integration test is skipped where loopback sockets are prohibited.
