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
    run: "Build the timetable", running: "Building…",
    eyebrow_compare: "Baseline vs optimiser", h_compare: "What the solver changes",
    p_compare: "The baseline mimics current practice: it avoids instructor, room and cohort clashes and ignores everything else. The optimiser treats accessibility as a hard requirement.",
    h_metrics: "Every metric, side by side", empty_compare: "Build the timetable (Data tab) to compare.",
    eyebrow_timetable: "Weekly grid", h_timetable: "Timetable",
    opt_student: "Student", opt_cohort: "Cohort", opt_instructor: "Instructor", opt_room: "Room",
    opt_optimised: "Optimised", opt_baseline: "Baseline", opt_compare_mode: "Before / after",
    legend_conflict: "Clash", legend_access: "Accessibility violation", legend_ok: "Scheduled",
    eyebrow_agent: "Arabic or English", h_agent: "Ask for a change",
    p_agent: "The agent never edits the schedule. It proposes a structured constraint, you confirm it, and the solver re-solves with the smallest possible change.",
    send: "Send", eyebrow_changes: "Versioned", h_changes: "Change log", undo: "Undo last change",
    metric: "Metric", baseline: "Baseline", apply: "Apply", cancel: "Cancel",
    applying: "Re-solving…", moved: "meetings moved", moved_col: "Moved",
    version: "Version", when: "When (UTC)",
    change: "Change", effect: "Effect", nothing: "No changes yet.", confirm: "Confirm this change",
    preview: "What-if preview", apply_this: "Apply this change", placeholder: "Ask, or state a constraint…",
    conflicts_with: "Conflicts with", better: "better", worse: "worse",
    abbr_repeater: "REPEAT", abbr_access: "ACCESS",
    tab_data: "Data", eyebrow_data: "From your file to a finished timetable",
    h_data: "Build the semester timetable",
    p_data: "Today this is built by hand, one level at a time, over one to one and a half weeks. Bring in the file you already prepare, state your rules, and let the solver build every level at once.",
    s1_title: "Bring in the data",
    s1_p: "Upload the Excel file you prepare today: courses, sections, rooms and instructors. Student groups are optional.",
    s1_drop: "Drag the .xlsx file here", s1_choose: "Choose a file",
    s1_template: "Download the template", s1_demo: "Use the demo campus",
    s2_title: "Add your rules",
    s2_p: "State rules to the assistant in Arabic or English. Each one is checked, shown to you, and applied only when you confirm.",
    s2_go: "Open the assistant",
    s2_empty: "Tell the assistant your rules, for example: no lectures from 12 to 1.",
    s2_built: "The timetable is built. From here, every change goes through the assistant and appears in the change log.",
    s3_title: "Build the timetable",
    s3_p: "Every level, every section, every room, at once, with no clashes for instructors, rooms or students.",
    race_us: "Jadwal", race_manual_label: "By hand", race_manual: "1 to 1.5 weeks",
    export: "Download timetable (Excel)",
  },
  ar: {
    tab_generate: "المقارنة", tab_timetable: "الجدول", tab_agent: "المساعد", tab_changes: "سجل التغييرات",
    run: "ابني الجدول", running: "جارٍ البناء…",
    eyebrow_compare: "الأساس مقابل المحسّن", h_compare: "ما الذي يغيّره المحرك",
    p_compare: "الجدول الأساسي يحاكي الممارسة الحالية: يتجنّب تعارض المدرّسين والقاعات والدفعات فقط. أمّا المحسّن فيعامل إمكانية الوصول كشرط إلزامي.",
    h_metrics: "كل المؤشرات جنبًا إلى جنب", empty_compare: "ابني الجدول (تبويب البيانات) للمقارنة.",
    eyebrow_timetable: "الجدول الأسبوعي", h_timetable: "الجدول",
    opt_student: "طالب", opt_cohort: "دفعة", opt_instructor: "مدرّس", opt_room: "قاعة",
    opt_optimised: "المحسّن", opt_baseline: "الأساسي", opt_compare_mode: "قبل / بعد",
    legend_conflict: "تعارض", legend_access: "مخالفة إمكانية وصول", legend_ok: "مجدول",
    eyebrow_agent: "بالعربية أو الإنجليزية", h_agent: "اطلب تعديلًا",
    p_agent: "المساعد لا يعدّل الجدول بنفسه. يقترح قيدًا منظّمًا، وأنت تؤكّده، ثم يعيد المحرك الحل بأقل تغيير ممكن.",
    send: "إرسال", eyebrow_changes: "بنسخ", h_changes: "سجل التغييرات", undo: "تراجع عن آخر تغيير",
    metric: "المؤشر", baseline: "الأساسي", apply: "تطبيق", cancel: "إلغاء",
    applying: "إعادة الحل…", moved: "محاضرة نُقلت", moved_col: "المنقولة",
    version: "النسخة", when: "الوقت (UTC)",
    change: "التغيير", effect: "الأثر", nothing: "لا توجد تغييرات بعد.", confirm: "أكّد هذا التغيير",
    preview: "معاينة ماذا لو", apply_this: "طبّق هذا التغيير", placeholder: "اسأل أو اذكر قيدًا…",
    conflicts_with: "يتعارض مع", better: "أفضل", worse: "أسوأ",
    abbr_repeater: "معيد", abbr_access: "وصول",
    tab_data: "البيانات", eyebrow_data: "من ملفك إلى جدول جاهز",
    h_data: "ابني جدول الفصل",
    p_data: "اليوم يُبنى الجدول يدويًا، مستوى بعد مستوى، خلال أسبوع إلى أسبوع ونص. أدخلي الملف الذي تجهّزينه أصلًا، واذكري قواعدك، ودعي المحرك يبني المستويات كلها دفعة واحدة.",
    s1_title: "أدخلي البيانات",
    s1_p: "ارفعي ملف Excel الذي تجهّزينه اليوم: المقررات والشعب والقاعات والمدرسون. مجموعات الطلاب اختيارية.",
    s1_drop: "اسحبي ملف ‎.xlsx‎ هنا", s1_choose: "اختاري ملفًا",
    s1_template: "تنزيل القالب", s1_demo: "استخدمي الحرم التجريبي",
    s2_title: "أضيفي القواعد",
    s2_p: "اذكري قواعدك للمساعد بالعربي أو بالإنجليزي. كل قاعدة تُفحص وتُعرض عليك، ولا تُطبَّق إلا بعد تأكيدك.",
    s2_go: "افتحي المساعد",
    s2_empty: "أخبري المساعد بقواعدك، مثل: لا محاضرات من ١٢ إلى ١",
    s2_built: "تم بناء الجدول. أي تغيير بعد الآن يمر عبر المساعد ويظهر في سجل التغييرات.",
    s3_title: "ابني الجدول",
    s3_p: "كل المستويات والشعب والقاعات دفعة واحدة، بلا تعارض للمدرسين أو القاعات أو الطلاب.",
    race_us: "جدول", race_manual_label: "يدويًا", race_manual: "أسبوع إلى أسبوع ونص",
    export: "تنزيل الجدول (Excel)",
  },
};

