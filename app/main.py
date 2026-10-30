import http.server
import json

PORT = 8097


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            payload = {"status": "ok", "service": "rail", "mode": "demo"}
        elif self.path == "/":
            payload = {"service": "rail", "mode": "demo"}
        else:
            self.send_error(404)
            return
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    with http.server.ThreadingHTTPServer(("0.0.0.0", PORT), Handler) as httpd:
        print(f"serving demo on port {PORT}")
        httpd.serve_forever()
