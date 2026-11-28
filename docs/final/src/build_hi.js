// 기말발표 고점 버전: 기존 형식과 무관한 다크 테마. 모든 수치는 experiments/main30 원자료와 docs/figures/gantt_replan.json에서 읽는다.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const OUT = process.argv[2] || "hi.pptx";
const REPO = "/home/claude/project4_manufacturing_logic";
const IMG = (f) => path.join(__dirname, f);
const FONT = "Noto Sans CJK KR";
const MONO = "Consolas";

// ---------------------------------------------------------------- data
const csv = (p) => {
  const lines = fs.readFileSync(path.join(REPO, p), "utf8").trim().split(/\r?\n/);
  const h = lines[0].split(",");
  return lines.slice(1).map((l) => { const v = l.split(","); return Object.fromEntries(h.map((k, i) => [k, v[i]])); });
};
const SUM = {};
for (const r of csv("experiments/main30/summary.csv")) SUM[`${r.condition}|${r.policy}`] = r;
const m = (c, p, f = "gate_delay_minutes") => +SUM[`${c}|${p}`][`${f}_mean`];
const RUNS = csv("experiments/main30/runs.csv").map((r) => ({
  cond: r.condition, cfg: r.policy + (r.overtime === "True" ? "+OT" : ""), seed: +r.seed,
  delay: +r.gate_delay_minutes, ot: +r.overtime_minutes,
}));
const GANTT = JSON.parse(fs.readFileSync(path.join(REPO, "docs/figures/gantt_replan.json"), "utf8"));
const CONDS = ["NORMAL", "SLOW", "STOPPAGE_REWORK"];
const CL = { NORMAL: "정상", SLOW: "작업시간 +20%", STOPPAGE_REWORK: "작업정지·재작업" };
const CFGS = ["KEEP", "FCFS", "FCFS+OT", "EDD", "EDD+OT", "SLACK", "SLACK+OT", "CR", "CR+OT"];
const lateCount = (c, k) => RUNS.filter((r) => r.cond === c && r.cfg === k && r.delay > 0).length;
const check = (ok, msg) => { if (!ok) throw new Error("data check: " + msg); };
check(RUNS.length === 810, "810 runs");
check(lateCount("STOPPAGE_REWORK", "EDD") === 5 && lateCount("NORMAL", "EDD") === 0 && lateCount("SLOW", "EDD") === 0, "EDD late");
check(Math.round(m("NORMAL", "EDD+OT", "overtime_minutes")) === 108, "108");
const fmt = (x, d = 0) => (Math.abs(x) < 0.05 ? "0" : x.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }));

// ---------------------------------------------------------------- style
const C = {
  bg: "0A0F1A", panel: "121A2A", panel2: "182337", line: "26344D", text: "E8EEF6", muted: "8798AE", dim: "5A6B82",
  late: "FF7A3D", ok: "2ED3A4", blue: "5AA9FF", ot: "FFC54D", white: "FFFFFF", red: "FF5A5A",
};
const W = 13.333, H = 7.5, M = 0.6;
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "박상현";
pres.title = "실적이 다음 작업지시를 바꾸는 시스템 — 공프4 기말발표";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

let page = 0;
const T = (s, text, o) => s.addText(text, { fontFace: FONT, isTextBox: true, margin: 0, valign: "top", color: C.text, ...o });
const rect = (s, x, y, w, h, fill, o = {}) => s.addShape(o.round ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE, {
  x, y, w, h, fill: { color: fill, transparency: o.tr || 0 }, line: { color: o.line || fill, width: o.lw || 0.75, transparency: o.ltr || 0 },
  rectRadius: o.round ? (o.r || 0.08) : undefined,
});
const line = (s, x, y, w, h, color, o = {}) => s.addShape(pres.shapes.LINE, {
  x, y, w, h, line: { color, width: o.w || 1.25, dashType: o.dash, endArrowType: o.end, beginArrowType: o.begin }, flipV: o.flipV, flipH: o.flipH,
});
const dot = (s, x, y, d, color) => s.addShape(pres.shapes.OVAL, { x: x - d / 2, y: y - d / 2, w: d, h: d, fill: { color }, line: { color } });

function slide(kicker, notes) {
  page += 1;
  const s = pres.addSlide();
  s.background = { color: C.bg };
  if (kicker) {
    T(s, String(page).padStart(2, "0"), { x: M, y: 0.36, w: 0.5, h: 0.25, fontSize: 10, bold: true, color: C.late, fontFace: MONO });
    T(s, kicker, { x: M + 0.48, y: 0.36, w: 8, h: 0.25, fontSize: 10, bold: true, color: C.muted, charSpacing: 1 });
  }
  T(s, "공프4 기말발표 · 박상현", { x: W - M - 3, y: H - 0.4, w: 3, h: 0.22, fontSize: 8.5, color: C.dim, align: "right" });
  if (notes) s.addNotes(notes);
  return s;
}
const title = (s, t, sub) => {
  T(s, t, { x: M, y: 0.68, w: W - 2 * M, h: 0.75, fontSize: 30, bold: true, color: C.white, valign: "middle" });
  if (sub) T(s, sub, { x: M, y: 1.42, w: W - 2 * M, h: 0.35, fontSize: 13.5, color: C.muted });
};
const chip = (s, x, y, w, text, color, o = {}) => {
  rect(s, x, y, w, o.h || 0.3, color, { round: true, r: 0.15, tr: o.solid ? 0 : 82, line: color, ltr: 30 });
  T(s, text, { x, y, w, h: o.h || 0.3, fontSize: o.size || 10, bold: true, color: o.solid ? C.bg : color, align: "center", valign: "middle" });
};

// ---------------------------------------------------------------- 1 cover
{
  const s = slide(null, "안녕하십니까. 메카트로닉스공학과 박상현입니다. 현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템의 기말발표를 시작하겠습니다.");
  // motif: orbit of loop nodes on the right
  const cx = 9.85, cy = 3.65, r = 2.35;
  s.addShape(pres.shapes.OVAL, { x: cx - r, y: cy - r, w: 2 * r, h: 2 * r, fill: { color: C.bg }, line: { color: C.line, width: 1.25, dashType: "dash" } });
  s.addShape(pres.shapes.OVAL, { x: cx - r * 0.62, y: cy - r * 0.62, w: 2 * r * 0.62, h: 2 * r * 0.62, fill: { color: C.panel }, line: { color: C.line, width: 0.75 } });
  T(s, "810", { x: cx - 1.5, y: cy - 0.62, w: 3, h: 0.9, fontSize: 54, bold: true, color: C.white, align: "center", valign: "middle", fontFace: MONO });
  T(s, "번의 폐루프 실행", { x: cx - 1.5, y: cy + 0.3, w: 3, h: 0.35, fontSize: 13, color: C.muted, align: "center" });
  const nodes = ["실적", "Forecast", "위험 판정", "재계획 후보", "승인", "작업지시"];
  nodes.forEach((n, i) => {
    const a = -Math.PI / 2 + (i * 2 * Math.PI) / nodes.length;
    const x = cx + r * Math.cos(a), y = cy + r * Math.sin(a);
    const hl = i === 5;
    rect(s, x - 0.72, y - 0.2, 1.44, 0.4, hl ? C.late : C.panel2, { round: true, r: 0.2, line: hl ? C.late : C.line });
    T(s, n, { x: x - 0.72, y: y - 0.2, w: 1.44, h: 0.4, fontSize: 11.5, bold: true, color: hl ? C.bg : C.text, align: "center", valign: "middle" });
  });
  chip(s, M, 1.2, 2.6, "공학프로젝트4 · 기말발표", C.late);
  T(s, "실적이 다음 작업지시를\n바꾸는 시스템", { x: M, y: 1.85, w: 6.6, h: 1.9, fontSize: 40, bold: true, color: C.white, lineSpacingMultiple: 1.05 });
  T(s, "현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템", { x: M, y: 3.85, w: 6.6, h: 0.4, fontSize: 15, color: C.muted });
  line(s, M, 4.55, 0.6, 0, C.late, { w: 2.5 });
  T(s, "FastAPI · SQLite · Streamlit · 가상 현장 시뮬레이터\nPico 2 WH 단말은 미연동", { x: M, y: 4.75, w: 6.4, h: 0.7, fontSize: 11.5, color: C.dim, lineSpacingMultiple: 1.3 });
  T(s, "12233707  박상현", { x: M, y: 6.3, w: 4, h: 0.35, fontSize: 15, bold: true, color: C.text });
  T(s, "메카트로닉스공학과", { x: M, y: 6.65, w: 4, h: 0.3, fontSize: 11.5, color: C.muted });
}

