"""A tiny stand-in for the local AI engine (Ollama), for fast model-based test runs.

It answers the four endpoints AudienceOS uses (/api/tags, /api/chat, /api/embed, /api/pull). /api/chat builds an
answer from the JSON schema the app sends in `format`, so it fits every stage (profile, signals, themes,
opportunities, asset drafts, claim review, calculator) without knowing them in advance. Quotes are copied from the
units in the prompt, and ids are picked from the numbered lists in the prompt, so answers pass the app's evidence
checks.

Behaviour is switched at run time by POST /__mode {"mode": ..., "seed": ...}:
  valid    schema-valid JSON (default)
  invalid  JSON that breaks the schema (wrong types, missing fields)
  garbage  not JSON at all
  slow     valid, after `delay` seconds
  error    HTTP 500
  mixed    each call picks one of the above with the seeded RNG
GET /__stats returns counts per mode served. Binds to 127.0.0.1 only.

  python fake_ollama.py --port 11471
"""
import argparse
import hashlib
import json
import random
import re
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

STATE = {"mode": "valid", "delay": 3.0, "rng": random.Random(1), "stats": {}, "models": ["qwen2.5:7b", "nomic-embed-text:latest"]}
LOCK = threading.Lock()

WORDS = "starter flour loaf crumb oven proof dough bake timing recipe kit guide schedule hydration".split()


def units(prompt: str):
    return [(m.group(1), m.group(2).strip()) for m in re.finditer(r'<unit ref="([^"]+)"[^>]*>\n(.*?)\n</unit>', prompt, re.S)]


def numbered(prompt: str):
    return [int(m.group(1)) for m in re.finditer(r"^(\d+)\. ", prompt, re.M)]


def tagged(prompt: str, letter: str):
    return sorted({int(m.group(1)) for m in re.finditer(rf"\b{letter}(\d+)[ .]", prompt)})


