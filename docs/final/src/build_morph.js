// 기말발표 모핑 시네마틱 버전. 같은 이름("!!...")의 도형이 다음 장에서 위치·크기·색을 바꾸면 PowerPoint 모핑 전환이 이어서 움직인다.
// 수치는 experiments/main30 원자료와 docs/figures/gantt_replan.json에서 읽는다. 전환 XML은 morph_post.py가 넣는다.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const OUT = process.argv[2] || "morph_raw.pptx";
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
  cond: r.condition, cfg: r.policy + (r.overtime === "True" ? "+OT" : ""), seed: +r.seed, delay: +r.gate_delay_minutes,
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
  bg: "07090F", panel: "111827", panel2: "1A2335", line: "263247", text: "E8EEF6", muted: "8798AE", dim: "4C5B70",
  late: "FF7A3D", ok: "2ED3A4", blue: "5AA9FF", ot: "FFC54D", white: "FFFFFF", grey: "3A475C",
};
const W = 13.333, H = 7.5, M = 0.6;
const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "박상현";
pres.title = "실적이 다음 작업지시를 바꾸는 시스템 — 공프4 기말발표 (모핑 버전)";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

let page = 0;
const T = (s, text, o) => s.addText(text, { fontFace: FONT, isTextBox: true, margin: 0, valign: "top", color: C.text, ...o });
const R = (s, name, x, y, w, h, fill, o = {}) => s.addShape(o.round ? pres.shapes.ROUNDED_RECTANGLE : pres.shapes.RECTANGLE, {
  objectName: name ? "!!" + name : undefined, x, y, w: Math.max(w, 0.01), h: Math.max(h, 0.01),
  fill: { color: fill, transparency: o.tr || 0 }, line: { color: o.line || fill, width: o.lw ?? 0.75, transparency: o.ltr || 0 },
  rectRadius: o.round ? (o.r || 0.08) : undefined,
});
const O = (s, name, cx, cy, d, fill, o = {}) => s.addShape(pres.shapes.OVAL, {
  objectName: name ? "!!" + name : undefined, x: cx - d / 2, y: cy - d / 2, w: d, h: d,
  fill: { color: fill, transparency: o.tr || 0 }, line: { color: o.line || fill, width: o.lw ?? 0.75 },
});
const L = (s, name, x, y, w, h, color, o = {}) => s.addShape(pres.shapes.LINE, {
  objectName: name ? "!!" + name : undefined, x, y, w, h, line: { color, width: o.w || 1.25, dashType: o.dash, endArrowType: o.end },
});
const N = (name) => ({ objectName: "!!" + name });

function slide(kicker, notes) {
  page += 1;
  const s = pres.addSlide();
  s.background = { color: C.bg };
  if (kicker) T(s, kicker, { ...N("kicker"), x: M, y: 0.38, w: 8, h: 0.25, fontSize: 10, bold: true, color: C.late, charSpacing: 1 });
  T(s, String(page).padStart(2, "0"), { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.22, fontSize: 9, color: C.dim, align: "right", fontFace: MONO });
  s.addNotes(notes);
  return s;
}
const head = (s, t, sub) => {
  T(s, t, { ...N("head"), x: M, y: 0.7, w: W - 2 * M, h: 0.75, fontSize: 30, bold: true, color: C.white, valign: "middle" });
  if (sub) T(s, sub, { ...N("sub"), x: M, y: 1.45, w: W - 2 * M, h: 0.35, fontSize: 13.5, color: C.muted });
};

// ================================================================ ACT 1 — the moment
// 1 scene
{
  const s = slide(null, "10월 22일 오후 1시 17분, 튜닝 장비 앞입니다. 작업자가 LOT-001의 마지막 Unit, U030에 앞으로 480분이 더 필요하다고 입력합니다.");
  T(s, "10/22  13:17  ·  튜닝 장비 앞", { ...N("clock"), x: M, y: 2.3, w: 8, h: 0.4, fontSize: 16, color: C.muted, fontFace: MONO });
  T(s, "U030,  480분 더.", { ...N("big"), x: M - 0.05, y: 2.85, w: 12, h: 1.6, fontSize: 80, bold: true, color: C.white });
  T(s, "작업자가 현장 단말에 예상 잔여 작업시간을 입력한다", { ...N("cap"), x: M, y: 4.6, w: 10, h: 0.4, fontSize: 16, color: C.muted });
  R(s, "scan", M, 5.3, 0.02, 0.04, C.late);
}
// 2 verdict
{
  const s = slide(null, "시스템은 바로 다시 계산합니다. LOT-001은 출하검사 시작보다 4시간 57분 늦습니다. 긴급입니다.");
  T(s, "10/22  13:17  ·  Forecast 재계산", { ...N("clock"), x: M, y: 1.3, w: 8, h: 0.4, fontSize: 16, color: C.muted, fontFace: MONO });
  T(s, "4h 57m", { ...N("big"), x: M - 0.08, y: 1.85, w: 12, h: 2.6, fontSize: 150, bold: true, color: C.late, fontFace: MONO });
  T(s, "LOT-001이 출하검사 시작보다 늦는 시간  →  긴급(URGENT)", { ...N("cap"), x: M, y: 4.6, w: 11, h: 0.45, fontSize: 19, bold: true, color: C.white });
  R(s, "scan", M, 5.3, W - 2 * M, 0.04, C.late);
}
// bar geometry shared by slide 3 and 12
const BX = M + 4.3, BW = 6.6, BMAX = 600, BY = 2.2, BS = 1.0;
const bar = (s, name, i, val, color, label, sub, subColor) => {
  const y = BY + i * BS;
  T(s, label, { ...N(name + "_l"), x: M, y: y + 0.02, w: 4.0, h: 0.38, fontSize: 15, bold: true, color: C.white });
  T(s, sub, { ...N(name + "_s"), x: M, y: y + 0.42, w: 4.0, h: 0.3, fontSize: 11.5, color: subColor || C.muted });
  R(s, name, BX, y + 0.05, (BW * val) / BMAX, 0.6, color, { round: true, r: 0.06 });
  T(s, String(val), { ...N(name + "_v"), x: BX + (BW * val) / BMAX + 0.15, y: y + 0.05, w: 1.2, h: 0.6, fontSize: 24, bold: true, color: C.white, valign: "middle", fontFace: MONO });
};
// 3 midterm wall
{
  const s = slide("중간발표의 벽", "중간발표에서는 여기서 멈췄습니다. FCFS, EDD, Slack, CR 어떤 순서로 바꿔도 297분은 그대로였고, FCFS는 LOT 두 개가 늦어 합계 549분이었습니다. 여기 숫자는 LOT별 지연의 합계입니다.");
  head(s, "어떤 순서로 바꿔도 줄지 않았다", "총 출하검사 진입 지연 (분, LOT별 지연 합계) · 재계획 후보별");
  bar(s, "b_seq", 0, 297, C.grey, "EDD · Slack · CR", "순서만 바꿈");
  bar(s, "b_fcfs", 1, 549, C.dim, "FCFS", "순서만 바꿈 · 지연 LOT 2개");
  L(s, "b_ref", BX + (BW * 297) / BMAX, BY - 0.15, 0, 2.2, C.late, { dash: "dash", w: 1 });
  T(s, "순서만으로는 안 되는 지연을 어떻게 다룰 것인가?", { ...N("q"), x: M, y: 5.2, w: 11, h: 0.5, fontSize: 20, bold: true, color: C.late });
}
// 4 title
{
  const s = slide(null, "안녕하십니까, 메카트로닉스공학과 박상현입니다. 기말에서는 이 문제에서 출발해, 실적이 다음 작업지시를 바꾸는 시스템을 완성하고 810번 돌려 확인했습니다.");
  T(s, "4h 57m", { ...N("big"), x: W - M - 3.2, y: 0.5, w: 3.2, h: 0.6, fontSize: 26, bold: true, color: C.late, fontFace: MONO, align: "right" });
  T(s, "공학프로젝트4 · 기말발표", { ...N("kicker"), x: M, y: 1.6, w: 8, h: 0.3, fontSize: 12, bold: true, color: C.late, charSpacing: 1 });
  T(s, "실적이 다음 작업지시를\n바꾸는 시스템", { ...N("head"), x: M, y: 2.05, w: 11, h: 2.3, fontSize: 54, bold: true, color: C.white, lineSpacingMultiple: 1.05 });
  T(s, "현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템", { ...N("sub"), x: M, y: 4.5, w: 11, h: 0.4, fontSize: 17, color: C.muted });
  R(s, "scan", M, 5.2, 1.2, 0.04, C.late);
  T(s, "12233707  박상현  ·  메카트로닉스공학과", { x: M, y: 5.5, w: 8, h: 0.35, fontSize: 14, bold: true, color: C.text });
  T(s, "FastAPI · SQLite · Streamlit · 가상 현장 시뮬레이터  ·  Pico 2 WH 단말 미연동", { x: M, y: 5.95, w: 11, h: 0.3, fontSize: 11.5, color: C.dim });
}

