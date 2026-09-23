from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from core.models import University

DIACRITICS = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۜ]")
TATWEEL = "ـ"
TITLES = ("د.", "د", "dr.", "dr", "prof.", "prof", "أ.د.", "أ.")


def normalize(text: str) -> str:
    """Fold Arabic orthography so 'احمد' matches 'أحمد'."""
    t = unicodedata.normalize("NFKC", text).strip().lower()
    t = DIACRITICS.sub("", t).replace(TATWEEL, "")
    t = re.sub("[إأآا]", "ا", t)
    t = t.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    t = re.sub(r"[^\w\s؀-ۿ-]", " ", t)
    words = [w for w in t.split() if w not in TITLES]
    return " ".join(words)


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
    return max(token, SequenceMatcher(None, q, c).ratio())


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
        out.append({"kind": "instructor", "id": i.id, "label": i.name, "keys": [i.name, i.id]})
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
                "keys": [st.name, st.id],
            }
        )
    return out


def resolve(u: University, query: str, kind: str | None = None, limit: int = 5) -> list[dict]:
    """Fuzzy match over every entity. Returns the plausible matches, best first."""
    pool = candidates(u)
    if kind:
        pool = [c for c in pool if c["kind"] == kind]
    exact = [c for c in pool if normalize(c["id"]) == normalize(query)]
    if exact:
        pool = exact
    scored = []
    for c in pool:
        best = max(_score(query, k) for k in c["keys"])
        if best >= 0.72:
            scored.append((best, c))
    scored.sort(key=lambda x: (-x[0], x[1]["id"]))
    top = scored[:limit]
    # keep only matches close to the best one, so a clear winner stays unambiguous
    if top:
        best = top[0][0]
        cutoff = best - (0.03 if best >= 0.9 else 0.06)
        top = [x for x in top if x[0] >= cutoff]
    return [
        {"kind": c["kind"], "id": c["id"], "label": c["label"], "score": round(s, 3)}
        for s, c in top
    ]
