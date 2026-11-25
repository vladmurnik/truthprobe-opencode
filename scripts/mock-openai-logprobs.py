#!/usr/bin/env python3
"""Mock of OpenAI-compatible streaming with token logprobs — for end-to-end checks of TruthProbe.

Run:
    python3 scripts/mock-openai-logprobs.py 8899

Check:
    OPENCODE_TRUTHPROBE=1 \
    OPENCODE_CONFIG=$(pwd)/scripts/mock-opencode.json \
    bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "What is the capital of France?"

The server returns two sentences: the first with high logprobs (confident), the second with low
(disputed). TruthProbe should mark the second one as doubtful. Every received request
is written to /tmp/mock/requests.jsonl — it shows whether the client really sent
`logprobs: true` and `top_logprobs`.
"""

from __future__ import annotations

import json
import math
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

_default_log = os.path.expanduser("~/mockwork/requests.jsonl")
LOG = os.environ.get("MOCK_LOG") or _default_log

# (token, logprob, alternatives). The first sentence is confident, the second is doubtful.
ANSWER = [
    ("The", -0.05, [("The", -0.05), ("A", -3.1), ("This", -3.4)]),
    (" capital", -0.02, [(" capital", -0.02), (" largest", -4.0)]),
    (" of", -0.01, [(" of", -0.01), (" city", -4.6)]),
    (" France", -0.03, [(" France", -0.03), (" Germany", -3.5)]),
    (" is", -0.01, [(" is", -0.01), (" was", -4.8)]),
    (" Paris", -0.08, [(" Paris", -0.08), (" Lyon", -3.0), (" Nice", -4.1)]),
    (".", -0.02, [(".", -0.02), (",", -4.0)]),
    (" It", -0.4, [(" It", -0.4), (" The", -1.2)]),
    (" is", -0.6, [(" is", -0.6), (" has", -1.1)]),
    (" home", -1.9, [(" home", -1.9), (" located", -2.0), (" famous", -2.2)]),
    (" to", -2.1, [(" to", -2.1), (" of", -2.3)]),
    (" about", -2.4, [(" about", -2.4), (" nearly", -2.6)]),
    (" 2", -2.8, [(" 2", -2.8), (" 12", -3.0)]),
    (" million", -2.6, [(" million", -2.6), (" billion", -3.1)]),
    (" people", -2.9, [(" people", -2.9), (" residents", -3.2)]),
    (".", -0.3, [(".", -0.3), ("!", -3.0)]),
]


def top_of(token: str, logprob: float, alternatives) -> list[dict]:
    """A top-k distribution cannot hold more than 1.0 of probability in total.

    The fixture is handwritten, and three rows summed past 1 (1.0297, 1.0006, 1.0001),
    which no real gateway emits. The chosen token is never touched: the alternatives
    are scaled down to fit the remaining probability mass.
    """
    main = math.exp(logprob)
    rest = [(alt, math.exp(value)) for alt, value in alternatives if alt != token]
    budget = 1.0 - main
    total = sum(prob for _, prob in rest)
    scale = budget / total if total > budget > 0 else 1.0
    rows = [{"token": token, "logprob": logprob, "bytes": None}]
    rows.extend(
        {"token": alt, "logprob": math.log(prob * scale), "bytes": None}
        for alt, prob in rest
        if prob > 0
    )
    return rows


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # silence on the console
        pass

    def do_GET(self):  # /v1/models
        body = json.dumps({"object": "list", "data": [{"id": "mock-1", "object": "model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # /v1/chat/completions
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length)
        try:
            body = json.loads(raw)
        except Exception:
            body = {}
        try:
            os.makedirs(os.path.dirname(LOG), exist_ok=True)
            handle = open(LOG, "a", encoding="utf-8")
        except OSError:
            handle = None
        if handle is not None:
            handle.write(
                json.dumps(
                    {
                        "path": self.path,
                        "model": body.get("model"),
                        "logprobs": body.get("logprobs"),
                        "top_logprobs": body.get("top_logprobs"),
                        "stream": body.get("stream"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )
            handle.close()

        # TruthProbe checks logprobs support with a single non-streaming request:
        # we answer with JSON, not SSE. MOCK_MODE=ignored imitates a gateway that
        # silently strips logprobs, MOCK_MODE=rejected — a rejection of the parameter.
        if os.environ.get("MOCK_MODE") == "rejected":
            payload = json.dumps({"error": {"message": "Unsupported parameter: logprobs"}}).encode()
            self.send_response(400)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if not body.get("stream"):
            first = ANSWER[0]
            content = [
                {
                    "token": first[0],
                    "logprob": first[1],
                    "bytes": None,
                    "top_logprobs": top_of(first[0], first[1], first[2]),
                }
            ]
            choice = {
                "index": 0,
                "message": {"role": "assistant", "content": first[0].strip()},
                "finish_reason": "length",
            }
            if body.get("logprobs") and os.environ.get("MOCK_MODE") != "ignored":
                choice["logprobs"] = {"content": content}
            payload = json.dumps(
                {
                    "id": "mock-1",
                    "object": "chat.completion",
                    "created": 0,
                    "model": body.get("model") or "mock-1",
                    "choices": [choice],
                }
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        def send(chunk: dict) -> None:
            self.wfile.write(b"data: " + json.dumps(chunk).encode() + b"\n\n")
            self.wfile.flush()

        base = {"id": "mock-1", "object": "chat.completion.chunk", "created": 0, "model": "mock-1"}
        send({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}, "finish_reason": None}]})
        for token, logprob, alternatives in ANSWER:
            send(
                {
                    **base,
                    "choices": [
                        {
                            "index": 0,
                            "delta": {"content": token},
                            "logprobs": {
                                "content": [
                                    {
                                        "token": token,
                                        "logprob": logprob,
                                        "bytes": None,
                                        "top_logprobs": top_of(token, logprob, alternatives),
                                    }
                                ]
                            },
                            "finish_reason": None,
                        }
                    ],
                }
            )
        send(
            {
                **base,
                "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": len(ANSWER),
                    "total_tokens": 10 + len(ANSWER),
                },
            }
        )
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8899
    print(f"mock openai with logprobs on http://127.0.0.1:{port}/v1")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()