// ---------------------------------------------------------------- 2 midterm number
{
  const s = slide("중간발표가 남긴 숫자", "중간발표 시연에서 LOT-001은 출하검사 시작보다 4시간 57분 늦었습니다. 그리고 이 지연은 FCFS, EDD, Slack, CR 어떤 순서 규칙으로도 줄지 않았습니다. 남은 네 가지 질문 중 폐루프, 반복 검증, 추가근무 세 가지는 이번에 구현하고 실행으로 확인했고, Pico는 연동하지 못했습니다.");
  T(s, "4h 57m", { x: M - 0.05, y: 1.15, w: 7, h: 1.9, fontSize: 110, bold: true, color: C.late, fontFace: MONO });
  T(s, "LOT-001이 출하검사 시작보다 늦는 시간", { x: M, y: 3.1, w: 6.5, h: 0.45, fontSize: 19, bold: true, color: C.white });
  T(s, "FCFS · EDD · Slack · CR, 어떤 순서 규칙으로도 줄지 않았다.\n순서만으로는 안 되는 지연을 어떻게 다룰 것인가?", { x: M, y: 3.65, w: 6.5, h: 0.9, fontSize: 14, color: C.muted, lineSpacingMultiple: 1.3 });
  const qs = [
    ["승인한 계획이 현장 순서를 실제로 바꾸나?", "작업지시 API + 가상 현장 폐루프", C.ok, "확인"],
    ["시나리오 하나를 넘어서도 효과가 있나?", "3조건 × 9구성 × 30회 = 810회", C.ok, "확인"],
    ["순서로 안 되면 추가근무는?", "평일 17~19시 후보 계산·승인·실행", C.ok, "구현"],
    ["Pico 단말로 입력할 수 있나?", "같은 HTTP API를 가상 단말로 검증", C.late, "미연동"],
  ];
  const x0 = 7.55, w0 = W - M - x0;
  qs.forEach((q, i) => {
    const y = 1.2 + i * 1.3;
    rect(s, x0, y, w0, 1.12, C.panel, { round: true, line: C.line });
    rect(s, x0, y + 0.18, 0.06, 0.76, q[2]);
    T(s, q[0], { x: x0 + 0.3, y: y + 0.16, w: w0 - 1.5, h: 0.4, fontSize: 14, bold: true, color: C.white });
    T(s, q[1], { x: x0 + 0.3, y: y + 0.6, w: w0 - 1.5, h: 0.35, fontSize: 12, color: C.muted });
    chip(s, x0 + w0 - 1.15, y + 0.41, 0.9, q[3], q[2]);
  });
  rect(s, M, 5.1, 6.5, 1.55, C.panel, { round: true, line: C.line });
  T(s, "이번 발표의 지표", { x: M + 0.3, y: 5.25, w: 6, h: 0.3, fontSize: 11, bold: true, color: C.late });
  T(s, "출하검사 진입 지연 = LOT별 max(0, 생산 완료 − 출하검사 예정 시작)의 합.\n고객 납기 지각과는 다른 지표다 (11번에서 따로 본다).", { x: M + 0.3, y: 5.6, w: 6, h: 0.9, fontSize: 12.5, color: C.text, lineSpacingMultiple: 1.3 });
}

// ---------------------------------------------------------------- 3 closed loop
{
  const s = slide("시스템 구성", "구성입니다. 현장에서 작업 시작, 완료, 합격과 불합격 같은 실적이 들어오면 FastAPI 서버가 검증해 저장하고, Forecast를 다시 계산해 출하검사 Gate에 늦을지 판정합니다. 긴급이면 재계획 후보를 만들고, 관리자가 승인하면 새 계획 버전이 생깁니다. 기말에서 추가한 것은 주황색으로 표시한 부분입니다. 승인된 계획이 작업지시 API로 현장에 다시 내려가고, 현장 역할은 시스템이 모르는 실제 작업시간으로 움직이는 가상 현장이 맡습니다.");
  title(s, "승인이 현장으로 돌아가는 폐루프", "실적이 들어와 계산되고, 승인된 계획이 다시 현장 작업지시로 내려간다. 주황 = 기말에서 추가");
  const nodes = [
    ["가상 현장", "숨은 실제 작업시간\n작업지시 순서대로 작업", true],
    ["실적 API", "FastAPI · 검증\n중복 이벤트 무시", false],
    ["Forecast", "LOT×공정 Pace\n유한용량 배치", false],
    ["위험 판정", "Gate 여유 ≤ 0\n→ 긴급", false],
    ["재계획 후보", "4규칙 × 추가근무\n사전식 순위", true],
    ["관리자 승인", "계획 버전 +1\n근무달력 저장", false],
    ["작업지시 API", "/work-orders\n다음 작업 순서", true],
  ];
  const cx = W / 2, cy = 4.45, rx = 4.6, ry = 2.05;
  const pos = nodes.map((_, i) => {
    const a = Math.PI + (i * 2 * Math.PI) / nodes.length;
    return [cx + rx * Math.cos(a), cy + ry * Math.sin(a)];
  });
  s.addShape(pres.shapes.OVAL, { x: cx - rx, y: cy - ry, w: 2 * rx, h: 2 * ry, fill: { color: C.bg }, line: { color: C.line, width: 2, dashType: "dash" } });
  // direction ticks
  for (let i = 0; i < nodes.length; i++) {
    const a = Math.PI + ((i + 0.5) * 2 * Math.PI) / nodes.length;
    const x = cx + rx * Math.cos(a), y = cy + ry * Math.sin(a);
    s.addShape(pres.shapes.ISOSCELES_TRIANGLE, {
      x: x - 0.11, y: y - 0.11, w: 0.22, h: 0.22, fill: { color: C.muted }, line: { color: C.muted },
      rotate: (((a + Math.PI / 2) * 180) / Math.PI + 90) % 360,
    });
  }
  T(s, "폐루프", { x: cx - 1.5, y: cy - 0.45, w: 3, h: 0.55, fontSize: 26, bold: true, color: C.white, align: "center" });
  T(s, "실적 → 계획 → 작업지시 → 실적", { x: cx - 2, y: cy + 0.12, w: 4, h: 0.3, fontSize: 12, color: C.muted, align: "center" });
  nodes.forEach((n, i) => {
    const [x, y] = pos[i];
    const w = 2.15, h = 1.0;
    rect(s, x - w / 2, y - h / 2, w, h, C.panel, { round: true, line: n[2] ? C.late : C.line, lw: n[2] ? 1.75 : 0.75 });
    T(s, n[0], { x: x - w / 2, y: y - h / 2 + 0.1, w, h: 0.34, fontSize: 14, bold: true, color: n[2] ? C.late : C.white, align: "center" });
    T(s, n[1], { x: x - w / 2, y: y - h / 2 + 0.46, w, h: 0.5, fontSize: 10.5, color: C.muted, align: "center", lineSpacingMultiple: 1.1 });
  });
}

