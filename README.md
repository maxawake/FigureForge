# FigureForge

A local web interface for editing Matplotlib figures. Select an artist in the left
sidebar, change its properties, and see the rendered figure update automatically.
Export your edits as readable Python / Matplotlib setter calls.

## Start the editor

```sh
uv sync
uv run figureforge
# Or print the URL without opening a browser:
uv run figureforge --no-browser --port 8765
```

The default demo includes two curves, axes, labels, grid lines, and a legend. Its
Python export is a standalone script, including the original plotting code.
The server uses only Python's standard library and listens on `127.0.0.1`.
Open the full printed URL, including its session token after `#`.
No frontend build, external assets, or internet connection is needed at runtime.

## Edit your own figure

```python
import matplotlib.pyplot as plt
import figureforge

fig, ax = plt.subplots()
ax.plot([1, 2, 3], [1, 4, 9], label="Measurements")
ax.legend()

edited_fig = figureforge.run(fig)
# Click Done in the browser to return the edited copy to your script.
edited_fig.savefig("edited.png", dpi=200)
```

`run` edits a copy; the input figure is unchanged. It blocks until **Done editing**
or Ctrl+C. Closing the browser tab does not stop the server. The returned figure
uses Matplotlib's Agg canvas and can be saved directly.

For an existing figure, **Download .py** exports an `apply_settings(fig)` function.
Keep your original data and plotting code, then call this function immediately
after constructing the same figure. The export uses Matplotlib directly and does
not require FigureForge. Artist paths refer to the original artist hierarchy;
apply the export with the same plotting code and Matplotlib version. Changing the
plot's structure can invalidate those paths. The function records accepted edits
in order, including edits that affect ticks and layout, drawing between changes.
It does not serialize arbitrary source figures or their input data.

## Controls

- Search the artist tree for figures, axes, lines, scatter collections, patches,
  text, legends, spines, or individual ticks.
- Filter the selected artist's properties. Matplotlib's inspection API exposes
  available setters with serializable getters, including color, font, marker,
  line style, visibility, limits, scale, figure size, and DPI where supported.
- Text and number controls update after a short pause. Checkboxes toggle boolean
  settings. Arrays, dictionaries, and nullable values use JSON (`[0, 10]`,
  `[1, 0, 0, 1]`, or `null`). Hover a control for accepted-value documentation.
- Invalid edits show an error and leave the last successful preview and export
  unchanged. Undo removes the last accepted change; Reset removes all edits.
- Download the displayed PNG, copy the Python code, or download a `.py` file.

Object-valued settings (transforms, callbacks, custom normalizers, font property
objects, and similar settings) remain in Python. Properties without readable
getters and arrays larger than 16 KB are omitted. Some getters and setters use
different conventions; unsupported inputs are rejected by Matplotlib. This is
an editor for existing artists, not a plotting-code or data-upload execution
service. PNG previews are limited to 5,000 pixels per side and 16 megapixels.

## Checks

```sh
uv run python -m unittest discover -s tests -v
node --check src/figureforge/static/app.js
```

Tests cover code-export image equivalence, standalone demo export, transaction
rollback, undo/reset, property inspection, and local HTTP routes and session
validation. The socket integration test is skipped in environments that prohibit
loopback sockets.
