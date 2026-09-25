"""Run with: python -m unittest discover -s tests -v."""

import copy
import io
import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use("Agg")
import numpy as np
from matplotlib.figure import Figure

from figureforge.editor import Editor
from figureforge.main import make_server


def figure():
    fig = Figure(figsize=(5, 3))
    ax = fig.subplots()
    ax.plot([1, 2, 3], [2, 4, 3], label="Signal")
    ax.scatter([1, 2], [3, 2])
    ax.bar([1, 2], [.5, .8])
    ax.set_title("Original")
    ax.legend()
    return fig


class EditorTests(unittest.TestCase):
    def setUp(self):
        self.original = figure()
        self.editor = Editor(self.original)

    def path(self, name, label=None):
        return next(node['path'] for node in self.editor.tree()
                    if name + '(…)' in node['name'] and (label is None or node['label'] == label))

    def edit(self, name, prop, value, label=None):
        self.editor.edit(dict(path=self.path(name, label), property=prop, value=value))

    def test_export_reproduces_pixels_and_does_not_modify_input(self):
        self.edit('plot', 'color', '#e34a78', 'Signal')
        self.edit('plot', 'linewidth', 4, 'Signal')
        self.edit('set_title', 'label', 'Edited "title"\nwith newline')
        self.edit('scatter', 's', 160)
        self.edit('figure', 'figsize', [6, 4])
        exported = {}
        exec(self.editor.code(), exported)
        replica = copy.deepcopy(self.original)
        exported['apply_settings'](replica)
        self.assertEqual(Editor.render(replica), self.editor.preview)
        self.assertEqual(self.original.axes[0].lines[0].get_linewidth(), 1.5)
        self.assertEqual(self.original.axes[0].get_title(), 'Original')

    def test_only_defined_plot_objects_and_call_parameters(self):
        names = [node['name'] for node in self.editor.tree()]
        self.assertEqual(names, ['plt.figure(…)', 'ax0.plot(…)', 'ax0.scatter(…)',
                                 'ax0.bar(…)', 'ax0.set_title(…)', 'ax0.legend(…)'])
        props = {p['name'] for p in self.editor.state(self.path('scatter'))['properties']}
        self.assertTrue({'x', 'y', 's', 'c', 'marker', 'cmap', 'norm', 'vmin', 'vmax', 'plotnonfinite', 'data'} <= props)
        self.assertNotIn('sizes', props)
        self.assertNotIn('offsets', props)
        props = {p['name'] for p in self.editor.state(self.path('figure'))['properties']}
        self.assertIn('figsize', props)
        self.assertNotIn('figwidth', props)

    def test_rc_params_are_separate_live_and_do_not_leak(self):
        original_size = matplotlib.rcParams['font.size']
        self.editor.edit(dict(scope='rc', property='font.size', value=21))
        self.assertEqual(self.editor.figure.axes[0].title.get_fontsize(), 21)
        self.assertEqual(matplotlib.rcParams['font.size'], original_size)
        self.assertTrue(any(p['name'] == 'axes.prop_cycle' for p in self.editor.state()['rc_properties']))
        self.edit('plot', 'linewidth', 7)
        self.editor.edit(dict(scope='rc', property='lines.linewidth', value=3))
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 7)
        with matplotlib.rc_context():
            exported = {}
            exec(self.editor.code(), exported)
            replica = copy.deepcopy(self.original)
            exported['apply_settings'](replica)
            self.assertEqual(Editor.render(replica), self.editor.preview)

    def test_invalid_edit_is_atomic(self):
        before = self.editor.preview
        for action in [dict(path=self.path('plot'), property='color', value='not-a-color'),
                       dict(path=[0], property='figsize', value=[100000, 100000]),
                       dict(scope='rc', property='font.size', value='not-a-number'),
                       dict(scope='rc', property='backend', value='QtAgg')]:
            with self.assertRaises((ValueError, TypeError)):
                self.editor.edit(action)
            self.assertEqual(self.editor.preview, before)
            self.assertEqual(self.editor.actions, [])

    def test_undo_reset_and_stable_selection(self):
        initial = self.editor.preview
        title_path = self.path('set_title')
        self.editor.edit(dict(path=title_path, property='label', value=''))
        self.editor.edit(dict(path=title_path, property='label', value='Restored'))
        self.assertEqual(self.editor.figure.axes[0].get_title(), 'Restored')
        self.editor.undo()
        self.assertEqual(self.editor.figure.axes[0].get_title(), '')
        self.editor.undo(reset=True)
        self.assertEqual(self.editor.preview, initial)

    def test_scatter_native_parameters(self):
        self.edit('scatter', 's', 95)
        self.edit('scatter', 'c', [1, 4])
        self.edit('scatter', 'cmap', 'plasma')
        self.edit('scatter', 'marker', 's')
        self.edit('scatter', 'vmin', 0)
        self.edit('scatter', 'vmax', 8)
        self.edit('scatter', 'norm', 'linear')
        scatter = self.editor.figure.axes[0].collections[0]
        self.assertEqual(scatter.get_sizes()[0], 95)
        self.assertEqual(scatter.get_cmap().name, 'plasma')
        np.testing.assert_allclose(scatter.get_array(), [1, 4])

    def test_parameter_reset_uses_global_value_and_is_undoable(self):
        self.edit('plot', 'linewidth', 7)
        self.editor.edit(dict(scope='rc', property='lines.linewidth', value=3))
        self.editor.edit(dict(path=self.path('plot'), property='linewidth', reset=True))
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 3)
        self.assertNotIn('set_linewidth(7)', self.editor.code())
        self.editor.undo()
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 7)

    def test_property_cycle_and_multiple_axes(self):
        second = self.original.add_subplot(212)
        second.plot([1, 2], [3, 4])
        self.editor = Editor(self.original)
        self.editor.edit(dict(scope='rc', property='axes.prop_cycle', value={'color': ['red', 'blue']}))
        for ax in self.editor.figure.axes:
            self.assertEqual(ax.lines[0].get_color(), 'red')
        self.assertTrue(any(n['name'] == 'ax1.plot(…)' for n in self.editor.tree()))
        self.editor.undo(reset=True)
        self.assertEqual(len(self.editor.actions), 0)

    def test_injection_and_invalid_paths_are_rejected(self):
        for path, name in [([0], '__class__'), ([-1], 'visible')]:
            with self.assertRaises(ValueError):
                self.editor.edit(dict(path=path, property=name, value='x'))

    def test_demo_is_standalone(self):
        from figureforge.editor import demo_figure
        editor = Editor(demo_figure(), demo=True)
        editor.edit(dict(path=[0], property='figsize', value=[7, 4]))
        namespace = {}
        with patch('matplotlib.pyplot.show'):
            exec(editor.code(), namespace)
        np.testing.assert_allclose(namespace['fig'].get_size_inches(), editor.figure.get_size_inches())


