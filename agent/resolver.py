from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from core.models import University

DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ]")
TATWEEL = "ـ"
# Titles and the generic nouns people put in front of a name. Stripping them
# means "شعبة S19" and "room B12" match the way "S19" and "B12" do.
NOISE = {
    "د", "د.", "دكتور", "دكتوره", "الدكتور", "الدكتوره", "أ", "أ.د.", "ا",
    "استاذ", "الاستاذ", "مدرس", "المدرس", "معلم",
    "dr", "dr.", "prof", "prof.", "professor", "doctor", "instructor", "teacher",
    "شعبه", "الشعبه", "قاعه", "القاعه", "غرفه", "الغرفه", "مقرر", "المقرر",
    "ماده", "الماده", "طالب", "الطالب", "طالبه", "دفعه", "الدفعه",
    "section", "room", "hall", "course", "class", "student", "cohort", "group",
}


def normalize(text: str) -> str:
    """Fold Arabic orthography so 'احمد' matches 'أحمد'."""
    t = unicodedata.normalize("NFKC", text).strip().lower()
    t = DIACRITICS.sub("", t).replace(TATWEEL, "")
    t = re.sub("[إأآا]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"[^\w\s؀-ۿ-]", " ", t)
    return " ".join(w for w in t.split() if w not in NOISE)


def _score(query: str, candidate: str) -> float:
    """Every query word must find a home in the candidate, so a single shared
    word like "level" cannot carry a match on its own."""
    q, c = normalize(query), normalize(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    qw, cw = q.split(), c.split()
    if not qw or not cw:
        return 0.0
    per_word = [
        max(SequenceMatcher(None, a, b).ratio() for b in cw) for a in qw
    ]
    token = sum(per_word) / len(per_word)
    # Whole-string similarity only rescues near-identical spellings ("b 12" vs
    # "B12"). Left ungated it pairs any two Arabic names of the same shape.
    whole = SequenceMatcher(None, q, c).ratio()
    return max(token, whole) if whole >= 0.85 else token


DEPT_WORDS = {
    "CS": ["CS", "Computer Science", "computer", "علوم الحاسب", "حاسب", "حاسوب"],
    "CE": ["CE", "Civil Engineering", "civil", "الهندسة المدنية", "مدني", "هندسة مدنية"],
    "BA": ["BA", "Business", "business admin", "إدارة الأعمال", "اعمال", "ادارة"],
    "AR": ["AR", "Architecture", "architect", "العمارة", "عمارة", "معماري"],
}

LEVEL_WORDS = {
    1: ["1", "level 1", "year 1", "first year", "المستوى الاول", "سنة اولى", "اولى"],
    2: ["2", "level 2", "year 2", "second year", "المستوى الثاني", "سنة ثانية", "ثانية"],
    3: ["3", "level 3", "year 3", "third year", "المستوى الثالث", "سنة ثالثة", "ثالثة"],
    4: ["4", "level 4", "year 4", "fourth year", "المستوى الرابع", "سنة رابعة", "رابعة"],
}


def cohort_keys(cohort: str) -> list[str]:
    dept, level = cohort.split("-L")
    return [cohort, f"{dept}{level}"] + [
        f"{d} {lv}" for d in DEPT_WORDS[dept] for lv in LEVEL_WORDS[int(level)]
    ]


def candidates(u: University) -> list[dict]:
    out: list[dict] = []
    for i in u.instructors:
        out.append(
            {
                "kind": "instructor",
                "id": i.id,
                "label": f"{i.name} ({i.name_en})" if i.name_en else i.name,
                "keys": [i.name, i.name_en, i.id],
            }
        )
    for r in u.rooms:
        out.append(
            {
                "kind": "room",
                "id": r.id,
                "label": f"{r.id} ({r.capacity} seats{', accessible' if r.accessible else ''})",
                "keys": [r.id, r.id.replace("-", " "), r.id.replace("-", "")],
            }
        )
    for c in u.cohorts:
        out.append(
            {
                "kind": "cohort",
                "id": c,
                "label": c,
                "keys": cohort_keys(c),
            }
        )
    for s in u.sections:
        course = u.course_by_id[s.course_id]
        out.append(
            {
                "kind": "section",
                "id": s.id,
                "label": f"{s.id} — {course.name} / {course.name_ar} ({s.cohort})",
                "keys": [s.id, course.name, course.name_ar, f"{course.name} {s.cohort}"],
            }
        )
    for st in u.students:
        out.append(
            {
                "kind": "student",
                "id": st.id,
                "label": f"{st.name} ({st.id}, {st.department}-L{st.level})",
                # the ID is matched exactly, never fuzzily: there are 300 of
                # them and "S99" must not drift into "ST099"
                "keys": [st.name],
            }
        )
    return out


def is_vague(query: str) -> bool:
    """True when the query is only a title or a generic noun, e.g. 'الدكتورة'."""
    return not normalize(query).strip()


def resolve(u: University, query: str, kind: str | None = None, limit: int = 5) -> list[dict]:
    """Fuzzy match over every entity. Returns the plausible matches, best first."""
    if is_vague(query):
        return []
    everything = candidates(u)
    # `kind` is a hint, not a filter: callers guess it wrong ("شعبة" reads as
    # cohort but means section), so fall back to searching everything.
    # The fallback pool needs a much stronger match before it overrides the
    # hint, or "S99" starts matching a student called ST099.
    pools = (
        [([c for c in everything if c["kind"] == kind], 0.72), (everything, 0.88)]
        if kind
        else [(everything, 0.72)]
    )
    exact = [c for c in everything if normalize(c["id"]) == normalize(query)]
    if exact:
        return [
            {"kind": c["kind"], "id": c["id"], "label": c["label"], "score": 1.0}
            for c in exact
        ]
    top: list[tuple[float, dict]] = []
    for pool, floor in pools:
        scored = []
        for c in pool:
            best = max(_score(query, k) for k in c["keys"] if k)
            if best >= floor:
                scored.append((best, c))
        scored.sort(key=lambda x: (-x[0], x[1]["id"]))
        top = scored[:limit]
        if top:
            break
    # keep only matches close to the best one, so a clear winner stays unambiguous
    if top:
        best = top[0][0]
        cutoff = best - (0.03 if best >= 0.9 else 0.06)
        top = [x for x in top if x[0] >= cutoff]
    return [
        {"kind": c["kind"], "id": c["id"], "label": c["label"], "score": round(s, 3)}
        for s, c in top
    ]
