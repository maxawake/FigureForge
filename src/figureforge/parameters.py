"""Call-oriented parameter adapters for already-created figures."""

import inspect

import matplotlib as mpl
from matplotlib.artist import ArtistInspector
from matplotlib.collections import PathCollection
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.markers import MarkerStyle
from matplotlib.text import Text
import numpy as np


# Current artists do not retain constructor data lookups or format strings.
OBJECT_PARAMETERS = {'agg_filter', 'clip_box', 'clip_path', 'figure', 'transform',
                     'path_effects', 'colorizer', 'subplotpars', 'offset_transform',
                     'paths', 'fontproperties'}


def json_value(value):
    if isinstance(value, np.ndarray):
        return json_value(value.tolist())
    if isinstance(value, np.generic):
        return json_value(value.item())
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float) and np.isfinite(value):
        return value
    if isinstance(value, (tuple, list)):
        return [json_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): json_value(v) for k, v in value.items()}
    raise ValueError('Requires a Python object')


def marker_name(collection):
    paths = collection.get_paths()
    if len(paths) != 1:
        return None
    for marker in MarkerStyle.markers:
        try:
            style = MarkerStyle(marker)
            path = style.get_path().transformed(style.get_transform())
            if np.array_equal(path.vertices, paths[0].vertices) and np.array_equal(path.codes, paths[0].codes):
                return marker
        except (ValueError, TypeError):
            pass
    return None


def actors(fig):
    """Only user-facing plot objects; never descend into ticks, spines or handles."""
    result = [{'name': 'plt.figure', 'label': fig.get_label(), 'expr': 'fig', 'artist': fig, 'kind': 'figure'}]
    for ai, ax in enumerate(fig.axes):
        prefix = f'fig.axes[{ai}]'
        contained = {id(child) for container in ax.containers for child in container.get_children()}
        for attr, kind, name in (('lines', 'plot', 'plot'), ('collections', 'scatter', 'scatter'),
                                 ('images', 'imshow', 'imshow'), ('texts', 'text', 'text'),
                                 ('patches', 'patch', 'patch')):
            for index, artist in enumerate(getattr(ax, attr)):
                if id(artist) in contained:
                    continue
                actual_kind = kind
                if kind == 'scatter' and not isinstance(artist, PathCollection):
                    actual_kind = 'collection'
                result.append(dict(name=f'ax{ai}.{name if actual_kind == kind else actual_kind}',
                                   label=artist.get_label(), expr=f'{prefix}.{attr}[{index}]',
                                   artist=artist, kind=actual_kind))
        for ci, container in enumerate(ax.containers):
            if type(container).__name__ == 'BarContainer':
                result.append(dict(name=f'ax{ai}.bar', label=container.get_label(),
                                   expr=f'{prefix}.containers[{ci}]', artist=container, kind='bar'))
            else:
                # Keep explicit container members accessible without recursive internals.
                for child in container.get_children():
                    if isinstance(child, Line2D) and child in ax.lines:
                        index = list(ax.lines).index(child)
                        result.append(dict(name=f'ax{ai}.plot', label=child.get_label(),
                                           expr=f'{prefix}.lines[{index}]', artist=child, kind='plot'))
        for prop, artist in (('title', ax.title), ('xaxis.label', ax.xaxis.label), ('yaxis.label', ax.yaxis.label)):
            if artist.get_text():
                name = {'title': 'set_title', 'xaxis.label': 'set_xlabel', 'yaxis.label': 'set_ylabel'}[prop]
                result.append(dict(name=f'ax{ai}.{name}', label=artist.get_text(),
                                   expr=f'{prefix}.{prop}', artist=artist, kind='text', call=name))
        if ax.get_legend() is not None:
            result.append(dict(name=f'ax{ai}.legend', label='', expr=f'{prefix}.get_legend()',
                               artist=ax.get_legend(), kind='legend'))
    for i, artist in enumerate(fig.texts):
        result.append(dict(name='fig.text', label=artist.get_text(), expr=f'fig.texts[{i}]', artist=artist, kind='text'))
    for i, artist in enumerate(fig.legends):
        result.append(dict(name='fig.legend', label='', expr=f'fig.legends[{i}]', artist=artist, kind='legend'))
    return result


