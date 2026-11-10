// 문제 추출기 웹 화면. 프레임워크 없이 같은 서버의 API를 부른다.
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const TYPE_LABEL = {
  multiple_choice: "객관식", short_answer: "단답형", essay: "서술형", true_false: "OX", other: "기타",
};
const CONF_LABEL = { high: "확실", medium: "애매", low: "검수 필요" };
const PAGE_SIZE = 30;

// API 서버 주소. 서버가 이 화면을 직접 띄울 때는 같은 주소(""),
// 한 파일짜리 index.html(Vercel 등)로 열 때는 저장해 둔 주소나 http://localhost:8000.
const DEFAULT_API = "http://localhost:8000";
function loadApiBase() {
  if (!window.PX_STANDALONE) return "";
  try { return localStorage.getItem("px-api-base") || DEFAULT_API; } catch { return DEFAULT_API; }
}
let API_BASE = loadApiBase();
const url = (path) => (path && path.startsWith("/") ? API_BASE + path : path);

// ---------------------------------------------------------------- 공통 도구

function h(tag, attrs = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else el.setAttribute(k, v === true ? "" : v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

async function api(path, opts = {}) {
  let res;
  try {
    res = await fetch(url(path), opts);
  } catch {
    const err = new Error(`서버(${API_BASE || location.origin})에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.`);
    err.status = 0;
    throw err;
  }
  if (!res.ok) {
    let detail = `${res.status} 오류`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") detail = body.detail;
      else if (Array.isArray(body.detail)) detail = body.detail.map((d) => d.msg).join(", ");
    } catch { /* 본문 없음 */ }
    const err = new Error(detail);
    err.status = res.status;
    throw err;
  }
  return res.status === 204 ? null : res.json();
}

/** 텍스트를 넣고 $...$ / $$...$$ 를 KaTeX로 그린다. KaTeX를 못 불러오면 원문 그대로. */
function math(el, text) {
  el.textContent = text ?? "";
  if (window.renderMathInElement) {
    // 블록 수식($$...$$)은 이미 줄을 차지하니, 바로 뒤 줄바꿈은 빼서 빈 줄이 생기지 않게
    el.textContent = el.textContent.replace(/\$\$[ \t]*\n/g, () => "$$");
    renderMathInElement(el, {
      delimiters: [
        { left: "$$", right: "$$", display: true },
        { left: "$", right: "$", display: false },
        { left: "\\(", right: "\\)", display: false },
        { left: "\\[", right: "\\]", display: true },
      ],
      throwOnError: false,
    });
  }
  return el;
}

let toastTimer;
function toast(msg, ms = 2500) {
  const el = $("#toast");
  el.textContent = msg;
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.hidden = true), ms);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/** 카드와 미리보기에 같이 쓰는 문제 본문 */
function problemBody(p) {
  const box = h("div", { class: "problem-body" });
  if (p.shared_context) box.append(math(h("div", { class: "context" }), p.shared_context));
  box.append(math(h("div"), p.stem));
  if (p.choices?.length) {
    box.append(h("ol", { class: "choices" },
      p.choices.map((c) => math(h("li"), `${c.label} ${c.text}`))));
  }
  if (p.answer) box.append(math(h("div", { class: "answer" }), `정답: ${p.answer}`));
  if (p.notes) box.append(h("div", { class: "note" }, `⚠ ${p.notes}`));
  return box;
}

// ---------------------------------------------------------------- 탭

const views = ["upload", "problems", "pages"];

function showView() {
  const name = location.hash.slice(1).split("?")[0] || "problems";
  const tab = views.includes(name) ? name : "problems";
  for (const v of views) $(`#view-${v}`).hidden = v !== tab;
  document.querySelectorAll(".tabs a").forEach((a) => a.classList.toggle("active", a.dataset.tab === tab));
  if (tab === "problems") loadProblems();
  if (tab === "pages") loadPages();
}
window.addEventListener("hashchange", showView);

function changeServer() {
  const next = prompt("API 서버 주소 (내 컴퓨터에서 켰다면 그대로 두세요)", API_BASE || DEFAULT_API);
  if (next == null) return;
  API_BASE = next.trim().replace(/\/+$/, "") || DEFAULT_API;
  try { localStorage.setItem("px-api-base", API_BASE); } catch { /* 저장 못 해도 이번 창에서는 씀 */ }
  refreshHeader();
  showView();
}

