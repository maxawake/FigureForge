"""Build figures from named Python data and a declarative plotting recipe."""

import copy
import inspect
from collections.abc import Mapping

import matplotlib as mpl
import numpy as np
from matplotlib.artist import ArtistInspector
from matplotlib.axes import Axes
from matplotlib.collections import PathCollection, PolyCollection
from matplotlib.figure import Figure
from matplotlib.image import AxesImage
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

from .editor import Editor
from .parameters import json_value
from .rc import READ_ONLY, decode_rc, rc_parameters


# Positional inputs are deliberately explicit: the browser never submits Python.
FUNCTIONS = {
    'plot': dict(positional=['x', 'y'], required=['y'], optional=[], artist=Line2D),
    'scatter': dict(positional=['x', 'y'], required=['x', 'y'], optional=['s', 'c'], artist=PathCollection),
    'imshow': dict(positional=['X'], required=['X'], optional=[], artist=AxesImage),
    'hist': dict(positional=['x'], required=['x'], optional=['weights'], artist=Rectangle),
    'bar': dict(positional=['x', 'height'], required=['x', 'height'], optional=['width', 'bottom', 'xerr', 'yerr'], artist=Rectangle),
    'barh': dict(positional=['y', 'width'], required=['y', 'width'], optional=['height', 'left', 'xerr', 'yerr'], artist=Rectangle),
    'step': dict(positional=['x', 'y'], required=['x', 'y'], optional=[], artist=Line2D),
    'errorbar': dict(positional=['x', 'y'], required=['x', 'y'], optional=['xerr', 'yerr'], artist=Line2D),
    'fill_between': dict(positional=['x', 'y1'], required=['x', 'y1'], optional=['y2', 'where'], artist=PolyCollection),
    'contour': dict(positional=['Z'], required=['Z'], optional=[], artist=None),
    'contourf': dict(positional=['Z'], required=['Z'], optional=[], artist=None),
    'pcolormesh': dict(positional=['C'], required=['C'], optional=[], artist=None),
}
OBJECT_ONLY = {'agg_filter', 'clip_box', 'clip_path', 'figure', 'transform', 'offset_transform',
               'path_effects', 'colorizer', 'paths'}
FIGURE_DEFAULTS = {'figsize': None, 'dpi': None, 'facecolor': None, 'edgecolor': None,
                   'frameon': True, 'layout': 'constrained'}
AXES_DEFAULTS = {'title': '', 'xlabel': '', 'ylabel': '', 'legend': True,
                 'legend_loc': 'best', 'grid': False, 'xscale': 'linear', 'yscale': 'linear',
                 'xlim': None, 'ylim': None, 'aspect': 'auto'}
PREFERRED = ['label', 'color', 'linewidth', 'linestyle', 'marker', 'markersize', 'alpha',
             's', 'c', 'cmap', 'vmin', 'vmax', 'bins', 'density', 'origin', 'interpolation']


def demo_data():
    x = np.linspace(0, 2 * np.pi, 120)
    return {'time': x, 'sine': np.sin(x), 'cosine': np.cos(x),
            'image': np.outer(np.sin(x[::4]), np.cos(x[::4]))}