class ServerTests(unittest.TestCase):
    def test_http_handlers_without_network(self):
        editor = Editor(figure())
        fake_server = Mock(server_port=8765)
        with patch('figureforge.main.HTTPServer', return_value=fake_server) as factory:
            _, url = make_server(editor)
        handler = factory.call_args.args[1]
        token = url.split('#')[1]

        def request(path, data=None, supplied_token=token, origin='http://127.0.0.1:8765'):
            body = b'' if data is None else json.dumps(data).encode()
            method = 'GET' if data is None else 'POST'
            raw = (f'{method} /{path} HTTP/1.0\r\nHost: 127.0.0.1:8765\r\n'
                   f'Origin: {origin}\r\nX-FigureForge-Token: {supplied_token}\r\n'
                   f'Content-Length: {len(body)}\r\n\r\n').encode() + body
            connection = Mock()
            connection.makefile.return_value = io.BytesIO(raw)
            output = io.BytesIO()
            connection.sendall.side_effect = output.write
            handler(connection, ('127.0.0.1', 10000), fake_server)
            headers, response = output.getvalue().split(b'\r\n\r\n', 1)
            return int(headers.split()[1]), response

        self.assertIn(b'FigureForge', request('')[1])
        self.assertIn(b'renderProperties', request('app.js')[1])
        self.assertEqual(request('api/state', supplied_token='invalid')[0], 403)
        self.assertEqual(request('api/state', origin='https://foreign.example')[0], 403)
        status, data = request('api/edit', {'path': [0], 'property': 'figsize', 'value': [7, 4]})
        self.assertEqual(status, 200)
        self.assertIn('set_size_inches([7, 4])', json.loads(data)['code'])
        status, _ = request('api/edit', {'path': [0], 'property': 'figsize', 'value': [-1, 4]})
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(request('api/state')[1])['edits'], 1)
        self.assertEqual(json.loads(request('api/undo', {})[1])['edits'], 0)
        self.assertEqual(request('missing')[0], 404)

    def test_endpoints_authentication_and_finish(self):
        editor = Editor(figure())
        try:
            server, url = make_server(editor)
        except PermissionError:
            self.skipTest('Environment does not permit loopback sockets')
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base, token = url.split('#')

        def request(path, data=None, headers=None):
            supplied = {'X-FigureForge-Token': token}
            supplied.update(headers or {})
            body = None if data is None else json.dumps(data).encode()
            with urlopen(Request(base + path, body, supplied), timeout=5) as response:
                return response.read()

        try:
            self.assertIn(b'FigureForge', request(''))
            self.assertIn(b'renderProperties', request('app.js'))
            self.assertIn('properties', json.loads(request('api/state')))
            for headers in ({'X-FigureForge-Token': 'bad'}, {'Origin': 'https://foreign.example'}, {'Host': 'foreign.example'}):
                with self.assertRaises(HTTPError) as error:
                    request('api/edit', {'path': [0], 'property': 'figsize', 'value': [7, 4]}, headers)
                self.assertEqual(error.exception.code, 403)
            result = json.loads(request('api/edit', {'path': [0], 'property': 'figsize', 'value': [7, 4]}))
            self.assertEqual(result['edits'], 1)
            self.assertIn('set_size_inches([7, 4])', result['code'])
            self.assertEqual(json.loads(request('api/undo', {}))['edits'], 0)
            request('api/finish', {})
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
