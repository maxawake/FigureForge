"""Loopback-only web server; no web framework or frontend build required."""

import argparse
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from importlib.resources import files
from urllib.parse import parse_qs, urlparse

from figureforge.builder import BuilderEditor, demo_data


def make_server(editor, port=0):
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            pass

        def respond(self, body, content_type="application/json", status=200):
            if not isinstance(body, bytes):
                body = json.dumps(body, allow_nan=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def authorized(self):
            # Reject foreign origins and DNS rebinding; only this browser session can edit.
            host = f"127.0.0.1:{self.server.server_port}"
            return (
                self.headers.get("Host") == host
                and self.headers.get("Origin", f"http://{host}") == f"http://{host}"
                and secrets.compare_digest(self.headers.get("X-FigureForge-Token", ""), token)
            )

        def do_GET(self):
            url = urlparse(self.path)
            if url.path in ("/", "/app.js", "/style.css"):
                filename, mime = {
                    "/": ("index.html", "text/html; charset=utf-8"),
                    "/app.js": ("app.js", "text/javascript"),
                    "/style.css": ("style.css", "text/css"),
                }[url.path]
                self.respond(files("figureforge").joinpath("static", filename).read_bytes(), mime)
            elif url.path == "/api/state":
                if not self.authorized():
                    self.respond({"error": "Invalid session. Open the URL printed in your terminal."}, status=403)
                    return
                try:
                    path = json.loads(parse_qs(url.query).get("path", ["[]"])[0])
                    self.respond(editor.state(path))
                except Exception as exc:
                    self.respond({"error": str(exc)}, status=400)
            else:
                self.respond({"error": "Not found"}, status=404)

        def do_POST(self):
            if not self.authorized():
                self.respond({"error": "Invalid session"}, status=403)
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 1_000_000:
                    raise ValueError("Invalid request size")
                data = json.loads(self.rfile.read(size))
                if self.path == "/api/edit":
                    editor.edit(data)
                elif self.path == "/api/undo":
                    editor.undo()
                elif self.path == "/api/reset":
                    editor.undo(reset=True)
                elif self.path == "/api/finish":
                    self.respond({"ok": True})
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                    return
                else:
                    self.respond({"error": "Not found"}, status=404)
                    return
                self.respond(editor.state(data.get("path", [])))
            except Exception as exc:
                self.respond({"error": str(exc)}, status=400)

    server = HTTPServer(("127.0.0.1", port), Handler)
    server.timeout = 1
    return server, f"http://127.0.0.1:{server.server_port}/#{token}"


def run(data=None, *, port=0, open_browser=True):
    """Build a figure from a dictionary of named data, then return that figure.

    Choose plotting functions and data keys in the browser. Click Done (or press
    Ctrl+C) to return the result. Exports define make_figure(data). When data is
    omitted, offer example arrays. An empty dictionary is also accepted.
    """
    editor = BuilderEditor(demo_data() if data is None else data)
    server, url = make_server(editor, port)
    print(f"FigureForge: {url}\nClick Done in the editor or press Ctrl+C to stop.", flush=True)
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return editor.figure


def main():
    parser = argparse.ArgumentParser(description="Edit Matplotlib figures in a local web interface")
    parser.add_argument("--port", type=int, default=0, help="Local port (default: choose a free port)")
    parser.add_argument("--no-browser", action="store_true", help="Print the URL without opening a browser")
    args = parser.parse_args()
    run(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
