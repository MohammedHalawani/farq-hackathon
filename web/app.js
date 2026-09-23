const $ = (s) => document.querySelector(s);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

const I18N = {
  en: {
    tab_generate: "Compare", tab_timetable: "Timetable", tab_agent: "Agent", tab_changes: "Change log",
    run: "Run solver", running: "Solving…",
    eyebrow_compare: "Baseline vs optimiser", h_compare: "What the solver changes",
    p_compare: "The baseline mimics current practice: it avoids instructor, room and cohort clashes and ignores everything else. The optimiser treats accessibility as a hard requirement.",
    h_metrics: "Every metric, side by side", empty_compare: "Run the solver to compare.",
    eyebrow_timetable: "Weekly grid", h_timetable: "Timetable",
    opt_student: "Student", opt_cohort: "Cohort", opt_instructor: "Instructor", opt_room: "Room",
    opt_optimised: "Optimised", opt_baseline: "Baseline",
    legend_conflict: "Clash", legend_access: "Accessibility violation", legend_ok: "Scheduled",
    eyebrow_agent: "Arabic or English", h_agent: "Ask for a change",
    p_agent: "The agent never edits the schedule. It proposes a structured constraint, you confirm it, and the solver re-solves with the smallest possible change.",
    send: "Send", eyebrow_changes: "Versioned", h_changes: "Change log", undo: "Undo last change",
    metric: "Metric", baseline: "Baseline", apply: "Apply", cancel: "Cancel",
    applying: "Re-solving…", moved: "meetings moved", version: "Version", when: "When",
    change: "Change", nothing: "No changes yet.", confirm: "Confirm this change",
    preview: "What-if preview", apply_this: "Apply this change", placeholder: "Ask, or state a constraint…",
    conflicts_with: "Conflicts with", better: "better", worse: "worse",
    abbr_repeater: "REPEAT", abbr_access: "ACCESS",
  },
  ar: {
    tab_generate: "المقارنة", tab_timetable: "الجدول", tab_agent: "المساعد", tab_changes: "سجل التغييرات",
    run: "شغّل المحرك", running: "جارٍ الحل…",
    eyebrow_compare: "الأساس مقابل المحسّن", h_compare: "ما الذي يغيّره المحرك",
    p_compare: "الجدول الأساسي يحاكي الممارسة الحالية: يتجنّب تعارض المدرّسين والقاعات والدفعات فقط. أمّا المحسّن فيعامل إمكانية الوصول كشرط إلزامي.",
    h_metrics: "كل المؤشرات جنبًا إلى جنب", empty_compare: "شغّل المحرك للمقارنة.",
    eyebrow_timetable: "الجدول الأسبوعي", h_timetable: "الجدول",
    opt_student: "طالب", opt_cohort: "دفعة", opt_instructor: "مدرّس", opt_room: "قاعة",
    opt_optimised: "المحسّن", opt_baseline: "الأساسي",
    legend_conflict: "تعارض", legend_access: "مخالفة إمكانية وصول", legend_ok: "مجدول",
    eyebrow_agent: "بالعربية أو الإنجليزية", h_agent: "اطلب تعديلًا",
    p_agent: "المساعد لا يعدّل الجدول بنفسه. يقترح قيدًا منظّمًا، وأنت تؤكّده، ثم يعيد المحرك الحل بأقل تغيير ممكن.",
    send: "إرسال", eyebrow_changes: "بنسخ", h_changes: "سجل التغييرات", undo: "تراجع عن آخر تغيير",
    metric: "المؤشر", baseline: "الأساسي", apply: "تطبيق", cancel: "إلغاء",
    applying: "إعادة الحل…", moved: "محاضرة نُقلت", version: "النسخة", when: "الوقت",
    change: "التغيير", nothing: "لا توجد تغييرات بعد.", confirm: "أكّد هذا التغيير",
    preview: "معاينة ماذا لو", apply_this: "طبّق هذا التغيير", placeholder: "اسأل أو اذكر قيدًا…",
    conflicts_with: "يتعارض مع", better: "أفضل", worse: "أسوأ",
    abbr_repeater: "معيد", abbr_access: "وصول",
  },
};