def parameters(actor):
    from matplotlib.axes import Axes
    from matplotlib.legend import Legend
    kind, artist = actor['kind'], actor['artist']
    result = {}

    def add(name, value=None, hint='', editable=True):
        try:
            value = json_value(value)
        except ValueError:
            value, editable = None, False
            hint = 'Python object: keep this parameter in your plotting code.'
        result[name] = dict(name=name, value=value, hint=hint, editable=editable)

    if kind == 'bar':
        patches = artist.patches
        for name, value in [('x', [p.get_x() + p.get_width()/2 for p in patches]),
                            ('height', [p.get_height() for p in patches]),
                            ('width', [p.get_width() for p in patches]),
                            ('bottom', [p.get_y() for p in patches])]:
            add(name, value)
        add('align', 'center', 'Recovered bars use center coordinates.')
        artist = patches[0] if patches else None
    if artist is None:
        return list(result.values())
    inspector = ArtistInspector(artist)
    getters = {}
    for name in inspector.get_setters():
        if name == 'constrained_layout_pads':
            continue
        getter = getattr(artist, 'get_' + name, None)
        try:
            getters[name] = getter() if getter else None
        except Exception:
            getters[name] = None
    if kind == 'figure':
        engine = artist.get_layout_engine()
        special = {'figsize': artist.get_size_inches(), 'layout': 'constrained' if engine and 'Constrained' in type(engine).__name__ else 'tight' if engine else 'none'}
        for name, param in inspect.signature(Figure).parameters.items():
            if param.kind == param.VAR_KEYWORD:
                continue
            add(name, special.get(name, getters.get(name, None)), str(param), name not in OBJECT_PARAMETERS)
        for name in ('num', 'clear', 'FigureClass'):
            add(name, None, 'Figure creation/identity option; specify in plt.figure before opening the editor.', False)
        # Figure's **kwargs are Artist properties, not arbitrary Axes properties.
        names = set(ArtistInspector(mpl.artist.Artist).get_setters()) - {'mouseover'}
    elif kind == 'plot':
        add('x', artist.get_xdata()); add('y', artist.get_ydata())
        add('fmt', '', 'Optional plot format, e.g. ro--. The original format string is not retained.')
        add('scalex', artist.axes.get_autoscalex_on()); add('scaley', artist.axes.get_autoscaley_on())
        add('data', None, 'Data lookup has already been resolved; edit x and y directly.', False)
        names = set(getters) - {'xdata', 'ydata', 'data'}
    elif kind == 'scatter':
        offsets = artist.get_offsets()
        special = {'x': offsets[:, 0], 'y': offsets[:, 1], 's': artist.get_sizes(),
                   'c': artist.get_array() if artist.get_array() is not None else artist.get_facecolors(),
                   'marker': marker_name(artist), 'cmap': artist.get_cmap().name,
                   'norm': {'Normalize': 'linear', 'LogNorm': 'log', 'SymLogNorm': 'symlog'}.get(type(artist.norm).__name__, artist.norm), 'vmin': artist.get_clim()[0], 'vmax': artist.get_clim()[1],
                   'linewidths': artist.get_linewidths(), 'edgecolors': artist.get_edgecolors(),
                   'alpha': artist.get_alpha(), 'plotnonfinite': None}
        for name, param in inspect.signature(Axes.scatter).parameters.items():
            if name == 'self' or param.kind == param.VAR_KEYWORD:
                continue
            hint = 'Constructor-only information is not retained by an existing scatter; set this in the original call.' if name in {'data', 'colorizer', 'plotnonfinite'} else str(param)
            add(name, special.get(name), hint, name not in {'data', 'colorizer', 'plotnonfinite'})
        names = set(getters) - {'sizes', 'offsets', 'array', 'paths', 'cmap', 'norm', 'alpha', 'clim', 'linewidth', 'edgecolor', 'facecolor'}
    elif kind == 'text':
        text_name = {'set_title': 'label', 'set_xlabel': 'xlabel', 'set_ylabel': 'ylabel'}.get(actor.get('call'), 's')
        add('x', artist.get_position()[0]); add('y', artist.get_position()[1]); add(text_name, artist.get_text())
        add('fontdict', {}, 'Dictionary of Text properties.')
        names = set(getters) - {'text', 'position'}
    elif kind == 'imshow':
        add('X', artist.get_array())
        add('cmap', artist.get_cmap().name)
        add('vmin', artist.get_clim()[0]); add('vmax', artist.get_clim()[1])
        add('aspect', artist.axes.get_aspect())
        for name, param in inspect.signature(Axes.imshow).parameters.items():
            if name in {'self', 'kwargs'} or name in result:
                continue
            value = getattr(artist, 'get_' + name, lambda: param.default if param.default is not param.empty else None)()
            if name == 'origin':
                value = artist.origin
            add(name, value, str(param), name not in {'data', 'colorizer'})
        names = set(getters) - {'data', 'array', 'cmap', 'clim'}
    elif kind == 'legend':
        for name, param in inspect.signature(Legend).parameters.items():
            if name in {'parent', 'handles', 'labels'} or param.kind == param.VAR_KEYWORD:
                continue
            value = getters.get(name, param.default if param.default is not param.empty else None)
            if name == 'fontsize' and artist.get_texts():
                value = artist.get_texts()[0].get_fontsize()
            if name == 'title':
                value = artist.get_title().get_text()
            add(name, value, str(param), name in {'loc', 'title', 'fontsize', 'frameon', 'ncols', 'alignment', 'draggable'})
        names = set()
    else:
        names = set(getters)
    for name in sorted(names - set(result)):
        hint = inspector.get_valid_values(name)
        getter = getattr(artist, 'get_' + name, None)
        add(name, getters.get(name), hint, getter is not None and name not in OBJECT_PARAMETERS)
    return list(result.values())