def function_properties(name):
    spec = FUNCTIONS[name]
    props = {}
    for key, parameter in inspect.signature(getattr(Axes, name)).parameters.items():
        if key in {'self', 'data'} or parameter.kind in {parameter.VAR_POSITIONAL, parameter.VAR_KEYWORD}:
            continue
        if key in spec['positional']:
            continue
        value = parameter.default if parameter.default is not parameter.empty else None
        try:
            value = json_value(value)
        except ValueError:
            value = None
        props[key] = dict(name=key, value=value, hint=str(parameter), editable=key not in OBJECT_ONLY)
    if spec['artist']:
        inspector = ArtistInspector(spec['artist'])
        for key in inspector.get_setters():
            if key in {'data', 'xdata', 'ydata', 'array', 'offsets', 'sizes'} or key in props:
                continue
            props[key] = dict(name=key, value='' if key == 'label' else None,
                              hint=inspector.get_valid_values(key), editable=key not in OBJECT_ONLY)
    # These are accepted by the contour/mesh constructors through **kwargs.
    if name in {'contour', 'contourf', 'pcolormesh'}:
        for key in ['cmap', 'norm', 'vmin', 'vmax', 'alpha'] + (['levels', 'colors', 'linewidths', 'linestyles'] if name.startswith('contour') else ['shading', 'edgecolors', 'linewidth']):
            props.setdefault(key, dict(name=key, value=None, hint='Matplotlib ' + name + ' parameter', editable=True))
    # A fmt string is useful but is positional only for plot/step.
    if name in {'plot', 'step'}:
        props['fmt'] = dict(name='fmt', value='', hint='Format string, for example ro--', editable=True)
    for key in spec['optional']:
        props.setdefault(key, dict(name=key, value=None, hint='Literal value, or choose a data key above.', editable=True))
    for prop in props.values():
        if prop['name'] in {'label', 'color', 'linestyle', 'marker', 'cmap', 'norm', 'origin', 'interpolation', 'fmt', 'drawstyle', 'shading', 'hatch'}:
            prop['input_type'] = 'text'
    return sorted(props.values(), key=lambda p: (PREFERRED.index(p['name']) if p['name'] in PREFERRED else len(PREFERRED), p['name']))