const PROFILE_LABEL = {
  en: { student_friendly: "Student-friendly", room_efficient: "Room-efficient", balanced: "Balanced" },
  ar: { student_friendly: "لصالح الطلاب", room_efficient: "كفاءة القاعات", balanced: "متوازن" },
};

const state = {
  lang: "en", meta: null, entities: null, comparison: null,
  entType: "student", entId: null, source: "baseline", pending: null, busy: false,
  lastApplied: null,
};

const t = (k) => I18N[state.lang][k] || k;
const api = async (path, opts) => {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error((await r.text()) || r.statusText);
  return r.json();
};

/* ---------- language ---------- */
function applyLang() {
  document.documentElement.lang = state.lang;
  document.documentElement.dir = state.lang === "ar" ? "rtl" : "ltr";
  $("#lang-toggle").textContent = state.lang === "ar" ? "English" : "العربية";
  document.querySelectorAll("[data-i18n]").forEach((n) => { n.textContent = t(n.dataset.i18n); });
  $("#chat-input").placeholder = t("placeholder");
  renderComparison(); renderEntitySelect(); renderGrid(); renderSide(); renderChanges(); renderSuggest();
}

/* ---------- tabs ---------- */
document.querySelectorAll(".tab").forEach((b) => {
  b.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
    document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("is-active", p.id === "panel-" + b.dataset.panel));
    if (b.dataset.panel === "changes") loadChanges();
  });
});

$("#lang-toggle").addEventListener("click", () => { state.lang = state.lang === "ar" ? "en" : "ar"; applyLang(); });

/* ---------- 1 · compare ---------- */
const FMT = {
  avg_idle_hours_per_student_per_day: (v) => (v * 60).toFixed(1),
  pct_students_conflict_free: (v) => v.toFixed(1) + "%",
  pct_repeaters_conflict_free: (v) => v.toFixed(1) + "%",
  avg_room_fill_rate: (v) => (v * 100).toFixed(1) + "%",
};
const fmt = (k, v) => (FMT[k] ? FMT[k](v) : String(v));

const ROWS = [
  ["pct_students_conflict_free", "% students conflict-free", "نسبة الطلاب بلا تعارض", "higher"],
  ["pct_repeaters_conflict_free", "% repeaters conflict-free", "نسبة المعيدين بلا تعارض", "higher"],
  ["total_student_conflicts", "Total student clashes", "إجمالي تعارضات الطلاب", "lower"],
  ["accessibility_violations", "Accessibility violations", "مخالفات إمكانية الوصول", "lower"],
  ["access_max_transit_minutes", "Max transit, accessibility (min)", "أقصى انتقال لذوي الإعاقة (د)", "lower"],
  ["access_avg_transit_minutes", "Avg transit, accessibility (min)", "متوسط الانتقال لذوي الإعاقة (د)", "lower"],
  ["avg_idle_hours_per_student_per_day", "Avg idle minutes / student / day", "متوسط دقائق الفراغ لكل طالب يوميًا", "lower"],
  ["avg_walk_minutes", "Avg walking minutes", "متوسط دقائق المشي", "lower"],
  ["avg_room_fill_rate", "Avg room fill rate", "متوسط إشغال القاعات", "higher"],
  ["instructor_load_std", "Instructor load std. dev.", "الانحراف المعياري لحمل المدرّسين", "lower"],
];

