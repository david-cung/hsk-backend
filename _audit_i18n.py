import re
from collections import Counter

import app.seed as seed

items = seed._content_lessons()

ENGLISH_STOPWORDS = {
    "the", "is", "are", "a", "an", "to", "of", "and", "or", "for", "in", "on",
    "this", "that", "with", "as", "it", "you", "your", "was", "were", "be",
    "learn", "learners", "practice", "lesson", "sentence", "word", "words",
    "choose", "arrange", "complete", "fill", "type", "correct", "meaning",
}

VI_CHAR_RE = re.compile(r"[À-ỹ]")
CJK_RE = re.compile(r"[\u4e00-\u9fff]")


LESSON_ID_RE = re.compile(r"^[A-Z]+\d*-[A-Z]+-\d+$")


def is_pinyin_text(text: str) -> bool:
    if text.startswith("Pinyin: "):
        return True
    words = re.findall(r"[A-Za-z']+[0-9]?", text)
    if not words:
        return False
    pinyin_words = sum(1 for w in words if re.search(r"[1-5]$", w))
    return pinyin_words >= max(1, len(words) - 1)


def is_untranslatable_content(text: str) -> bool:
    """Chinese/pinyin/grammar-symbol/ID content that legitimately stays identical."""
    if CJK_RE.search(text):
        return True
    if not re.search(r"[A-Za-z]", text):
        return True
    if is_pinyin_text(text):
        return True
    if LESSON_ID_RE.match(text):
        return True
    return False


MIXED_ENGLISH_FUNCTION_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "am", "do", "does", "did",
    "will", "would", "can", "could", "should", "has", "have", "had", "and",
    "or", "but", "if", "when", "where", "what", "how", "who", "whom", "whose",
    "which", "why", "at", "in", "on", "to", "of", "for", "with", "before",
    "after", "behind", "front", "this", "that", "these", "those", "it", "its",
    "he", "she", "they", "we", "you", "your", "my", "his", "her", "their",
    "our", "not", "no", "yes", "shows", "image", "speaker", "asking",
}


def looks_english_leftover(vi_text: str) -> bool:
    if not vi_text:
        return False
    words = re.findall(r"[A-Za-z]+", vi_text)
    lower_words = [w.lower() for w in words if len(w) > 2]
    if not lower_words:
        return False
    if not VI_CHAR_RE.search(vi_text):
        # Fully-English VI field (no Vietnamese diacritics at all): flag on 2+
        # generic English stopword hits.
        hits = sum(1 for w in lower_words if w in ENGLISH_STOPWORDS)
        return hits >= 2
    # Mixed field: VI diacritics ARE present, but so are common English
    # function words. This is a worse bug than a fully-English field (it is a
    # broken half-translation visible on screen), so flag on a single hit,
    # while ignoring Chinese-content lines (grammar explanations that
    # legitimately quote CJK text alongside Vietnamese commentary).
    if CJK_RE.search(vi_text):
        return False
    hits = sum(1 for w in lower_words if w in MIXED_ENGLISH_FUNCTION_WORDS)
    return hits >= 1


def finalize_content(item):
    title_translations = item.get("title_translations") or seed._lesson_title_translations(
        item["title"], item["lesson_type"]
    )
    description_translations = item.get("description_translations") or seed._lesson_description_translations(
        item.get("description"), item["lesson_type"], int(item["hsk_level"]), title_translations
    )
    content = dict(item["content"])
    content["title_translations"] = title_translations
    if description_translations:
        content["description_translations"] = description_translations
    content = seed._augment_content_translations(content)
    return content


fake_pairs = []  # (path, en, vi)
leftover_pairs = []  # (path, en, vi)
missing_en = []
missing_vi = []

TRANS_SUFFIXES = ("_translations",)


def walk(node, path):
    if isinstance(node, dict):
        for key, value in node.items():
            if key.endswith("_translations") and isinstance(value, dict):
                en = value.get("en")
                vi = value.get("vi")
                if isinstance(en, list) or isinstance(vi, list):
                    for idx, (e_item, v_item) in enumerate(zip(en or [], vi or [])):
                        if not isinstance(e_item, str) or not isinstance(v_item, str):
                            continue
                        p = f"{path}.{key}[{idx}]"
                        if e_item.strip() and not v_item.strip():
                            missing_vi.append(p)
                        elif v_item.strip() and not e_item.strip():
                            missing_en.append(p)
                        elif (
                            e_item.strip()
                            and v_item.strip()
                            and e_item.strip() == v_item.strip()
                            and not is_untranslatable_content(e_item.strip())
                        ):
                            fake_pairs.append((p, e_item, v_item))
                        elif looks_english_leftover(v_item) and not is_pinyin_text(v_item):
                            leftover_pairs.append((p, e_item, v_item))
                    continue
                if not isinstance(en, str) or not isinstance(vi, str):
                    continue
                p = f"{path}.{key}"
                if en.strip() and not vi.strip():
                    missing_vi.append(p)
                elif vi.strip() and not en.strip():
                    missing_en.append(p)
                elif (
                    en.strip()
                    and vi.strip()
                    and en.strip() == vi.strip()
                    and not is_untranslatable_content(en.strip())
                ):
                    fake_pairs.append((p, en, vi))
                elif looks_english_leftover(vi) and not is_pinyin_text(vi):
                    leftover_pairs.append((p, en, vi))
            else:
                walk(value, f"{path}.{key}")
    elif isinstance(node, list):
        for idx, value in enumerate(node):
            walk(value, f"{path}[{idx}]")


for item in items:
    content = finalize_content(item)
    walk(content, f"lesson:{item['id']}")

print("Total lesson items:", len(items))
print("Missing EN fields:", len(missing_en))
print("Missing VI fields:", len(missing_vi))
print("Fake (identical en==vi) fields:", len(fake_pairs))
print("Leftover-English-in-VI fields (heuristic):", len(leftover_pairs))
print()
print("=== ALL fake pairs (genuine, non-CJK) ===")
for p, en, vi in fake_pairs:
    print(f"- {p}\n    en: {en!r}\n    vi: {vi!r}")
print()
print("=== ALL leftover-English pairs ===")
for p, en, vi in leftover_pairs:
    print(f"- {p}\n    en: {en!r}\n    vi: {vi!r}")
print()
print("=== Sample missing VI (up to 20) ===")
for p in missing_vi[:20]:
    print(f"- {p}")
print()
print("=== Sample missing EN (up to 20) ===")
for p in missing_en[:20]:
    print(f"- {p}")
