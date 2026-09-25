"""Call-style controls for existing figures, rcParams, and code export."""

import base64
import copy
import io

import matplotlib as mpl
import numpy as np
from cycler import cycler
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.collections import PathCollection
from matplotlib.markers import MarkerStyle
from matplotlib.text import Text

from .parameters import actors, commands, json_value, parameters
from .rc import READ_ONLY, decode_rc, rc_commands, rc_parameters


DEMO_SOURCE = '''import numpy as np
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
x = np.linspace(0, 2 * np.pi, 120)
ax.plot(x, np.sin(x), color="#6366f1", linewidth=2.5, label="Sine")
ax.scatter(x[::8], np.cos(x[::8]), s=45, color="#14b8a6", label="Samples")
ax.set(title="Make this figure yours", xlabel="Time (s)", ylabel="Amplitude")
ax.grid(True, alpha=0.2)
ax.legend()
'''


def demo_figure():
    namespace = {}
    exec(DEMO_SOURCE, namespace)
    return namespace['fig']


class Editor:
    def __init__(self, figure, *, demo=False):
        self.initial = copy.deepcopy(figure)
        self.definitions = actors(self.initial)
        self.baseline_rc = mpl.rcParams.copy()
        self.actions = []
        self.demo = demo
        self.figure, self.preview, self.settings = self.rebuild([])

    @staticmethod
    def render(fig):
        width, height = fig.get_size_inches() * fig.dpi
        if not (0 < width <= 5000 and 0 < height <= 5000 and width * height <= 16_000_000):
            raise ValueError('Preview must be positive, at most 5000 pixels per side and 16 megapixels')
        buffer = io.BytesIO()
        FigureCanvasAgg(fig).print_png(buffer)
        return 'data:image/png;base64,' + base64.b64encode(buffer.getvalue()).decode()

    def tree(self):
        result = []
        for index, actor in enumerate(self.entries()):
            artist = actor['artist']
            label = artist.get_text() if isinstance(artist, Text) else artist.get_label()
            if not isinstance(label, str) or label.startswith('_'):
                label = ''
            result.append(dict(path=[index], depth=0, name=actor['name'] + '(…)', label=label[:90]))
        return result

    def entries(self):
        # Expressions are generated from the original figure, never from requests.
        # Keep identities stable even when a title or label is cleared by the user.
        return [dict(actor, artist=eval(actor['expr'], {'fig': self.figure}))
                for actor in self.definitions]

    def program(self, actions):
        rc = {a['property']: a['value'] for a in actions if a.get('scope') == 'rc'}
        lines = []
        for key, value in rc.items():
            lines.extend(rc_commands(key, value))
        definitions = self.definitions
        resets = {(tuple(a['path']), a['property']): index for index, a in enumerate(actions)
                  if a.get('reset') and a.get('scope') != 'rc'}
        for index, action in enumerate(actions):
            if action.get('scope') == 'rc':
                continue
            if action.get('reset') or index < resets.get((tuple(action['path']), action['property']), -1):
                continue
            actor = definitions[action['path'][0]]
            lines.append('a = ' + actor['expr'])
            lines.extend(commands(actor, action['property'], action['value']))
        return rc, lines

    def rebuild(self, actions):
        rc, lines = self.program(actions)
        settings = self.baseline_rc.copy()
        settings.update({key: decode_rc(key, value) for key, value in rc.items()})
        trial = copy.deepcopy(self.initial)
        namespace = dict(fig=trial, np=np, Text=Text, PathCollection=PathCollection,
                         MarkerStyle=MarkerStyle, cycler=cycler)
        with mpl.rc_context(settings):
            exec('\n'.join(lines), namespace)
            preview = self.render(trial)
        return trial, preview, settings

    def code(self):
        rc, lines = self.program(self.actions)
        imports = ('import matplotlib.pyplot as plt\nimport numpy as np\nfrom cycler import cycler\n'
                   'from matplotlib.text import Text\nfrom matplotlib.markers import MarkerStyle\n'
                   'from matplotlib.collections import PathCollection\n')
        output = [imports, '# Apply to the same original figure construction.', 'def apply_settings(fig):']
        for key, value in rc.items():
            literal = f'cycler(**{value!r})' if key == 'axes.prop_cycle' else repr(value)
            output.append(f'    plt.rcParams[{key!r}] = {literal}')
        for line in lines:
            output.extend('    ' + part for part in line.splitlines())
        output += ['    fig.canvas.draw()', '    return fig', '']
        code = '\n'.join(output)
        return (DEMO_SOURCE + '\n' + code + '\napply_settings(fig)\nplt.show()\n') if self.demo else code

    def state(self, path=None):
        entries = self.entries()
        index = path[0] if isinstance(path, list) and len(path) == 1 and type(path[0]) is int else 0
        if not 0 <= index < len(entries):
            index = 0
        return dict(tree=self.tree(), selected=[index], properties=parameters(entries[index]),
                    rc_properties=rc_parameters(self.settings), preview=self.preview,
                    code=self.code(), edits=len(self.actions))

    def edit(self, action):
        if not isinstance(action, dict):
            raise ValueError('Expected an edit object')
        name = action.get('property')
        value = json_value(action.get('value'))
        if action.get('scope') == 'rc':
            if name not in self.baseline_rc or name in READ_ONLY:
                raise ValueError('This rcParam is not editable in the running editor')
            candidate = dict(scope='rc', property=name, value=value)
        else:
            path = action.get('path')
            entries = self.entries()
            if not isinstance(path, list) or len(path) != 1 or type(path[0]) is not int or not 0 <= path[0] < len(entries):
                raise ValueError('Invalid plot selection')
            prop = next((p for p in parameters(entries[path[0]]) if p['name'] == name), None)
            if prop is None or not prop['editable']:
                raise ValueError('This parameter must be specified in the original Python plotting code')
            candidate = dict(path=path, property=name, value=value)
            if action.get('reset') is True:
                candidate['reset'] = True
        actions = self.actions + [candidate]
        figure, preview, settings = self.rebuild(actions)
        self.figure, self.preview, self.settings, self.actions = figure, preview, settings, actions

    def undo(self, reset=False):
        actions = [] if reset else self.actions[:-1]
        figure, preview, settings = self.rebuild(actions)
        self.figure, self.preview, self.settings, self.actions = figure, preview, settings, actions