function renderHeadline() {
  const host = $("#headline");
  host.innerHTML = "";
  if (!state.comparison) return;
  const b = state.comparison.baseline;
  const best = state.comparison.profiles[state.comparison.active_profile].metrics;
  const band = el("div", "band");
  band.appendChild(el("p", "eyebrow", state.lang === "ar" ? "النتيجة" : "Headline"));
  const grid = el("div", "band-grid");
  const stats = [
    [state.lang === "ar" ? "مخالفات إمكانية الوصول" : "Accessibility violations",
     b.accessibility_violations, best.accessibility_violations,
     state.lang === "ar" ? "قاعة غير مهيّأة أو انتقال يتجاوز ٦ دقائق" : "inaccessible room, or transit over 6 minutes", true],
    [state.lang === "ar" ? "المعيدون بلا تعارض" : "Repeaters conflict-free",
     b.pct_repeaters_conflict_free.toFixed(0) + "%", best.pct_repeaters_conflict_free.toFixed(0) + "%",
     state.lang === "ar" ? "الطلاب الذين يحملون مقررات من مستوى أدنى" : "students carrying a lower-level course", false],
    [state.lang === "ar" ? "دقائق الفراغ يوميًا" : "Idle minutes per day",
     (b.avg_idle_hours_per_student_per_day * 60).toFixed(0),
     (best.avg_idle_hours_per_student_per_day * 60).toFixed(0),
     state.lang === "ar" ? "متوسط لكل طالب" : "average per student", false],
  ];
  for (const [label, from, to, note, signal] of stats) {
    const s = el("div", "stat");
    s.appendChild(el("div", "stat__label", label));
    const row = el("div", "stat__row");
    row.appendChild(el("span", "stat__from", String(from)));
    const arrow = el("span", "stat__arrow", "\u2192");
    arrow.setAttribute("aria-hidden", "true");
    row.appendChild(arrow);
    row.appendChild(el("span", "stat__to" + (signal ? " stat__to--signal" : ""), String(to)));
    s.appendChild(row);
    s.appendChild(el("div", "stat__note", note));
    grid.appendChild(s);
  }
  band.appendChild(grid);
  host.appendChild(band);
}

function renderComparison() {
  renderHeadline();
  const table = $("#compare");
  table.innerHTML = "";
  if (!state.comparison) {
    const tb = el("tbody");
    const tr = el("tr");
    const td = el("td", "empty", t("empty_compare"));
    tr.appendChild(td); tb.appendChild(tr); table.appendChild(tb);
    return;
  }
  const names = Object.keys(state.comparison.profiles);
  const thead = el("thead");
  const hr = el("tr");
  hr.appendChild(el("th", null, t("metric")));
  hr.appendChild(el("th", "num", t("baseline")));
  names.forEach((n) => hr.appendChild(el("th", "num", PROFILE_LABEL[state.lang][n])));
  thead.appendChild(hr); table.appendChild(thead);

  const tb = el("tbody");
  for (const [key, en, ar, dir] of ROWS) {
    const tr = el("tr");
    tr.appendChild(el("td", "metric-name", state.lang === "ar" ? ar : en));
    const bv = state.comparison.baseline[key];
    tr.appendChild(el("td", "num", fmt(key, bv)));
    const vals = names.map((n) => state.comparison.profiles[n].metrics[key]);
    const bestVal = dir === "higher" ? Math.max(...vals) : Math.min(...vals);
    names.forEach((n, i) => {
      const v = vals[i];
      const improved = dir === "higher" ? v > bv : v < bv;
      const td = el("td", "num " + (improved ? "win" : v === bv ? "" : "lose"), fmt(key, v));
      if (v === bestVal) td.classList.add("best");
      tr.appendChild(td);
    });
    tb.appendChild(tr);
  }
  table.appendChild(tb);

  const secs = names.map((n) => state.comparison.profiles[n].seconds);
  $("#solve-note").textContent = state.lang === "ar"
    ? `زمن الحل ${Math.max(...secs).toFixed(0)} ثانية لكل ملف`
    : `solved in ${Math.max(...secs).toFixed(0)}s per profile`;
}