async function refreshHeader() {
  const health$ = $("#health");
  if (window.PX_STANDALONE) {
    health$.classList.add("clickable");
    health$.title = "눌러서 API 서버 주소 바꾸기";
  }
  try {
    const health = await api("/health");
    health$.textContent = `${health.provider} · ${health.model ?? "기본 모델"}${window.PX_STANDALONE ? ` · ${API_BASE}` : ""}`;
    const pending = await api("/problems?reviewed=false&limit=1");
    const badge = $("#badge-unreviewed");
    badge.hidden = pending.total === 0;
    badge.textContent = pending.total;
    badge.title = `검수 전 ${pending.total}문제`;
  } catch {
    health$.textContent = window.PX_STANDALONE
      ? `서버(${API_BASE})에 연결할 수 없어요 · 주소 바꾸기`
      : "서버에 연결할 수 없어요";
  }
}

// ---------------------------------------------------------------- 올리기

const queue = [];
let running = false;

function addFiles(files) {
  for (const file of files) {
    if (!/^image\/(jpeg|png|webp)$/.test(file.type)) {
      toast(`${file.name}: JPEG / PNG / WEBP만 올릴 수 있어요`);
      continue;
    }
    const item = { file, status: "wait", msg: "대기 중", url: URL.createObjectURL(file) };
    item.el = h("li");
    queue.push(item);
    $("#queue").append(item.el);
    renderItem(item);
  }
  runQueue();
}

function renderItem(item) {
  const cls = { ok: "status-ok", err: "status-err", wait: "status-wait", busy: "status-wait" }[item.status];
  const actions = [];
  if (item.result) {
    actions.push(h("button", {
      type: "button", class: "ghost small",
      onclick: () => openSource(item.result.source),
    }, "검수하기"));
  }
  if (item.status === "err") {
    actions.push(h("button", {
      type: "button", class: "ghost small",
      onclick: () => { item.status = "wait"; item.msg = "대기 중"; renderItem(item); runQueue(); },
    }, "다시 시도"));
  }
  item.el.replaceChildren(
    h("img", { src: item.url, alt: "" }),
    h("div", { class: "info" },
      h("div", { class: "name" }, item.file.name),
      h("div", { class: `small ${cls}` }, item.msg)),
    ...actions,
  );
}

async function runQueue() {
  if (running) return;
  running = true;
  try {
    let item;
    // 무료 한도를 아끼려고 한 장씩 차례로 보낸다.
    while ((item = queue.find((i) => i.status === "wait"))) {
      await uploadOne(item);
    }
  } finally {
    running = false;
    refreshHeader();
  }
}

async function uploadOne(item) {
  const force = $("#force").checked;
  for (let attempt = 0; attempt < 4; attempt++) {
    item.status = "busy";
    item.msg = "추출 중… (한 장에 10~60초쯤 걸려요)";
    renderItem(item);
    const form = new FormData();
    form.append("file", item.file, item.file.name);
    try {
      const res = await api(`/extract?force=${force}`, { method: "POST", body: form });
      item.result = res;
      item.status = "ok";
      const n = res.problems.length;
      item.msg = res.duplicate
        ? `이미 처리한 사진이에요 · ${n}문제 (다시 하려면 위의 '다시 추출'을 켜세요)`
        : `${n}문제 추출 · ${res.problems.filter((p) => p.confidence !== "high").length}문제는 꼭 확인해 주세요`;
      renderItem(item);
      return;
    } catch (err) {
      if (err.status === 429 && attempt < 3) {
        // 무료 등급 분당 한도: 잠깐 기다렸다 자동 재시도
        for (let s = 60; s > 0; s--) {
          item.msg = `요청 한도에 걸렸어요. ${s}초 뒤 다시 시도해요 (${attempt + 1}/3)`;
          renderItem(item);
          await sleep(1000);
        }
        continue;
      }
      item.status = "err";
      item.msg = err.message;
      renderItem(item);
      return;
    }
  }
}

function setupUpload() {
  const zone = $("#dropzone");
  const input = $("#file-input");
  input.addEventListener("change", () => { addFiles([...input.files]); input.value = ""; });
  zone.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") input.click(); });
  zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("over"); });
  zone.addEventListener("dragleave", () => zone.classList.remove("over"));
  zone.addEventListener("drop", (e) => {
    e.preventDefault();
    zone.classList.remove("over");
    addFiles([...e.dataTransfer.files]);
  });
  document.addEventListener("paste", (e) => {
    if ($("#editor").open) return;
    const files = [...e.clipboardData.files].filter((f) => f.type.startsWith("image/"));
    if (!files.length) return;
    const named = files.map((f, i) => new File([f], `붙여넣기-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}-${i + 1}.png`, { type: f.type }));
    location.hash = "upload";
    addFiles(named);
  });
  $("#clear-done").addEventListener("click", () => {
    for (let i = queue.length - 1; i >= 0; i--) {
      if (queue[i].status === "ok") {
        queue[i].el.remove();
        URL.revokeObjectURL(queue[i].url);
        queue.splice(i, 1);
      }
    }
  });
}