def commands(actor, name, value):
    """Export the same Matplotlib operations used for the live preview."""
    kind = actor['kind']
    if kind in {'scatter', 'collection'} and name == 'linestyle' and isinstance(value, list):
        value = [(item[0], None if item[1] is None else tuple(item[1])) for item in value]
    v = repr(value)
    if name == 'sketch_params' and isinstance(value, list):
        return [f'a.set_sketch_params(*{v})']
    if kind == 'figure':
        mapping = {'figsize': 'size_inches', 'layout': 'layout_engine'}
        return [f"a.set_{mapping.get(name, name)}({v})"]
    if kind == 'plot':
        if name in {'x', 'y'}:
            return [f'a.set_{name}data({v})']
        if name in {'scalex', 'scaley'}:
            dim = name[-1]
            return [f'a.axes.set_autoscale{dim}_on({v})', 'a.axes.relim()', f'a.axes.autoscale_view(scalex={dim == "x"}, scaley={dim == "y"})']
        if name == 'fmt':
            return [f'_sample = a.axes.plot([], [], {v})[0]',
                    'a.set(color=_sample.get_color(), marker=_sample.get_marker(), linestyle=_sample.get_linestyle())', '_sample.remove()']
    if kind == 'scatter':
        if name in {'x', 'y'}:
            return ['_offsets = np.array(a.get_offsets(), copy=True)', f'_offsets[:, {0 if name == "x" else 1}] = {v}', 'a.set_offsets(_offsets)']
        if name == 's':
            if value is not None and np.size(value) not in {1, len(actor['artist'].get_offsets())}:
                raise ValueError('s must be a scalar or contain one size per point')
            return [f'a.set_sizes(np.atleast_1d({v}))']
        if name == 'c':
            if isinstance(value, list) and value and all(isinstance(item, (int, float)) for item in value):
                if len(value) == len(actor['artist'].get_offsets()):
                    return [f'a.set_array(np.asarray({v}))', 'a.autoscale_None()']
                if len(value) not in {3, 4}:
                    raise ValueError('c must contain one number per point or a valid color')
            return ['a.set_array(None)', f'a.set_facecolor({v})']
        if name == 'marker':
            return [f'_marker = MarkerStyle({v})', 'a.set_paths([_marker.get_path().transformed(_marker.get_transform())])']
        if name in {'linewidths', 'edgecolors'}:
            return [f'a.set_{name}({v})']
    if kind in {'scatter', 'imshow'} and name in {'vmin', 'vmax'}:
        return [f'a.set_clim({name}={v})']
    if kind == 'text':
        if name in {'x', 'y'}:
            return [f'a.set_{name}({v})']
        text_name = {'set_title': 'label', 'set_xlabel': 'xlabel', 'set_ylabel': 'ylabel'}.get(actor.get('call'), 's')
        if name == text_name:
            return [f'a.set_text({v})']
        if name == 'fontdict':
            return [f'a.update({v})']
    if kind == 'imshow':
        if name == 'X':
            return [f'a.set_data({v})']
        if name == 'aspect':
            return [f'a.axes.set_aspect({v})']
        if name == 'origin':
            if value not in {'upper', 'lower'}:
                raise ValueError('origin must be upper or lower')
            return [f'a.origin = {v}']
    if kind == 'legend' and name == 'fontsize':
        return [f'for _text in a.get_texts(): _text.set_fontsize({v})']
    if kind == 'bar':
        if name in {'x', 'height', 'width', 'bottom'}:
            attr = {'x': 'x', 'height': 'height', 'width': 'width', 'bottom': 'y'}[name]
            expression = '_value - _patch.get_width()/2' if name == 'x' else '_value'
            return [f'_values = np.broadcast_to({v}, (len(a.patches),))',
                    f'for _patch, _value in zip(a.patches, _values): _patch.set_{attr}({expression})']
        if name == 'align':
            if value != 'center':
                raise ValueError('Existing bars use center x coordinates. Change x to reposition them.')
            return []
        return [f'for _patch in a.patches: _patch.set_{name}({v})']
    return [f'a.set_{name}({v})']