class Gen:
    def __init__(self, prompt: str, rng: random.Random):
        self.p, self.r = prompt, rng
        self.units = units(prompt)
        self.nums = numbered(prompt)
        self.t_ids, self.e_ids = tagged(prompt, "T"), tagged(prompt, "E")
        self.calc_inputs: list[str] = []

    def text(self, n=6):
        return " ".join(self.r.choice(WORDS) for _ in range(n)).capitalize() + "."

    def value(self, s: dict, name: str = ""):
        t = s.get("type")
        if "enum" in s:
            return self.r.choice(s["enum"])
        if "anyOf" in s:
            return self.value(next((x for x in s["anyOf"] if x.get("type") != "null"), s["anyOf"][0]), name)
        if t == "object":
            return self.obj(s)
        if t == "array":
            return self.arr(s, name)
        if t == "integer":
            lo, hi = s.get("minimum", 0), s.get("maximum", 5)
            return self.r.randint(lo, max(lo, hi))
        if t == "number":
            if name in ("price",):
                return self.r.choice([9, 19, 29, 49, 97])
            return round(self.r.uniform(s.get("minimum", 0), s.get("maximum", 100)), 2)
        if t == "boolean":
            return self.r.random() < .5
        if t == "string":
            if name == "expression":
                return f"{self.calc_inputs[0]} * 2" if self.calc_inputs else "1 + 1"
            if name == "name" and self.calc_inputs is not None and getattr(self, "_in_calc", False):
                nm = f"input_{len(self.calc_inputs) + 1}"
                self.calc_inputs.append(nm)
                return nm
            if name == "markdown":
                return f"# {self.text(3)}\n\n{self.text(20)}\n\n- {self.text(5)}\n- {self.text(5)}\n"
            return self.text(4)
        return self.text(3)

    def obj(self, s: dict):
        props = s.get("properties", {})
        out = {}
        if "ref" in props and "quote" in props:  # an extracted signal: quote a real unit verbatim
            ref, txt = self.r.choice(self.units) if self.units else ("C1", "no units")
            words = txt.split()
            start = self.r.randint(0, max(0, len(words) - 12))
            out["ref"], out["quote"] = ref, " ".join(words[start:start + 12])
        self._in_calc = "inputs" in props and "outputs" in props
        if self._in_calc:
            self.calc_inputs = []
        order = sorted(props, key=lambda k: (k == "outputs",))  # inputs before outputs, so expressions use them
        for k in order:
            if k in out:
                continue
            out[k] = self.value(props[k], k)
        return out

    def arr(self, s: dict, name: str):
        if name == "signal_ids":
            pool = self.nums or [0]
            return sorted(set(self.r.sample(pool, k=min(len(pool), self.r.randint(1, 4)))))
        if name == "theme_ids":
            return self.t_ids[:2] or [1]
        if name == "evidence_ids":
            pool = self.e_ids or [1]
            return pool[: self.r.randint(1, min(4, len(pool)))]
        item = s.get("items", {})
        if name == "signals":
            n = min(len(self.units), self.r.randint(2, 6)) if self.units else 0
        elif name == "themes":
            n = max(1, min(4, len(self.nums) // 3 or 1))
        elif name == "opportunities":
            n = self.r.randint(1, 3)
        elif name == "issues":
            n = self.r.randint(0, 2)
        else:
            n = self.r.randint(1, 3)
        return [self.value(item, name) for _ in range(n)]


def answer(body: dict) -> tuple[int, str, str]:
    with LOCK:
        mode, rng = STATE["mode"], STATE["rng"]
        if mode == "mixed":
            mode = rng.choices(["valid", "invalid", "garbage", "slow", "error"], [70, 10, 8, 7, 5])[0]
        STATE["stats"][mode] = STATE["stats"].get(mode, 0) + 1
        seed = rng.random()
    if mode == "error":
        return 500, json.dumps({"error": "fake engine error"}), mode
    if mode == "slow":
        time.sleep(STATE["delay"])
    schema = body.get("format")
    prompt = "\n".join(m.get("content", "") for m in body.get("messages", []))
    if mode == "garbage":
        content = rng_pick(seed, ["Sure! Here is what I found:", "{{{not json", "", "null", "```json\n[1,2\n```"])
    elif not isinstance(schema, dict):
        content = "A plain-text answer from the stand-in engine."
    else:
        g = Gen(prompt, random.Random(seed))
        out = g.value(schema)
        if mode == "invalid":
            out = break_it(out, random.Random(seed))
        content = json.dumps(out)
    return 200, json.dumps({"model": body.get("model"), "message": {"role": "assistant", "content": content}, "done": True}), mode


def rng_pick(seed, xs):
    return xs[int(seed * len(xs)) % len(xs)]


def break_it(out, r):
    if isinstance(out, dict) and out:
        k = r.choice(list(out))
        choice = r.randint(0, 2)
        if choice == 0:
            out.pop(k)
        elif choice == 1:
            out[k] = {"nested": "wrong type"}
        else:
            out[k] = float("1e309") if isinstance(out[k], (int, float)) else 12345
    return out


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.startswith("/api/tags"):
            return self._send(200, json.dumps({"models": [{"name": m} for m in STATE["models"]]}))
        if self.path.startswith("/__stats"):
            return self._send(200, json.dumps({"mode": STATE["mode"], "stats": STATE["stats"]}))
        self._send(404, "{}")

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            body = {}
        if self.path == "/__mode":
            with LOCK:
                STATE["mode"] = body.get("mode", STATE["mode"])
                STATE["delay"] = float(body.get("delay", STATE["delay"]))
                if "seed" in body:
                    STATE["rng"] = random.Random(body["seed"])
                if "models" in body:
                    STATE["models"] = body["models"]
            return self._send(200, json.dumps({"mode": STATE["mode"]}))
        if self.path == "/api/chat":
            code, out, _ = answer(body)
            return self._send(code, out)
        if self.path == "/api/embed":
            vecs = []
            for t in body.get("input", []):
                h = hashlib.sha256(t.encode()).digest()
                vecs.append([(b - 128) / 128 for b in h[:32]])
            return self._send(200, json.dumps({"embeddings": vecs}))
        if self.path == "/api/pull":
            m = body.get("model", "")
            lines = [{"status": "pulling manifest"}, {"status": "downloading", "digest": "sha256:aa", "total": 1000, "completed": 500},
                     {"status": "downloading", "digest": "sha256:aa", "total": 1000, "completed": 1000}, {"status": "success"}]
            with LOCK:
                if m and m not in STATE["models"]:
                    STATE["models"].append(m)
            return self._send(200, "\n".join(json.dumps(x) for x in lines) + "\n", "application/x-ndjson")
        self._send(404, "{}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=11471)
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), H).serve_forever()
