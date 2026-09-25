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
                    if node['name'] == name and (label is None or node['label'] == label))

    def edit(self, name, prop, value, label=None):
        self.editor.edit(dict(path=self.path(name, label), property=prop, value=value))

    def test_export_reproduces_pixels_and_does_not_modify_input(self):
        self.edit('Line2D', 'color', '#e34a78', 'Signal')
        self.edit('Line2D', 'linewidth', 4, 'Signal')
        self.edit('Text', 'text', 'Edited "title"\nwith newline', 'Original')
        self.edit('Axes', 'xlim', [0, 5])
        self.edit('PathCollection', 'sizes', [160])
        self.edit('Figure', 'size_inches', [6, 4])
        exported = {}
        exec(self.editor.code(), exported)
        replica = copy.deepcopy(self.original)
        exported['apply_settings'](replica)
        self.assertEqual(Editor.render(replica), self.editor.preview)
        self.assertEqual(self.original.axes[0].lines[0].get_linewidth(), 1.5)
        self.assertEqual(self.original.axes[0].get_title(), 'Original')

    def test_invalid_edit_is_atomic(self):
        before = self.editor.preview
        with self.assertRaises(ValueError):
            self.edit('Line2D', 'color', 'not-a-color', 'Signal')
        self.assertEqual(self.editor.preview, before)
        self.assertEqual(self.editor.actions, [])
        with self.assertRaises(ValueError):
            self.edit('Figure', 'size_inches', [100000, 100000])
        self.assertEqual(self.editor.preview, before)

    def test_undo_reset_and_property_inspection(self):
        initial = self.editor.preview
        self.edit('Line2D', 'linewidth', 7, 'Signal')
        first = self.editor.preview
        self.edit('Axes', 'facecolor', '#eeeeff')
        self.editor.undo()
        self.assertEqual(self.editor.preview, first)
        self.editor.undo(reset=True)
        self.assertEqual(self.editor.preview, initial)
        names = {item['name'] for item in self.editor.state(self.path('Line2D', 'Signal'))['properties']}
        self.assertTrue({'color', 'linewidth', 'marker', 'visible'} <= names)
        self.assertNotIn('transform', names)

    def test_injection_and_invalid_paths_are_rejected(self):
        with self.assertRaises(ValueError):
            self.editor.edit({'path': [], 'property': '__class__', 'value': 'x'})
        with self.assertRaises(ValueError):
            self.editor.edit({'path': [-1], 'property': 'visible', 'value': False})

    def test_demo_is_standalone(self):
        from figureforge.editor import demo_figure
        from unittest.mock import patch
        editor = Editor(demo_figure(), demo=True)
        editor.edit({'path': [], 'property': 'figwidth', 'value': 7})
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
        status, data = request('api/edit', {'path': [], 'property': 'figwidth', 'value': 7})
        self.assertEqual(status, 200)
        self.assertIn('set_figwidth(7)', json.loads(data)['code'])
        status, _ = request('api/edit', {'path': [], 'property': 'figwidth', 'value': -1})
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
                    request('api/edit', {'path': [], 'property': 'figwidth', 'value': 7}, headers)
                self.assertEqual(error.exception.code, 403)
            result = json.loads(request('api/edit', {'path': [], 'property': 'figwidth', 'value': 7}))
            self.assertEqual(result['edits'], 1)
            self.assertIn('set_figwidth(7)', result['code'])
            self.assertEqual(json.loads(request('api/undo', {}))['edits'], 0)
            request('api/finish', {})
            thread.join(timeout=3)
            self.assertFalse(thread.is_alive())
        finally:
            server.shutdown()
            server.server_close()


if __name__ == '__main__':
    unittest.main()