// ---------------------------------------------------------------- 문제 목록

const listState = { offset: 0, source: null, items: [], total: 0 };

function filterParams() {
  const params = new URLSearchParams();
  for (const [k, v] of new FormData($("#filters"))) if (v.trim()) params.set(k, v.trim());
  if (listState.source) params.set("source_id", listState.source.id);
  return params;
}

async function loadProblems() {
  const params = filterParams();
  params.set("limit", PAGE_SIZE);
  params.set("offset", listState.offset);
  const list = $("#problem-list");
  let data;
  try {
    data = await api(`/problems?${params}`);
  } catch (err) {
    list.replaceChildren(h("div", { class: "empty" }, err.message));
    return;
  }
  listState.items = data.items;
  listState.total = data.total;

  const chip = $("#source-chip");
  chip.hidden = !listState.source;
  if (listState.source) {
    chip.replaceChildren(
      `페이지: ${listState.source.page_title || listState.source.filename || "#" + listState.source.id}`,
      h("button", { type: "button", title: "페이지 필터 해제", onclick: () => { listState.source = null; listState.offset = 0; loadProblems(); } }, "✕"),
    );
  }
  $("#problem-count").textContent = `${data.total}문제`;
  const pages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const page = Math.floor(listState.offset / PAGE_SIZE) + 1;
  $("#page-info").textContent = `${page} / ${pages}`;
  $("#prev-page").disabled = listState.offset === 0;
  $("#next-page").disabled = listState.offset + PAGE_SIZE >= data.total;

  if (!data.items.length) {
    list.replaceChildren(h("div", { class: "empty" },
      data.total === 0 && !filterParams().toString() ?"아직 문제가 없어요. '올리기'에서 사진을 올려 보세요." : "조건에 맞는 문제가 없어요."));
    return;
  }
  list.replaceChildren(...data.items.map((p, i) => problemCard(p, i)));
}

function problemCard(p, index) {
  const card = h("article", {
    class: "card", tabindex: "0",
    onclick: () => openEditor(index),
    onkeydown: (e) => { if (e.key === "Enter") openEditor(index); },
  },
    h("div", { class: "card-head" },
      h("span", { class: "num" }, p.number ? `${p.number}번` : "번호 없음"),
      h("span", { class: "muted" }, TYPE_LABEL[p.problem_type]),
      p.topic && h("span", { class: "muted" }, `· ${p.topic}`),
      p.tags.map((t) => h("span", { class: "tag" }, t)),
      h("span", { class: "spacer" }),
      p.confidence !== "high" && h("span", { class: `pill ${p.confidence}` }, CONF_LABEL[p.confidence]),
      p.reviewed ? h("span", { class: "pill ok" }, "검수 완료") : h("span", { class: "muted" }, "검수 전"),
    ),
    problemBody(p),
    p.figures.length > 0 && h("div", { class: "thumbs" },
      p.figures.map((f) => h("img", { src: url(f.url), alt: f.description, title: f.description, loading: "lazy" }))),
  );
  return card;
}

function openSource(source) {
  listState.source = source;
  listState.offset = 0;
  $("#filters").reset();
  if (location.hash === "#problems") loadProblems();
  else location.hash = "problems";
}

async function exportJson() {
  const params = filterParams();
  const all = [];
  for (let offset = 0; ; offset += 200) {
    params.set("limit", 200);
    params.set("offset", offset);
    const data = await api(`/problems?${params}`);
    all.push(...data.items);
    if (all.length >= data.total || !data.items.length) break;
  }
  const blob = new Blob([JSON.stringify(all, null, 2)], { type: "application/json" });
  const a = h("a", { href: URL.createObjectURL(blob), download: `problems-${new Date().toISOString().slice(0, 10)}.json` });
  a.click();
  URL.revokeObjectURL(a.href);
  toast(`${all.length}문제를 내보냈어요`);
}

