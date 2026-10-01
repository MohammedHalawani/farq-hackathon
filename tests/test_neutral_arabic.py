"""The Arabic UI addresses the administrator in gender-neutral language: verbal
nouns on buttons and titles, no gendered imperatives. Example sentences (what
the administrator types to the assistant) are their own words and exempt."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# imperatives and second-person verbs, feminine and masculine, that the UI used
GENDERED = re.compile(
    r"اختاري|أدخلي|ارفعي|اسحبي|استخدمي|أضيفي|اذكري|افتحي|أخبري|ابني|صحّحي|دعي |املئي|اكتبي|"
    r"حذفتِ|تجهّزين|تحضّرين|اكتب |اسأل|اطلب|أكّد|طبّق |اختر |ارفع |أدخل |أضف |افتح |شغّل|تطلب|تؤكّد|"
    r"أنتِ|يمكنك أن"
)


def _ui_lines(path: str, skip: tuple[str, ...] = ()) -> list[tuple[int, str]]:
    out = []
    for i, line in enumerate((ROOT / path).read_text().splitlines(), 1):
        if any(s in line for s in skip):
            continue
        out.append((i, line))
    return out


def test_no_gendered_address_in_the_arabic_ui():
    offenders = []
    for path, skip in [
        ("web/app.js", ()),
        ("web/index.html", ()),
        ("agent/catalog.py", ("example_ar",)),
        ("data/excel_io.py", ()),
        ("api/state.py", ()),
        ("core/explain.py", ()),
        ("agent/trace.py", ()),
        ("agent/describe.py", ()),
    ]:
        for i, line in _ui_lines(path, skip):
            # the example sentences the administrator would type, in app.js
            if path == "web/app.js" and re.search(r'^\s*"(د\.|ماذا لو|ليش|وش|لا محاضرات)', line):
                continue
            if GENDERED.search(line):
                offenders.append(f"{path}:{i}: {line.strip()[:90]}")
    assert not offenders, "\n".join(offenders)


def test_the_assistant_is_told_to_be_neutral_too():
    from agent.agent import SYSTEM

    assert "gender-neutral" in SYSTEM
