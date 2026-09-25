"""Data binding, recipe transactions, and standalone Matplotlib export."""

import copy
import io
import json
import unittest
from unittest.mock import Mock, patch

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from figureforge.builder import BuilderEditor, FUNCTIONS
from figureforge.editor import Editor
from figureforge.main import make_server, run


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.data = {'time': np.arange(5), 'signal': np.array([1, 3, 2, 4, 3]),
                     'other': np.arange(5) ** 2, 'image': np.arange(16).reshape(4, 4),
                     'errors': np.full(5, .2), 'bad': np.arange(3)}
        self.editor = BuilderEditor(self.data)

    def tearDown(self):
        plt.close('all')

    def add(self, name, **bindings):
        self.editor.edit(dict(op='add', function=name, bindings=bindings))
        return self.editor.selected

    def edit(self, path, name, value):
        self.editor.edit(dict(path=path, property=name, value=value))

    def test_empty_start_and_named_metadata(self):
        state = self.editor.state()
        self.assertEqual(len(self.editor.figure.axes[0].lines), 0)
        self.assertEqual(set(state['functions']), set(FUNCTIONS))
        self.assertEqual(state['datasets'][0]['key'], 'time')
        self.assertNotIn('values', state['datasets'][0])
        self.assertEqual(len(state['tree']), 2)
        self.assertTrue(BuilderEditor({}).state()['builder'])
        with self.assertRaises(TypeError):
            BuilderEditor({1: [1, 2]})

    def test_plot_scatter_labels_and_export_match_pixels(self):
        line = self.add('plot', x='time', y='signal')
        self.edit(line, 'label', 'Measured')
        self.edit(line, 'linewidth', 3.5)
        self.edit(line, 'color', '#ef476f')
        points = self.add('scatter', x='time', y='other', c='signal')
        self.edit(points, 's', 80)
        self.edit(points, 'cmap', 'plasma')
        self.edit(points, 'label', 'Samples')
        for name, value in [('title', 'Experiment'), ('xlabel', 'Time (s)'), ('ylabel', 'Voltage'), ('grid', True)]:
            self.edit([-1], name, value)
        self.editor.edit(dict(scope='rc', property='font.size', value=13))
        code = self.editor.code()
        self.assertIn("ax.plot(data['time'], data['signal']", code)
        self.assertIn("c=data['signal']", code)
        namespace = {}
        exec(code, namespace)
        self.assertEqual(Editor.render(namespace['make_figure'](self.data)), self.editor.preview)
        ax = self.editor.figure.axes[0]
        self.assertEqual(ax.get_title(), 'Experiment')
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ['Measured', 'Samples'])
        np.testing.assert_array_equal(self.data['time'], np.arange(5))

    def test_all_function_bindings(self):
        cases = {
            'plot': {'y': 'signal'}, 'scatter': {'x': 'time', 'y': 'signal'},
            'imshow': {'X': 'image'}, 'hist': {'x': 'signal'},
            'bar': {'x': 'time', 'height': 'signal'}, 'barh': {'y': 'time', 'width': 'signal'},
            'step': {'x': 'time', 'y': 'signal'},
            'errorbar': {'x': 'time', 'y': 'signal', 'yerr': 'errors'},
            'fill_between': {'x': 'time', 'y1': 'signal', 'y2': 'other'},
            'contour': {'Z': 'image'}, 'contourf': {'Z': 'image'}, 'pcolormesh': {'C': 'image'},
        }
        for name, bindings in cases.items():
            with self.subTest(name=name):
                self.editor = BuilderEditor(self.data)
                self.add(name, **bindings)
                namespace = {}
                exec(self.editor.code(), namespace)
                self.assertEqual(Editor.render(namespace['make_figure'](self.data)), self.editor.preview)

    def test_failures_do_not_commit(self):
        before = self.editor.preview
        actions = [dict(op='add', function='__getattribute__', bindings={}),
                   dict(op='add', function='scatter', bindings={'x': 'time'}),
                   dict(op='add', function='plot', bindings={'y': 'missing'}),
                   dict(op='add', function='plot', bindings={'x': 'time', 'y': 'bad'}),
                   dict(path=[0], property='figsize', value=[100000, 100000])]
        for action in actions:
            with self.subTest(action=action):
                with self.assertRaises((ValueError, TypeError)):
                    self.editor.edit(action)
                self.assertEqual(self.editor.preview, before)
                self.assertEqual(self.editor.history, [])

    def test_rebind_remove_undo_reset_and_ids(self):
        line = self.add('plot', x='time', y='signal')
        self.editor.edit(dict(op='bind', path=line, bindings={'x': 'time', 'y': 'other'}))
        np.testing.assert_array_equal(self.editor.figure.axes[0].lines[0].get_ydata(), self.data['other'])
        self.editor.edit(dict(op='remove', path=line))
        self.assertEqual(self.editor.config['layers'], [])
        self.editor.undo()
        self.assertEqual(self.editor.config['layers'][0]['id'], line[0])
        self.editor.undo(reset=True)
        new_line = self.add('plot', y='signal')
        self.assertNotEqual(line, new_line)

    def test_literal_and_binding_are_mutually_exclusive(self):
        scatter = self.add('scatter', x='time', y='signal', s='other')
        self.edit(scatter, 's', 25)
        self.assertNotIn('s', self.editor.config['layers'][0]['bindings'])
        self.editor.edit(dict(op='bind', path=scatter, bindings={'x': 'time', 'y': 'signal', 's': 'signal'}))
        self.assertNotIn('s', self.editor.config['layers'][0]['kwargs'])

    def test_rc_defaults_are_applied_at_construction_without_leaking(self):
        original = matplotlib.rcParams['lines.linewidth']
        line = self.add('plot', y='signal')
        self.editor.edit(dict(scope='rc', property='lines.linewidth', value=6))
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 6)
        self.assertEqual(matplotlib.rcParams['lines.linewidth'], original)
        self.edit(line, 'linewidth', 2)
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 2)
        self.editor.edit(dict(path=line, property='linewidth', reset=True))
        self.assertEqual(self.editor.figure.axes[0].lines[0].get_linewidth(), 6)

    def test_unusual_keys_are_literal_references(self):
        key = "a'] ; raise RuntimeError('bad') #"
        self.editor = BuilderEditor({key: [1, 2], '': [3, 4]})
        self.add('plot', x='', y=key)
        namespace = {}
        exec(self.editor.code(), namespace)
        fig = namespace['make_figure']({key: [1, 2], '': [3, 4]})
        np.testing.assert_array_equal(fig.axes[0].lines[0].get_ydata(), [1, 2])

    def test_public_run_accepts_dictionary_and_returns_figure(self):
        server = Mock()
        with patch('figureforge.main.make_server', return_value=(server, 'http://127.0.0.1:1234/#test')) as factory:
            with patch('figureforge.main.webbrowser.open') as browser:
                result = run(self.data, open_browser=False)
        self.assertIsInstance(factory.call_args.args[0], BuilderEditor)
        self.assertIs(result, factory.call_args.args[0].figure)
        browser.assert_not_called()
        server.server_close.assert_called_once()

    def test_builder_http_flow_without_network(self):
        server = Mock(server_port=8765)
        with patch('figureforge.main.HTTPServer', return_value=server) as factory:
            _, url = make_server(self.editor)
        handler = factory.call_args.args[1]
        token = url.split('#')[1]

        def request(path, data=None):
            body = b'' if data is None else json.dumps(data).encode()
            method = 'GET' if data is None else 'POST'
            raw = (f'{method} /{path} HTTP/1.0\r\nHost: 127.0.0.1:8765\r\n'
                   f'X-FigureForge-Token: {token}\r\nContent-Length: {len(body)}\r\n\r\n').encode() + body
            connection = Mock()
            connection.makefile.return_value = io.BytesIO(raw)
            output = io.BytesIO()
            connection.sendall.side_effect = output.write
            handler(connection, ('127.0.0.1', 10000), server)
            headers, response = output.getvalue().split(b'\r\n\r\n', 1)
            return int(headers.split()[1]), json.loads(response)

        status, state = request('api/state')
        self.assertEqual(status, 200)
        self.assertIn('imshow', state['functions'])
        status, state = request('api/edit', dict(op='add', function='imshow', bindings={'X': 'image'}))
        self.assertEqual(status, 200)
        self.assertEqual(state['layer']['bindings'], {'X': 'image'})
        image_path = state['selected']
        status, state = request('api/edit', dict(path=[-1], property='title', value='Image'))
        self.assertEqual(state['selected'], [-1])
        self.assertIn("ax.set_title('Image')", state['code'])
        status, _ = request('api/edit', dict(op='bind', path=image_path, bindings={'X': 'unknown'}))
        self.assertEqual(status, 400)
        status, state = request('api/reset', {})
        self.assertEqual(status, 200)
        self.assertEqual(len(state['tree']), 2)


if __name__ == '__main__':
    unittest.main()