// ================================================================ ACT 2 — the loop
const LOOP = [
  ["현장", "가상 현장 · 숨은 실제 작업시간"],
  ["실적 API", "FastAPI · 검증 · 중복 무시"],
  ["Forecast", "Pace · 유한용량 배치"],
  ["위험 판정", "Gate 여유 ≤ 0 → 긴급"],
  ["재계획 후보", "4규칙 × 추가근무 · 순위"],
  ["관리자 승인", "계획 버전 +1 · 근무달력"],
  ["작업지시 API", "/work-orders · 다음 작업 순서"],
];
const LCX = W / 2, LCY = 4.35, LRX = 4.75, LRY = 2.1;
const lpos = (i) => { const a = Math.PI + (i * 2 * Math.PI) / LOOP.length; return [LCX + LRX * Math.cos(a), LCY + LRY * Math.sin(a)]; };
function loopSlide(step, notes, caption) {
  const s = slide("시스템 구성 · 폐루프", notes);
  head(s, ["실적이 들어온다", "늦을지 판단한다", "사람이 고른다", "현장으로 돌아간다"][step], caption);
  s.addShape(pres.shapes.OVAL, { objectName: "!!ring", x: LCX - LRX, y: LCY - LRY, w: 2 * LRX, h: 2 * LRY, fill: { color: C.bg }, line: { color: C.line, width: 2, dashType: "dash" } });
  const active = [[0, 1, 2], [2, 3, 4], [4, 5], [5, 6, 0]][step];
  LOOP.forEach((n, i) => {
    const [x, y] = lpos(i), w = 2.25, h = 1.0, on = active.includes(i), isNew = step === 3 && (i === 6 || i === 0);
    R(s, "n" + i, x - w / 2, y - h / 2, w, h, on ? C.panel2 : C.panel, { round: true, line: isNew ? C.late : on ? C.blue : C.line, lw: on ? 1.75 : 0.75 });
    T(s, n[0], { ...N("nt" + i), x: x - w / 2, y: y - h / 2 + 0.12, w, h: 0.36, fontSize: 15, bold: true, color: isNew ? C.late : on ? C.white : C.muted, align: "center" });
    T(s, n[1], { ...N("ns" + i), x: x - w / 2 + 0.08, y: y - h / 2 + 0.52, w: w - 0.16, h: 0.4, fontSize: 10, color: on ? C.text : C.dim, align: "center" });
  });
  const at = [1, 3, 5, 6][step];
  const [px, py] = lpos(at);
  O(s, "pulse", px, py - 0.62, 0.26, C.late);
  T(s, ["실적", "긴급", "v2", "작업지시"][step], { ...N("pulse_t"), x: px - 0.8, y: py - 1.02, w: 1.6, h: 0.28, fontSize: 11, bold: true, color: C.late, align: "center" });
  if (step === 3) T(s, "기말에서 닫은 고리", { x: LCX - 1.6, y: LCY - 0.25, w: 3.2, h: 0.5, fontSize: 20, bold: true, color: C.late, align: "center" });
  else T(s, "폐루프", { x: LCX - 1.5, y: LCY - 0.25, w: 3, h: 0.5, fontSize: 20, bold: true, color: C.dim, align: "center" });
  return s;
}
loopSlide(0, "구성입니다. 현장 실적이 들어오면 FastAPI 서버가 검증해 저장하고, Forecast가 남은 작업을 자원과 근무시간 안에 다시 배치합니다.", "작업 시작·완료·합격·불합격이 들어오면 저장하고 Forecast를 다시 계산한다");
loopSlide(1, "출하검사 시작보다 늦을 것 같으면 긴급으로 판정하고, 재계획 후보를 계산합니다.", "생산 완료 예상이 출하검사 Gate를 넘으면 긴급, 후보를 계산한다");
loopSlide(2, "관리자가 후보를 비교해 승인하면 계획 버전이 올라갑니다. 자동 적용은 없습니다.", "자동 적용 없음. 승인해야 계획 버전이 올라간다");
loopSlide(3, "기말에서 닫은 고리가 이 부분입니다. 승인된 계획이 작업지시 API로 현장에 내려가고, 현장은 그 순서대로만 일합니다. 현장은 시스템이 모르는 실제 작업시간으로 움직이는 가상 현장이 맡았고, Pico 단말은 연동하지 못했습니다.", "승인된 계획이 작업지시로 내려가고, 현장은 그 순서대로만 일한다. Pico 단말은 미연동");