function setupProblems() {
  $("#filters").addEventListener("submit", (e) => { e.preventDefault(); listState.offset = 0; loadProblems(); });
  $("#reset-filters").addEventListener("click", () => {
    $("#filters").reset();
    listState.source = null;
    listState.offset = 0;
    loadProblems();
  });
  $("#filters").addEventListener("change", (e) => {
    if (e.target.tagName === "SELECT") { listState.offset = 0; loadProblems(); }
  });
  $("#prev-page").addEventListener("click", () => { listState.offset = Math.max(0, listState.offset - PAGE_SIZE); loadProblems(); });
  $("#next-page").addEventListener("click", () => { listState.offset += PAGE_SIZE; loadProblems(); });
  $("#export").addEventListener("click", () => exportJson().catch((err) => toast(err.message)));
}

// ---------------------------------------------------------------- 검수 편집기

const editor = { index: -1, problem: null, dirty: false };

function choiceRow(c = { label: "", text: "" }) {
  const row = h("div", { class: "choice-row" },
    h("input", { "data-k": "label", value: c.label, placeholder: "①", "aria-label": "보기 기호" }),
    h("input", { "data-k": "text", value: c.text, placeholder: "보기 내용", "aria-label": "보기 내용" }),
    h("button", { type: "button", class: "ghost small", title: "보기 삭제", onclick: () => { row.remove(); onEdit(); } }, "✕"),
  );
  return row;
}

function readForm() {
  const f = $("#edit-form").elements;
  const orNull = (v) => (v.trim() === "" ? null : v.trim());
  const points = f.points.value.trim();
  return {
    number: orNull(f.number.value),
    problem_type: f.problem_type.value,
    topic: orNull(f.topic.value),
    tags: f.tags.value.split(",").map((t) => t.trim()).filter(Boolean),
    points: points === "" ? null : Number(points),
    shared_context: orNull(f.shared_context.value),
    stem: f.stem.value.trim(),
    choices: [...document.querySelectorAll("#choice-rows .choice-row")]
      .map((r) => ({ label: $("[data-k=label]", r).value.trim(), text: $("[data-k=text]", r).value.trim() }))
      .filter((c) => c.label || c.text),
    answer: orNull(f.answer.value),
    solution: orNull(f.solution.value),
    notes: orNull(f.notes.value),
  };
}

let previewTimer;
function onEdit() {
  editor.dirty = true;
  $("#edit-status").textContent = "저장 안 됨";
  clearTimeout(previewTimer);
  previewTimer = setTimeout(() => {
    const v = readForm();
    const box = problemBody({ ...v, notes: null });
    if (v.solution) box.append(math(h("div", { class: "muted" }), `해설: ${v.solution}`));
    $("#preview").replaceChildren(box);
  }, 150);
}

function openEditor(index) {
  const p = listState.items[index];
  if (!p) return;
  editor.index = index;
  editor.problem = p;
  const f = $("#edit-form").elements;
  f.number.value = p.number ?? "";
  f.problem_type.value = p.problem_type;
  f.topic.value = p.topic ?? "";
  f.tags.value = p.tags.join(", ");
  f.points.value = p.points ?? "";
  f.shared_context.value = p.shared_context ?? "";
  f.stem.value = p.stem;
  f.answer.value = p.answer ?? "";
  f.solution.value = p.solution ?? "";
  f.notes.value = p.notes ?? "";
  $("#choice-rows").replaceChildren(...p.choices.map(choiceRow));

  $("#edit-title").textContent = p.number ? `${p.number}번` : "번호 없는 문제";
  $("#edit-meta").textContent =
    `${listState.offset + index + 1} / ${listState.total} · 자신감 ${CONF_LABEL[p.confidence]}${p.reviewed ? " · 검수 완료" : ""}`;
  $("#edit-image").src = `${url(p.image_url)}?v=${encodeURIComponent(p.updated_at)}`;
  $("#open-page").href = url(`/sources/${p.source_id}/image`);
  $("#edit-figures").replaceChildren(...p.figures.map((fig) =>
    h("figure", {}, h("img", { src: url(fig.url), alt: fig.description }), h("figcaption", {}, fig.description))));

  onEdit();
  editor.dirty = false;
  $("#edit-status").textContent = "";
  const dlg = $("#editor");
  if (!dlg.open) dlg.showModal();
  f.stem.focus();
}

