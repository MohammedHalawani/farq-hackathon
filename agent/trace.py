"""The step tracker the UI shows beside the chat.

Every entry is built from what actually happened — the lookups the agent ran,
the constraint it validated, the solve that followed. Nothing here is written
by the model.
"""

from __future__ import annotations

from agent.describe import describe, short_label, short_label_ar
from core.models import University


def step(name_en: str, name_ar: str, status: str, detail_en: str, detail_ar: str) -> dict:
    return {
        "step": name_en,
        "step_ar": name_ar,
        "status": status,
        "detail": detail_en,
        "detail_ar": detail_ar,
    }


def for_message(u: University, message: str, tools, card: dict | None) -> list[dict]:
    """Steps 1-5: what the agent did with one request."""
    out = [
        step("read request", "قراءة الطلب", "ok",
             message if len(message) <= 90 else message[:90] + "…",
             message if len(message) <= 90 else message[:90] + "…")
    ]

    lookups = tools.lookups
    if lookups:
        last = lookups[-1]
        names = ", ".join(
            f"{m['id']}" for m in _matches_of(tools, last["query"])
        )
        if last["vague"]:
            status, en, ar = ("warn",
                              f"'{last['query']}' names nothing specific",
                              f"«{last['query']}» لا يحدد كيانًا بعينه")
        elif last["count"] == 0:
            status, en, ar = ("fail",
                              f"'{last['query']}' — no match",
                              f"«{last['query']}» — لا يوجد تطابق")
        elif last["count"] == 1:
            status, en, ar = ("ok",
                              f"'{last['query']}' — 1 match ({names})",
                              f"«{last['query']}» — تطابق واحد ({names})")
        else:
            status, en, ar = ("warn",
                              f"'{last['query']}' — {last['count']} matches ({names}), asking which",
                              f"«{last['query']}» — {last['count']} تطابقات ({names})، نسأل أيّها")
        out.append(step("entity resolution", "تحديد الكيان", status, en, ar))
    else:
        out.append(step("entity resolution", "تحديد الكيان", "ok",
                        "no new lookup needed", "لا حاجة لبحث جديد"))

    if card is None:
        return out

    c = card["constraint"]
    out.append(step("rule built", "بناء القاعدة", "ok",
                    short_label(u, c), short_label_ar(u, c)))
    title = describe(u, c)
    out.append(step(
        "schema validation", "التحقق من الصيغة", "ok",
        f"«{title['title_en']}» accepted by the strict schema",
        f"«{title['title_ar']}» مقبولة وفق الصيغة الصارمة",
    ))

    if card["kind"] == "what_if" and card.get("feasible") is False:
        out.append(step(
            "re-solving", "إعادة الحل", "fail",
            "no schedule satisfies this — " + "; ".join(card.get("blocking", [])),
            "لا يوجد جدول يحقق هذا — " + "؛ ".join(card.get("blocking_ar") or card.get("blocking", [])),
        ))
        return out

    if card["kind"] == "what_if":
        n = card.get("moved_count", 0)
        total = len(u.meetings)
        out.append(step("preview solved", "حُلّت المعاينة", "ok",
                        f"{total - n} kept, {n} would move",
                        f"{total - n} ثابتة، {n} ستُنقل"))

    out.append(step("waiting for approval", "بانتظار الموافقة", "wait",
                    "nothing applied yet", "لم يُطبَّق شيء بعد"))
    return out


def for_apply(u: University, constraint: dict, result: dict, total: int) -> list[dict]:
    """Steps 6-7: what the confirmed change actually did."""
    label, label_ar = short_label(u, constraint), short_label_ar(u, constraint)
    if not result["ok"]:
        blocking = "; ".join(short_label(u, b) for b in result.get("blocking", []))
        blocking_ar = "؛ ".join(short_label_ar(u, b) for b in result.get("blocking", []))
        return [
            step("re-solving", "إعادة الحل", "fail",
                 result.get("message", "no feasible schedule"),
                 "لا يوجد جدول يحقق هذه القاعدة مع القواعد المؤكدة"),
            step("rules check", "فحص القواعد", "fail",
                 f"conflicts with: {blocking}", f"يتعارض مع: {blocking_ar}"),
        ]

    if result.get("stage") == "setup":
        n = len(result.get("rules", []))
        return [
            step("rule saved for the build", "حُفظت القاعدة للبناء", "ok", label, label_ar),
            step("feasibility check", "فحص الإمكانية", "ok",
                 f"a timetable still exists with all {n} setup rules",
                 f"يوجد جدول ممكن مع قواعد الإعداد كلها ({n})"),
        ]

    v = result["version"]
    moved = v["moved_count"]
    m = v["metrics"]
    return [
        step("rule applied", "طُبِّقت القاعدة", "ok", label, label_ar),
        step("re-solving (minimal change)", "إعادة الحل بأقل تغيير", "ok",
             f"{total - moved} meetings kept, {moved} moved",
             f"{total - moved} محاضرة ثابتة، {moved} نُقلت"),
        step("rules check", "فحص القواعد", "ok",
             f"{m['total_student_conflicts']} clashes, "
             f"{m['accessibility_violations']} accessibility violations",
             f"{m['total_student_conflicts']} تعارض، "
             f"{m['accessibility_violations']} مخالفة وصول"),
    ]


def _matches_of(tools, query: str) -> list[dict]:
    """The matches the last lookup for this query returned."""
    from agent.resolver import resolve

    return resolve(tools.s.u, query)[:3]