// ================================================================ ACT 3 — the plant and the conflict
function plantSlide(stage, notes) {
  const s = slide("모의 생산환경", notes);
  head(s, stage === 0 ? "3 LOT × 30대, 병목은 장비 두 대" : "출하검사가 빠른 LOT-003이 뒤에 있다", stage === 0 ? "표준시간은 로직 검증용 가정값 · 작업자 2명 · 평일 09–17시" : "재계획이 고칠 수 있는 충돌을 일부러 만든 시작 상태");
  const procs = [["테이핑", "10분/대", 0], ["일반 조립", "10분/대", 0], ["튜닝", "25분 · 장비 1대", 1], ["마무리 조립", "10분/대", 0], ["최종 성능시험", "30분 · 장비 1대", 1], ["출하검사", "Gate", 2]];
  const pw = 1.83, pg = 0.2, py = stage === 0 ? 2.25 : 1.95, ph = stage === 0 ? 1.15 : 0.8;
  procs.forEach((p, i) => {
    const x = M + i * (pw + pg), col = p[2] === 1 ? C.late : p[2] === 2 ? C.blue : C.line;
    R(s, "p" + i, x, py, pw, ph, p[2] === 1 ? "2A1A12" : C.panel, { round: true, line: col, lw: p[2] ? 1.5 : 0.75 });
    T(s, p[0], { ...N("pt" + i), x, y: py + 0.12, w: pw, h: 0.35, fontSize: 14, bold: true, color: p[2] === 1 ? C.late : C.white, align: "center" });
    T(s, p[1], { ...N("ps" + i), x, y: py + ph - 0.38, w: pw, h: 0.28, fontSize: 10.5, color: C.muted, align: "center" });
  });
  // LOT chips: baseline order (stage 0) → gate order (stage 1)
  const lots = [["LOT-001", "Gate 10/23", C.text], ["LOT-002", "Gate 11/06", C.late], ["LOT-003", "Gate 10/28", C.ok]];
  const order = stage === 0 ? [0, 1, 2] : [0, 2, 1];
  T(s, stage === 0 ? "기준계획 (접수순)" : "출하검사 순서", { ...N("ordlab"), x: M, y: 4.05, w: 4, h: 0.35, fontSize: 13, bold: true, color: C.muted });
  lots.forEach((l, i) => {
    const slot = order.indexOf(i), x = M + slot * 3.0, y = 4.5;
    R(s, "lot" + i, x, y, 2.7, 1.1, C.panel, { round: true, line: l[2], lw: 1.5 });
    T(s, l[0], { ...N("lott" + i), x, y: y + 0.15, w: 2.7, h: 0.4, fontSize: 18, bold: true, color: l[2], align: "center" });
    T(s, l[1], { ...N("lots" + i), x, y: y + 0.6, w: 2.7, h: 0.3, fontSize: 11.5, color: C.muted, align: "center" });
  });
  if (stage === 0) {
    T(s, "튜닝·시험 장비를 쓰는 순서도 이대로", { x: 9.75, y: 4.6, w: 3, h: 0.9, fontSize: 13, color: C.muted });
  } else {
    T(s, "LOT-003(10/28)이\nLOT-002(11/06)보다\n병목 장비를 늦게 받는다", { x: 9.75, y: 4.45, w: 3.1, h: 1.3, fontSize: 13.5, bold: true, color: C.late, lineSpacingMultiple: 1.2 });
  }
  T(s, "90대 · 작업자 2명 · K=9 (튜닝 9대 후 마무리 착수) · 외부 피드 본딩은 LOT 단위 외부 리드타임", { x: M, y: 6.15, w: 12, h: 0.3, fontSize: 11, color: C.dim });
}
plantSlide(0, "모의 공장은 3개 LOT, 90대입니다. 작업자 2명, 튜닝장비와 시험장비가 1대씩이라 이 두 장비가 병목입니다. 기준계획은 접수순, LOT-001, 002, 003입니다.");
plantSlide(1, "그런데 출하검사 순서는 LOT-003이 10월 28일, LOT-002가 11월 6일입니다. 출하검사가 빠른 LOT-003이 병목 장비를 늦게 받는, 일부러 만든 충돌입니다.");

// 11 candidates and ranking
{
  const s = slide("재계획 후보", "긴급이 되면 네 규칙에 평일 17시부터 19시 추가근무안을 더해 후보 8개를 만들고, 지연 LOT 수, 총 지연시간, 추가 가동시간, 계획 변경량 순서로 순위를 매깁니다. 지연이 같으면 추가근무가 적은 안이 앞섭니다.");
  head(s, "후보 8개, 순위 기준 4개", "추가 가동시간 = 17시 ~ 그날 창 안 마지막 작업 종료 (대기 포함)");
  [["FCFS", "접수순"], ["EDD", "Gate 빠른 LOT"], ["Slack", "여유 적은 LOT"], ["CR", "긴급도 비율"]].forEach((r, i) => {
    const y = 2.2 + i * 1.02;
    R(s, "c" + i, M, y, 2.0, 0.85, C.panel, { round: true, line: C.line });
    T(s, r[0], { x: M + 0.18, y: y + 0.1, w: 1.7, h: 0.35, fontSize: 15, bold: true, color: C.white });
    T(s, r[1], { x: M + 0.18, y: y + 0.48, w: 1.75, h: 0.28, fontSize: 10.5, color: C.muted });
    R(s, "co" + i, M + 2.15, y, 2.15, 0.85, "2B2410", { round: true, line: C.ot });
    T(s, r[0] + " + 추가근무", { x: M + 2.3, y: y + 0.1, w: 1.95, h: 0.35, fontSize: 13, bold: true, color: C.ot });
    T(s, "평일 17~19시", { x: M + 2.3, y: y + 0.48, w: 1.9, h: 0.28, fontSize: 10.5, color: C.muted });
  });
  const fx = 5.6;
  ["지연 LOT 수", "총 지연시간", "추가 가동시간", "계획 변경량"].forEach((c, i) => {
    const w = 4.2 - i * 0.5, x = fx + (4.2 - w) / 2, y = 2.2 + i * 0.95;
    R(s, "f" + i, x, y, w, 0.78, i === 2 ? "2B2410" : C.panel2, { round: true, line: i === 2 ? C.ot : C.line });
    T(s, `${i + 1}  ${c}`, { x, y, w, h: 0.78, fontSize: 15, bold: true, color: i === 2 ? C.ot : C.white, align: "center", valign: "middle" });
  });
  T(s, "앞 기준이 같을 때만 다음을 본다", { x: fx, y: 6.1, w: 4.2, h: 0.3, fontSize: 11.5, color: C.muted, align: "center" });
  R(s, "appr", 10.25, 2.2, W - M - 10.25, 3.75, C.panel, { round: true, line: C.late, lw: 1.5 });
  T(s, "관리자 승인", { x: 10.45, y: 2.4, w: 2.2, h: 0.35, fontSize: 15, bold: true, color: C.late });
  T(s, "자동 적용 없음\n\n승인 → 계획 v+1\n\n추가근무는 근무달력에 저장, Forecast와 현장이 같은 시간을 쓴다", { x: 10.45, y: 2.9, w: 2.1, h: 2.9, fontSize: 11.5, color: C.text });
}