async function runSolver() {
  if (state.busy) return;
  state.busy = true;
  const btn = $("#run");
  btn.disabled = true;
  btn.replaceChildren(el("span", "spinner"), document.createTextNode(" " + t("running")));
  btn.querySelector(".spinner").setAttribute("aria-hidden", "true");
  try {
    state.comparison = await api("/api/generate", { method: "POST" });
    renderComparison();
    setStatus();
    state.source = "current";
    $("#ent-source").value = "current";
    await loadGrid();
  } catch (e) {
    alert(e.message);
  } finally {
    state.busy = false;
    btn.disabled = false;
    btn.textContent = t("run");
  }
}
$("#run").addEventListener("click", runSolver);

function setStatus() {
  const s = $("#bar-status");
  if (!state.comparison) { s.textContent = ""; s.className = "chip"; return; }
  const m = state.comparison.profiles[state.comparison.active_profile].metrics;
  s.className = "chip " + (m.accessibility_violations === 0 ? "chip--ok" : "chip--bad");
  s.textContent = `${m.accessibility_violations} ${state.lang === "ar" ? "مخالفة" : "violations"}`;
}

/* ---------- 2 · timetable ---------- */
function entityOptions() {
  const e = state.entities;
  if (!e) return [];
  if (state.entType === "student")
    return e.students.map((s) => ({
      id: s.id,
      label: `${s.name} · ${s.cohort}${s.repeater ? " · " + t("abbr_repeater") : ""}${s.needs_accessibility ? " · " + t("abbr_access") : ""}`,
    }));
  if (state.entType === "cohort") return e.cohorts.map((c) => ({ id: c.id, label: c.name }));
  if (state.entType === "instructor") return e.instructors.map((i) => ({ id: i.id, label: i.name }));
  return e.rooms.map((r) => ({ id: r.id, label: `${r.id} · ${r.capacity}${r.accessible ? " · " + t("abbr_access") : ""}` }));
}

function renderEntitySelect() {
  const sel = $("#ent-id");
  if (!state.entities) return;
  const opts = entityOptions();
  sel.innerHTML = "";
  for (const o of opts) {
    const n = el("option", null, o.label);
    n.value = o.id;
    n.dir = "auto";
    sel.appendChild(n);
  }
  if (!opts.find((o) => o.id === state.entId)) state.entId = opts[0]?.id ?? null;
  sel.value = state.entId;
}

$("#ent-type").addEventListener("change", (e) => {
  state.entType = e.target.value;
  const featured = state.entities?.featured;
  state.entId = state.entType === "student" ? featured?.needs_accessibility : null;
  renderEntitySelect();
  loadGrid();
});
$("#ent-id").addEventListener("change", (e) => { state.entId = e.target.value; loadGrid(); });
$("#ent-source").addEventListener("change", (e) => { state.source = e.target.value; loadGrid(); });

let gridData = null;
async function loadGrid() {
  if (!state.entId) return;
  if (state.source === "current" && !state.comparison) { gridData = null; renderGrid(); return; }
  gridData = await api(`/api/schedule/${state.entType}/${state.entId}?source=${state.source}`);
  renderGrid();
}