const PROFILE_LABEL = {
  en: { student_friendly: "Student-friendly", room_efficient: "Room-efficient", balanced: "Balanced" },
  ar: { student_friendly: "لصالح الطلاب", room_efficient: "كفاءة القاعات", balanced: "متوازن" },
};

const REDUCED = window.matchMedia
  ? window.matchMedia("(prefers-reduced-motion: reduce)")
  : { matches: false };

/** Primitive 1: count a figure up to its value. Reduced motion prints it. */
function countUp(node, to, render) {
  const target = Number(to);
  if (!Number.isFinite(target) || REDUCED.matches) {
    node.textContent = render(target);
    return;
  }
  const started = performance.now();
  const dur = 1100;
  const step = (now) => {
    const t = Math.min((now - started) / dur, 1);
    const eased = 1 - Math.pow(1 - t, 3);
    node.textContent = render(target * eased);
    if (t < 1) requestAnimationFrame(step);
    else node.textContent = render(target);
  };
  requestAnimationFrame(step);
}

/** Primitive 2: one-shot stagger. Index drives the delay, CSS does the rest. */
function stagger(nodes, from = 0) {
  nodes.forEach((n, i) => {
    n.style.setProperty("--i", String(Math.min(from + i, 12)));
    n.classList.add("reveal");
  });
}

/** Percentages the headline shows: keep a decimal while the number is small,
 *  so 0.7% does not round away to 1%. */
const pctLabel = (v) => (v < 10 ? Number(v).toFixed(1) : String(Math.round(v))) + "%";

const state = {
  lang: "en", meta: null, entities: null, comparison: null,
  entType: "student", entId: null, source: "baseline", pending: null, busy: false,
  lastApplied: null, movedMeetings: new Set(), trace: [], moves: [], overlay: null,
  upload: null,   // the last upload's report, kept even when it was rejected
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
  renderComparison(); renderPersonas(); renderEntitySelect(); renderGrid(); renderSide(); renderChanges(); renderSuggest();
  renderTrace(state.trace, { animate: false });
  renderData();
}

/* ---------- tabs ---------- */
function showTab(name) {
  document.querySelectorAll(".tab").forEach((x) => x.setAttribute("aria-selected", String(x.dataset.panel === name)));
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("is-active", p.id === "panel-" + name));
  if (name === "changes") loadChanges();
}
document.querySelectorAll(".tab").forEach((b) => {
  b.addEventListener("click", () => showTab(b.dataset.panel));
});

$("#lang-toggle").addEventListener("click", () => { state.lang = state.lang === "ar" ? "en" : "ar"; applyLang(); });