// ---------------------------------------------------------------- 4 mock plant
{
  const s = slide("모의 생산환경", "모의 생산환경은 중간발표와 같습니다. 3개 LOT, 90대, 다섯 개 내부 공정이고, 작업자 2명, 튜닝장비와 시험장비가 각각 1대라 이 두 장비가 병목입니다. 아래 줄이 핵심입니다. 기준계획은 접수순이라 LOT-001, 002, 003 순서인데, 출하검사는 LOT-003이 10월 28일, LOT-002가 11월 6일입니다. 출하검사가 빠른 LOT-003이 병목 장비를 늦게 받는, 일부러 만든 충돌입니다.");
  title(s, "3 LOT × 30대, 병목은 장비 두 대", "표준시간은 로직 검증용 가정값. 외부 피드 본딩은 LOT 단위 외부 리드타임으로 처리");
  const procs = [["테이핑", "10분/대", 0], ["일반 조립", "10분/대", 0], ["튜닝", "25분/대 · 장비 1대", 1], ["마무리 조립", "10분/대", 0], ["최종 성능시험", "30분/대 · 장비 1대", 1], ["출하검사", "Gate", 2]];
  const pw = 1.83, pg = 0.2;
  procs.forEach((p, i) => {
    const x = M + i * (pw + pg), y = 2.0;
    const col = p[2] === 1 ? C.late : p[2] === 2 ? C.blue : C.line;
    rect(s, x, y, pw, 1.05, p[2] === 1 ? "2A1A12" : C.panel, { round: true, line: col, lw: p[2] ? 1.5 : 0.75 });
    T(s, p[0], { x, y: y + 0.17, w: pw, h: 0.35, fontSize: 14.5, bold: true, color: p[2] === 1 ? C.late : C.white, align: "center" });
    T(s, p[1], { x, y: y + 0.57, w: pw, h: 0.3, fontSize: 10.5, color: C.muted, align: "center" });
    if (i < procs.length - 1) T(s, "›", { x: x + pw - 0.02, y: y + 0.25, w: pg + 0.04, h: 0.5, fontSize: 22, color: C.dim, align: "center" });
  });
  const stats = [["2명", "작업자, 전 공정 공용"], ["09–17시", "월~금 근무"], ["K = 9", "튜닝 9대 후 마무리 착수"], ["90대", "LOT-001·002·003 각 30"]];
  stats.forEach((st, i) => {
    const x = M + i * 3.07;
    T(s, st[0], { x, y: 3.35, w: 2.9, h: 0.55, fontSize: 26, bold: true, color: C.white, fontFace: st[0].match(/[0-9]/) ? MONO : FONT });
    T(s, st[1], { x, y: 3.9, w: 2.9, h: 0.3, fontSize: 11, color: C.muted });
  });
  // conflict timeline
  rect(s, M, 4.55, W - 2 * M, 2.2, C.panel, { round: true, line: C.line });
  T(s, "의도적으로 만든 충돌", { x: M + 0.3, y: 4.72, w: 5, h: 0.3, fontSize: 12, bold: true, color: C.late });
  T(s, "기준계획(접수순)", { x: M + 0.3, y: 5.25, w: 2.2, h: 0.3, fontSize: 11.5, color: C.muted });
  T(s, "출하검사 순서", { x: M + 0.3, y: 6.0, w: 2.2, h: 0.3, fontSize: 11.5, color: C.muted });
  const order = [["LOT-001", C.text], ["LOT-002", C.late], ["LOT-003", C.ok]];
  order.forEach((o, i) => chip(s, M + 2.6 + i * 1.75, 5.2, 1.5, o[0], o[1], { h: 0.38, size: 12 }));
  const gates = [["LOT-001", "10/23", C.text], ["LOT-003", "10/28", C.ok], ["LOT-002", "11/06", C.late]];
  gates.forEach((o, i) => chip(s, M + 2.6 + i * 1.75, 5.95, 1.5, `${o[0]} · ${o[1]}`, o[2], { h: 0.38, size: 11 }));
  line(s, M + 2.6 + 1.75 + 0.75, 5.6, 1.75, 0.33, C.dim, { end: "triangle", w: 1 });
  line(s, M + 2.6 + 1.75 + 0.75, 5.6, 1.75, 0.33, C.dim, { end: "triangle", w: 1, flipH: true });
  T(s, "출하검사가 빠른 LOT-003이\n병목 장비를 LOT-002보다 늦게 받는다.\n재계획이 고칠 수 있는 상황을 일부러 만들었다.", { x: 8.3, y: 5.15, w: 4.3, h: 1.3, fontSize: 12.5, color: C.text, lineSpacingMultiple: 1.3 });
}