function renderGrid() {
  const host = $("#grid");
  host.innerHTML = "";
  if (!state.meta) return;
  const days = state.lang === "ar" ? state.meta.days_ar : state.meta.days;
  host.appendChild(el("div", "gh", ""));
  days.forEach((d) => host.appendChild(el("div", "gh", d)));

  const cells = {};
  (gridData?.cells ?? []).forEach((c) => {
    (cells[`${c.day}:${c.period}`] ||= []).push(c);
  });

  state.meta.periods.forEach((label, p) => {
    host.appendChild(el("div", "gt", label));
    for (let d = 0; d < days.length; d++) {
      const box = el("div", "cell");
      const list = cells[`${d}:${p}`] || [];
      if (!list.length) box.classList.add("cell--empty");
      for (const c of list) {
        const ev = el("div", "ev" + (c.conflict ? " ev--conflict" : c.accessibility_issue ? " ev--access" : ""));
        const title = el("div", "ev__title", state.lang === "ar" ? c.course_ar : c.course);
        title.dir = "auto";
        ev.appendChild(title);
        const meta = el("div", "ev__meta", `${c.room} · ${c.enrollment}/${c.capacity}${c.accessible ? " · " + t("abbr_access") : ""}`);
        ev.appendChild(meta);
        if (state.entType !== "instructor") {
          const who = el("div", "ev__meta", c.instructor);
          who.dir = "auto";
          ev.appendChild(who);
        }
        if (c.conflict) ev.appendChild(el("span", "flag flag--conflict", state.lang === "ar" ? "تعارض" : "clash"));
        if (c.accessibility_issue) ev.appendChild(el("span", "flag flag--access", c.accessibility_issue));
        box.appendChild(ev);
      }
      host.appendChild(box);
    }
  });

  const flags = $("#ent-flags");
  flags.innerHTML = "";
  const nConf = (gridData?.cells ?? []).filter((c) => c.conflict).length;
  const nAcc = (gridData?.cells ?? []).filter((c) => c.accessibility_issue).length;
  const chip = (cls, text) => { const c = el("span", "chip " + cls, text); flags.appendChild(c); };
  if (gridData) {
    chip(nConf ? "chip--bad" : "chip--ok", `${nConf} ${state.lang === "ar" ? "تعارض" : "clashes"}`);
    chip(nAcc ? "chip--warn" : "chip--ok", `${nAcc} ${state.lang === "ar" ? "مخالفة وصول" : "access issues"}`);
  }
}

/* ---------- 3 · agent ---------- */
const SUGGEST = {
  en: [
    "Dr. Ahmed can't teach Tuesday after 2pm",
    "What if we close room B12?",
    "Why does BA-L2 have a gap on Monday?",
    "Why is S01-m1 scheduled where it is?",
  ],
  ar: [
    "د. أحمد ما يقدر يدرّس الثلاثاء بعد الساعة ٢",
    "ماذا لو أغلقنا قاعة B12؟",
    "ليش عند BA-L2 فراغ يوم الاثنين؟",
    "وش وضع جدول د. سارة القحطاني؟",
  ],
};

function renderSuggest() {
  const host = $("#suggest");
  if (!host) return;
  host.replaceChildren();
  for (const text of SUGGEST[state.lang]) {
    const b = el("button", null, text);
    b.type = "button";
    b.dir = "auto";
    b.title = text;
    b.addEventListener("click", () => sendMessage(text));
    host.appendChild(b);
  }
}

function addMessage(role, text) {
  const log = $("#chat-log");
  const wrap = el("div", "msg msg--" + role);
  wrap.appendChild(el("div", "msg__who", role === "admin"
    ? (state.lang === "ar" ? "أنت" : "Admin")
    : (state.lang === "ar" ? "المساعد" : "Assistant")));
  const body = el("div", "msg__body", text);
  body.dir = "auto";
  wrap.appendChild(body);
  log.appendChild(wrap);
  log.scrollTop = log.scrollHeight;
  return wrap;
}

$("#chat-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const v = $("#chat-input").value.trim();
  if (v) sendMessage(v);
});

async function sendMessage(text) {
  if (state.busy) return;
  state.busy = true;
  $("#chat-input").value = "";
  addMessage("admin", text);
  const pending = addMessage("agent", state.lang === "ar" ? "…" : "…");
  try {
    const out = await api("/api/agent/message", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ message: text }),
    });
    pending.querySelector(".msg__body").textContent = out.reply;
    state.pending = out.card || null;
    renderSide();
  } catch (e) {
    pending.querySelector(".msg__body").textContent = e.message;
  } finally {
    state.busy = false;
  }
}

