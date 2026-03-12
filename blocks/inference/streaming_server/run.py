"""Streaming Server — configure an HTTP inference endpoint for serving models.

Workflows:
  1. Local model serving: train/download model -> streaming server -> chat UI
  2. API gateway: configure proxy -> unified endpoint for multiple providers
  3. Load testing: server config -> benchmark tool -> performance metrics
  4. Prototype deployment: model -> server script -> docker container
  5. Multi-model proxy: router -> server -> client applications
"""

import json
import os


def run(ctx):
    host = ctx.config.get("host", "0.0.0.0")
    port = int(ctx.config.get("port", 8080))
    model_name = ctx.config.get("model_name", "")
    provider = ctx.config.get("backend", "ollama")
    endpoint = ctx.config.get("endpoint", "http://localhost:11434")
    max_concurrent = int(ctx.config.get("max_concurrent", 4))
    cors_enabled = ctx.config.get("cors_enabled", True)
    api_key_required = ctx.config.get("api_key_required", False)

    # Try to get model from input
    if ctx.inputs.get("model"):
        try:
            model_info = ctx.load_input("model")
            if isinstance(model_info, dict):
                model_name = model_name or model_info.get("model_name", model_info.get("model_id", ""))
                provider = model_info.get("source", model_info.get("provider", provider))
                endpoint = model_info.get("endpoint", endpoint)
        except Exception:
            pass

    if not model_name:
        model_name = "llama3.2"

    ctx.log_message(f"Configuring streaming inference server")
    ctx.log_message(f"  Host: {host}:{port}, Model: {model_name}")
    ctx.log_message(f"  Provider: {provider}, Backend: {endpoint}")
    ctx.report_progress(1, 3)

    # Determine backend routes per provider
    ep = endpoint.rstrip("/")
    if provider == "ollama":
        backend_chat = f"{ep}/api/chat"
        backend_gen = f"{ep}/api/generate"
        backend_emb = f"{ep}/api/embeddings"
    elif provider == "anthropic":
        backend_chat = f"{ep}/v1/messages"
        backend_gen = f"{ep}/v1/messages"
        backend_emb = ""
    else:  # openai, mlx
        backend_chat = f"{ep}/v1/chat/completions"
        backend_gen = f"{ep}/v1/completions"
        backend_emb = f"{ep}/v1/embeddings"

    # Server configuration object
    server_config = {
        "host": host,
        "port": port,
        "model_name": model_name,
        "provider": provider,
        "backend_endpoint": endpoint,
        "max_concurrent_requests": max_concurrent,
        "cors_enabled": cors_enabled,
        "api_key_required": api_key_required,
        "endpoints": {
            "chat": f"http://{host}:{port}/v1/chat/completions",
            "completions": f"http://{host}:{port}/v1/completions",
            "embeddings": f"http://{host}:{port}/v1/embeddings",
            "models": f"http://{host}:{port}/v1/models",
            "health": f"http://{host}:{port}/health",
        },
        "backend_routes": {
            "chat": backend_chat,
            "generate": backend_gen,
            "embeddings": backend_emb or None,
        },
    }

    ctx.report_progress(2, 3)

    # Generate server script pieces
    cors_methods = ""
    cors_call = ""
    if cors_enabled:
        cors_methods = '''
    def _send_cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-API-Key")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors()
        self.end_headers()
'''
        cors_call = "        self._send_cors()"

    key_method = ""
    key_guard = ""
    if api_key_required:
        key_method = '''
    def _check_key(self):
        if not self.headers.get("X-API-Key"):
            self._respond(401, {"error": "X-API-Key header required"})
            return False
        return True
'''
        key_guard = "        if not self._check_key(): return"

    server_script = f'''#!/usr/bin/env python3
"""Blueprint Streaming Server — auto-generated.

Endpoints:
  POST /v1/chat/completions — OpenAI-compatible chat
  POST /v1/completions      — text completions
  POST /v1/embeddings       — text embeddings
  GET  /v1/models           — list models
  GET  /health              — health check

To start: python server.py
"""

import http.server
import json
import threading
import urllib.request

HOST = "{host}"
PORT = {port}
MODEL = "{model_name}"
PROVIDER = "{provider}"
BACKEND_CHAT = "{backend_chat}"
BACKEND_GEN = "{backend_gen}"
BACKEND_EMB = "{backend_emb}"
MAX_CONCURRENT = {max_concurrent}

_semaphore = threading.Semaphore(MAX_CONCURRENT)


class InferenceHandler(http.server.BaseHTTPRequestHandler):
{cors_methods}{key_method}
    def _forward(self, url, data):
        payload = json.dumps(data).encode()
        req = urllib.request.Request(
            url, data=payload,
            headers={{"Content-Type": "application/json"}}
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:
                return json.loads(resp.read().decode()), resp.status
        except urllib.error.HTTPError as e:
            body = e.read().decode() if e.fp else '{{"error": "backend error"}}'
            return json.loads(body), e.code
        except Exception as e:
            return {{"error": str(e)}}, 502

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
{cors_call}
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())

    def do_POST(self):
{key_guard}
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode()
        data = json.loads(body) if body else {{}}
        data.setdefault("model", MODEL)

        route = {{
            "/v1/chat/completions": BACKEND_CHAT,
            "/v1/completions": BACKEND_GEN,
            "/v1/embeddings": BACKEND_EMB,
        }}.get(self.path)

        if route:
            acquired = _semaphore.acquire(timeout=30)
            if not acquired:
                self._respond(503, {{"error": "Server at max capacity", "max_concurrent": MAX_CONCURRENT}})
                return
            try:
                result, status = self._forward(route, data)
                self._respond(status, result)
            finally:
                _semaphore.release()
        else:
            self._respond(404, {{"error": f"Unknown endpoint: {{self.path}}"}})

    def do_GET(self):
        if self.path == "/health":
            self._respond(200, {{"status": "ok", "model": MODEL, "provider": PROVIDER}})
        elif self.path == "/v1/models":
            self._respond(200, {{"data": [{{"id": MODEL, "object": "model"}}]}})
        else:
            self._respond(404, {{"error": "not found"}})

    def log_message(self, fmt, *args):
        pass


if __name__ == "__main__":
    server = http.server.ThreadingHTTPServer((HOST, PORT), InferenceHandler)
    print(f"Blueprint Server — {{MODEL}} ({{PROVIDER}}) on http://{{HOST}}:{{PORT}}")
    print(f"Max concurrent requests: {{MAX_CONCURRENT}}")
    server.serve_forever()
'''

    # Save files
    out_dir = os.path.join(ctx.run_dir, "server")
    os.makedirs(out_dir, exist_ok=True)

    script_path = os.path.join(out_dir, "server.py")
    with open(script_path, "w") as f:
        f.write(server_script)

    config_path = os.path.join(out_dir, "config.json")
    with open(config_path, "w") as f:
        json.dump(server_config, f, indent=2)

    ctx.save_output("config", server_config)
    ctx.save_output("artifact", out_dir)
    ctx.save_output("metrics", {
        "host": host,
        "port": port,
        "model": model_name,
        "provider": provider,
        "cors_enabled": cors_enabled,
        "api_key_required": api_key_required,
        "max_concurrent": max_concurrent,
    })
    ctx.log_metric("port", port)
    ctx.log_message(f"Server script: {script_path}")
    ctx.log_message(f"To start: python {script_path}")
    ctx.report_progress(3, 3)