// 12 demo with overtime (bars continue from slide 3)
{
  const s = slide("시연 결과", "다시 시연 상황입니다. 추가근무를 켜면 10월 22일 하루 2시간을 여는 안이 177분, 2시간 57분으로 1위가 됩니다. 승인하면 계획 v2가 되지만 여전히 긴급입니다. 평일 17시에서 19시 추가근무만으로는 다 없앨 수 없습니다.");
  head(s, "2시간을 더 열어 2시간을 줄였다. 그래도 긴급", "총 출하검사 진입 지연 (분, LOT별 지연 합계) · 추가근무 후보 포함 · 시연 시각 10/22 13:17");
  bar(s, "b_seq", 0, 297, C.grey, "EDD · Slack · CR", "순서만 바꿈");
  bar(s, "b_fcfs", 1, 549, C.dim, "FCFS", "순서만 바꿈 · 지연 LOT 2개");
  bar(s, "b_ot", 2, 177, C.ok, "EDD · Slack · CR + 추가근무", "추가 가동 120분 · 공동 1위", C.ot);
  bar(s, "b_fot", 3, 177, C.ot, "FCFS + 추가근무", "추가 가동 360분 · 4위", C.ot);
  L(s, "b_ref", BX + (BW * 297) / BMAX, BY - 0.15, 0, 4.2, C.late, { dash: "dash", w: 1 });
  T(s, "승인 → 계획 v2 · LOT-001은 여전히 긴급", { ...N("q"), x: M, y: 6.35, w: 11, h: 0.45, fontSize: 17, bold: true, color: C.late });
}

// 13 video
{
  const s = slide("실행 시연", "(영상 재생, 약 45초) 실적 입력, 긴급 판정, 후보 비교, 추가근무안 승인, v2 반영 순서입니다.");
  head(s, "실행 시연", "실적 입력 → 긴급 판정 → 후보 비교 → 추가근무안 승인 → v2 반영");
  R(s, "screen", 1.4, 2.0, W - 2.8, 4.95, C.panel, { round: true, line: C.line });
  O(s, null, W / 2, 4.2, 1.2, C.late);
  s.addShape(pres.shapes.ISOSCELES_TRIANGLE, { x: W / 2 - 0.2, y: 3.92, w: 0.5, h: 0.56, rotate: 90, fill: { color: C.bg }, line: { color: C.bg } });
  T(s, "MP4 삽입 영역 · 약 45초", { x: 1.4, y: 5.05, w: W - 2.8, h: 0.4, fontSize: 16, bold: true, color: C.white, align: "center" });
}