function deltaRows(deltas) {
  const table = el("table");
  const tb = el("tbody");
  let any = false;
  for (const key of Object.keys(deltas)) {
    const d = deltas[key];
    if (d.delta === 0) continue;
    any = true;
    const improved = d.better === "higher" ? d.delta > 0 : d.delta < 0;
    const tr = el("tr");
    tr.appendChild(el("td", "metric-name", d.label));
    tr.appendChild(el("td", "num", fmt(key, d.before)));
    tr.appendChild(el("td", "num " + (improved ? "delta-up" : "delta-down"), fmt(key, d.after)));
    tb.appendChild(tr);
  }
  if (!any) {
    const tr = el("tr");
    tr.appendChild(el("td", "empty", state.lang === "ar" ? "لا تغيّر في المؤشرات" : "No metric changed"));
    tb.appendChild(tr);
  }
  table.appendChild(tb);
  return table;
}

function cardRows(describe) {
  const dl = el("dl", "confirm__rows");
  for (const r of describe.rows) {
    const row = el("div", "crow");
    row.appendChild(el("dt", null, state.lang === "ar" ? r.label_ar : r.label_en));
    const dd = el("dd", null, state.lang === "ar" && r.value_ar ? r.value_ar : r.value);
    dd.dir = "auto";
    row.appendChild(dd);
    dl.appendChild(row);
  }
  return dl;
}

function renderSide() {
  const host = $("#side");
  if (!host) return;
  host.replaceChildren();
  const c = state.pending;
  if (!c) {
    const card = el("div", "card");
    card.appendChild(el("div", "empty", state.lang === "ar"
      ? "لا يوجد تغيير بانتظار التأكيد."
      : "No change is waiting for confirmation."));
    host.appendChild(card);
    if (state.lastApplied) host.appendChild(appliedCard(state.lastApplied));
    return;
  }

  const card = el("div", "card");
  const head = el("div", "card__head");
  head.appendChild(el("h3", null, state.lang === "ar" ? c.describe.title_ar : c.describe.title_en));
  head.appendChild(el("span", "chip " + (c.kind === "what_if" ? "chip--signal" : ""),
    c.kind === "what_if" ? t("preview") : t("confirm")));
  card.appendChild(head);
  card.appendChild(cardRows(c.describe));

  if (c.kind === "what_if" && c.feasible === false) {
    const n = el("div", "notice notice--bad",
      (state.lang === "ar" ? "لا يوجد جدول ممكن. " : "No feasible schedule. ") +
      t("conflicts_with") + ": " + (c.blocking || []).join("; "));
    n.style.margin = "0 var(--space-sm) var(--space-xs)";
    card.appendChild(n);
  } else if (c.kind === "what_if") {
    const sub = el("div", "card__head");
    sub.appendChild(el("span", "eyebrow", state.lang === "ar" ? "أثر التغيير" : "Effect"));
    sub.appendChild(el("span", "chip", `${c.moved_count} ${t("moved")}`));
    card.appendChild(sub);
    card.appendChild(deltaRows(c.deltas));
  }

  const actions = el("div", "actions");
  if (!(c.kind === "what_if" && c.feasible === false)) {
    const apply = el("button", "btn btn--primary",
      c.kind === "what_if" ? t("apply_this") : t("apply"));
    apply.type = "button";
    apply.addEventListener("click", () => applyPending(apply));
    actions.appendChild(apply);
  }
  const cancel = el("button", "btn btn--ghost", t("cancel"));
  cancel.type = "button";
  cancel.addEventListener("click", () => { state.pending = null; renderSide(); });
  actions.appendChild(cancel);
  card.appendChild(actions);
  host.appendChild(card);
  if (state.lastApplied) host.appendChild(appliedCard(state.lastApplied));
}

