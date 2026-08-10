#!/usr/bin/env python3
"""
embed_compare.py — Project Aleph

Embeds the docs corpus with two Ollama models, runs the golden question set
against both, and reports where they disagree.

The point is not a leaderboard. It is to find the ~20 queries where the two
models retrieve different things, look at those by hand, and decide. Everything
else is noise you don't need to read.

Usage:
    ollama serve &
    python3 embed_compare.py --docs ./docs --questions ../eval/golden-v1.yaml

    # with a labels file, also reports recall@k
    python3 embed_compare.py --docs ./docs --labels labels.yaml

Requires: numpy, pyyaml, a running Ollama. No other dependencies.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import urllib.error
import urllib.request

try:
    import numpy as np
    import yaml
except ImportError:
    sys.exit(
        "missing dependencies. On macOS `pip` is usually not on PATH:\n"
        "    python3 -m venv .venv && source .venv/bin/activate\n"
        "    pip install numpy pyyaml"
    )

OLLAMA = "http://localhost:11434"

# Qwen3-Embedding expects an instruction on the QUERY side only; documents go in
# bare. bge-m3 is instruction-free and must NOT get a prefix. Getting this wrong
# is the classic silent failure — retrieval just quietly gets worse.
QUERY_PREFIX = {
    "qwen3-embedding": (
        "Instruct: Given a support question about the Wildcat lending protocol, "
        "retrieve the documentation passage that answers it\nQuery: "
    ),
}


def query_prefix_for(model: str) -> str:
    for key, prefix in QUERY_PREFIX.items():
        if model.startswith(key):
            return prefix
    return ""


# --------------------------------------------------------------------------
# chunking — heading boundaries, breadcrumb prepended
# --------------------------------------------------------------------------

def chunk_markdown(path: pathlib.Path, root: pathlib.Path) -> list[dict]:
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.split("\n")
    chunks, trail, buf, current = [], {}, [], None

    def flush():
        if not buf:
            return
        body = "\n".join(buf).strip()
        if len(body) < 40:                       # drop stubs
            return
        crumb = " › ".join(v for _, v in sorted(trail.items()) if v)
        chunks.append({
            "id": f"{path.relative_to(root)}#{len(chunks)}",
            "path": str(path.relative_to(root)),
            "breadcrumb": crumb,
            "display_text": body,
            # what the embedder sees: breadcrumb carries context the body lacks
            "embed_text": (crumb + "\n\n" + body) if crumb else body,
        })

    for line in lines:
        m = re.match(r"^(#{1,4})\s+(.*)", line)
        if m:
            flush()
            buf = []
            level = len(m.group(1))
            trail[level] = m.group(2).strip()
            for deeper in [k for k in trail if k > level]:
                trail.pop(deeper)
            current = m.group(2).strip()
        buf.append(line)
    flush()
    return chunks


def load_corpus(docs_dir: str) -> list[dict]:
    root = pathlib.Path(docs_dir)
    files = sorted(root.rglob("*.md"))
    if not files:
        sys.exit(f"no markdown found under {root}")
    out = []
    for f in files:
        out.extend(chunk_markdown(f, root))
    return out


# --------------------------------------------------------------------------
# ollama
# --------------------------------------------------------------------------

def embed(model: str, texts: list[str], batch: int = 16) -> np.ndarray:
    vecs = []
    for i in range(0, len(texts), batch):
        payload = json.dumps({"model": model, "input": texts[i:i + batch]}).encode()
        req = urllib.request.Request(
            f"{OLLAMA}/api/embed", data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                data = json.loads(r.read())
        except urllib.error.HTTPError as e:
            sys.exit(f"{model}: HTTP {e.code} — is the model pulled? `ollama pull {model}`")
        except urllib.error.URLError as e:
            sys.exit(f"cannot reach Ollama at {OLLAMA}: {e}")
        got = data.get("embeddings")
        if not got:
            sys.exit(f"{model}: no embeddings in response — {str(data)[:200]}")
        vecs.extend(got)
        print(f"\r  {model}: {min(i + batch, len(texts))}/{len(texts)}", end="", flush=True)
    print()
    arr = np.array(vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return arr / norms                            # cosine == dot after this


def search(qvecs: np.ndarray, cvecs: np.ndarray, k: int) -> np.ndarray:
    sims = qvecs @ cvecs.T
    return np.argsort(-sims, axis=1)[:, :k]


# --------------------------------------------------------------------------
# questions
# --------------------------------------------------------------------------

def load_questions(path: str, only_corpus: bool) -> list[dict]:
    p = pathlib.Path(path)
    if not p.exists():
        sys.exit(f"question set not found: {p}\n"
                 f"pass --questions explicitly, or run from the repo root")
    d = yaml.safe_load(p.open())
    qs = d["questions"]
    if only_corpus:
        qs = [q for q in qs
              if q.get("expected") in ("corpus", "corpus+live")
              and "corpus_gap" not in q]      # no chunk exists; scoring is meaningless
    return qs


# --------------------------------------------------------------------------
# main
# --------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--docs", required=True, help="directory of markdown to index")
    ap.add_argument("--questions",
                    default=str(pathlib.Path(__file__).resolve().parent / "golden-v1.yaml"),
                    help="default: golden-v1.yaml next to this script, whatever the cwd")
    ap.add_argument("--models", nargs="+",
                    default=["bge-m3", "qwen3-embedding:0.6b", "qwen3-embedding:8b"])
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--labels", help="optional YAML of {question_id: [substring, ...]}")
    ap.add_argument("--all-questions", action="store_true",
                    help="include refuse/triage items (they have no right answer)")
    ap.add_argument("--no-prefix", action="store_true",
                    help="disable query instruction prefixes (diagnostic — see RUNBOOK §5a)")
    args = ap.parse_args()

    chunks = load_corpus(args.docs)
    questions = load_questions(args.questions, only_corpus=not args.all_questions)
    print(f"{len(chunks)} chunks, {len(questions)} questions, k={args.k}\n")

    labels = yaml.safe_load(open(args.labels)) if args.labels else None
    results = {}

    for model in args.models:
        print(f"embedding with {model}")
        cvecs = embed(model, [c["embed_text"] for c in chunks])
        prefix = "" if args.no_prefix else query_prefix_for(model)
        if prefix:
            print(f"  (query prefix applied)")
        qvecs = embed(model, [prefix + q["question"] for q in questions])
        if cvecs.shape[1] != qvecs.shape[1]:
            sys.exit("dimension mismatch — different models cannot share an index")
        # each model gets its own index; they are never compared vector-to-vector
        results[model] = search(qvecs, cvecs, args.k)
        print(f"  dim={cvecs.shape[1]}\n")

    # ---- concentration: topical clustering vs genuine collapse ----
    #
    # Raw repetition is not evidence of failure. Section A of the golden set is
    # 18 withdrawal questions, so a withdrawal chunk winning 7 times is correct
    # behaviour. Collapse is when ONE chunk absorbs queries from many unrelated
    # sections — that is the model failing to discriminate, not the corpus being
    # lopsided.
    import collections as _c
    print("=" * 72)
    print("TOP-1 CONCENTRATION")
    print("=" * 72)
    section_of = {q["id"]: q["id"][0] for q in questions}
    for model in args.models:
        firsts = [results[model][i][0] for i in range(len(questions))]
        counts = _c.Counter(firsts)
        print(f"\n  {model}")
        print(f"    {len(counts)}/{len(questions)} distinct chunks in first place")
        flagged = False
        for chunk_idx, n in counts.most_common(4):
            if n < 3:
                break
            secs = {section_of[questions[i]["id"]]
                    for i in range(len(questions)) if firsts[i] == chunk_idx}
            label = chunks[chunk_idx]["breadcrumb"] or chunks[chunk_idx]["path"]
            verdict = "COLLAPSE" if len(secs) >= 4 else "topical"
            if verdict == "COLLAPSE":
                flagged = True
            print(f"    {n}x  {label[:58]}")
            print(f"         sections {sorted(secs)}  → {verdict}")
        if flagged:
            print("    ^^ one chunk is absorbing queries from 4+ unrelated sections.")
            print("       Try --no-prefix; if unchanged, the model is a poor fit.")
    print()

    # ---- agreement report: the only part worth reading in full ----
    models = args.models
    if len(models) > 1:
        print("=" * 72)
        print("PAIRWISE TOP-1 DISAGREEMENT")
        print("=" * 72)
        for x in range(len(models)):
            for y in range(x + 1, len(models)):
                a, b = models[x], models[y]
                n = sum(1 for i in range(len(questions))
                        if results[a][i][0] != results[b][i][0])
                print(f"  {a:26} vs {b:26} {n}/{len(questions)} "
                      f"({n/len(questions):.0%})")

        # full detail only where ALL models fail to agree on first place —
        # those are the queries where the choice actually matters
        contested = [i for i in range(len(questions))
                     if len({results[m][i][0] for m in models}) == len(models)]
        print(f"\n{len(contested)} question(s) where every model disagrees — read these:\n")
        for i in contested:
            q = questions[i]
            print(f"[{q['id']}] {q['question'][:100]}")
            for m in models:
                t = results[m][i][0]
                print(f"  {m:26} → {chunks[t]['breadcrumb'] or chunks[t]['path']}")
            print()
        # and the pairwise ones between the two you care most about
        a, b = models[0], models[1]
        rest = [i for i in range(len(questions))
                if results[a][i][0] != results[b][i][0] and i not in contested]
        print(f"{len(rest)} further disagreement(s) between {a} and {b}:\n")
        for i in rest:
            q = questions[i]
            ta, tb = results[a][i][0], results[b][i][0]
            ov = len(set(results[a][i]) & set(results[b][i]))
            print(f"[{q['id']}] {q['question'][:100]}")
            print(f"  {a:26} → {chunks[ta]['breadcrumb'] or chunks[ta]['path']}")
            print(f"  {b:26} → {chunks[tb]['breadcrumb'] or chunks[tb]['path']}")
            print(f"  top-{args.k} overlap: {ov}/{args.k}\n")
        print("Where they agree, neither model is telling you anything.\n")

    # ---- scored report, only if labels exist ----
    if labels:
        # Report at several cutoffs. recall@5 saturates fast on a small corpus —
        # 90%+ across every model tells you the test is easy, not that the models
        # are equal. recall@1 is where they separate.
        cutoffs = [c for c in (1, 3, 5, 10) if c <= args.k]
        print("=" * 72)
        print("RECALL (labelled subset)")
        print("=" * 72)
        header = "  " + "model".ljust(26) + "".join(f"@{c}".rjust(9) for c in cutoffs)
        print(header)
        for model in args.models:
            row = f"  {model:26}"
            for c in cutoffs:
                hits = scored = 0
                for i, q in enumerate(questions):
                    want = labels.get(q["id"])
                    if not want:
                        continue
                    scored += 1
                    texts = [chunks[j]["display_text"].lower()
                             for j in results[model][i][:c]]
                    if any(any(w.lower() in t for t in texts) for w in want):
                        hits += 1
                row += f"{hits}/{scored}".rjust(9)
            print(row)
        print()
        n_lab = sum(1 for q in questions if labels.get(q["id"]))
        print(f"  {n_lab} labelled questions. A one-question gap is "
              f"{1/n_lab:.0%} and means nothing —")
        print("  read it as a tie and decide on something else.\n")
    else:
        print("No --labels supplied, so no scores. The disagreement list above is "
              "the actionable output; labels only matter once you want a number "
              "to gate builds on.\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
