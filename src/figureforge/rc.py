"""Global defaults panel and live styling of already-created figures."""

from cycler import Cycler, cycler

from .parameters import json_value


READ_ONLY = {'backend', 'backend_fallback', 'interactive', 'toolbar', 'webagg.address',
             'webagg.port', 'webagg.port_retries', 'webagg.open_in_browser'}


def rc_value(value):
    return json_value(value.by_key() if isinstance(value, Cycler) else value)


def decode_rc(key, value):
    return cycler(**value) if key == 'axes.prop_cycle' and isinstance(value, dict) else value


def rc_parameters(settings):
    result = []
    for name in sorted(settings):
        editable = name not in READ_ONLY
        try:
            value = rc_value(settings[name])
        except ValueError:
            value, editable = None, False
        result.append(dict(name=name, value=value, editable=editable,
                           hint='Runtime setting; configure before starting FigureForge.' if not editable else
                           'Global Matplotlib default. Explicit edits in a plot panel take precedence.'))
    return result


def rc_commands(name, value):
    """Make construction-time defaults visible on an existing scene as well."""
    v = repr(value)
    group, _, prop = name.partition('.')
    if name == 'figure.figsize':
        return [f'fig.set_size_inches({v})']
    if group == 'figure' and prop in {'dpi', 'facecolor', 'edgecolor', 'frameon'}:
        return [f'fig.set_{prop}({v})']
    if group == 'font' and prop in {'size', 'family', 'style', 'variant', 'weight', 'stretch'}:
        return [f'for _text in fig.findobj(Text): _text.set_font{prop}({v})']
    if name == 'text.color':
        return [f'for _text in fig.findobj(Text): _text.set_color({v})']
    if group == 'lines' and prop in {'linewidth', 'linestyle', 'color', 'marker', 'markersize', 'markeredgewidth', 'markeredgecolor', 'markerfacecolor', 'antialiased', 'dash_capstyle', 'solid_capstyle', 'dash_joinstyle', 'solid_joinstyle'}:
        return [f'for _ax in fig.axes:\n    for _line in _ax.lines: _line.set_{prop}({v})']
    if name == 'axes.prop_cycle':
        return [f'_cycle = list(cycler(**{v}))',
                'for _ax in fig.axes:\n    for _i, _line in enumerate(_ax.lines): _line.set(**_cycle[_i % len(_cycle)])']
    if name in {'axes.facecolor', 'axes.axisbelow'}:
        return [f'for _ax in fig.axes: _ax.set_{prop}({v})']
    if name in {'axes.titlesize', 'axes.titleweight', 'axes.titlecolor'}:
        setter = {'titlesize': 'fontsize', 'titleweight': 'fontweight', 'titlecolor': 'color'}[prop]
        if value == 'auto':
            return []
        return [f'for _ax in fig.axes: _ax.title.set_{setter}({v})']
    if name in {'axes.labelsize', 'axes.labelweight', 'axes.labelcolor'}:
        setter = {'labelsize': 'fontsize', 'labelweight': 'fontweight', 'labelcolor': 'color'}[prop]
        return [f'for _ax in fig.axes:\n    for _axis in (_ax.xaxis, _ax.yaxis): _axis.label.set_{setter}({v})']
    if name in {'axes.edgecolor', 'axes.linewidth'}:
        setter = 'edgecolor' if prop == 'edgecolor' else 'linewidth'
        return [f'for _ax in fig.axes:\n    for _spine in _ax.spines.values(): _spine.set_{setter}({v})']
    if name.startswith('axes.spines.'):
        return [f'for _ax in fig.axes: _ax.spines[{prop.split(".")[1]!r}].set_visible({v})']
    if name == 'axes.grid':
        return [f'for _ax in fig.axes: _ax.grid({v})']
    if group == 'grid' and prop in {'color', 'linestyle', 'linewidth', 'alpha'}:
        return [f'for _ax in fig.axes:\n    for _grid in _ax.get_xgridlines() + _ax.get_ygridlines(): _grid.set_{prop}({v})']
    if group in {'xtick', 'ytick'}:
        parts = prop.split('.')
        which = parts[0] if len(parts) == 2 else 'both'
        parameter = {'size': 'length', 'labelsize': 'labelsize'}.get(parts[-1], parts[-1])
        if parameter in {'length', 'width', 'pad', 'color', 'labelcolor', 'labelsize', 'direction', 'top', 'bottom', 'left', 'right', 'labeltop', 'labelbottom', 'labelleft', 'labelright'}:
            return [f'for _ax in fig.axes: _ax.tick_params(axis={group[0]!r}, which={which!r}, {parameter}={v})']
    if group == 'image' and prop in {'cmap', 'interpolation', 'resample'}:
        return [f'for _ax in fig.axes:\n    for _image in _ax.images: _image.set_{prop}({v})']
    if group == 'patch' and prop in {'facecolor', 'edgecolor', 'linewidth', 'antialiased'}:
        return [f'for _ax in fig.axes:\n    for _patch in _ax.patches: _patch.set_{prop}({v})']
    if name == 'scatter.marker':
        return [f'_marker = MarkerStyle({v})', 'for _ax in fig.axes:\n    for _collection in _ax.collections:\n        if isinstance(_collection, PathCollection): _collection.set_paths([_marker.get_path().transformed(_marker.get_transform())])']
    if name == 'legend.fontsize':
        return [f'for _ax in fig.axes:\n    if _ax.get_legend():\n        for _text in _ax.get_legend().get_texts(): _text.set_fontsize({v})']
    if name in {'legend.facecolor', 'legend.edgecolor', 'legend.framealpha', 'legend.frameon'}:
        setter = {'facecolor': 'facecolor', 'edgecolor': 'edgecolor', 'framealpha': 'alpha', 'frameon': 'visible'}[prop]
        if value == 'inherit':
            return []
        return [f'for _ax in fig.axes:\n    if _ax.get_legend(): _ax.get_legend().get_frame().set_{setter}({v})']
    return []