function appliedCard(v) {
  const card = el("div", "card");
  const head = el("div", "card__head");
  head.appendChild(el("h3", null, state.lang === "ar" ? "آخر تغيير مطبّق" : "Last applied change"));
  head.appendChild(el("span", "chip chip--ok", `${v.moved_count} ${t("moved")}`));
  card.appendChild(head);
  card.appendChild(deltaRows(v.deltas));
  const actions = el("div", "actions");
  const undo = el("button", "btn", t("undo"));
  undo.type = "button";
  undo.addEventListener("click", () => doUndo(undo));
  actions.appendChild(undo);
  card.appendChild(actions);
  return card;
}

async function applyPending(btn) {
  if (state.busy) return;
  state.busy = true;
  btn.disabled = true;
  btn.replaceChildren(el("span", "spinner"), document.createTextNode(" " + t("applying")));
  btn.querySelector(".spinner").setAttribute("aria-hidden", "true");
  try {
    const out = await api("/api/changes/apply", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ constraint: state.pending.constraint }),
    });
    if (!out.ok) {
      addMessage("agent", (state.lang === "ar" ? "تعذّر التطبيق: " : "Could not apply: ") +
        out.message + " — " + t("conflicts_with") + ": " +
        (out.blocking || []).map((b) => b.type).join(", "));
      state.pending = null;
    } else {
      state.lastApplied = out.version;
      state.pending = null;
      addMessage("agent", (state.lang === "ar"
        ? `تم التطبيق. نُقلت ${out.version.moved_count} محاضرة.`
        : `Applied. ${out.version.moved_count} meetings moved.`));
      await refreshAfterChange();
    }
    renderSide();
  } catch (e) {
    addMessage("agent", e.message);
  } finally {
    state.busy = false;
  }
}

async function doUndo(btn) {
  if (state.busy) return;
  state.busy = true;
  if (btn) btn.disabled = true;
  try {
    const out = await api("/api/changes/undo", { method: "POST" });
    if (!out.ok) { addMessage("agent", out.message); return; }
    state.lastApplied = out.version.index > 0 ? out.version : null;
    addMessage("agent", state.lang === "ar" ? "تم التراجع." : "Change undone.");
    await refreshAfterChange();
    renderSide();
  } finally {
    state.busy = false;
    if (btn) btn.disabled = false;
  }
}

$("#undo").addEventListener("click", () => doUndo($("#undo")));

async function refreshAfterChange() {
  state.source = "current";
  $("#ent-source").value = "current";
  await loadGrid();
  await loadChanges();
}

/* ---------- 4 · change log ---------- */
let changeData = null;

async function loadChanges() {
  changeData = await api("/api/changes");
  renderChanges();
}

function renderChanges() {
  const table = $("#changes");
  if (!table) return;
  table.replaceChildren();
  const thead = el("thead");
  const hr = el("tr");
  [t("version"), t("change"), t("when"), t("moved")].forEach((h, i) =>
    hr.appendChild(el("th", i === 3 ? "num" : null, h)));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tb = el("tbody");
  const rows = changeData?.versions ?? [];
  if (!rows.length) {
    const tr = el("tr");
    const td = el("td", "empty", t("nothing"));
    td.colSpan = 4;
    tr.appendChild(td);
    tb.appendChild(tr);
  }
  for (const v of rows) {
    const tr = el("tr");
    tr.appendChild(el("td", "num", "#" + v.index));
    const what = el("td", "metric-name", v.label);
    what.dir = "auto";
    tr.appendChild(what);
    tr.appendChild(el("td", "mono", v.at.replace("T", " ").replace("+00:00", "")));
    tr.appendChild(el("td", "num", v.index ? String(v.moved_count) : "—"));
    tb.appendChild(tr);
  }
  table.appendChild(tb);
}

/* ---------- boot ---------- */
(async function boot() {
  state.meta = await api("/api/meta");
  state.entities = await api("/api/entities");
  state.entId = state.entities.featured.needs_accessibility;
  applyLang();
  renderEntitySelect();
  await loadGrid();
  await loadChanges();
})();