// ================================================================ ACT 4 — 810 runs
{
  const s = slide("실험 설계", "이게 한 번의 우연이 아닌지 확인하려고 반복 실험을 했습니다. 교란 조건 3가지, 재계획 구성 9가지, 각 30번, 810번입니다. 정상 조건은 표준시간에 로그정규 잡음, 시그마 0.15를 곱했고, 작업정지는 작업시간을 240분 늘리는 모델입니다. 같은 seed는 모든 구성에 같은 실제 작업시간을 줬습니다.");
  head(s, "같은 출발점, 다른 결정", "시작: 10/22 13:00 데모 상태, 기준계획 접수순 · 공통 난수 · 평균 ± 95% 신뢰구간");
  const eq = [["3", "교란 조건", C.white], ["×", "", C.dim], ["9", "재계획 구성", C.white], ["×", "", C.dim], ["30", "seed", C.white], ["=", "", C.dim], ["810", "폐루프 실행", C.late]];
  let ex = M + 0.4;
  eq.forEach((e) => {
    const w = e[1] ? 2.0 : 0.7;
    T(s, e[0], { ...(e[0] === "810" ? N("n810") : {}), x: ex, y: 2.2, w, h: 1.2, fontSize: e[1] ? 66 : 40, bold: true, align: "center", valign: "middle", color: e[2], fontFace: MONO });
    if (e[1]) T(s, e[1], { x: ex, y: 3.45, w, h: 0.3, fontSize: 12, align: "center", color: C.muted });
    ex += w + 0.08;
  });
  [["정상", "표준시간 × 로그정규 잡음 σ=0.15\n(±15% 한계가 아님) · 추정 오차 σ=0.2", C.blue],
   ["작업시간 +20%", "모든 작업이 평균 1.2배", C.ot],
   ["작업정지·재작업", "작업 시도 3%에 +240분 (작업시간 연장 모델,\nHOLD 이벤트 아님) · 최종시험 8% 불합격", C.late]].forEach((c, i) => {
    const x = M + i * 4.1, y = 4.35, w = 3.9;
    R(s, null, x, y, w, 1.9, C.panel, { round: true, line: C.line });
    R(s, null, x, y, w, 0.06, c[2]);
    T(s, c[0], { x: x + 0.22, y: y + 0.22, w: w - 0.4, h: 0.35, fontSize: 15, bold: true, color: c[2] });
    T(s, c[1], { x: x + 0.22, y: y + 0.7, w: w - 0.4, h: 1.1, fontSize: 11.5, color: C.text, lineSpacingMultiple: 1.25 });
  });
  T(s, "재계획 구성 9: 계획 유지(KEEP) · FCFS · EDD · Slack · CR × 추가근무 끔/켬", { x: M, y: 6.45, w: 12, h: 0.3, fontSize: 11.5, color: C.muted });
}
// dots: order runs by (cond, cfg, seed)
const ORDERED = [];
CONDS.forEach((c) => CFGS.forEach((k) => RUNS.filter((r) => r.cond === c && r.cfg === k).sort((a, b) => a.seed - b.seed).forEach((r) => ORDERED.push(r))));
const WF = { gx: M + 1.8, top: 2.3, ds: 0.15, cellH: 1.3 };
WF.cellW = (W - M - WF.gx) / 9;
const wafflePos = (idx) => {
  const ci = Math.floor(idx / 270), k = Math.floor((idx % 270) / 30), n = idx % 30;
  return [WF.gx + k * WF.cellW + (n % 6) * WF.ds, WF.top + ci * WF.cellH + Math.floor(n / 6) * WF.ds];
};
// 15 all grey block
{
  const s = slide("810번, 한 점이 한 번", "810번의 실행을 점 하나씩으로 놓겠습니다.");
  head(s, "810번의 실행", "점 하나 = 폐루프 실행 1회");
  const cols = 54, ds = 0.17, x0 = (W - cols * ds) / 2, y0 = 2.6;
  ORDERED.forEach((r, i) => {
    s.addShape(pres.shapes.RECTANGLE, { objectName: "!!d" + i, x: x0 + (i % cols) * ds, y: y0 + Math.floor(i / cols) * ds, w: ds - 0.04, h: ds - 0.04, fill: { color: C.grey }, line: { color: C.grey, width: 0 } });
  });
  T(s, "810", { ...N("n810"), x: W / 2 - 2, y: 5.4, w: 4, h: 1.0, fontSize: 54, bold: true, color: C.white, align: "center", fontFace: MONO });
}
// 16 waffle
{
  const s = slide("810번, 한 점이 한 번", "조건과 방법별로 나누면 이렇습니다. 주황은 출하검사 진입 지연이 남은 실행입니다. 계획을 유지하면 세 조건 모두 30번 전부 늦고, EDD는 정상과 작업시간 증가에서 0번, 작업정지·재작업에서 5번 늦었습니다.");
  head(s, "어디서 늦었나", "주황 = 출하검사 진입 지연이 남은 실행 · 초록 = 지연 0 · 같은 위치 = 같은 seed");
  CFGS.forEach((k, j) => {
    const ot = k.endsWith("+OT");
    T(s, ot ? "+OT" : k, { x: WF.gx + j * WF.cellW, y: WF.top - 0.4, w: 6 * WF.ds, h: 0.3, fontSize: ot ? 10 : 11, bold: true, color: ot ? C.ot : C.white, align: "center" });
  });
  CONDS.forEach((c, i) => {
    T(s, CL[c], { x: M, y: WF.top + i * WF.cellH + 0.25, w: 1.7, h: 0.5, fontSize: 12, bold: true, color: C.text, valign: "middle" });
    CFGS.forEach((k, j) => {
      const late = lateCount(c, k);
      T(s, `${late}/30`, { x: WF.gx + j * WF.cellW, y: WF.top + i * WF.cellH + 5 * WF.ds + 0.06, w: 6 * WF.ds, h: 0.22, fontSize: 9, color: late ? C.late : C.ok, align: "center", fontFace: MONO });
    });
  });
  ORDERED.forEach((r, i) => {
    const [x, y] = wafflePos(i), col = r.delay > 0 ? C.late : C.ok;
    s.addShape(pres.shapes.RECTANGLE, { objectName: "!!d" + i, x, y, w: WF.ds - 0.03, h: WF.ds - 0.03, fill: { color: col }, line: { color: col, width: 0 } });
  });
  T(s, "810", { ...N("n810"), x: W - M - 1.6, y: 6.25, w: 1.6, h: 0.5, fontSize: 22, bold: true, color: C.dim, align: "right", fontFace: MONO });
  T(s, "계획 유지 30/30 지연 · EDD 0 · 0 · 5/30 · FCFS ≈ 계획 유지 · +OT는 남은 지연을 더 줄인다", { x: M, y: 6.35, w: 10.5, h: 0.35, fontSize: 12, bold: true, color: C.text });
}
// 17 numbers
{
  const s = slide("결과 ① 지연의 크기", `평균으로는 계획 유지 ${fmt(m("NORMAL", "KEEP"))}, ${fmt(m("SLOW", "KEEP"))}, ${fmt(m("STOPPAGE_REWORK", "KEEP"))}분이 EDD로 0, 0, ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분이 됐습니다. 작업정지 조건에서 5번 지연이 남았으니, 없앴다가 아니라 크게 줄였다고 말씀드립니다.`);
  head(s, "재계획은 출하검사 진입 지연을 크게 줄였다", "평균, n=30 · 지연 = LOT별 max(0, 생산 완료 − 출하검사 예정 시작)의 합");
  CONDS.forEach((c, i) => {
    const y = 2.25 + i * 1.45;
    R(s, null, M, y, W - 2 * M, 1.25, C.panel, { round: true, line: C.line });
    T(s, CL[c], { x: M + 0.3, y, w: 2.6, h: 1.25, fontSize: 17, bold: true, color: C.text, valign: "middle" });
    T(s, fmt(m(c, "KEEP")), { x: M + 3.0, y, w: 3.1, h: 1.25, fontSize: 46, bold: true, color: C.late, valign: "middle", align: "right", fontFace: MONO });
    T(s, "→", { x: M + 6.25, y, w: 0.8, h: 1.25, fontSize: 34, color: C.dim, valign: "middle", align: "center" });
    const e = m(c, "EDD");
    T(s, e < 0.05 ? "0" : fmt(e, 1), { x: M + 7.1, y, w: 2.6, h: 1.25, fontSize: 46, bold: true, color: C.ok, valign: "middle", fontFace: MONO });
    T(s, `분 · EDD 지연 ${lateCount(c, "EDD")}/30회`, { x: M + 9.6, y, w: 2.5, h: 1.25, fontSize: 13, color: C.muted, valign: "middle" });
  });
  T(s, "왼쪽 = 계획 유지 · 오른쪽 = EDD 재계획 · 원자료 experiments/main30/summary.csv", { x: M, y: 6.6, w: 12, h: 0.3, fontSize: 10.5, color: C.dim });
}

