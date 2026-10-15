"""Spike for ADR-0004: measure Ollama on this machine."""

import json
import subprocess
import time
import urllib.request

BASE = "http://127.0.0.1:11500"
MODEL = "qwen3:8b"


def post(path, body, timeout=300):
    req = urllib.request.Request(
        BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        out = json.loads(r.read())
    out["_wall"] = time.time() - t0
    return out


def vram():
    q = subprocess.run(
        ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
        capture_output=True,
        check=False,
        text=True,
    )
    return int(q.stdout.strip())


def rate(r):
    return r["eval_count"] / (r["eval_duration"] / 1e9)


print("VRAM before (MiB):", vram())
r = post(
    "/api/generate",
    {
        "model": MODEL,
        "prompt": "Explain what ECOG performance status is in 150 words.",
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "seed": 1, "num_predict": 200},
    },
)
print(
    f"cold: load={r['load_duration'] / 1e9:.1f}s prompt_tokens={r['prompt_eval_count']} gen_tokens={r['eval_count']} tok/s={rate(r):.1f} wall={r['_wall']:.1f}s"
)
print("VRAM loaded (MiB):", vram())
r = post(
    "/api/generate",
    {
        "model": MODEL,
        "prompt": "Explain what HER2 is in 150 words.",
        "stream": False,
        "think": False,
        "options": {"temperature": 0, "seed": 1, "num_predict": 200},
    },
)
print(f"warm: load={r['load_duration'] / 1e9:.2f}s tok/s={rate(r):.1f}")

schema = {
    "type": "object",
    "properties": {
        "criteria": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "concept": {"type": "string"},
                    "operator": {
                        "type": "string",
                        "enum": ["=", "<=", ">=", "<", ">", "in", "not_in"],
                    },
                    "value": {"type": "string"},
                    "kind": {"type": "string", "enum": ["inclusion", "exclusion"]},
                    "evaluable": {"type": "boolean"},
                },
                "required": ["concept", "operator", "value", "kind", "evaluable"],
            },
        }
    },
    "required": ["criteria"],
}
text = (
    "Inclusion: ECOG performance status 0 or 1; HER2-negative; CLDN18.2 positive in at least 75% of tumor cells; "
    "no prior systemic therapy for advanced disease. Exclusion: known MSI-H; TNM stage IIIA."
)
ok = 0
times = []
ntok = []
for i in range(10):
    r = post(
        "/api/chat",
        {
            "model": MODEL,
            "stream": False,
            "think": False,
            "format": schema,
            "messages": [
                {"role": "user", "content": "Extract the trial criteria as JSON.\n" + text}
            ],
            "options": {"temperature": 0, "seed": i},
        },
    )
    try:
        d = json.loads(r["message"]["content"])
        assert isinstance(d["criteria"], list) and d["criteria"]
        ok += 1
    except (json.JSONDecodeError, KeyError, AssertionError) as e:
        print("invalid:", e, r["message"]["content"][:120])
    times.append(r["_wall"])
    ntok.append(r["eval_count"])
print(
    f"structured: valid {ok}/10, mean wall {sum(times) / 10:.1f}s, mean tokens {sum(ntok) / 10:.0f}"
)
print("sample:", json.dumps(d)[:420])

t0 = time.time()
post("/api/generate", {"model": MODEL, "keep_alive": 0, "stream": False})
u = time.time() - t0
time.sleep(1)
print(f"unload: {u:.1f}s; VRAM after unload (MiB):", vram())
r = post(
    "/api/generate",
    {
        "model": MODEL,
        "prompt": "hi",
        "stream": False,
        "think": False,
        "options": {"num_predict": 1},
    },
)
print(f"reload load={r['load_duration'] / 1e9:.1f}s")
