import hashlib
import json
import urllib.request

schema = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"concept": {"type": "string"}, "value": {"type": "string"}},
                "required": ["concept", "value"],
            },
        }
    },
    "required": ["criteria"],
}
prompt = "Extract the criteria as JSON. Inclusion: ECOG 0 or 1; HER2-negative; CLDN18.2 positive. Exclusion: MSI-H."


def call(url, body):
    req = urllib.request.Request(
        url, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    return json.loads(urllib.request.urlopen(req, timeout=300).read())


def ollama():
    r = call(
        "http://127.0.0.1:11500/api/chat",
        {
            "model": "qwen3:8b",
            "stream": False,
            "think": False,
            "format": schema,
            "messages": [{"role": "user", "content": prompt}],
            "options": {"temperature": 0, "seed": 7},
        },
    )
    return r["message"]["content"]


def llama():
    r = call(
        "http://127.0.0.1:11600/v1/chat/completions",
        {
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0,
            "seed": 7,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "c", "strict": True, "schema": schema},
            },
        },
    )
    return r["choices"][0]["message"]["content"]


for name, fn in (("ollama", ollama), ("llama.cpp", llama)):
    hashes = [hashlib.sha256(fn().encode()).hexdigest()[:10] for _ in range(5)]
    print(name, "distinct outputs in 5 runs:", len(set(hashes)))