// ================================================================ ACT 5 — why, cost, limits
const GT0 = Date.parse("2026-10-22T09:00"), GT1 = Date.parse("2026-10-29T00:00");
const GX = M + 2.0, GW = W - M - GX - 0.1;
const GXf = (iso) => GX + (GW * (Date.parse(iso) - GT0)) / (GT1 - GT0);
const PROCS = ["튜닝", "마무리 조립", "최종 성능시험"];
const PCOL = { "튜닝": C.late, "마무리 조립": C.blue, "최종 성능시험": C.ok };
function ganttSlide(layer, notes) {
  const s = slide("결과 ② 무엇이 바뀌었나", notes);
  const keep = layer === "현재 Forecast";
  head(s, keep ? "계획을 유지하면 LOT-003이 Gate를 넘는다" : "EDD는 LOT-003을 앞당긴다", keep ? "실험 시작 시점(10/22 13:00)의 계획 유지 Forecast" : "같은 시점의 EDD 재계획안 · 바뀐 것은 병목 장비를 쓰는 순서뿐");
  const lots = ["LOT-003", "LOT-002", "LOT-001"], top = 2.25, laneH = 1.3;
  for (let d = 22; d <= 28; d++) {
    if (d > 22) L(s, null, GXf(`2026-10-${d}T00:00`), top - 0.1, 0, laneH * 3 + 0.1, C.line, { w: 0.75 });
    T(s, `10/${d}`, { x: GXf(`2026-10-${d}T12:00`) - 0.4, y: top + laneH * 3 + 0.1, w: 0.8, h: 0.25, fontSize: 10, color: C.muted, align: "center", fontFace: MONO });
  }
  lots.forEach((lot, i) => {
    const y0 = top + i * laneH;
    R(s, null, M, y0, W - 2 * M, laneH - 0.12, i % 2 ? C.bg : C.panel);
    T(s, lot, { x: M + 0.15, y: y0 + 0.15, w: 1.6, h: 0.35, fontSize: 16, bold: true, color: C.white });
    const gate = GANTT.markers.find((g) => g.lot_label === lot);
    T(s, `출하검사 ${gate.at.slice(5, 10).replace("-", "/")} ${gate.at.slice(11)}`, { x: M + 0.15, y: y0 + 0.55, w: 1.8, h: 0.25, fontSize: 9.5, color: C.muted });
    PROCS.forEach((p, k) => {
      const b = GANTT.bars.find((x) => x.lot_label === lot && x.layer === layer && x.process_label === p);
      if (!b) return;
      const xa = GXf(b.start), xb = Math.max(GXf(b.end), xa + 0.05);
      R(s, `g_${lot}_${k}`, xa, y0 + 0.15 + k * 0.3, Math.min(xb, GX + GW) - xa, 0.22, PCOL[p], { round: true, r: 0.04 });
    });
    if (Date.parse(gate.at) < GT1) L(s, "gate" + i, GXf(gate.at), y0 + 0.02, 0, laneH - 0.16, C.white, { w: 2.25 });
    else T(s, "Gate 11/06 → 그림 밖", { x: GX + GW - 2.2, y: y0 + 0.05, w: 2.2, h: 0.22, fontSize: 9.5, color: C.muted, align: "right" });
  });
  const tb = GANTT.bars.find((x) => x.lot_label === "LOT-003" && x.layer === layer && x.process_label === "최종 성능시험");
  const label = `LOT-003 최종시험 ${tb.end.slice(5, 10).replace("-", "/")} ${tb.end.slice(11)} 완료${keep ? " → Gate 10/28 09:00 초과" : " · Gate 안쪽"}`;
  T(s, label, { ...N("g_label"), x: keep ? GXf(tb.end) - 5.2 : GXf(tb.end) + 0.15, y: top - 0.42, w: 5.0, h: 0.3, fontSize: 12, bold: true, color: keep ? C.late : C.ok, align: keep ? "right" : "left" });
  PROCS.forEach((p, k) => { R(s, null, M + k * 2.0, 6.55, 0.3, 0.14, PCOL[p]); T(s, p, { x: M + 0.4 + k * 2.0, y: 6.48, w: 1.5, h: 0.28, fontSize: 10.5, color: C.muted }); });
  T(s, "흰 선 = 출하검사 예정 · 막대 = LOT×공정의 첫 작업 시작 ~ 마지막 작업 종료", { x: M + 6.2, y: 6.48, w: 6.0, h: 0.28, fontSize: 10.5, color: C.muted, align: "right" });
}
ganttSlide("현재 Forecast", "왜 줄었는지 일정으로 보겠습니다. 계획을 유지하면 LOT-003의 최종 시험이 10월 28일 12시 15분에 끝나 출하검사 시작 9시를 넘습니다.");
ganttSlide("재계획안", "EDD는 LOT-003을 앞당겨 10월 23일에 끝내고, 여유가 많은 LOT-002를 뒤로 보냅니다. 바뀐 것은 병목 장비를 쓰는 순서뿐입니다. 일부러 만든 충돌이라 EDD가 어디서나 최선이라는 뜻은 아닙니다.");