async function save(markReviewed) {
  const body = readForm();
  if (!body.stem) { toast("발문은 비울 수 없어요"); return false; }
  if (body.points != null && Number.isNaN(body.points)) { toast("배점은 숫자로 적어 주세요"); return false; }
  if (markReviewed) body.reviewed = true;
  $("#edit-status").textContent = "저장 중…";
  try {
    const updated = await api(`/problems/${editor.problem.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    listState.items[editor.index] = updated;
    editor.problem = updated;
    editor.dirty = false;
    $("#edit-status").textContent = "저장했어요";
    const card = $("#problem-list").children[editor.index];
    if (card) card.replaceWith(problemCard(updated, editor.index));
    return true;
  } catch (err) {
    $("#edit-status").textContent = "";
    toast(`저장 실패: ${err.message}`);
    return false;
  }
}

function closeEditor() {
  if (editor.dirty && !confirm("저장하지 않은 수정이 있어요. 닫을까요?")) return;
  $("#editor").close();
}

async function saveAndNext() {
  if (!(await save(true))) return;
  refreshHeader();
  if (editor.index + 1 < listState.items.length) {
    openEditor(editor.index + 1);
  } else if (listState.offset + PAGE_SIZE < listState.total) {
    listState.offset += PAGE_SIZE;
    await loadProblems();
    openEditor(0);
  } else {
    $("#editor").close();
    toast("마지막 문제까지 검수했어요");
  }
}

function setupEditor() {
  const dlg = $("#editor");
  const form = $("#edit-form");
  form.addEventListener("input", onEdit);
  form.addEventListener("submit", (e) => e.preventDefault());
  $("#add-choice").addEventListener("click", () => {
    const n = $("#choice-rows").children.length;
    const row = choiceRow({ label: "①②③④⑤⑥⑦⑧⑨⑩"[n] ?? "", text: "" });
    $("#choice-rows").append(row);
    $("[data-k=text]", row).focus();
  });
  dlg.querySelector("[data-close]").addEventListener("click", closeEditor);
  dlg.addEventListener("cancel", (e) => { e.preventDefault(); closeEditor(); });
  dlg.addEventListener("click", (e) => { if (e.target === dlg) closeEditor(); });
  $("#save").addEventListener("click", () => save(false));
  $("#save-next").addEventListener("click", saveAndNext);
  dlg.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); saveAndNext(); }
    if ((e.ctrlKey || e.metaKey) && e.key === "s") { e.preventDefault(); save(false); }
  });
  $("#delete-problem").addEventListener("click", async () => {
    if (!confirm("이 문제를 지울까요? 되돌릴 수 없어요.")) return;
    try {
      await api(`/problems/${editor.problem.id}`, { method: "DELETE" });
      editor.dirty = false;
      dlg.close();
      toast("문제를 지웠어요");
      loadProblems();
      refreshHeader();
    } catch (err) {
      toast(`삭제 실패: ${err.message}`);
    }
  });
}

// ---------------------------------------------------------------- 페이지 목록

async function loadPages() {
  const grid = $("#page-list");
  let data;
  try {
    data = await api("/sources?limit=200");
  } catch (err) {
    grid.replaceChildren(h("div", { class: "empty" }, err.message));
    return;
  }
  if (!data.items.length) {
    grid.replaceChildren(h("div", { class: "empty" }, "아직 처리한 페이지가 없어요."));
    return;
  }
  grid.replaceChildren(...data.items.map((s) => h("div", { class: "page-card" },
    h("img", { src: url(s.image_url), alt: s.filename ?? "", loading: "lazy" }),
    h("div", { class: "body" },
      h("div", { class: "title" }, s.page_title || "제목 없음"),
      h("div", { class: "muted small" }, s.filename ?? ""),
      h("div", { class: "muted small" }, `${s.problem_count}문제 · ${s.created_at.slice(0, 16).replace("T", " ")}`),
      h("div", { class: "muted small" }, s.model ?? ""),
      h("div", { class: "actions" },
        h("button", { type: "button", class: "small", onclick: () => openSource(s) }, "문제 보기"),
        h("a", { href: url(s.image_url), target: "_blank", rel: "noopener", class: "small" }, "원본"),
        h("span", { class: "spacer" }),
        h("button", {
          type: "button", class: "ghost small danger",
          onclick: async () => {
            if (!confirm(`이 페이지와 문제 ${s.problem_count}개를 모두 지울까요? 되돌릴 수 없어요.`)) return;
            try {
              await api(`/sources/${s.id}`, { method: "DELETE" });
              toast("페이지를 지웠어요");
              loadPages();
              refreshHeader();
            } catch (err) { toast(`삭제 실패: ${err.message}`); }
          },
        }, "삭제"),
      ),
    ),
  )));
}

// ---------------------------------------------------------------- 시작

function start() {
  if (window.PX_STANDALONE) $("#health").addEventListener("click", changeServer);
  setupUpload();
  setupProblems();
  setupEditor();
  refreshHeader();
  showView();
}
if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
else start();