// ---------------------------------------------------------------- 5 decision engine
{
  const s = slide("재계획 후보와 추가근무", "긴급이 되면 FCFS, EDD, Slack, CR 네 규칙으로 남은 작업을 다시 배치합니다. 기말에서는 규칙마다 평일 17시부터 19시까지를 연 추가근무안을 함께 계산해서 후보가 8개가 됩니다. 쓰는 날은 17시부터 창 안 마지막 작업 종료까지를 추가 가동시간으로 셉니다. 순위는 지연 LOT 수, 총 지연시간, 추가 가동시간, 계획 변경량 순서로, 앞 기준이 같을 때만 다음 기준을 봅니다. 관리자가 승인해야 계획 버전이 올라가고, 추가근무는 근무달력에 저장되어 현장도 같은 시간을 씁니다.");
  title(s, "후보 8개, 순위 기준 4개, 결정은 사람이", "긴급일 때만 계산한다. 같은 기준으로 순위를 매기고, 관리자가 승인해야 현장에 내려간다");
  // candidates grid
  T(s, "① 후보", { x: M, y: 2.0, w: 3, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  const rules = [["FCFS", "접수순"], ["EDD", "Gate 빠른 LOT"], ["Slack", "여유 적은 LOT"], ["CR", "긴급도 비율"]];
  rules.forEach((r, i) => {
    const y = 2.4 + i * 1.02;
    rect(s, M, y, 1.95, 0.85, C.panel, { round: true, line: C.line });
    T(s, r[0], { x: M + 0.18, y: y + 0.1, w: 1.7, h: 0.35, fontSize: 15, bold: true, color: C.white });
    T(s, r[1], { x: M + 0.18, y: y + 0.47, w: 1.7, h: 0.28, fontSize: 10.5, color: C.muted });
    rect(s, M + 2.1, y, 1.95, 0.85, "2B2410", { round: true, line: C.ot });
    T(s, r[0] + " + 추가근무", { x: M + 2.25, y: y + 0.1, w: 1.75, h: 0.35, fontSize: 13, bold: true, color: C.ot });
    T(s, "평일 17~19시", { x: M + 2.25, y: y + 0.47, w: 1.7, h: 0.28, fontSize: 10.5, color: C.muted });
  });
  T(s, "기말 추가", { x: M + 2.1, y: 2.03, w: 1.95, h: 0.28, fontSize: 10.5, bold: true, color: C.ot, align: "center" });
  // funnel
  const fx = 5.25;
  T(s, "② 사전식 순위 (D029)", { x: fx, y: 2.0, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  const crit = ["지연 LOT 수", "총 지연시간", "추가 가동시간", "계획 변경량"];
  crit.forEach((c, i) => {
    const w = 3.9 - i * 0.45, x = fx + (3.9 - w) / 2, y = 2.4 + i * 0.86;
    rect(s, x, y, w, 0.7, i === 2 ? "2B2410" : C.panel2, { round: true, line: i === 2 ? C.ot : C.line });
    T(s, `${i + 1}  ${c}`, { x, y, w, h: 0.7, fontSize: 14, bold: true, color: i === 2 ? C.ot : C.white, align: "center", valign: "middle" });
  });
  T(s, "앞 기준이 같을 때만 다음 기준을 본다.\n→ 지연이 같으면 추가근무가 적은 안이 앞선다.", { x: fx, y: 5.95, w: 3.9, h: 0.7, fontSize: 11.5, color: C.muted, align: "center", lineSpacingMultiple: 1.25 });
  // approval
  const ax = 9.6, aw = W - M - ax;
  T(s, "③ 승인", { x: ax, y: 2.0, w: 3, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  rect(s, ax, 2.4, aw, 4.25, C.panel, { round: true, line: C.late, lw: 1.5 });
  const steps = [["자동 적용 없음", "관리자가 비교 후 선택"], ["계획 버전 +1", "v1 → v2, 이전 버전 보존"], ["근무달력 OVERTIME", "추가근무 시간 저장"], ["Forecast = 현장", "같은 달력·같은 순서 사용"]];
  steps.forEach((st, i) => {
    const y = 2.6 + i * 0.98;
    dot(s, ax + 0.35, y + 0.2, 0.16, C.late);
    if (i < steps.length - 1) line(s, ax + 0.35, y + 0.3, 0, 0.8, C.line, { w: 1.5 });
    T(s, st[0], { x: ax + 0.65, y: y + 0.03, w: aw - 0.8, h: 0.35, fontSize: 13.5, bold: true, color: C.white });
    T(s, st[1], { x: ax + 0.65, y: y + 0.4, w: aw - 0.8, h: 0.3, fontSize: 11, color: C.muted });
  });
}

// ---------------------------------------------------------------- 6 demo
{
  const s = slide("시연 결과", "시연은 중간발표와 같은 상황입니다. U030 튜닝에 480분이 더 필요하다고 입력하면 LOT-001이 출하검사보다 297분, 4시간 57분 늦어 긴급이 됩니다. 순서만 바꾸는 후보는 297분 그대로이고, FCFS는 549분입니다. 추가근무를 켜면 10월 22일 하루 2시간을 여는 안이 177분, 2시간 57분으로 1위가 됩니다. 승인하면 계획 v2가 되지만 여전히 긴급입니다. 평일 17시에서 19시 추가근무만으로는 이 지연을 다 없앨 수 없다는 뜻입니다.");
  title(s, "2시간을 더 열어 2시간을 줄였다. 그래도 긴급", "중간발표 상황 그대로: LOT-001 U030 튜닝에 480분 추가 입력 (시연 시각 10/22 13:17 고정)");
  // custom horizontal bars (data from tests/integration/test_demo_overtime_option.py)
  const rows = [
    ["EDD · Slack · CR", "순서만", 297, 0, C.muted],
    ["FCFS", "순서만", 549, 0, C.dim],
    ["EDD · Slack · CR + 추가근무", "1위", 177, 120, C.ok],
    ["FCFS + 추가근무", "4위", 177, 360, C.ot],
  ];
  const bx = M + 3.4, bw = 4.6, max = 600, y0 = 2.25;
  T(s, "LOT-001 출하검사 진입 지연 (분)", { x: M, y: 1.95, w: 6, h: 0.28, fontSize: 11, bold: true, color: C.muted });
  rows.forEach((r, i) => {
    const y = y0 + 0.3 + i * 0.95;
    T(s, r[0], { x: M, y: y, w: 3.2, h: 0.32, fontSize: 13, bold: true, color: C.white });
    T(s, r[3] ? `추가 가동 ${r[3]}분 · ${r[1]}` : r[1], { x: M, y: y + 0.33, w: 3.2, h: 0.28, fontSize: 10.5, color: r[3] ? C.ot : C.muted });
    rect(s, bx, y + 0.05, (bw * r[2]) / max, 0.5, r[4], { round: true, r: 0.05 });
    T(s, `${r[2]}`, { x: bx + (bw * r[2]) / max + 0.12, y: y + 0.05, w: 1, h: 0.5, fontSize: 18, bold: true, color: C.white, valign: "middle", fontFace: MONO });
  });
  line(s, bx + (bw * 297) / max, y0 + 0.2, 0, 3.9, C.late, { dash: "dash", w: 1 });
  T(s, "297분 = 4h 57m", { x: bx + (bw * 297) / max - 0.9, y: y0 - 0.05, w: 1.8, h: 0.25, fontSize: 10, color: C.late, align: "center" });
  // screenshots
  const ix = 9.35, iw = W - M - ix;
  const shot = (f, ratio, y) => { const h = iw / ratio; rect(s, ix - 0.05, y - 0.05, iw + 0.1, h + 0.1, C.white, { round: true, r: 0.03 }); s.addImage({ path: IMG(f), x: ix, y, w: iw, h }); return h; };
  T(s, "실제 화면", { x: ix, y: 1.95, w: 3, h: 0.28, fontSize: 11, bold: true, color: C.muted });
  let y = 2.35;
  y += shot("e_problem.png", 2480 / 114, y) + 0.2;
  y += shot("f_ranking.png", 2480 / 636, y) + 0.2;
  y += shot("i_approved_flash.png", 2480 / 114, y) + 0.2;
  shot("j_metrics_v2.png", 2480 / 156, y);
  rect(s, M, 6.25, 8.6, 0.55, C.panel, { round: true, line: C.line });
  T(s, "승인 → 계획 v2, LOT-001은 여전히 긴급. 평일 17~19시 추가근무만으로는 다 없앨 수 없다.", { x: M + 0.25, y: 6.25, w: 8.2, h: 0.55, fontSize: 12.5, color: C.text, valign: "middle" });
}

// ---------------------------------------------------------------- 7 video
{
  const s = slide("실행 시연 영상", "(영상 재생, 약 45초) 실적 입력, 긴급 판정, 후보 비교, 추가근무안 승인, v2 반영 순서입니다.");
  title(s, "실행 시연", "실적 입력 → 긴급 판정 → 후보 비교 → 추가근무안 승인 → v2 반영");
  rect(s, 1.6, 2.0, W - 3.2, 4.85, C.panel, { round: true, line: C.line });
  dot(s, W / 2, 4.2, 1.2, C.late);
  s.addShape(pres.shapes.ISOSCELES_TRIANGLE, { x: W / 2 - 0.2, y: 3.92, w: 0.5, h: 0.56, rotate: 90, fill: { color: C.bg }, line: { color: C.bg } });
  T(s, "MP4 삽입 영역 · 약 45초", { x: 1.6, y: 5.05, w: W - 3.2, h: 0.4, fontSize: 16, bold: true, color: C.white, align: "center" });
  T(s, "촬영 가이드 순서대로 녹화한 파일을 이 상자 위에 넣는다", { x: 1.6, y: 5.5, w: W - 3.2, h: 0.3, fontSize: 11, color: C.muted, align: "center" });
}

// ---------------------------------------------------------------- 8 experiment design
{
  const s = slide("실험 설계", "반복 실험 설계입니다. 시작은 중간발표 데모 상태이고 기준계획은 접수순입니다. 조건은 세 가지입니다. 정상 조건은 표준시간에 로그정규 잡음, 시그마 0.15를 곱한 것으로, ±15%를 넘는 경우도 있습니다. 작업시간 20% 증가, 그리고 작업정지·재작업 조건이 있는데, 작업정지는 실제 보류 이벤트가 아니라 작업시간을 240분 늘리는 모델입니다. 재계획 방법은 계획 유지와 네 규칙의 추가근무 끔과 켬, 9가지입니다. 각 30번, 총 810번이고, 같은 seed는 모든 구성이 같은 실제 작업시간과 불합격을 받게 해서 공정하게 비교했습니다.");
  title(s, "같은 출발점, 다른 결정 — 810번", "시작: 중간발표 데모 상태(10/22 13:00), 기준계획 접수순. 관리자는 시스템이 '긴급'이라 할 때만 해당 규칙을 승인");
  const eq = [["3", "교란 조건", C.white], ["×", "", C.dim], ["9", "재계획 구성", C.white], ["×", "", C.dim], ["30", "seed", C.white], ["=", "", C.dim], ["810", "폐루프 실행", C.late]];
  let ex = M;
  eq.forEach((e) => {
    const w = e[1] ? 1.65 : 0.6;
    T(s, e[0], { x: ex, y: 2.0, w, h: 1.0, fontSize: e[1] ? 56 : 36, bold: true, align: "center", valign: "middle", color: e[2], fontFace: MONO });
    if (e[1]) T(s, e[1], { x: ex, y: 3.0, w, h: 0.3, fontSize: 11.5, align: "center", color: C.muted });
    ex += w + 0.08;
  });
  const cards = [
    ["정상", "표준시간 × 로그정규 잡음 σ=0.15\n작업자 추정 오차 σ=0.2\nσ=0.15는 ±15% 한계가 아님", C.blue],
    ["작업시간 +20%", "모든 작업이 평균 1.2배\n(같은 잡음 포함)", C.ot],
    ["작업정지·재작업", "작업 시도의 3%에 +240분\n(작업시간 연장 모델, HOLD 이벤트 아님)\n최종시험 8% 불합격 → 튜닝 재작업", C.late],
  ];
  cards.forEach((c, i) => {
    const x = M + i * 3.0, y = 3.75, w = 2.85;
    rect(s, x, y, w, 2.95, C.panel, { round: true, line: C.line });
    rect(s, x, y, w, 0.06, c[2]);
    T(s, c[0], { x: x + 0.22, y: y + 0.25, w: w - 0.4, h: 0.35, fontSize: 15, bold: true, color: c[2] });
    T(s, c[1], { x: x + 0.22, y: y + 0.75, w: w - 0.4, h: 2.0, fontSize: 11.5, color: C.text, lineSpacingMultiple: 1.3 });
  });
  const rx = 9.75, rw = W - M - rx;
  rect(s, rx, 2.0, rw, 4.7, C.panel2, { round: true, line: C.line });
  T(s, "공정한 비교", { x: rx + 0.25, y: 2.2, w: rw - 0.5, h: 0.32, fontSize: 13, bold: true, color: C.ok });
  T(s, [
    { text: "공통 난수: 같은 seed는 모든 구성이 같은 실제 작업시간·불합격을 받는다", options: { bullet: true, breakLine: true } },
    { text: "평균 ± 95% 신뢰구간(t분포)", options: { bullet: true, breakLine: true } },
    { text: "KEEP과 같은 seed끼리 짝지은 차이", options: { bullet: true, breakLine: true } },
    { text: "명령 한 줄로 재현, 중단돼도 이어서 실행", options: { bullet: true } },
  ], { x: rx + 0.25, y: 2.65, w: rw - 0.45, h: 2.9, fontSize: 11.5, color: C.text, paraSpaceAfter: 8 });
  T(s, "python -m production_control.sim.experiment --reps 30", { x: rx + 0.25, y: 5.75, w: rw - 0.4, h: 0.7, fontSize: 9.5, color: C.muted, fontFace: MONO });
}

// ---------------------------------------------------------------- 9 waffle
{
  const s = slide("810번, 한 점이 한 번", "810번의 실행을 점 하나씩으로 그렸습니다. 주황은 출하검사 진입 지연이 남은 실행, 초록은 지연이 0인 실행입니다. 계획을 유지하면 세 조건 모두 30번 전부 늦습니다. FCFS도 기준계획과 같은 접수순이라 거의 그대로입니다. EDD와 Slack은 정상과 작업시간 증가 조건에서 거의 모두 초록이고, 작업정지·재작업 조건에서는 EDD도 30번 중 5번, Slack은 10번 지연이 남았습니다. 추가근무를 켜면 이 남은 지연이 더 줄어듭니다.");
  title(s, "810번 중 어디서 늦었나", "점 하나 = 실행 1회.  주황 = 출하검사 진입 지연이 남음,  초록 = 지연 0.  같은 열의 같은 위치는 같은 seed");
  const gx = M + 1.8, cellW = (W - M - (M + 1.8)) / 9, cellH = 1.3, ds = 0.15, top = 2.3;
  CFGS.forEach((k, j) => {
    const ot = k.endsWith("+OT");
    T(s, ot ? "+OT" : k, { x: gx + j * cellW, y: top - 0.4, w: cellW - 0.15, h: 0.3, fontSize: ot ? 10 : 11.5, bold: true, color: ot ? C.ot : C.white, align: "center" });
  });
  CONDS.forEach((c, i) => {
    const y0 = top + i * cellH;
    T(s, CL[c], { x: M, y: y0 + 0.3, w: 1.75, h: 0.5, fontSize: 12, bold: true, color: C.text, valign: "middle" });
    CFGS.forEach((k, j) => {
      const x0 = gx + j * cellW;
      const rs = RUNS.filter((r) => r.cond === c && r.cfg === k).sort((a, b) => a.seed - b.seed);
      rs.forEach((r, n) => {
        const col = n % 6, row = Math.floor(n / 6);
        s.addShape(pres.shapes.RECTANGLE, {
          x: x0 + col * ds, y: y0 + row * ds, w: ds - 0.03, h: ds - 0.03,
          fill: { color: r.delay > 0 ? C.late : C.ok }, line: { color: r.delay > 0 ? C.late : C.ok, width: 0 },
        });
      });
      const late = rs.filter((r) => r.delay > 0).length;
      T(s, `${late}/30`, { x: x0, y: y0 + 5 * ds + 0.06, w: 6 * ds, h: 0.22, fontSize: 9, color: late ? C.late : C.ok, align: "center", fontFace: MONO });
    });
  });
  rect(s, M, 6.3, W - 2 * M, 0.55, C.panel, { round: true, line: C.line });
  T(s, [
    { text: "계획 유지 30/30 지연   ·   ", options: { color: C.late } },
    { text: "EDD 0 · 0 · 5/30   ·   ", options: { color: C.ok } },
    { text: "FCFS ≈ 계획 유지   ·   ", options: {} },
    { text: "+OT는 남은 지연을 더 줄인다", options: { color: C.ot } },
  ], { x: M + 0.25, y: 6.3, w: W - 2 * M - 3.2, h: 0.55, fontSize: 12, bold: true, color: C.text, valign: "middle" });
  T(s, "원자료: experiments/main30/runs.csv", { x: W - M - 3.1, y: 6.3, w: 2.9, h: 0.55, fontSize: 9.5, color: C.dim, align: "right", valign: "middle" });
}

// ---------------------------------------------------------------- 10 result numbers
{
  const s = slide("결과 ① 지연의 크기", `결과입니다. 지표는 LOT별로 출하검사 시작보다 늦은 시간만 더한 값의 평균입니다. 계획을 유지하면 정상 ${fmt(m("NORMAL", "KEEP"))}분, 작업시간 증가 ${fmt(m("SLOW", "KEEP"))}분, 작업정지·재작업 ${fmt(m("STOPPAGE_REWORK", "KEEP"))}분입니다. EDD로 재계획하면 0, 0, 그리고 ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분으로 크게 줄었습니다. 작업정지 조건에서는 5번 지연이 남았기 때문에 없앴다가 아니라 크게 줄였다고 말씀드립니다.`);
  title(s, "재계획은 출하검사 진입 지연을 크게 줄였다", "평균, n=30. 지연 = LOT별 max(0, 생산 완료 − 출하검사 예정 시작)의 합. 추가근무 없는 구성 기준");
  const cw = (W - 2 * M - 0.5) / 3;
  CONDS.forEach((c, i) => {
    const x = M + i * (cw + 0.25), y = 2.0;
    rect(s, x, y, cw, 4.75, C.panel, { round: true, line: C.line });
    T(s, CL[c], { x: x + 0.25, y: y + 0.18, w: cw - 0.5, h: 0.32, fontSize: 13, bold: true, color: C.muted });
    T(s, fmt(m(c, "KEEP")), { x: x + 0.25, y: y + 0.55, w: cw / 2, h: 0.7, fontSize: 30, bold: true, color: C.late, fontFace: MONO });
    T(s, "계획 유지", { x: x + 0.25, y: y + 1.22, w: cw / 2, h: 0.25, fontSize: 10, color: C.muted });
    T(s, "→", { x: x + cw / 2 - 0.15, y: y + 0.6, w: 0.5, h: 0.6, fontSize: 24, color: C.dim });
    const e = m(c, "EDD");
    T(s, e < 0.05 ? "0" : fmt(e, 1), { x: x + cw / 2 + 0.3, y: y + 0.55, w: cw / 2 - 0.5, h: 0.7, fontSize: 30, bold: true, color: C.ok, fontFace: MONO });
    T(s, `EDD · 지연 ${lateCount(c, "EDD")}/30회`, { x: x + cw / 2 + 0.3, y: y + 1.22, w: cw / 2 - 0.4, h: 0.25, fontSize: 10, color: C.muted });
    const pol = ["KEEP", "FCFS", "EDD", "SLACK", "CR"];
    const vals = pol.map((p) => m(c, p));
    s.addChart(pres.charts.BAR, [{ name: CL[c], labels: ["KEEP", "FCFS", "EDD", "Slack", "CR"], values: vals.map((v) => Math.round(v * 10) / 10) }], {
      x: x + 0.1, y: y + 1.65, w: cw - 0.2, h: 3.0, barDir: "col", chartColors: ["8798AE", "5A6B82", "2ED3A4", "5AA9FF", "FFC54D"],
      showValue: true, dataLabelPosition: "outEnd", dataLabelColor: "E8EEF6", dataLabelFontSize: 10, dataLabelFormatCode: "#,##0.#",
      dataLabelFontFace: FONT, catAxisLabelColor: "8798AE", catAxisLabelFontSize: 10, catAxisLabelFontFace: FONT, valAxisHidden: true,
      valGridLine: { style: "none" }, catGridLine: { style: "none" }, catAxisLineShow: false, showLegend: false, barGapWidthPct: 45,
      plotArea: { fill: { color: C.panel } }, varyColors: true,
    });
  });
}

// ---------------------------------------------------------------- 11 gantt (drawn from gantt_replan.json)
{
  const s = slide("결과 ② 무엇이 바뀌었나", "왜 줄었는지 실험 시작 시점의 일정으로 보겠습니다. 위 줄은 계획을 유지했을 때의 Forecast, 아래 줄은 EDD 재계획안입니다. 계획을 유지하면 LOT-003의 최종 성능시험이 10월 28일 12시 15분에 끝나 출하검사 시작 9시를 넘습니다. EDD는 출하검사가 빠른 LOT-003의 튜닝과 시험을 앞당겨 10월 23일에 끝내고, 출하검사가 11월 6일이라 여유가 많은 LOT-002를 뒤로 보냅니다. 작업시간과 자원은 같고 병목 장비를 쓰는 순서만 바뀌었습니다. 일부러 만든 충돌이므로 EDD가 모든 현장에서 최선이라는 뜻은 아니고, 시스템이 이런 충돌을 찾아 고친다는 결과입니다.");
  title(s, "바꾼 것은 병목 장비를 쓰는 순서뿐", "실험 시작 시점(10/22 13:00)에 시스템이 계산한 두 일정. 막대 = LOT×공정의 첫 작업 시작 ~ 마지막 작업 종료");
  const t0 = Date.parse("2026-10-22T09:00"), t1 = Date.parse("2026-10-29T00:00");
  const gx = M + 2.35, gw = W - M - gx - 0.1;
  const X = (iso) => gx + (gw * (Date.parse(iso) - t0)) / (t1 - t0);
  const lots = ["LOT-003", "LOT-002", "LOT-001"];
  const procCol = { "튜닝": C.late, "마무리 조립": C.blue, "최종 성능시험": C.ok };
  const layers = [["현재 Forecast", "계획 유지"], ["재계획안", "EDD 재계획"]];
  const top = 2.25, laneH = 1.3;
  // day grid
  for (let d = 22; d <= 28; d++) {
    const iso = `2026-10-${d}T00:00`;
    const x = X(iso) < gx ? gx : X(iso);
    if (d > 22) line(s, x, top - 0.1, 0, laneH * 3 + 0.2, C.line, { w: 0.75 });
    T(s, `10/${d}`, { x: Math.max(gx, X(`2026-10-${d}T12:00`) - 0.4), y: top + laneH * 3 + 0.15, w: 0.8, h: 0.25, fontSize: 9.5, color: C.muted, align: "center", fontFace: MONO });
  }
  lots.forEach((lot, i) => {
    const y0 = top + i * laneH;
    rect(s, M, y0, W - 2 * M, laneH - 0.1, i % 2 ? C.bg : C.panel, { line: i % 2 ? C.bg : C.panel });
    T(s, lot, { x: M + 0.15, y: y0 + 0.1, w: 1.4, h: 0.32, fontSize: 14, bold: true, color: C.white });
    const gate = GANTT.markers.find((g) => g.lot_label === lot);
    T(s, `출하검사 ${gate.at.slice(5, 10).replace("-", "/")} ${gate.at.slice(11)}`, { x: M + 0.15, y: y0 + 0.45, w: 2.1, h: 0.25, fontSize: 9.5, color: C.muted });
    layers.forEach(([layer, lab], li) => {
      const ly = y0 + 0.22 + li * 0.5;
      T(s, lab, { x: gx - 0.95, y: ly, w: 0.9, h: 0.32, fontSize: 9, color: li ? C.white : C.muted, align: "right", valign: "middle" });
      GANTT.bars.filter((b) => b.lot_label === lot && b.layer === layer).forEach((b) => {
        const xa = X(b.start), xb = Math.max(X(b.end), xa + 0.04);
        const ph = 0.13, k = ["튜닝", "마무리 조립", "최종 성능시험"].indexOf(b.process_label);
        rect(s, xa, ly + 0.02 + k * ph, Math.min(xb, gx + gw) - xa, ph - 0.02, procCol[b.process_label], { tr: li ? 0 : 55 });
      });
    });
    if (Date.parse(gate.at) < t1) {
      const gxp = X(gate.at);
      line(s, gxp, y0 + 0.05, 0, laneH - 0.2, C.white, { w: 2 });
      dot(s, gxp, y0 + 0.05, 0.12, C.white);
    } else {
      T(s, "Gate 11/06 → 그림 밖 (여유 충분)", { x: gx + gw - 2.6, y: y0 + 0.05, w: 2.6, h: 0.22, fontSize: 9, color: C.muted, align: "right" });
    }
  });
  // annotation LOT-003
  const keepEnd = GANTT.bars.find((b) => b.lot_label === "LOT-003" && b.layer === "현재 Forecast" && b.process_label === "최종 성능시험").end;
  const eddEnd = GANTT.bars.find((b) => b.lot_label === "LOT-003" && b.layer === "재계획안" && b.process_label === "최종 성능시험").end;
  T(s, `유지: ${keepEnd.slice(5, 10).replace("-", "/")} ${keepEnd.slice(11)} 완료 → Gate 초과`, { x: X(GANTT.markers.find((g) => g.lot_label === "LOT-003").at) - 3.2, y: top + 0.0, w: 3.0, h: 0.22, fontSize: 9.5, bold: true, color: C.late, align: "right" });
  T(s, `EDD: ${eddEnd.slice(5, 10).replace("-", "/")} ${eddEnd.slice(11)} 완료`, { x: X(eddEnd) + 0.1, y: top + 0.78, w: 2.6, h: 0.22, fontSize: 9.5, bold: true, color: C.ok });
  // legend
  const ly = 6.6;
  Object.entries(procCol).forEach(([k, v], i) => { rect(s, M + i * 1.9, ly + 0.07, 0.3, 0.13, v); T(s, k, { x: M + 0.38 + i * 1.9, y: ly, w: 1.5, h: 0.28, fontSize: 10, color: C.muted }); });
  T(s, "흐린 막대 = 계획 유지 Forecast · 진한 막대 = EDD 재계획안 · 흰 선 = 출하검사 예정", { x: M + 5.8, y: ly, w: 6.4, h: 0.28, fontSize: 10, color: C.muted, align: "right" });
}

// ---------------------------------------------------------------- 12 overtime dumbbells
{
  const cases = [
    ["STOPPAGE_REWORK", "CR"], ["STOPPAGE_REWORK", "EDD"], ["SLOW", "CR"], ["NORMAL", "FCFS"], ["NORMAL", "CR"], ["NORMAL", "EDD"],
  ];
  const s = slide("결과 ③ 추가근무의 효과와 비용", `추가근무는 지연이 남는 규칙에서 효과가 있었습니다. 작업정지 조건의 CR은 ${fmt(m("STOPPAGE_REWORK", "CR"))}분에서 ${fmt(m("STOPPAGE_REWORK", "CR+OT"))}분으로, 정상 조건의 FCFS는 약 ${fmt(m("NORMAL", "FCFS"))}분에서 ${fmt(m("NORMAL", "FCFS+OT"))}분으로 줄었습니다. 맨 아래 줄이 비용입니다. 정상 조건의 EDD는 이미 지연이 0인데도 추가근무를 켜면 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분을 열었고, 30번 중 27번 실제로 사용했습니다. 결정 시점의 Forecast가 비관적이었던 것으로 보이며, 이를 한계로 보고합니다.`);
  title(s, "추가근무: 남은 지연엔 약, 없는 지연엔 비용", "같은 규칙에서 추가근무를 끄고(○) 켰을 때(●)의 평균 지연, 오른쪽은 평균 추가 가동시간 (n=30)");
  const lx = M + 2.6, lw = 5.3, max = 220;
  const ox = lx + lw + 0.9, ow = W - M - ox - 0.7, omax = 400;
  T(s, "출하검사 진입 지연 (분)", { x: lx, y: 1.95, w: lw, h: 0.28, fontSize: 11, bold: true, color: C.muted });
  T(s, "추가 가동시간 (분)", { x: ox, y: 1.95, w: ow + 0.7, h: 0.28, fontSize: 11, bold: true, color: C.ot });
  [0, 50, 100, 150, 200].forEach((v) => {
    const x = lx + (lw * v) / max;
    line(s, x, 2.3, 0, 3.75, C.line, { w: 0.75 });
    T(s, String(v), { x: x - 0.3, y: 6.08, w: 0.6, h: 0.22, fontSize: 9, color: C.dim, align: "center", fontFace: MONO });
  });
  cases.forEach(([c, p], i) => {
    const y = 2.55 + i * 0.6, a = m(c, p), b = m(c, p + "+OT"), ot = m(c, p + "+OT", "overtime_minutes");
    const waste = a < 0.05;
    T(s, `${CL[c]} · ${p === "SLACK" ? "Slack" : p}`, { x: M, y: y - 0.16, w: 2.5, h: 0.32, fontSize: 11.5, bold: true, color: waste ? C.ot : C.white, valign: "middle" });
    const xa = lx + (lw * Math.min(a, max)) / max, xb = lx + (lw * Math.min(b, max)) / max;
    if (Math.abs(xa - xb) > 0.02) line(s, Math.min(xa, xb), y, Math.abs(xa - xb), 0, C.ok, { w: 3 });
    s.addShape(pres.shapes.OVAL, { x: xa - 0.1, y: y - 0.1, w: 0.2, h: 0.2, fill: { color: C.bg }, line: { color: C.muted, width: 1.5 } });
    dot(s, xb, y, 0.2, waste ? C.ot : C.ok);
    T(s, waste ? "0 → 0" : `${fmt(a)} → ${fmt(b)}`, { x: Math.max(xa, xb) + 0.18, y: y - 0.15, w: 1.3, h: 0.3, fontSize: 10.5, color: C.text, valign: "middle", fontFace: MONO });
    rect(s, ox, y - 0.13, (ow * ot) / omax, 0.26, C.ot, { tr: waste ? 0 : 45 });
    T(s, fmt(ot), { x: ox + (ow * ot) / omax + 0.08, y: y - 0.15, w: 0.7, h: 0.3, fontSize: 10.5, bold: true, color: C.ot, valign: "middle", fontFace: MONO });
  });
  rect(s, M, 6.3, W - 2 * M, 0.62, "2B2410", { round: true, line: C.ot });
  T(s, `정상·EDD: 이미 0분인데 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분을 연다(30회 중 27회 사용). 추정 원인: 결정 시점 Forecast가 비관적 → 예측 보정 없이는 필요 없는 추가근무를 산다. 한계로 보고.`, { x: M + 0.25, y: 6.3, w: W - 2 * M - 0.5, h: 0.62, fontSize: 11, color: C.text, valign: "middle" });
}

// ---------------------------------------------------------------- 13 two metrics
{
  const s = slide("두 지표", "지표를 두 가지로 나눴습니다. 출하검사 진입 지연은 생산 완료가 출하검사 시작보다 늦은 시간이고, 중간발표의 4시간 57분도 이것입니다. 최종 납기 지각은 출하검사가 시작일을 포함해 3근무일에 끝난다고 가정했을 때 출하가 고객 납기보다 늦은 시간입니다. 이 가정하에서 810번 모두 0이었고, 가장 빠듯한 경우도 납기 당일 17시 출하였습니다. 이 데모는 고객 납기에 여유가 있어서, 실제로 지켜야 하는 선은 출하검사 시작이었습니다.");
  title(s, "지켜야 할 선은 두 개, 이번에 걸린 건 하나", "생산이 지켜야 하는 선(출하검사 시작)과 고객이 받는 선(납기)은 다르다");
  const y = 2.75, x0 = M + 0.5, x1 = W - M - 0.5;
  line(s, x0, y, x1 - x0, 0, C.line, { w: 3 });
  const marks = [[0.03, "생산 완료", "마지막 최종시험 합격", C.white], [0.32, "출하검사 시작", "Gate 예정 시각", C.late], [0.7, "출하", "시작일 포함 3근무일, 17:00 (가정)", C.white], [0.97, "고객 납기", "Lot.due_at", C.blue]];
  marks.forEach((mk) => {
    const x = x0 + (x1 - x0) * mk[0];
    dot(s, x, y, 0.26, mk[3]);
    T(s, mk[1], { x: x - 1.3, y: y - 0.68, w: 2.6, h: 0.35, fontSize: 14, bold: true, align: "center", color: mk[3] });
    T(s, mk[2], { x: x - 1.5, y: y + 0.25, w: 3.0, h: 0.28, fontSize: 10, align: "center", color: C.muted });
  });
  const bx = (f) => x0 + (x1 - x0) * f;
  rect(s, bx(0.03), y - 0.08, bx(0.32) - bx(0.03), 0.16, C.late, { tr: 40 });
  rect(s, bx(0.7), y - 0.08, bx(0.97) - bx(0.7), 0.16, C.blue, { tr: 40 });
  const cards = [
    ["출하검사 진입 지연", "재계획의 KPI", C.late, ["LOT별 max(0, 생산 완료 − 출하검사 예정 시작)의 합", "출하검사 소요 가정 불필요", "중간발표 ‘4h 57m’도 이 지표", `계획 유지 ${fmt(m("NORMAL", "KEEP"))}~${fmt(m("STOPPAGE_REWORK", "KEEP"))}분 → EDD 0~${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분`]],
    ["최종 납기 지각", "고객 기준", C.blue, ["LOT별 max(0, 출하 − 고객 납기)의 합", "출하검사 3근무일 가정 (대시보드와 같은 규칙)", "이 가정하에서 810회 모두 0", "가장 빠듯한 경우 납기 당일 17:00 출하 (KEEP 2회, FCFS 1회)"]],
  ];
  cards.forEach((c, i) => {
    const x = M + i * 6.15, w = 5.95, yy = 3.7;
    rect(s, x, yy, w, 3.0, C.panel, { round: true, line: C.line });
    rect(s, x, yy, 0.07, 3.0, c[2]);
    T(s, c[0], { x: x + 0.3, y: yy + 0.2, w: w - 2, h: 0.4, fontSize: 17, bold: true, color: c[2] });
    chip(s, x + w - 1.7, yy + 0.25, 1.45, c[1], c[2]);
    T(s, c[3].map((b, k) => ({ text: b, options: { bullet: true, breakLine: k < c[3].length - 1 } })), { x: x + 0.3, y: yy + 0.8, w: w - 0.55, h: 2.1, fontSize: 12.5, color: C.text, paraSpaceAfter: 7 });
  });
}

// ---------------------------------------------------------------- 14 verification
{
  const s = slide("검증과 트러블슈팅", "검증입니다. 자동 테스트 384개가 Python 두 버전에서 통과하고, 810번 실행에서 공장 규칙 위반은 0건입니다. 반복 실험은 버그를 찾는 데도 쓰였습니다. 17시 정각 재계획 때 진행 중 작업을 처리하지 못하는 문제로 810번 중 3번이 실패했고, 고친 뒤 다시 돌려 모두 성공했습니다. 실패 기록은 지우지 않고 남겼습니다.");
  title(s, "실험은 버그를 찾는 도구이기도 했다", "고친 문제는 회귀 테스트로 고정했다. 실패 기록은 지우지 않았다");
  const st = [["384", "자동 테스트", "Python 3.11 · 3.13 CI"], ["810", "폐루프 실행", "27개 조합 × 30회"], ["0", "공장 규칙 위반", "중복·용량·선후·근무시간"], ["0", "최종 실패", "첫 실행 3회 실패 → 수정"]];
  st.forEach((v, i) => {
    const x = M + i * 3.07;
    rect(s, x, 2.0, 2.9, 1.65, C.panel, { round: true, line: C.line });
    T(s, v[0], { x: x + 0.25, y: 2.1, w: 2.5, h: 0.8, fontSize: 40, bold: true, color: i < 2 ? C.white : C.ok, fontFace: MONO });
    T(s, v[1], { x: x + 0.25, y: 2.9, w: 2.5, h: 0.3, fontSize: 13, bold: true, color: C.text });
    T(s, v[2], { x: x + 0.25, y: 3.22, w: 2.5, h: 0.28, fontSize: 10, color: C.muted });
  });
  const bugs = [
    ["17:00 정각 재계획에서 실행 실패", "810회 중 3회, HTTP 409", "진행 중 작업이 결정 시각에 바로 이어진다고 가정", "다음 근무 시작에 재개 → 3회 재실행 성공"],
    ["재작업으로 다시 열린 공정 누락", "후보 계산 오류", "승인 계획에 없는 공정을 찾지 못함", "부모 계획 뒤 순위로 배치"],
    ["실험·대시보드 출하검사 기준 불일치", "지표 정의 충돌", "실험만 '완료 후 24근무시간' 가정", "한 모듈로 통일, 기록 재계산"],
  ];
  const ty = 4.25;
  line(s, M + 0.15, ty + 0.15, W - 2 * M - 0.3, 0, C.line, { w: 1.5 });
  bugs.forEach((b, i) => {
    const x = M + i * 4.1, w = 3.9;
    dot(s, x + 0.15, ty + 0.15, 0.22, C.late);
    T(s, b[0], { x: x + 0.4, y: ty, w: w - 0.4, h: 0.32, fontSize: 13, bold: true, color: C.white });
    T(s, b[1], { x: x + 0.4, y: ty + 0.33, w: w - 0.4, h: 0.26, fontSize: 10, color: C.late });
    rect(s, x, ty + 0.75, w, 1.7, C.panel, { round: true, line: C.line });
    T(s, "원인", { x: x + 0.2, y: ty + 0.88, w: 0.7, h: 0.26, fontSize: 10, bold: true, color: C.muted });
    T(s, b[2], { x: x + 0.9, y: ty + 0.88, w: w - 1.05, h: 0.6, fontSize: 11, color: C.text });
    T(s, "해결", { x: x + 0.2, y: ty + 1.6, w: 0.7, h: 0.26, fontSize: 10, bold: true, color: C.ok });
    T(s, b[3], { x: x + 0.9, y: ty + 1.6, w: w - 1.05, h: 0.6, fontSize: 11, color: C.text });
  });
}

// ---------------------------------------------------------------- 15 proven / not proven
{
  const s = slide("한계", "한계입니다. 오른쪽이 증명하지 않은 것입니다. Pico 단말은 연동하지 못했고, TCP 통신은 같은 컴퓨터 안에서만 확인했습니다. 작업시간 분포와 교란 확률은 실제 데이터가 아닌 가정값이고, 작업정지는 실제 보류 이벤트가 아니라 작업시간 연장으로 모사했습니다. 최종 납기 지각 0은 출하검사 3근무일 가정하의 결과이고, 시작 상태는 재계획 효과를 보려고 만든 충돌이므로 EDD가 일반적으로 최선이라는 뜻이 아닙니다.");
  title(s, "증명한 것과 증명하지 않은 것", "결론을 읽을 때 함께 봐야 하는 범위");
  const cols = [
    ["증명한 것 (실행·테스트 근거)", C.ok, [
      "승인한 계획이 작업지시로 내려가 현장 순서를 바꾼다",
      "실제 시간 = 표준시간이면 현장 결과가 Forecast와 일치",
      "추가근무 승인이 달력·Forecast·현장에 함께 반영",
      "810회: 이 충돌 상황에서 재계획이 진입 지연을 크게 줄임",
      "예측이 비관적이면 불필요한 추가근무를 고를 수 있음",
    ]],
    ["증명하지 않은 것", C.late, [
      "Pico 2 WH 단말 연동 (TCP는 localhost만, Wi-Fi 아님)",
      "실제 공장 데이터 (작업시간 분포·교란 확률은 가정값)",
      "작업정지 = 작업시간 240분 연장 모델 (HOLD 이벤트 아님)",
      "출하검사 자체의 대기·불합격 (3근무일 가정)",
      "EDD가 일반 현장에서 최선이라는 것 (의도적 충돌 상황)",
    ]],
  ];
  cols.forEach((c, i) => {
    const x = M + i * 6.15, w = 5.95, y = 2.0;
    rect(s, x, y, w, 4.75, C.panel, { round: true, line: C.line });
    T(s, c[0], { x: x + 0.3, y: y + 0.22, w: w - 0.6, h: 0.4, fontSize: 16, bold: true, color: c[1] });
    c[2].forEach((b, k) => {
      const yy = y + 0.85 + k * 0.76;
      T(s, i ? "✕" : "✓", { x: x + 0.3, y: yy, w: 0.35, h: 0.4, fontSize: 15, bold: true, color: c[1] });
      T(s, b, { x: x + 0.7, y: yy + 0.02, w: w - 1.0, h: 0.62, fontSize: 12.5, color: C.text });
    });
  });
}

// ---------------------------------------------------------------- 16 closing
{
  const s = slide(null, "정리하면, 실적이 다음 작업지시를 바꾸는 폐루프를 실행으로 확인했고, 810번의 반복 실험에서 재계획이 출하검사 진입 지연을 크게 줄였습니다. 추가근무는 순서로 안 되는 지연을 줄였지만, 예측이 비관적이면 필요 없는 추가근무를 고른다는 한계도 확인했습니다. 앞으로는 Pico 연동, 예측 보정, 추가근무 비용을 반영한 선택을 해 보고 싶습니다. 감사합니다.");
  chip(s, M, 1.0, 1.6, "결론", C.late);
  T(s, "실적을 보여주는 대시보드가 아니라,\n실적이 다음 작업지시를 바꾸는 시스템", { x: M, y: 1.55, w: W - 2 * M, h: 1.7, fontSize: 34, bold: true, color: C.white, lineSpacingMultiple: 1.1 });
  const k = [
    ["폐루프", "승인 → 작업지시 → 현장 순서 변경, 테스트로 확인", C.white],
    [`${fmt(m("STOPPAGE_REWORK", "KEEP"))} → ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}`, "작업정지 조건 평균 진입 지연(분), 계획 유지 → EDD", C.ok],
    ["108분", "지연 0인데 산 추가근무: 예측 보정이 다음 과제", C.ot],
  ];
  k.forEach((v, i) => {
    const x = M + i * 4.1;
    line(s, x, 3.75, 3.8, 0, C.line, { w: 1 });
    T(s, v[0], { x, y: 3.95, w: 3.8, h: 0.75, fontSize: 32, bold: true, color: v[2], fontFace: v[0].match(/^[0-9]/) ? MONO : FONT });
    T(s, v[1], { x, y: 4.75, w: 3.7, h: 0.6, fontSize: 12, color: C.muted });
  });
  T(s, "향후 과제   Pico 단말을 같은 API에 연결 · 실적으로 Forecast 보정 · 추가근무 비용을 순위에 반영 · 실제 현장 데이터로 시뮬레이터 보정", { x: M, y: 5.95, w: W - 2 * M, h: 0.4, fontSize: 12, color: C.muted });
  T(s, "감사합니다", { x: M, y: 6.5, w: 4, h: 0.45, fontSize: 18, bold: true, color: C.late });
}

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT, page, "slides"));