// overtime dumbbells (two steps)
const OTC = [["STOPPAGE_REWORK", "CR"], ["STOPPAGE_REWORK", "EDD"], ["SLOW", "CR"], ["NORMAL", "FCFS"], ["NORMAL", "CR"], ["NORMAL", "EDD"]];
function otSlide(on, notes) {
  const s = slide("결과 ③ 추가근무", notes);
  head(s, on ? "남은 지연엔 약, 없는 지연엔 비용" : "추가근무를 끈 상태", on ? "추가근무를 켰을 때 평균 지연(●)과 평균 추가 가동시간 (n=30)" : "규칙별 평균 출하검사 진입 지연 (n=30)");
  const lx = M + 2.8, lw = 5.4, max = 220, ox = lx + lw + 1.1, ow = W - M - ox - 0.75, omax = 400;
  T(s, "출하검사 진입 지연 (분)", { x: lx, y: 1.95, w: lw, h: 0.28, fontSize: 11, bold: true, color: C.muted });
  if (on) T(s, "추가 가동시간 (분)", { x: ox, y: 1.95, w: 3, h: 0.28, fontSize: 11, bold: true, color: C.ot });
  [0, 100, 200].forEach((v) => { const x = lx + (lw * v) / max; L(s, null, x, 2.3, 0, 3.85, C.line, { w: 0.75 }); T(s, String(v), { x: x - 0.3, y: 6.18, w: 0.6, h: 0.22, fontSize: 9.5, color: C.dim, align: "center", fontFace: MONO }); });
  OTC.forEach(([c, p], i) => {
    const y = 2.6 + i * 0.6, a = m(c, p), b = m(c, p + "+OT"), ot = m(c, p + "+OT", "overtime_minutes"), waste = a < 0.05;
    T(s, `${CL[c]} · ${p}`, { x: M, y: y - 0.16, w: 2.7, h: 0.32, fontSize: 12, bold: true, color: on && waste ? C.ot : C.white, valign: "middle" });
    const xa = lx + (lw * a) / max, xb = lx + (lw * (on ? b : a)) / max;
    s.addShape(pres.shapes.OVAL, { x: xa - 0.11, y: y - 0.11, w: 0.22, h: 0.22, fill: { color: C.bg }, line: { color: C.muted, width: 1.5 } });
    O(s, "otd" + i, xb, y, 0.22, on ? (waste ? C.ot : C.ok) : C.muted);
    T(s, on ? (waste ? "0 → 0" : `${fmt(a)} → ${fmt(b)}`) : fmt(a), { ...N("otv" + i), x: Math.max(xa, xb) + 0.2, y: y - 0.15, w: 1.4, h: 0.3, fontSize: 11, color: C.text, valign: "middle", fontFace: MONO });
    R(s, "otb" + i, ox, y - 0.13, on ? (ow * ot) / omax : 0.01, 0.26, C.ot, on ? { tr: !waste ? 40 : 0 } : { tr: 100, ltr: 100 });
    if (on) T(s, fmt(ot), { x: ox + (ow * ot) / omax + 0.08, y: y - 0.15, w: 0.7, h: 0.3, fontSize: 11, bold: true, color: C.ot, valign: "middle", fontFace: MONO });
  });
  if (on) {
    R(s, null, M, 6.42, W - 2 * M, 0.5, "2B2410", { round: true, line: C.ot });
    T(s, `정상·EDD: 지연 개선 없이 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분 추가 가동 (30회 중 27회 사용). 원인은 결정 시점 Forecast의 비관적 예측으로 추정 → 한계로 보고`, { x: M + 0.25, y: 6.42, w: W - 2 * M - 0.5, h: 0.5, fontSize: 11.5, color: C.text, valign: "middle" });
  }
}
otSlide(false, "추가근무를 끈 상태의 평균 지연입니다.");
otSlide(true, `켜면 지연이 남던 규칙은 줄어듭니다. 작업정지 CR은 ${fmt(m("STOPPAGE_REWORK", "CR"))}에서 ${fmt(m("STOPPAGE_REWORK", "CR+OT"))}분, 정상 FCFS는 ${fmt(m("NORMAL", "FCFS"))}에서 ${fmt(m("NORMAL", "FCFS+OT"))}분입니다. 하지만 정상 EDD는 이미 0인데 평균 108분을 열었습니다. 원인은 결정 시점 예측이 비관적이었던 것으로 추정하며, 한계로 보고합니다.`);

