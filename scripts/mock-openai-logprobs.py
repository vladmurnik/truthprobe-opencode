#!/usr/bin/env python3
"""Мок OpenAI-совместимого стриминга с token logprobs — для сквозной проверки TruthProbe.

Запуск:
    python3 scripts/mock-openai-logprobs.py 8899

Проверка:
    OPENCODE_TRUTHPROBE=1 \
    OPENCODE_CONFIG=$(pwd)/scripts/mock-opencode.json \
    bun run --cwd packages/cli src/index.ts run --model mock/mock-1 "What is the capital of France?"

Сервер отдаёт два предложения: первое с высокими logprob (уверенное), второе с низкими
(спорное). TruthProbe должен пометить второе как doubtful. Каждый полученный запрос
пишется в /tmp/mock/requests.jsonl — по нему видно, что клиент реально отправил
`logprobs: true` и `top_logprobs`.
"""

from __future__ import annotations

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = "/tmp/mock/requests.jsonl"

# (токен, logprob, альтернативы). Первое предложение — уверенное, второе — сомнительное.
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


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # тишина в консоли
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
        os.makedirs("/tmp/mock", exist_ok=True)
        with open(LOG, "a", encoding="utf-8") as handle:
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
                                        "top_logprobs": [
                                            {"token": alt, "logprob": value, "bytes": None}
                                            for alt, value in alternatives
                                        ],
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
