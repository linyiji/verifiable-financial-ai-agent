"""Serve the built product UI with SPA navigation, bound by Docker to host loopback."""

from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory="/app/apps/web/dist", **kwargs)

    def do_GET(self):
        if not Path(self.translate_path(urlsplit(self.path).path)).is_file():
            self.path = "/index.html"
        super().do_GET()

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 4173), Handler).serve_forever()
