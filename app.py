from flask import Flask, render_template, request, jsonify
from spellchecker import SpellChecker
import re

app = Flask(__name__)
spell = SpellChecker()
custom_dict = set()

# ---------------- Tokenization Helpers ---------------- #
WORD_RE = re.compile(r"\w+", re.UNICODE)
TOKEN_RE = re.compile(r"\w+|[^\w\s]", re.UNICODE)

PUNCT_STICKY_RIGHT = re.compile(r"^[,.;:!?%)]}]+$")
PUNCT_STICKY_LEFT = re.compile(r"^[([{]+$")
APOSTROPHE = re.compile(r"^[’'`]")

# Slang and contractions mapping
CHAT_SLANG = {
    "u": "you", "ur": "your", "r": "are", "pls": "please", "plz": "please",
    "thx": "thanks", "ty": "thanks", "btw": "by the way", "idk": "I don't know",
    "imo": "in my opinion", "imho": "in my opinion", "afaik": "as far as I know",
    "brb": "be right back", "ttyl": "talk to you later"
}
CONTRACTIONS_FIX = {
    "dont": "don't", "cant": "can't", "wont": "won't", "im": "I'm",
    "ive": "I've", "youre": "you're", "isnt": "isn't", "wasnt": "wasn't",
    "werent": "weren't", "shouldnt": "shouldn't", "couldnt": "couldn't",
    "wouldnt": "wouldn't", "didnt": "didn't", "doesnt": "doesn't"
}
VOWELS = set("aeiou")


def match_case(src: str, tgt: str) -> str:
    """Match capitalization style of src with tgt."""
    if src.isupper():
        return tgt.upper()
    if src.istitle():
        return tgt.title()
    return tgt


def detokenize(tokens):
    """Reconstruct text from tokens."""
    out = ""
    prev = ""
    for t in tokens:
        if not out:
            out = t
        else:
            if PUNCT_STICKY_RIGHT.match(t):
                out += t
            elif APOSTROPHE.match(t) and WORD_RE.search(prev):
                out += t
            else:
                out += " " + t
        prev = t
    return out


def reduce_repeats(word: str) -> str:
    # heeellooo -> heelloo (limit repeats to 2)
    return re.sub(r"(\w)\1{2,}", r"\1\1", word)


def preprocess_informal(text: str) -> str:
    """Handle slang, contractions, and quotes cleanup."""
    t = (
        text.replace("\u2019", "'")
        .replace("\u2018", "'")
        .replace("\u201c", '"')
        .replace("\u201d", '"')
    )
    t = re.sub(r"\s+", " ", t)

    def _map_token(tok: str) -> str:
        if not WORD_RE.fullmatch(tok):
            return tok
        low = tok.lower()
        if low in CONTRACTIONS_FIX:
            return match_case(tok, CONTRACTIONS_FIX[low])
        if low in CHAT_SLANG:
            return match_case(tok, CHAT_SLANG[low])
        rr = reduce_repeats(low)
        return match_case(tok, rr)

    tokens = TOKEN_RE.findall(t)
    tokens = [_map_token(tok) for tok in tokens]
    return detokenize(tokens)


def basic_spell_correct(text: str):
    """Perform basic spelling correction."""
    tokens = TOKEN_RE.findall(text)
    suggestions = []
    corrected = []

    for idx, tok in enumerate(tokens):
        if WORD_RE.fullmatch(tok):
            low = tok.lower()
            # allow custom words + known words
            if low in custom_dict or not spell.unknown([low]):
                corrected.append(tok)
                continue

            best = spell.correction(low)
            if best is None:
                corrected.append(tok)
                continue

            fixed = match_case(tok, best)
            corrected.append(fixed)

            if fixed != tok:
                cands = list(spell.candidates(low))
                suggestions.append(
                    {
                        "index": idx,
                        "from": tok,
                        "to": fixed,
                        "candidates": list(cands)[:5],
                    }
                )
        else:
            corrected.append(tok)

    return detokenize(corrected), suggestions


def post_fluency(text: str) -> str:
    """Tidy spaces/punctuation + sentence case; fix 'a/an' + lowercase i."""
    s = text
    s = re.sub(r"\s+([,.;:!?])", r"\1", s)
    s = re.sub(r"([,.;:!?])(?!\s|$)", r"\1 ", s)
    s = re.sub(r"\s+\)", ")", s)
    s = re.sub(r"\(\s+", "(", s)
    s = re.sub(r"\s+", " ", s).strip()
    s = re.sub(r"\bi\b", "I", s)

    def a_an(m):
        nxt = m.group(2)
        return "an " + nxt if nxt and nxt[0].lower() in VOWELS else "a " + nxt

    s = re.sub(r"\b(a|an)\s+([A-Za-z]+)", a_an, s)

    def cap_sentences(t: str) -> str:
        parts = re.split(r"(\.|\?|!)(\s+)", t)
        out = []
        for i in range(0, len(parts), 3):
            chunk = parts[i]
            sep = parts[i + 1] if i + 1 < len(parts) else ""
            sp = parts[i + 2] if i + 2 < len(parts) else ""
            if chunk:
                chunk = chunk[:1].upper() + chunk[1:]
            out.append(chunk + sep + sp)
        return "".join(out).strip()

    return cap_sentences(s)


def pipeline_correct(text: str):
    """Main text-correction pipeline + metrics."""
    pre = preprocess_informal(text)
    spelled, suggestions = basic_spell_correct(pre)
    final = post_fluency(spelled)

    metrics = {
        "chars": len(final),
        "words": len(re.findall(r"\b\w+\b", final)),
        "sentences": len(re.findall(r"[.!?]", final)) or (1 if final else 0),
    }

    # Extra: rough Grammar Score & Readability (Flesch Reading Ease approximation)
    grammar_score = max(100 - (len(suggestions) * 5), 0)
    avg_words_per_sentence = metrics["words"] / (metrics["sentences"] or 1)
    # crude syllable proxy: characters/word; fine for a lightweight metric
    avg_syllables_per_word = (len(final) / max(metrics["words"], 1)) / 3.0
    readability = 206.835 - 1.015 * avg_words_per_sentence - 84.6 * avg_syllables_per_word

    return final, suggestions, metrics, grammar_score, round(readability, 2)


# ---------------- Flask Routes ---------------- #
@app.route("/")
def index():
    return render_template("index.html")


@app.post("/api/correct")
def api_correct():
    data = request.get_json(force=True)
    text = data.get("text", "")
    final, suggestions, metrics, score, readability = pipeline_correct(text)
    return jsonify(
        {
            "original": text,
            "corrected": final,
            "suggestions": suggestions,
            "metrics": metrics,
            "grammar_score": score,
            "readability": readability,
        }
    )


@app.post("/api/add_word")
def api_add_word():
    data = request.get_json(force=True)
    word = data.get("word", "").strip().lower()
    if not word.isalpha():
        return jsonify({"success": False, "error": "Please provide a single alphabetic word."})
    custom_dict.add(word)
    try:
        spell.word_frequency.load_words([word])
    except Exception:
        pass
    return jsonify({"success": True, "word": word})


@app.post("/api/correct_file")
def api_correct_file():
    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file uploaded"})
    f = request.files["file"]
    try:
        text = f.read().decode("utf-8", errors="ignore")
    except Exception:
        return jsonify({"success": False, "error": "Unable to read file as text"})

    final, suggestions, metrics, score, readability = pipeline_correct(text)
    return jsonify(
        {
            "success": True,
            "corrected": final,
            "suggestions": suggestions,
            "metrics": metrics,
            "grammar_score": score,
            "readability": readability,
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