class BuilderEditor:
    """Transactional recipe editor. Data stays on the Python side."""

    def __init__(self, data):
        if not isinstance(data, Mapping) or not all(isinstance(key, str) for key in data):
            raise TypeError('run(data) expects a dictionary with string keys, e.g. {"x": x, "y": y}')
        self.data = copy.deepcopy(dict(data))
        self.baseline_rc = mpl.rcParams.copy()
        self.config = dict(figure={}, axes={}, rc={}, layers=[])
        self.history = []
        self.next_id = 1
        self.selected = [0]
        self.figure, self.preview, self.settings = self.build(self.config)

    def validate_bindings(self, name, bindings):
        spec = FUNCTIONS[name]
        if not isinstance(bindings, dict):
            raise ValueError('Data bindings must be an object')
        allowed = set(spec['positional'] + spec['optional'])
        if set(bindings) - allowed:
            raise ValueError('Unknown data input')
        for parameter, key in bindings.items():
            if not isinstance(key, str) or key not in self.data:
                raise ValueError(f'Unknown data key for {parameter}: {key!r}')
        missing = set(spec['required']) - bindings.keys()
        if missing:
            raise ValueError('Choose a data key for ' + ', '.join(sorted(missing)))

    @staticmethod
    def call_parts(layer, resolve):
        name, bindings = layer['function'], layer['bindings']
        args = [resolve(bindings[key]) for key in FUNCTIONS[name]['positional'] if key in bindings]
        kwargs = dict(layer['kwargs'])
        for key in FUNCTIONS[name]['optional']:
            if key in bindings:
                kwargs[key] = resolve(bindings[key])
        if name in {'plot', 'step'} and 'fmt' in kwargs:
            args.append(kwargs.pop('fmt'))
        return args, kwargs

    def build(self, config):
        settings = self.baseline_rc.copy()
        settings.update({k: decode_rc(k, v) for k, v in config['rc'].items()})
        with mpl.rc_context(settings):
            fig = Figure(**({'layout': 'constrained'} | config['figure']))
            # Validate dimensions before any renderer allocates a pixel buffer.
            width, height = fig.get_size_inches() * fig.dpi
            if not (0 < width <= 5000 and 0 < height <= 5000 and width * height <= 16_000_000):
                raise ValueError('Preview dimensions exceed the 5000-pixel / 16-megapixel limit')
            ax = fig.subplots()
            for layer in config['layers']:
                self.validate_bindings(layer['function'], layer['bindings'])
                args, kwargs = self.call_parts(layer, self.data.__getitem__)
                getattr(ax, layer['function'])(*args, **kwargs)
            for key, value in config['axes'].items():
                if key not in {'legend', 'legend_loc', 'grid'}:
                    getattr(ax, 'set_' + key)(value)
            if 'grid' in config['axes']:
                ax.grid(config['axes']['grid'])
            if config['axes'].get('legend', True) and ax.get_legend_handles_labels()[1]:
                ax.legend(loc=config['axes'].get('legend_loc', 'best'))
            preview = Editor.render(fig)
        return fig, preview, settings

    def code(self):
        lines = ['import matplotlib.pyplot as plt', 'from cycler import cycler', '',
                 'def make_figure(data):', '    """Build the figure from your named data dictionary."""']
        rc = '{' + ', '.join(f'{key!r}: ' + (f'cycler(**{value!r})' if key == 'axes.prop_cycle' else repr(value)) for key, value in self.config['rc'].items()) + '}'
        lines.append(f'    with plt.rc_context({rc}):')
        figure = {'layout': 'constrained'} | self.config['figure']
        lines.append('        fig, ax = plt.subplots(' + ', '.join(f'{k}={v!r}' for k, v in figure.items()) + ')')
        for layer in self.config['layers']:
            # Separate key references from literal keyword values in exported code.
            bindings, name = layer['bindings'], layer['function']
            args = [f'data[{bindings[key]!r}]' for key in FUNCTIONS[name]['positional'] if key in bindings]
            kwargs = {key: repr(value) for key, value in layer['kwargs'].items()}
            for key in FUNCTIONS[name]['optional']:
                if key in bindings:
                    kwargs[key] = f'data[{bindings[key]!r}]'
            if name in {'plot', 'step'} and 'fmt' in kwargs:
                args.append(kwargs.pop('fmt'))
            args.extend(f'{key}={value}' for key, value in kwargs.items())
            lines.append(f'        ax.{name}(' + ', '.join(args) + ')')
        for key, value in self.config['axes'].items():
            if key not in {'legend', 'legend_loc', 'grid'}:
                lines.append(f'        ax.set_{key}({value!r})')
        if 'grid' in self.config['axes']:
            lines.append(f'        ax.grid({self.config["axes"]["grid"]!r})')
        if self.config['axes'].get('legend', True):
            lines += ['        if ax.get_legend_handles_labels()[1]:',
                      f'            ax.legend(loc={self.config["axes"].get("legend_loc", "best")!r})']
        lines += ['        fig.canvas.draw()', '    return fig', '',
                  '# Pass the same dictionary used in figureforge.run(data):',
                  '# fig = make_figure(data)', '# plt.show()', '']
        return '\n'.join(lines)

    def state(self, path=None):
        valid = [[0], [-1]] + [[layer['id']] for layer in self.config['layers']]
        if path in valid:
            self.selected = path
        if self.selected not in valid:
            self.selected = [0]
        tree = [dict(path=[0], depth=0, name='Figure', label='Size & layout'),
                dict(path=[-1], depth=0, name='Labels & axes', label='Title, labels, legend & grid')]
        tree += [dict(path=[layer['id']], depth=0, name=layer['function'] + '(…)', label=layer['kwargs'].get('label', '') or ', '.join(layer['bindings'].values())) for layer in self.config['layers']]
        layer = next((item for item in self.config['layers'] if [item['id']] == self.selected), None)
        if layer:
            properties = function_properties(layer['function'])
            for prop in properties:
                if prop['name'] in layer['kwargs']:
                    prop['value'] = layer['kwargs'][prop['name']]
                prop['explicit'] = prop['name'] in layer['kwargs']
                if prop['name'] in layer['bindings']:
                    prop['hint'] = 'Currently bound to data[' + repr(layer['bindings'][prop['name']]) + ']. Entering a literal replaces that binding.'
        else:
            scope = 'figure' if self.selected == [0] else 'axes'
            defaults = FIGURE_DEFAULTS if scope == 'figure' else AXES_DEFAULTS
            properties = [dict(name=k, value=self.config[scope].get(k, v), hint='Matplotlib ' + scope + ' parameter', editable=True, explicit=k in self.config[scope]) for k, v in defaults.items()]
            if scope == 'figure':
                for prop in properties:
                    if prop['value'] is None and prop['name'] in {'figsize', 'dpi', 'facecolor', 'edgecolor'}:
                        prop['value'] = json_value(self.settings['figure.' + prop['name']])
        datasets = []
        for key, value in self.data.items():
            try:
                array = np.asarray(value)
                description = f'{array.dtype} · shape {array.shape}'
            except (TypeError, ValueError):
                description = type(value).__name__
            datasets.append(dict(key=key, description=description))
        functions = {name: {k: v for k, v in spec.items() if k != 'artist'} for name, spec in FUNCTIONS.items()}
        return dict(builder=True, tree=tree, selected=self.selected, properties=properties,
                    rc_properties=rc_parameters(self.settings), datasets=datasets, functions=functions,
                    layer=copy.deepcopy(layer), preview=self.preview, code=self.code(), edits=len(self.history))

    def edit(self, action):
        if not isinstance(action, dict):
            raise ValueError('Expected an edit object')
        trial = copy.deepcopy(self.config)
        selected = self.selected
        op = action.get('op')
        if op == 'add':
            name = action.get('function')
            if name not in FUNCTIONS:
                raise ValueError('Unsupported plot function')
            bindings = action.get('bindings', {})
            self.validate_bindings(name, bindings)
            trial['layers'].append(dict(id=self.next_id, function=name, bindings=bindings, kwargs={}))
            selected = [self.next_id]
        else:
            path = action.get('path', self.selected)
            layer = next((item for item in trial['layers'] if path == [item['id']]), None)
            if op == 'remove':
                if layer is None:
                    raise ValueError('Select a plot to remove')
                trial['layers'].remove(layer)
                selected = [0]
            elif op == 'bind':
                if layer is None:
                    raise ValueError('Select a plot to bind')
                self.validate_bindings(layer['function'], action.get('bindings'))
                layer['bindings'] = dict(action['bindings'])
                for key in layer['bindings']:
                    layer['kwargs'].pop(key, None)
            else:
                name = action.get('property')
                value = json_value(action.get('value'))
                if action.get('scope') == 'rc':
                    if name not in self.baseline_rc or name in READ_ONLY:
                        raise ValueError('This rcParam is not editable')
                    target = trial['rc']
                elif path == [0] or path == [-1]:
                    scope = 'figure' if path == [0] else 'axes'
                    if name not in (FIGURE_DEFAULTS if scope == 'figure' else AXES_DEFAULTS):
                        raise ValueError('Unknown parameter')
                    target = trial[scope]
                elif layer:
                    prop = next((p for p in function_properties(layer['function']) if p['name'] == name), None)
                    if prop is None or not prop['editable']:
                        raise ValueError('Unsupported parameter')
                    target = layer['kwargs']
                    if name in FUNCTIONS[layer['function']]['optional']:
                        layer['bindings'].pop(name, None)
                else:
                    raise ValueError('Select a figure, axes, or plot')
                if action.get('reset'):
                    target.pop(name, None)
                else:
                    target[name] = value
        figure, preview, settings = self.build(trial)
        self.history.append(self.config)
        self.config, self.figure, self.preview, self.settings = trial, figure, preview, settings
        self.selected = selected
        if op == 'add':
            self.next_id += 1

    def undo(self, reset=False):
        target = dict(figure={}, axes={}, rc={}, layers=[]) if reset else self.history[-1] if self.history else self.config
        figure, preview, settings = self.build(target)
        self.config, self.figure, self.preview, self.settings = copy.deepcopy(target), figure, preview, settings
        if reset:
            self.history.clear()
        elif self.history:
            self.history.pop()
