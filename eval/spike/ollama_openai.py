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
body = {
    "model": "qwen3:8b",
    "messages": [
        {
            "role": "user",
            "content": "Extract criteria as JSON. Inclusion: ECOG 0 or 1; HER2-negative.",
        }
    ],
    "temperature": 0,
    "seed": 7,
    "reasoning_effort": "none",
    "response_format": {
        "type": "json_schema",
        "json_schema": {"name": "c", "strict": True, "schema": schema},
    },
}
req = urllib.request.Request(
    "http://127.0.0.1:11500/v1/chat/completions",
    json.dumps(body).encode(),
    {"Content-Type": "application/json"},
)
r = json.loads(urllib.request.urlopen(req, timeout=300).read())
c = r["choices"][0]["message"]["content"]
print(json.loads(c)["criteria"][:2])
