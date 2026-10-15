"""Spike for ADR-0004: measure llama.cpp llama-server on this machine."""

import json
import time
import urllib.request

BASE = "http://127.0.0.1:11600"


def post(path, body):
    req = urllib.request.Request(
        BASE + path, json.dumps(body).encode(), {"Content-Type": "application/json"}
    )
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=300) as r:
        out = json.loads(r.read())
    out["_wall"] = time.time() - t0
    return out


kw = {"chat_template_kwargs": {"enable_thinking": False}}
r = post(
    "/v1/chat/completions",
    {
        "messages": [
            {"role": "user", "content": "Explain what ECOG performance status is in 150 words."}
        ],
        "temperature": 0,
        "seed": 1,
        "max_tokens": 200,
        **kw,
    },
)
t = r["timings"]
print(
    f"free text: gen tok/s={t['predicted_per_second']:.1f} prompt tok/s={t['prompt_per_second']:.0f} tokens={t['predicted_n']}"
)
r = post(
    "/v1/chat/completions",
    {
        "messages": [{"role": "user", "content": "Explain what HER2 is in 150 words."}],
        "temperature": 0,
        "seed": 1,
        "max_tokens": 200,
        **kw,
    },
)
t = r["timings"]
print(f"free text 2: gen tok/s={t['predicted_per_second']:.1f}")

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
walls = []
toks = []
for i in range(10):
    r = post(
        "/v1/chat/completions",
        {
            "messages": [
                {"role": "user", "content": "Extract the trial criteria as JSON.\n" + text}
            ],
            "temperature": 0,
            "seed": i,
            **kw,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "criteria", "strict": True, "schema": schema},
            },
        },
    )
    try:
        d = json.loads(r["choices"][0]["message"]["content"])
        assert isinstance(d["criteria"], list) and d["criteria"]
        ok += 1
    except (json.JSONDecodeError, KeyError, AssertionError) as e:
        print("invalid:", e, r["choices"][0]["message"]["content"][:120])
    walls.append(r["_wall"])
    toks.append(r["timings"]["predicted_n"])
print(
    f"structured: valid {ok}/10, mean wall {sum(walls) / 10:.1f}s, mean tokens {sum(toks) / 10:.0f}"
)
