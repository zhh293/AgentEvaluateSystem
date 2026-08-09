import json
from http.server import BaseHTTPRequestHandler, HTTPServer


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200 if self.path == "/health" else 404)
        self.end_headers()

    def do_POST(self):
        if self.path != "/v1/evaluations/run":
            self.send_response(404)
            self.end_headers()
            return
        size = int(self.headers.get("content-length", "0"))
        request = json.loads(self.rfile.read(size))
        response = {
            "result": {"status": "success", "output": f"received: {request['task']['input']}"},
            "trace": {"spans": []},
        }
        body = json.dumps(response).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


HTTPServer(("0.0.0.0", 8080), Handler).serve_forever()