/* ---------- 1 · compare ---------- */
const FMT = {
  avg_idle_minutes_per_student_per_day: (v) => v.toFixed(1),
  instructor_load_std: (v) => v.toFixed(2),
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
  ["avg_idle_minutes_per_student_per_day", "Avg idle minutes / student / day", "متوسط دقائق الفراغ لكل طالب يوميًا", "lower"],
  ["pct_students_with_2h_gap", "% students with a 2h+ gap", "نسبة الطلاب بفراغ ساعتين فأكثر", "lower"],
  ["pct_students_with_any_gap", "% students with any gap", "نسبة الطلاب بأي فراغ", "lower"],
  ["worst_gap_hours", "Worst single gap (hours)", "أطول فراغ متصل (ساعات)", "lower"],
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
  const applied = state.lastApplied;
  const total = (state.meta?.counts?.sections ?? 60) * 2;
  const stats = [
    [state.lang === "ar" ? "مخالفات إمكانية الوصول" : "Accessibility violations",
     b.accessibility_violations, best.accessibility_violations,
     state.lang === "ar" ? "قاعة غير مهيّأة أو انتقال يتجاوز ٦ دقائق" : "inaccessible room, or transit over 6 minutes", true],
    [state.lang === "ar" ? "المعيدون بلا تعارض" : "Repeaters conflict-free",
     pctLabel(b.pct_repeaters_conflict_free), pctLabel(best.pct_repeaters_conflict_free),
     state.lang === "ar" ? "الطلاب الذين يحملون مقررات من مستوى أدنى" : "students carrying a lower-level course", false],
    [state.lang === "ar" ? "طلاب بفراغ ساعتين فأكثر" : "Students with a 2h+ gap",
     pctLabel(b.pct_students_with_2h_gap), pctLabel(best.pct_students_with_2h_gap),
     state.lang === "ar" ? "فراغ متصل خلال اليوم" : "an unbroken idle block in their day", false],
    [state.lang === "ar" ? "محاضرات نُقلت بآخر تغيير" : "Meetings moved by the last change",
     applied ? String(total - applied.moved_count) + " " + (state.lang === "ar" ? "ثابتة" : "kept") : "\u2014",
     applied ? String(applied.moved_count) : "\u2014",
     applied ? applied.label : (state.lang === "ar" ? "لم يُطبَّق تغيير بعد" : "no change applied yet"),
     false],
  ];
  const counters = [];
  stats.forEach(([label, from, to, note, signal], i) => {
    const s = el("div", "stat");
    s.style.setProperty("--i", String(i));
    s.classList.add("reveal");
    s.appendChild(el("div", "stat__label", label));
    const row = el("div", "stat__row");
    row.appendChild(el("span", "stat__from", String(from)));
    const arrow = el("span", "stat__arrow", "\u2192");
    arrow.setAttribute("aria-hidden", "true");
    row.appendChild(arrow);
    const toNode = el("span", "stat__to" + (signal ? " stat__to--signal" : ""), String(to));
    row.appendChild(toNode);
    counters.push([toNode, String(to)]);
    s.appendChild(row);
    s.appendChild(el("div", "stat__note", note));
    grid.appendChild(s);
  });
  band.appendChild(grid);
  host.appendChild(band);

  // count each headline figure up once the band is on screen
  counters.forEach(([node, text], i) => {
    if (!/\d/.test(text)) return;   // the placeholder dash never counts up
    const isPct = text.endsWith("%");
    const value = parseFloat(text);
    const render = (v) => (isPct ? pctLabel(v) : String(Math.round(v)));
    node.textContent = render(0);
    setTimeout(() => countUp(node, value, render), 220 + i * 90);
  });
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
  const rows = [];
  for (const [key, en, ar, dir] of ROWS) {
    const tr = el("tr");
    rows.push(tr);
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
  stagger(rows);

  const secs = names.map((n) => state.comparison.profiles[n].seconds);
  $("#solve-note").textContent = state.lang === "ar"
    ? `زمن الحل ${Math.max(...secs).toFixed(0)} ثانية لكل ملف`
    : `solved in ${Math.max(...secs).toFixed(0)}s per profile`;
}

function showProgress() {
  const host = $("#build-progress");
  host.replaceChildren();
  const box = el("div", "progress");
  const head = el("div", "progress__head");
  head.appendChild(el("span", "eyebrow", state.lang === "ar" ? "جارٍ الحل" : "Solving"));
  const count = el("span", "chip chip--signal", "0/3");
  head.appendChild(count);
  box.appendChild(head);
  const track = el("div", "progress__track progress__track--idle");
  const bar = el("div", "progress__bar");
  track.appendChild(bar);
  box.appendChild(track);
  const steps = el("div", "progress__steps");
  box.appendChild(steps);
  const note = el("div", "stat__note", state.lang === "ar"
    ? "ثلاثة ملفات تُحل بالتوازي، نحو ٣٥ ثانية للحرم التجريبي."
    : "Three profiles solved in parallel, about 35 seconds on the demo campus.");
  note.style.color = "var(--color-ink-3)";
  box.appendChild(note);
  host.appendChild(box);
  return { track, bar, count, steps };
}

async function pollProgress(ui, stop) {
  while (!stop.done) {
    try {
      const p = await api("/api/progress");
      if (p.rounds_total) {
        ui.track.classList.remove("progress__track--idle");
        ui.bar.style.transform = `scaleX(${p.rounds_done / p.rounds_total})`;
        ui.count.textContent = `${p.done}/${p.total}`;
        ui.steps.replaceChildren(
          ...p.solved.map((n) => el("span", "chip chip--ok", PROFILE_LABEL[state.lang][n] || n))
        );
      }
    } catch (e) { /* the solve itself reports real failures */ }
    await new Promise((r) => setTimeout(r, 400));
  }
}

async function runSolver() {
  if (state.busy) return;
  state.busy = true;
  const btn = $("#run");
  btn.disabled = true;
  btn.replaceChildren(el("span", "spinner"), document.createTextNode(" " + t("running")));
  btn.querySelector(".spinner").setAttribute("aria-hidden", "true");
  const stop = { done: false };
  const ui = showProgress();
  pollProgress(ui, stop);
  // the clock the coordinator compares with a week and a half by hand
  const started = performance.now();
  const clock = $("#build-time");
  const tick = setInterval(() => { clock.textContent = seconds((performance.now() - started) / 1000); }, 100);
  try {
    state.comparison = await api("/api/generate", { method: "POST" });
    stop.done = true;
    clearInterval(tick);
    state.buildSeconds = (performance.now() - started) / 1000;
    showBuildTime(state.buildSeconds);
    $("#build-progress").replaceChildren();
    state.meta = await api("/api/meta");
    renderComparison();
    setStatus();
    renderData();
    renderSuggest();
    // after the first solve, move the reader from the problem to the fix —
    // but never override a view they chose themselves
    if (state.source === "baseline") {
      state.source = "current";
      $("#ent-source").value = "current";
    }
    showTab("timetable");
    await loadGrid();
  } catch (e) {
    stop.done = true;
    clearInterval(tick);
    clock.textContent = "—";
    $("#build-progress").replaceChildren(el("div", "notice notice--bad", errorText(e)));
  } finally {
    stop.done = true;
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

function renderPersonas() {
  const host = $("#personas");
  if (!host || !state.entities) return;
  host.replaceChildren();
  for (const p of state.entities.personas || []) {
    const b = el("button", "persona");
    b.type = "button";
    b.setAttribute("aria-pressed", String(state.entId === p.id && state.entType === p.entity_type));
    const av = el("div", "persona__avatar persona__avatar--" + p.kind, p.initial);
    av.setAttribute("aria-hidden", "true");
    b.appendChild(av);
    const box = el("div");
    const name = el("div", "persona__name", state.lang === "ar" ? p.name : p.name_en);
    name.dir = "auto";
    box.appendChild(name);
    const tag = el("div", "persona__tag",
      (state.lang === "ar" ? p.tag_ar : p.tag_en) + (p.cohort ? " · " + p.cohort : ""));
    tag.dir = "auto";
    box.appendChild(tag);
    b.appendChild(box);
    b.addEventListener("click", () => {
      state.entType = p.entity_type;
      state.entId = p.id;
      $("#ent-type").value = p.entity_type;
      renderEntitySelect();
      renderPersonas();
      loadGrid();
    });
    host.appendChild(b);
  }
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
  renderPersonas();
  loadGrid();
});
$("#ent-id").addEventListener("change", (e) => { state.entId = e.target.value; renderPersonas(); loadGrid(); });
$("#ent-source").addEventListener("change", (e) => { state.source = e.target.value; loadGrid(); });

let gridData = null;
let compareData = { baseline: null, current: null };

async function loadGrid() {
  if (!state.entId) return;
  const path = (src) => `/api/schedule/${state.entType}/${state.entId}?source=${src}`;
  if (state.source === "compare") {
    if (!state.comparison) { await runSolver(); if (!state.comparison) return; }
    const [b, c] = await Promise.all([api(path("baseline")), api(path("current"))]);
    compareData = { baseline: b, current: c };
    renderGrid();
    return;
  }
  if (state.source === "current" && !state.comparison) { gridData = null; renderGrid(); return; }
  gridData = await api(path(state.source));
  renderGrid();
}

function buildGrid(host, data, opts = {}) {
  host.replaceChildren();
  if (!state.meta) return;
  const days = state.lang === "ar" ? state.meta.days_ar : state.meta.days;
  host.appendChild(el("div", "gh", ""));
  days.forEach((d) => host.appendChild(el("div", "gh", d)));

  const cells = {};
  (data?.cells ?? []).forEach((c) => {
    (cells[`${c.day}:${c.period}`] ||= []).push(c);
  });

  // where each moved meeting used to sit, so the grid can show the jump
  const ghosts = {};
  if (opts.ghosts !== false) {
    const shown = new Set((data?.cells ?? []).map((c) => c.meeting_id));
    for (const m of state.moves || []) {
      if (!shown.has(m.meeting_id) || !m.from) continue;
      (ghosts[`${m.from.day_index}:${m.from.period}`] ||= []).push(m);
    }
  }

  state.meta.periods.forEach((label, p) => {
    host.appendChild(el("div", "gt", label));
    for (let d = 0; d < days.length; d++) {
      const box = el("div", "cell");
      const list = cells[`${d}:${p}`] || [];
      const gh = ghosts[`${d}:${p}`] || [];
      if (!list.length && !gh.length) box.classList.add("cell--empty");
      if (opts.overlay && opts.overlay.day === d
          && opts.overlay.gap_hours.includes(state.meta.periods[p])) {
        box.classList.add("cell--gap");
      }
      for (const g of gh) {
        const ghost = el("div", "ev ev--ghost");
        const t = el("div", "ev__title", state.lang === "ar" ? g.course_ar : g.course);
        t.dir = "auto";
        ghost.appendChild(t);
        ghost.appendChild(el("div", "ev__meta", `${g.from.room} → ${g.to.hour}`));
        box.appendChild(ghost);
      }
      for (const c of list) {
        const moved = state.movedMeetings.has(c.meeting_id);
        const landed = (state.moves || []).some((m) => m.meeting_id === c.meeting_id);
        const ev = el("div", "ev"
          + (c.conflict ? " ev--conflict" : c.accessibility_issue ? " ev--access" : "")
          + (moved ? " ev--moved" : "")
          + (landed ? " ev--landed" : ""));
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
        const problems = c.problems || [];
        if (opts.why && problems.length) {
          for (const p of problems) {
            const w = el("span", "why why--" + p.kind, state.lang === "ar" ? p.text_ar : p.text_en);
            w.dir = "auto";
            ev.appendChild(w);
          }
        } else {
          if (c.conflict) ev.appendChild(el("span", "flag flag--conflict", state.lang === "ar" ? "تعارض" : "clash"));
          if (c.accessibility_issue) ev.appendChild(el("span", "flag flag--access", c.accessibility_issue));
        }
        if (opts.why && !problems.length) {
          ev.appendChild(el("span", "ok-mark", "\u2705 " + (state.lang === "ar" ? "سليم" : "clear")));
        }
        for (const b of (opts.overlay?.blocked ?? []).filter((x) => x.meeting_id === c.meeting_id)) {
          const row = el("div", "blocked blocked--" + b.kind);
          const ic = el("span", "blocked__icon", BLOCK_ICON[b.kind] || BLOCK_ICON.other);
          ic.setAttribute("aria-hidden", "true");
          row.appendChild(ic);
          row.appendChild(el("span", null,
            `${b.to_hour} · ${state.lang === "ar" ? b.label_ar : b.label_en}`));
          box.classList.add("cell--try");
          ev.appendChild(row);
        }
        box.appendChild(ev);
      }
      host.appendChild(box);
    }
  });

  stagger([...host.querySelectorAll(".ev")].slice(0, 13));
}

function problemChip(n) {
  const word = state.lang === "ar" ? (n === 1 ? "مشكلة" : "مشاكل") : (n === 1 ? "problem" : "problems");
  return el("span", "chip " + (n ? "chip--bad" : "chip--ok"), `${n} ${word}`);
}

function renderGrid() {
  const split = $("#split-view"), single = $("#single-view");
  const isCompare = state.source === "compare";
  single.hidden = isCompare;
  split.hidden = !isCompare;

  if (isCompare) {
    split.replaceChildren();
    const wrap = el("div", "split");
    for (const [key, label] of [
      ["baseline", state.lang === "ar" ? "الأساسي" : "Baseline"],
      ["current", state.lang === "ar" ? "المحسّن" : "Optimised"],
    ]) {
      const side = el("div", "split__side");
      const head = el("div", "split__head");
      head.appendChild(el("span", "eyebrow", label));
      const data = compareData[key];
      head.appendChild(problemChip(data ? data.problem_count : 0));
      side.appendChild(head);
      const gw = el("div", "grid-wrap");
      const g = el("div", "grid");
      gw.appendChild(g);
      side.appendChild(gw);
      wrap.appendChild(side);
      buildGrid(g, data, { why: true });
    }
    split.appendChild(wrap);
    $("#ent-flags").replaceChildren();
    return;
  }

  buildGrid($("#grid"), gridData, { overlay: state.overlay });
  const flags = $("#ent-flags");
  flags.replaceChildren();
  if (gridData) {
    const nConf = gridData.cells.filter((c) => c.conflict).length;
    const nAcc = gridData.cells.filter((c) => c.accessibility_issue).length;
    flags.appendChild(el("span", "chip " + (nConf ? "chip--bad" : "chip--ok"),
      `${nConf} ${state.lang === "ar" ? "تعارض" : "clashes"}`));
    flags.appendChild(el("span", "chip " + (nAcc ? "chip--warn" : "chip--ok"),
      `${nAcc} ${state.lang === "ar" ? "مخالفة وصول" : "access issues"}`));
  }
}

/* ---------- 3 · agent ---------- */
// before the first build the useful things to say are setup rules
const SUGGEST_SETUP = {
  en: [
    "No lectures from 12 to 1 for anyone",
    "No lectures after 2 on Thursday",
    "Dr. Ahmed Alali can't teach on Sunday",
  ],
  ar: [
    "لا محاضرات من ١٢ إلى ١",
    "لا محاضرات بعد ٢ يوم الخميس",
    "د. أحمد العلي ما يقدر يدرّس يوم الأحد",
  ],
};
const SUGGEST = {
  en: [
    "Dr. Ahmed can't teach Tuesday after 2pm",
    "What if we close room B12?",
    "Why does AR-L2 have a 3-hour gap on Thursday?",
    "Why is meeting S01-m1 scheduled where it is?",
  ],
  ar: [
    "د. أحمد ما يقدر يدرّس الثلاثاء بعد الساعة ٢",
    "ماذا لو أغلقنا قاعة B12؟",
    "ليش عند عمارة المستوى الثاني فراغ ٣ ساعات يوم الخميس؟",
    "وش جدول د. سارة القحطاني؟",
  ],
};

function renderSuggest() {
  const host = $("#suggest");
  if (!host) return;
  host.replaceChildren();
  const built = state.comparison || state.meta?.data?.built;
  for (const text of (built ? SUGGEST : SUGGEST_SETUP)[state.lang]) {
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
    if (out.card && out.card.kind === "what_if" && out.card.moves) {
      state.moves = out.card.moves;
      loadGrid();
    }
    state.trace = out.trace || [];
    renderTrace(state.trace);
    if (out.overlay) {
      state.overlay = out.overlay;
      state.entType = out.overlay.entity_type;
      state.entId = out.overlay.entity_id;
      if (state.source === "compare") state.source = "current";
      $("#ent-source").value = state.source;
      $("#ent-type").value = state.entType;
      renderEntitySelect();
      renderPersonas();
      await loadGrid();
    }
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

const STATUS_MARK = { ok: "\u2713", warn: "!", wait: "", fail: "\u2715" };

// icons for why a class could not move into a gap
const BLOCK_ICON = {
  instructor: "\u{1F464}", unavailable: "\u{1F6AB}", rule: "\u{1F4CB}",
  room: "\u{1F6AA}", access: "\u267F", days: "\u{1F4C5}",
  clash: "\u26A0", pointless: "\u2014", other: "\u2022",
};

/** Reveal the tracker one step at a time so a viewer can follow it. */
function renderTrace(trace, { animate = true } = {}) {
  const host = $("#tracker");
  if (!host) return;
  host.replaceChildren();
  if (!trace || !trace.length) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  const card = el("div", "card");
  const head = el("div", "card__head");
  head.appendChild(el("h3", null, state.lang === "ar" ? "ما فعله المساعد" : "What the agent did"));
  card.appendChild(head);
  const list = el("ol", "tracker");
  card.appendChild(list);
  host.appendChild(card);

  const paint = (t) => {
    const li = el("li", "tstep tstep--" + t.status);
    const dot = el("div", "tstep__dot", STATUS_MARK[t.status] || "");
    dot.setAttribute("aria-hidden", "true");
    li.appendChild(dot);
    const body = el("div");
    body.appendChild(el("div", "tstep__name", state.lang === "ar" ? t.step_ar : t.step));
    const detail = el("div", "tstep__detail", state.lang === "ar" ? t.detail_ar : t.detail);
    detail.dir = "auto";
    body.appendChild(detail);
    li.appendChild(body);
    if (animate && !REDUCED.matches) li.classList.add("reveal");
    list.appendChild(li);
  };

  if (!animate || REDUCED.matches) {
    trace.forEach(paint);
    return;
  }
  trace.forEach((t, i) => setTimeout(() => paint(t), i * 300));
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
    if (state.overlay) host.appendChild(gapCard(state.overlay));
    if (state.lastApplied) host.appendChild(appliedCard(state.lastApplied));
    if ((state.moves || []).length) host.appendChild(movesCard(state.moves));
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
  if (state.overlay) host.appendChild(gapCard(state.overlay));
  if (state.lastApplied) host.appendChild(appliedCard(state.lastApplied));
  if ((state.moves || []).length) host.appendChild(movesCard(state.moves));
}

function gapCard(overlay) {
  const card = el("div", "card");
  const head = el("div", "card__head");
  head.appendChild(el("h3", null, state.lang === "ar" ? "لماذا الفراغ موجود" : "Why the gap is there"));
  head.appendChild(el("span", "chip chip--warn",
    `${overlay.entity_id} · ${overlay.gap_hours.join(", ")}`));
  card.appendChild(head);
  const list = el("ul", "gap-note");
  for (const b of overlay.blocked) {
    const li = el("li");
    const what = el("div", "move__what",
      `${BLOCK_ICON[b.kind] || "•"} ${state.lang === "ar" ? b.course_ar : b.course} · ${b.from_hour} → ${b.to_hour}`);
    what.dir = "auto";
    li.appendChild(what);
    const why = el("div", "move__path", state.lang === "ar" ? b.detail_ar : b.detail);
    why.dir = "auto";
    li.appendChild(why);
    list.appendChild(li);
  }
  card.appendChild(list);
  return card;
}

function movesCard(moves) {
  const card = el("div", "card");
  const head = el("div", "card__head");
  head.appendChild(el("h3", null, state.lang === "ar" ? "ما الذي تحرّك" : "What moved"));
  head.appendChild(el("span", "chip chip--signal", String(moves.length)));
  card.appendChild(head);
  const list = el("ul", "moves");
  for (const m of moves.slice(0, 12)) {
    const li = el("li", "move");
    const what = el("div", "move__what",
      `${state.lang === "ar" ? m.course_ar : m.course} · ${m.section_id}`);
    what.dir = "auto";
    li.appendChild(what);
    const path = el("div", "move__path");
    const from = state.lang === "ar" ? m.from.day_ar : m.from.day;
    const to = state.lang === "ar" ? m.to.day_ar : m.to.day;
    path.append(
      `${from} ${m.from.hour} · ${m.from.room}  →  `,
      Object.assign(document.createElement("b"), { textContent: `${to} ${m.to.hour} · ${m.to.room}` })
    );
    li.appendChild(path);
    list.appendChild(li);
  }
  if (moves.length > 12) {
    list.appendChild(el("li", "move", `+${moves.length - 12} more`));
  }
  card.appendChild(list);
  return card;
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
    state.trace = (state.trace || []).concat(out.trace || []);
    renderTrace(out.trace || [], { animate: true });
    if (!out.ok) {
      addMessage("agent", (state.lang === "ar" ? "تعذّر التطبيق: " : "Could not apply: ") +
        out.message + " — " + t("conflicts_with") + ": " +
        (out.blocking || []).map((b) => b.type).join(", "));
      state.pending = null;
    } else if (out.stage === "setup") {
      // nothing to re-solve yet: the rule waits for the build
      state.pending = null;
      state.meta.data.setup_rules = out.rules || [];
      addMessage("agent", state.lang === "ar"
        ? "حُفظت كقاعدة إعداد، وستُطبَّق عند بناء الجدول (تبويب البيانات، الخطوة ٣)."
        : "Saved as a setup rule. It is applied when you build the timetable (Data tab, step 3).");
      renderData();
    } else {
      state.lastApplied = out.version;
      state.moves = out.version.moves || [];
      state.pending = null;
      addMessage("agent", (state.lang === "ar"
        ? `تم التطبيق. نُقلت ${out.version.moved_count} محاضرة.`
        : `Applied. ${out.version.moved_count} meetings moved.`));
      await refreshAfterChange(out.version.moved);
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
    state.moves = out.version.moves || [];
    addMessage("agent", state.lang === "ar" ? "تم التراجع." : "Change undone.");
    await refreshAfterChange(out.version.moved);
    renderSide();
  } finally {
    state.busy = false;
    if (btn) btn.disabled = false;
  }
}

$("#undo").addEventListener("click", () => doUndo($("#undo")));

async function refreshAfterChange(moved) {
  state.movedMeetings = new Set(moved || []);
  state.source = "current";
  $("#ent-source").value = "current";
  await loadGrid();
  await loadChanges();
  // the flash is one-shot: drop the marks so a later re-render is calm
  setTimeout(() => { state.movedMeetings = new Set(); }, 1600);
}

/* ---------- 4 · change log ---------- */
let changeData = null;

async function loadChanges() {
  changeData = await api("/api/changes");
  renderChanges();
}

const METRIC_LABEL = (key) => {
  const row = ROWS.find((r) => r[0] === key);
  return row ? (state.lang === "ar" ? row[2] : row[1]) : key;
};

/** The change in the reader's language, from Python's description. */
function changeLabel(v) {
  if (!v.describe) {
    return v.index === 0
      ? (state.lang === "ar" ? "الجدول الأول" : "Initial schedule")
      : v.label;
  }
  const d = v.describe;
  const title = state.lang === "ar" ? d.title_ar : d.title_en;
  const parts = d.rows.map((r) => (state.lang === "ar" && r.value_ar ? r.value_ar : r.value));
  return `${title} — ${parts.join(" · ")}`;
}

/** What the change actually did to the schedule. */
function effectCell(v) {
  const td = el("td");
  if (!v.index) {
    td.appendChild(el("span", "chip", state.lang === "ar" ? "نقطة البداية" : "starting point"));
    return td;
  }
  const changed = Object.entries(v.deltas || {}).filter(([, x]) => x.delta !== 0);
  if (!changed.length) {
    td.appendChild(el("span", "chip chip--ok", state.lang === "ar" ? "لا تغيّر" : "no metric moved"));
    return td;
  }
  for (const [key, x] of changed.slice(0, 4)) {
    const improved = x.better === "higher" ? x.delta > 0 : x.delta < 0;
    const row = el("div", "effect");
    row.appendChild(el("span", "effect__name", METRIC_LABEL(key)));
    row.appendChild(el("span", "effect__val " + (improved ? "delta-up" : "delta-down"),
      `${fmt(key, x.before)} → ${fmt(key, x.after)}`));
    td.appendChild(row);
  }
  if (changed.length > 4) td.appendChild(el("div", "effect__more", `+${changed.length - 4}`));
  return td;
}

function renderChanges() {
  const table = $("#changes");
  if (!table) return;
  table.replaceChildren();
  const thead = el("thead");
  const hr = el("tr");
  [t("version"), t("change"), t("effect"), t("when"), t("moved_col")].forEach((h, i) =>
    hr.appendChild(el("th", i === 4 ? "num" : null, h)));
  thead.appendChild(hr);
  table.appendChild(thead);
  const tb = el("tbody");
  const rows = changeData?.versions ?? [];
  if (!rows.length) {
    const tr = el("tr");
    const td = el("td", "empty", t("nothing"));
    td.colSpan = 5;
    tr.appendChild(td);
    tb.appendChild(tr);
  }
  for (const v of [...rows].reverse()) {
    const tr = el("tr");
    tr.appendChild(el("td", "num", "#" + v.index));
    const what = el("td", "metric-name", changeLabel(v));
    what.dir = "auto";
    tr.appendChild(what);
    tr.appendChild(effectCell(v));
    const when = el("td", "mono", v.at.replace("T", " ").replace("+00:00", ""));
    when.title = state.lang === "ar" ? "بتوقيت UTC" : "UTC";
    tr.appendChild(when);
    tr.appendChild(el("td", "num", v.index ? String(v.moved_count) : "—"));
    tb.appendChild(tr);
  }
  table.appendChild(tb);
}

/* ---------- 0 · data ---------- */
const seconds = (v) => (state.lang === "ar" ? `${v.toFixed(1)} ث` : `${v.toFixed(1)} s`);

/** FastAPI errors arrive as JSON text; show the message, not the braces. */
function errorText(e) {
  try { return JSON.parse(e.message).detail || e.message; } catch { return e.message; }
}

const SUMMARY = [
  ["levels", "Levels", "المستويات"], ["courses", "Courses", "المقررات"],
  ["sections", "Sections", "الشعب"], ["students", "Students", "الطلاب"],
  ["instructors", "Instructors", "المدرسون"], ["rooms", "Rooms", "القاعات"],
];

function reportList(items, kind) {
  const ul = el("ul", "report report--" + kind);
  for (const it of items) {
    const li = el("li");
    const where = [it.sheet, it.row ? (state.lang === "ar" ? `صف ${it.row}` : `row ${it.row}`) : null]
      .filter(Boolean).join(" · ");
    if (where) li.appendChild(el("span", "report__where", where));
    const msg = el("span", null, state.lang === "ar" ? it.ar : it.en);
    msg.dir = "auto";
    li.appendChild(msg);
    ul.appendChild(li);
  }
  return ul;
}

function renderData() {
  const host = $("#data-status");
  if (!host || !state.meta) return;
  const d = state.meta.data;
  host.replaceChildren();

  // which campus is loaded
  const src = el("div", "source");
  src.appendChild(el("span", "chip " + (d.is_demo ? "" : "chip--signal"),
    d.is_demo ? (state.lang === "ar" ? "الحرم التجريبي" : "demo campus")
              : (state.lang === "ar" ? "ملفك" : "your file")));
  if (!d.is_demo) {
    const name = el("span", "source__name", d.source);
    name.dir = "auto";
    src.appendChild(name);
  }
  host.appendChild(src);

  const grid = el("dl", "summary");
  for (const [key, en, ar] of SUMMARY) {
    const box = el("div", "summary__item");
    box.appendChild(el("dt", null, state.lang === "ar" ? ar : en));
    box.appendChild(el("dd", null, String(state.meta.counts[key] ?? "—")));
    grid.appendChild(box);
  }
  host.appendChild(grid);

  // the last upload's report: its own when it was rejected, else the loaded one
  const rep = state.upload || d.report;
  if (rep) {
    const n = rep.errors.length, w = rep.warnings.length;
    const head = el("div", "report__head");
    head.appendChild(el("span", "chip " + (n ? "chip--bad" : "chip--ok"),
      state.lang === "ar" ? `${n} خطأ` : `${n} error${n === 1 ? "" : "s"}`));
    head.appendChild(el("span", "chip " + (w ? "chip--warn" : ""),
      state.lang === "ar" ? `${w} تنبيه` : `${w} warning${w === 1 ? "" : "s"}`));
    if (rep.filename && rep.filename !== d.source) {
      const f = el("span", "source__name", rep.filename);
      f.dir = "auto";
      head.appendChild(f);
    }
    host.appendChild(head);
    if (n) {
      host.appendChild(el("div", "notice notice--bad", state.lang === "ar"
        ? "لم يُستبدل شيء: صحّحي الأخطاء وارفعي الملف مرة أخرى. البيانات المحمّلة حاليًا باقية."
        : "Nothing was replaced: fix the errors and upload again. The data loaded now stays."));
      host.appendChild(reportList(rep.errors, "bad"));
    }
    if (w) host.appendChild(reportList(rep.warnings, "warn"));
    if (rep.notes?.length) host.appendChild(reportList(rep.notes, "note"));
  }

  renderRules();
  const built = !!(state.comparison || d.built);
  $("#step-data").classList.toggle("step--done", !d.is_demo && !(state.upload?.errors.length));
  $("#step-build").classList.toggle("step--done", built);
  $("#export").disabled = !built;
  if (built && state.buildSeconds == null && d.build_seconds != null) {
    showBuildTime(d.build_seconds);
  }
}

/** Elapsed build time. A cached build returns at once, so show the time the
 *  solve really took when it ran, and say it came from the cache. */
function showBuildTime(elapsed) {
  const solved = state.comparison
    ? Math.max(...Object.values(state.comparison.profiles).map((p) => p.seconds || 0))
    : 0;
  const cached = solved > 2 * elapsed + 1;
  $("#build-time").textContent = seconds(cached ? solved : elapsed) +
    (cached ? (state.lang === "ar" ? " · محفوظ" : " · cached") : "");
}

function renderRules() {
  const host = $("#rules");
  const d = state.meta.data;
  host.replaceChildren();
  const built = !!(state.comparison || d.built);
  if (built) {
    host.appendChild(el("p", "step__note", t("s2_built")));
    return;
  }
  const rules = d.setup_rules || [];
  $("#step-rules").classList.toggle("step--done", rules.length > 0);
  if (!rules.length) {
    const p = el("p", "step__note", t("s2_empty"));
    p.dir = "auto";
    host.appendChild(p);
    return;
  }
  const ul = el("ul", "rules");
  for (const r of rules) {
    const li = el("li", "rule");
    const d2 = r.describe;
    const text = el("span", "rule__text", (state.lang === "ar" ? d2.title_ar : d2.title_en) + " — " +
      d2.rows.map((x) => (state.lang === "ar" && x.value_ar ? x.value_ar : x.value)).join(" · "));
    text.dir = "auto";
    li.appendChild(text);
    const rm = el("button", "btn btn--sm btn--ghost", state.lang === "ar" ? "حذف" : "Remove");
    rm.type = "button";
    rm.addEventListener("click", async () => {
      const out = await api(`/api/setup/rules/${r.index}`, { method: "DELETE" });
      if (out.ok) { state.meta.data.setup_rules = out.rules; renderData(); }
    });
    li.appendChild(rm);
    ul.appendChild(li);
  }
  host.appendChild(ul);
}

async function uploadFile(file) {
  if (!file || state.busy) return;
  state.busy = true;
  const drop = $("#drop");
  drop.classList.add("drop--busy");
  try {
    const r = await fetch("/api/data/upload", {
      method: "POST",
      headers: { "content-type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                 "x-filename": encodeURIComponent(file.name) },
      body: file,
    });
    const out = await r.json();
    out.report.filename = file.name;
    if (out.ok) {
      await resetClient();
      state.upload = null;
    } else {
      state.upload = out.report;
    }
    renderData();
  } catch (e) {
    $("#data-status").prepend(el("div", "notice notice--bad", e.message));
  } finally {
    state.busy = false;
    drop.classList.remove("drop--busy");
    $("#file").value = "";
  }
}

/** A new campus: forget every schedule, card and view that belonged to the old one. */
async function resetClient() {
  Object.assign(state, {
    comparison: null, pending: null, lastApplied: null, movedMeetings: new Set(),
    trace: [], moves: [], overlay: null, source: "baseline", buildSeconds: null, upload: null,
  });
  $("#ent-source").value = "baseline";
  $("#chat-log").replaceChildren();
  $("#build-time").textContent = "—";
  $("#build-progress").replaceChildren();
  state.meta = await api("/api/meta");
  state.entities = await api("/api/entities");
  pickOpening();
  setStatus();
  applyLang();
  await loadGrid();
  await loadChanges();
}

/** Open on the first persona on the demo campus; on uploaded data, which has
 *  none, open on the first cohort. */
function pickOpening() {
  const opening = (state.entities.personas || [])[0];
  if (opening) {
    state.entType = opening.entity_type;
    state.entId = opening.id;
  } else {
    state.entType = "cohort";
    state.entId = state.entities.cohorts[0]?.id ?? null;
  }
  $("#ent-type").value = state.entType;
}

$("#choose").addEventListener("click", () => $("#file").click());
$("#file").addEventListener("change", (e) => uploadFile(e.target.files[0]));
const dropZone = $("#drop");
["dragenter", "dragover"].forEach((ev) => dropZone.addEventListener(ev, (e) => {
  e.preventDefault();
  dropZone.classList.add("drop--over");
}));
["dragleave", "drop"].forEach((ev) => dropZone.addEventListener(ev, (e) => {
  e.preventDefault();
  dropZone.classList.remove("drop--over");
}));
dropZone.addEventListener("drop", (e) => uploadFile(e.dataTransfer.files[0]));
$("#use-demo").addEventListener("click", async () => {
  if (state.busy) return;
  await api("/api/data/reset", { method: "POST" });
  await resetClient();
});
$("#go-agent").addEventListener("click", () => { showTab("agent"); $("#chat-input").focus(); });
$("#export").addEventListener("click", () => { window.location.href = "/api/data/export"; });

/* ---------- boot ---------- */
(async function boot() {
  state.meta = await api("/api/meta");
  state.entities = await api("/api/entities");
  // the timetable opens on Noura, who the baseline fails
  pickOpening();
  applyLang();
  renderPersonas();
  renderEntitySelect();
  await loadGrid();
  await loadChanges();
})();