// two metrics
{
  const s = slide("두 지표", "지표는 두 가지입니다. 출하검사 진입 지연이 이번 KPI이고, 최종 납기 지각은 출하검사가 3근무일에 끝난다는 가정하에서 810번 모두 0이었습니다.");
  head(s, "지켜야 할 선은 두 개, 이번에 걸린 건 하나", "생산이 지켜야 하는 선(출하검사 시작)과 고객이 받는 선(납기)은 다르다");
  const y = 2.8, x0 = M + 0.5, x1 = W - M - 0.5, bx = (f) => x0 + (x1 - x0) * f;
  L(s, null, x0, y, x1 - x0, 0, C.line, { w: 3 });
  R(s, null, bx(0.03), y - 0.08, bx(0.32) - bx(0.03), 0.16, C.late, { tr: 40 });
  R(s, null, bx(0.7), y - 0.08, bx(0.97) - bx(0.7), 0.16, C.blue, { tr: 40 });
  [[0.03, "생산 완료", "마지막 최종시험 합격", C.white], [0.32, "출하검사 시작", "Gate 예정 시각", C.late], [0.7, "출하", "시작일 포함 3근무일 17:00 (가정)", C.white], [0.97, "고객 납기", "Lot.due_at", C.blue]].forEach((mk) => {
    O(s, null, bx(mk[0]), y, 0.26, mk[3]);
    T(s, mk[1], { x: bx(mk[0]) - 1.3, y: y - 0.7, w: 2.6, h: 0.35, fontSize: 14, bold: true, align: "center", color: mk[3] });
    T(s, mk[2], { x: bx(mk[0]) - 1.6, y: y + 0.25, w: 3.2, h: 0.28, fontSize: 10, align: "center", color: C.muted });
  });
  [["출하검사 진입 지연", "재계획 KPI", C.late, `LOT별 max(0, 생산 완료 − 출하검사 예정 시작)의 합\n중간발표 ‘4h 57m’도 이 지표\n계획 유지 ${fmt(m("NORMAL", "KEEP"))}~${fmt(m("STOPPAGE_REWORK", "KEEP"))}분 → EDD 0~${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분`],
   ["최종 납기 지각", "고객 기준", C.blue, "LOT별 max(0, 출하 − 고객 납기)의 합\n출하검사 3근무일 가정하에서 810회 모두 0\n가장 빠듯한 경우 납기 당일 17:00 출하"]].forEach((c, i) => {
    const x = M + i * 6.15, w = 5.95, yy = 3.75;
    R(s, null, x, yy, w, 2.9, C.panel, { round: true, line: C.line });
    R(s, null, x, yy, 0.07, 2.9, c[2]);
    T(s, c[0], { x: x + 0.3, y: yy + 0.22, w: w - 2, h: 0.4, fontSize: 17, bold: true, color: c[2] });
    T(s, c[1], { x: x + w - 1.8, y: yy + 0.27, w: 1.5, h: 0.3, fontSize: 10.5, bold: true, color: c[2], align: "right" });
    T(s, c[3], { x: x + 0.3, y: yy + 0.85, w: w - 0.55, h: 1.9, fontSize: 13, color: C.text, lineSpacingMultiple: 1.45 });
  });
}
// verification
{
  const s = slide("검증", "자동 테스트 384개가 통과하고 공장 규칙 위반은 0건입니다. 실험은 버그도 찾았습니다. 17시 정각 재계획 버그로 3번 실패했고, 고친 뒤 다시 돌려 모두 성공했습니다.");
  head(s, "실험은 버그를 찾는 도구이기도 했다", "고친 문제는 회귀 테스트로 고정했다 · 실패 기록은 지우지 않았다");
  [["384", "자동 테스트", "Python 3.11 · 3.13 CI"], ["810", "폐루프 실행", "27개 조합 × 30회"], ["0", "공장 규칙 위반", "중복·용량·선후·근무시간"], ["0", "최종 실패", "첫 실행 3회 실패 → 수정"]].forEach((v, i) => {
    const x = M + i * 3.07;
    R(s, null, x, 2.05, 2.9, 1.7, C.panel, { round: true, line: C.line });
    T(s, v[0], { ...(v[0] === "810" ? N("n810") : {}), x: x + 0.25, y: 2.15, w: 2.5, h: 0.85, fontSize: 44, bold: true, color: i < 2 ? C.white : C.ok, fontFace: MONO });
    T(s, v[1], { x: x + 0.25, y: 3.0, w: 2.5, h: 0.3, fontSize: 13, bold: true, color: C.text });
    T(s, v[2], { x: x + 0.25, y: 3.32, w: 2.5, h: 0.28, fontSize: 10, color: C.muted });
  });
  [["17:00 정각 재계획 실패 (810회 중 3회)", "진행 중 작업이 결정 시각에 바로 이어진다고 가정", "다음 근무 시작에 재개 → 재실행 성공"],
   ["재작업으로 다시 열린 공정 누락", "승인 계획에 없는 공정을 후보가 찾지 못함", "부모 계획 뒤 순위로 배치"],
   ["실험·대시보드 출하검사 기준 불일치", "실험만 '완료 후 24근무시간' 가정", "한 모듈로 통일, 기록 재계산"]].forEach((b, i) => {
    const x = M + i * 4.1, w = 3.9, y = 4.2;
    R(s, null, x, y, w, 2.5, C.panel, { round: true, line: C.line });
    T(s, b[0], { x: x + 0.22, y: y + 0.18, w: w - 0.4, h: 0.6, fontSize: 13, bold: true, color: C.late });
    T(s, "원인  " + b[1], { x: x + 0.22, y: y + 0.9, w: w - 0.4, h: 0.65, fontSize: 11.5, color: C.text });
    T(s, "해결  " + b[2], { x: x + 0.22, y: y + 1.65, w: w - 0.4, h: 0.65, fontSize: 11.5, color: C.ok });
  });
}
// limits
{
  const s = slide("한계", "증명하지 않은 것도 분명히 말씀드립니다. Pico 단말과 Wi-Fi 통신, 실제 공장 데이터, 출하검사 자체, 그리고 EDD의 일반적인 우월성입니다.");
  head(s, "증명한 것과 증명하지 않은 것", "결론을 읽을 때 함께 봐야 하는 범위");
  [["증명한 것 (실행·테스트 근거)", C.ok, "✓", ["승인한 계획이 작업지시로 내려가 현장 순서를 바꾼다", "실제 시간 = 표준시간이면 현장 결과가 Forecast와 일치", "추가근무 승인이 달력·Forecast·현장에 함께 반영", "810회: 이 충돌 상황에서 재계획이 진입 지연을 크게 줄임", "정상 조건 EDD+OT에서 지연 개선 없이 평균 108분 추가 가동 발생"]],
   ["증명하지 않은 것", C.late, "✕", ["Pico 2 WH 단말 연동 (TCP는 localhost만, Wi-Fi 아님)", "실제 공장 데이터 (작업시간 분포·교란 확률은 가정값)", "작업정지 = 작업시간 240분 연장 모델 (HOLD 이벤트 아님)", "출하검사 자체의 대기·불합격 (3근무일 가정)", "EDD가 일반 현장에서 최선이라는 것 (의도적 충돌 상황)"]]].forEach((c, i) => {
    const x = M + i * 6.15, w = 5.95, y = 2.0;
    R(s, null, x, y, w, 4.8, C.panel, { round: true, line: C.line });
    T(s, c[0], { x: x + 0.3, y: y + 0.22, w: w - 0.6, h: 0.4, fontSize: 16, bold: true, color: c[1] });
    c[3].forEach((b, k) => {
      const yy = y + 0.85 + k * 0.77;
      T(s, c[2], { x: x + 0.3, y: yy, w: 0.35, h: 0.4, fontSize: 15, bold: true, color: c[1] });
      T(s, b, { x: x + 0.7, y: yy + 0.02, w: w - 1.0, h: 0.65, fontSize: 12.5, color: C.text });
    });
  });
}
// close
{
  const s = slide(null, "정리하면, 실적이 다음 작업지시를 바꾸는 폐루프를 실행으로 확인했고, 810번의 실험에서 재계획이 출하검사 진입 지연을 크게 줄였습니다. 앞으로는 Pico 연동과 예측 보정을 해 보고 싶습니다. 감사합니다.");
  T(s, "실적을 보여주는 대시보드가 아니라,", { x: M, y: 1.5, w: 12, h: 0.7, fontSize: 30, bold: true, color: C.muted });
  T(s, "실적이 다음 작업지시를\n바꾸는 시스템", { ...N("head"), x: M, y: 2.2, w: 12, h: 2.0, fontSize: 50, bold: true, color: C.white, lineSpacingMultiple: 1.05 });
  R(s, "scan", M, 4.5, W - 2 * M, 0.04, C.late);
  [["4h 57m", "중간발표의 벽에서 출발", C.late], [`${fmt(m("STOPPAGE_REWORK", "KEEP"))} → ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}`, "작업정지 조건 평균 진입 지연(분)", C.ok], ["108분", "지연 0인데 연 추가근무 → 예측 보정이 다음 과제", C.ot]].forEach((v, i) => {
    const x = M + i * 4.1;
    T(s, v[0], { ...(i === 0 ? N("big") : {}), x, y: 4.8, w: 3.9, h: 0.75, fontSize: 32, bold: true, color: v[2], fontFace: MONO });
    T(s, v[1], { x, y: 5.6, w: 3.8, h: 0.5, fontSize: 12, color: C.muted });
  });
  T(s, "감사합니다", { x: M, y: 6.45, w: 4, h: 0.45, fontSize: 18, bold: true, color: C.late });
}

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT, page, "slides"));
