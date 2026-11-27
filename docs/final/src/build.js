// 기말발표 PPT: 중간발표 v5의 디자인(흰 배경, 네이비·블루, 섹션 라벨, 번호 제목)을 이어간다.
const pptxgen = require("pptxgenjs");
const path = require("path");
const script = require("./script.js");

const OUT = process.argv[2] || "deck.pptx";
const IMG = (f) => path.join(__dirname, f);

const FONT = "Noto Sans CJK KR";
const C = {
  navy: "0E2C48", ink: "14213D", blue: "2F7DBD", gray: "596B7A", light: "8D9AA6",
  line: "C7D3DE", bg: "F5F8FB", tint: "E8F3FB", red: "C53A32", redT: "FCECEA",
  green: "2E8B57", greenT: "E5F4EA", amber: "B87511", amberT: "FFF0D6", white: "FFFFFF",
  gold: "FFD166",
};
const W = 13.333, H = 7.5, M = 0.55;

const pres = new pptxgen();
pres.layout = "LAYOUT_WIDE";
pres.author = "박상현";
pres.title = "공학프로젝트4 기말발표 — 생산진도 관리 및 동적 재계획 시스템";
pres.theme = { headFontFace: FONT, bodyFontFace: FONT };

const notes = Object.fromEntries(script.map((s) => [s.n, s.say]));
let page = 0;

function t(slide, text, o) {
  slide.addText(text, { fontFace: FONT, isTextBox: true, margin: 0, valign: "top", color: C.ink, ...o });
}
function box(slide, x, y, w, h, fill, line) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, {
    x, y, w, h, rectRadius: 0.08, fill: { color: fill }, line: { color: line || fill, width: 0.75 },
  });
}
function pill(slide, x, y, w, text, fill, color) {
  slide.addShape(pres.shapes.ROUNDED_RECTANGLE, { x, y, w, h: 0.3, rectRadius: 0.15, fill: { color: fill }, line: { color: fill } });
  t(slide, text, { x, y: y + 0.02, w, h: 0.26, fontSize: 10.5, bold: true, color, align: "center", valign: "middle" });
}
function arrow(slide, x, y, w) {
  slide.addShape(pres.shapes.RIGHT_ARROW, { x, y, w, h: 0.26, fill: { color: C.navy }, line: { color: C.navy } });
}
function num(slide, x, y, n, fill) {
  slide.addShape(pres.shapes.OVAL, { x, y, w: 0.34, h: 0.34, fill: { color: fill || C.blue }, line: { color: fill || C.blue } });
  t(slide, String(n), { x, y: y + 0.02, w: 0.34, h: 0.3, fontSize: 12, bold: true, color: C.white, align: "center", valign: "middle" });
}
function content(section, title, subtitle, n) {
  page += 1;
  const s = pres.addSlide();
  s.background = { color: C.white };
  t(s, `${section}   ·   생산진도 관리 및 동적 재계획 시스템`, { x: M, y: 0.28, w: 9, h: 0.25, fontSize: 9.5, bold: true, color: C.blue });
  t(s, title, { x: M, y: 0.55, w: W - 2 * M, h: 0.6, fontSize: 25, bold: true, color: C.ink, valign: "middle" });
  if (subtitle) t(s, subtitle, { x: M, y: 1.17, w: W - 2 * M, h: 0.35, fontSize: 13, color: C.gray });
  t(s, "공프4 기말발표", { x: M, y: H - 0.38, w: 3, h: 0.22, fontSize: 9, color: C.light });
  t(s, String(page), { x: W - M - 1, y: H - 0.38, w: 1, h: 0.22, fontSize: 9, color: C.light, align: "right" });
  if (notes[n]) s.addNotes(notes[n]);
  return s;
}
function card(s, x, y, w, h, head, body, o = {}) {
  box(s, x, y, w, h, o.fill || C.bg, o.line || C.line);
  t(s, head, { x: x + 0.2, y: y + 0.15, w: w - 0.4, h: 0.32, fontSize: o.headSize || 14, bold: true, color: o.headColor || C.navy });
  if (body) t(s, body, { x: x + 0.2, y: y + 0.52, w: w - 0.4, h: h - 0.62, fontSize: o.bodySize || 12, color: o.bodyColor || C.ink, lineSpacingMultiple: 1.15 });
}
function img(s, file, x, y, w, ratio, frame = true) {
  const h = w / ratio;
  if (frame) box(s, x - 0.06, y - 0.06, w + 0.12, h + 0.12, C.white, C.line);
  s.addImage({ path: IMG(file), x, y, w, h });
  return h;
}
function dark(s, x, y, w, h, runs, size = 16) {
  box(s, x, y, w, h, C.navy);
  s.addText(runs, { x: x + 0.3, y, w: w - 0.6, h, fontFace: FONT, fontSize: size, color: C.white, align: "center", valign: "middle", isTextBox: true, margin: 0 });
}

// ---------------------------------------------------------------- 1 표지
{
  page += 1;
  const s = pres.addSlide();
  s.background = { color: C.white };
  pill(s, M, 0.9, 2.5, "공학프로젝트4 기말발표", C.tint, C.blue);
  t(s, "현장 작업실적 기반", { x: M, y: 1.55, w: 6.2, h: 0.45, fontSize: 18, color: C.gray });
  t(s, "생산진도 관리 및\n동적 재계획 시스템", { x: M, y: 2.05, w: 6.4, h: 1.6, fontSize: 36, bold: true, color: C.ink, lineSpacingMultiple: 1.05 });
  t(s, "현장 실적 → Forecast → 납기 위험 판단 → 재계획 승인 → 작업지시", { x: M, y: 3.85, w: 6.4, h: 0.35, fontSize: 14, bold: true, color: C.ink });
  t(s, "FastAPI · SQLite · Streamlit · 가상 현장 시뮬레이터   |   Pico 2 WH 단말: 미연동", { x: M, y: 4.25, w: 6.4, h: 0.3, fontSize: 11, color: C.gray });
  t(s, "12233707  박상현   메카트로닉스공학과", { x: M, y: 6.55, w: 6, h: 0.3, fontSize: 13, bold: true, color: C.ink });
  img(s, "f_ranking.png", 7.2, 1.25, 5.6, 2480 / 636);
  img(s, "g_replan_gantt.png", 7.2, 3.15, 5.6, 2480 / 614);
  t(s, "실제 시스템 화면: 추가근무를 포함한 재계획 후보 순위와 간트차트", { x: 7.2, y: 4.72, w: 5.6, h: 0.3, fontSize: 10, color: C.light });
  s.addNotes(notes[1]);
}

// ---------------------------------------------------------------- 2 중간 이후
{
  const s = content("INTRODUCTION", "1. 중간발표 이후 — 남았던 질문", "중간발표는 화면에서 흐름을 보였다. 기말은 그 흐름이 실제로 작동하는지를 실행 결과로 확인했다.", 2);
  box(s, M, 1.75, 4.1, 4.95, C.navy);
  t(s, "중간발표의 결론", { x: M + 0.25, y: 1.95, w: 3.6, h: 0.3, fontSize: 13, bold: true, color: C.gold });
  t(s, "“재계획의 효과는 지연 단축이 아니라\n추가 피해 차단이다”", { x: M + 0.25, y: 2.35, w: 3.6, h: 0.9, fontSize: 15, bold: true, color: C.white });
  t(s, "근거는 시나리오 1개.\nLOT-001 4시간 57분 지연은 어떤 순서로도 줄지 않았다.\n\n남은 과제로 적은 것\n· Pico 2 WH 단말 연동\n· 추가근무 대안\n· 한 시나리오 밖에서의 검증", { x: M + 0.25, y: 3.4, w: 3.6, h: 3.1, fontSize: 12.5, color: "D6E2EE", lineSpacingMultiple: 1.2 });
  const rows = [
    ["승인한 계획이 실제 현장 순서를 바꾸나?", "가상 현장 폐루프 + 작업지시 API", "확인", C.greenT, C.green],
    ["시나리오 하나를 넘어서도 효과가 있나?", "3조건 × 9구성 × 30회 = 810회 실행", "확인", C.greenT, C.green],
    ["추가근무는 어떻게 다루나?", "평일 17~19시 후보 생성·승인·실행", "구현", C.greenT, C.green],
    ["Pico 단말로 입력할 수 있나?", "미연동. 같은 HTTP API를 가상 단말로 검증", "미연동", C.redT, C.red],
  ];
  const x0 = M + 4.4, w0 = W - M - x0;
  t(s, "남은 질문", { x: x0, y: 1.75, w: 3.5, h: 0.3, fontSize: 12, bold: true, color: C.gray });
  t(s, "기말에서 한 것", { x: x0 + 3.75, y: 1.75, w: 3.5, h: 0.3, fontSize: 12, bold: true, color: C.gray });
  rows.forEach((r, i) => {
    const y = 2.15 + i * 1.13;
    box(s, x0, y, w0, 0.98, C.bg, C.line);
    t(s, r[0], { x: x0 + 0.2, y: y + 0.12, w: 3.4, h: 0.75, fontSize: 13.5, bold: true, color: C.ink, valign: "middle" });
    t(s, r[1], { x: x0 + 3.75, y: y + 0.12, w: 3.0, h: 0.75, fontSize: 12.5, color: C.ink, valign: "middle" });
    pill(s, x0 + w0 - 1.15, y + 0.34, 0.95, r[2], r[3], r[4]);
  });
}

// ---------------------------------------------------------------- 3 시스템 구성
{
  const s = content("METHOD", "2. 시스템 구성 — 승인이 현장으로 돌아가는 폐루프", "실적이 들어와 계산되고, 승인된 계획이 다시 현장 작업지시로 내려간다.", 3);
  const steps = [
    ["현장", "가상 현장 시뮬레이터\n(화면 입력도 가능)"],
    ["FastAPI", "실적 수신·검증\n중복 이벤트 무시"],
    ["SQLite", "실적·계획 버전\n근무달력"],
    ["계산 로직", "Forecast · 위험도\n재계획 후보"],
    ["관리자 승인", "Streamlit 화면\n후보 비교 → 승인"],
  ];
  const bw = 2.05, gap = 0.42, y = 2.0;
  steps.forEach((st, i) => {
    const x = M + i * (bw + gap);
    const hl = i === 3;
    box(s, x, y, bw, 1.45, hl ? C.navy : C.bg, hl ? C.navy : C.line);
    t(s, st[0], { x: x + 0.1, y: y + 0.18, w: bw - 0.2, h: 0.35, fontSize: 15, bold: true, align: "center", color: hl ? C.white : C.navy });
    t(s, st[1], { x: x + 0.1, y: y + 0.6, w: bw - 0.2, h: 0.75, fontSize: 11.5, align: "center", color: hl ? "D6E2EE" : C.gray });
    if (i < steps.length - 1) arrow(s, x + bw + 0.07, y + 0.6, gap - 0.14);
  });
  // return path
  const ry = 3.85, rx0 = M + 1.0, rx1 = M + 4 * (bw + gap) + 1.0;
  s.addShape(pres.shapes.LINE, { x: rx0, y: ry, w: rx1 - rx0, h: 0, line: { color: C.blue, width: 2.5, dashType: "dash", beginArrowType: "triangle" } });
  s.addShape(pres.shapes.LINE, { x: rx1, y: y + 1.45, w: 0, h: ry - y - 1.45, line: { color: C.blue, width: 2.5, dashType: "dash" } });
  s.addShape(pres.shapes.LINE, { x: rx0, y: y + 1.45, w: 0, h: ry - y - 1.45, line: { color: C.blue, width: 2.5, dashType: "dash", beginArrowType: "triangle" } });
  box(s, 4.35, ry - 0.24, 4.6, 0.48, C.white, C.blue);
  t(s, "승인된 계획 → 작업지시 API (/work-orders)  · 기말 추가", { x: 4.35, y: ry - 0.2, w: 4.6, h: 0.4, fontSize: 12, bold: true, color: C.blue, align: "center", valign: "middle" });
  card(s, M, 4.55, 3.9, 2.1, "가상 현장 시뮬레이터 (기말)", "시스템이 모르는 실제 작업시간으로 작업하고, 작업지시 순서대로만 움직인다. 작업자 잔여시간 추정에는 오차를 넣었다.");
  card(s, M + 4.15, 4.55, 3.9, 2.1, "추가근무 (기말, D078)", "평일 17~19시를 여는 후보를 함께 계산하고, 승인하면 근무달력에 저장해 Forecast와 현장이 같은 시간을 쓴다.");
  card(s, M + 8.3, 4.55, 3.93, 2.1, "Pico 2 WH 단말", "미연동. 현장 입력은 같은 HTTP API를 쓰는 가상 단말과 화면 입력으로 검증했다.", { fill: C.redT, line: "F0C5C1", headColor: C.red });
}

// ---------------------------------------------------------------- 4 모의 환경 + Forecast
{
  const s = content("METHOD", "3. 모의 생산환경과 Forecast", "3 LOT × 30대(90 Unit), 5개 내부 공정. 튜닝·시험 장비가 1대씩이라 LOT끼리 순서를 다툰다.", 4);
  const procs = [["테이핑", "10분/대", C.bg], ["일반 조립", "10분/대", C.bg], ["튜닝", "25분/대", C.amberT], ["마무리 조립", "10분/대", C.bg], ["최종 성능시험", "30분/대", C.amberT], ["출하검사", "Gate", C.redT]];
  const pw = 1.83, pg = 0.25;
  procs.forEach((p, i) => {
    const x = M + i * (pw + pg);
    box(s, x, 1.75, pw, 0.95, p[2], C.line);
    t(s, p[0], { x, y: 1.85, w: pw, h: 0.35, fontSize: 14, bold: true, align: "center", color: i === 5 ? C.red : C.navy });
    t(s, p[1], { x, y: 2.22, w: pw, h: 0.3, fontSize: 12, align: "center", color: C.gray });
    if (i < procs.length - 1) arrow(s, x + pw + 0.03, 2.1, pg - 0.06);
  });
  const stats = [["2명", "작업자 (전 공정 공용)"], ["1대", "튜닝장비 — 병목"], ["1대", "시험장비 — 병목"], ["09–17시", "근무 (월~금)"], ["K = 9", "튜닝 9대 후 마무리 착수"]];
  stats.forEach((st, i) => {
    const x = M + i * 2.47;
    t(s, st[0], { x, y: 2.95, w: 2.3, h: 0.45, fontSize: 22, bold: true, color: C.navy });
    t(s, st[1], { x, y: 3.42, w: 2.3, h: 0.3, fontSize: 11, color: C.gray });
  });
  t(s, "Forecast — 실적에서 납기 위험까지", { x: M, y: 4.05, w: 8, h: 0.35, fontSize: 15, bold: true, color: C.blue });
  const fsteps = [
    ["Pace 계산", "완료 Unit의 실적으로 LOT×공정 속도"],
    ["남은 작업량", "속도 × 남은 수량. 지연 작업은 작업자 잔여시간"],
    ["유한용량 배치", "자원·선후·근무시간을 지켜 남은 작업 배치"],
    ["Gate 여유", "출하검사 시작 − 생산 완료 예상. 0 이하 긴급"],
  ];
  fsteps.forEach((f, i) => {
    const x = M + i * 3.07;
    box(s, x, 4.5, 2.9, 1.65, C.bg, C.line);
    num(s, x + 0.2, 4.68, i + 1);
    t(s, f[0], { x: x + 0.65, y: 4.7, w: 2.1, h: 0.32, fontSize: 14, bold: true, color: C.navy });
    t(s, f[1], { x: x + 0.2, y: 5.18, w: 2.55, h: 0.85, fontSize: 12, color: C.ink });
  });
  t(s, "표준시간은 시연과 로직 검증을 위한 모의값이다. 외부 피드 본딩은 LOT 단위 외부 Lead Time으로 처리한다.", { x: M, y: 6.38, w: 12, h: 0.3, fontSize: 10.5, color: C.light });
}

// ---------------------------------------------------------------- 5 재계획 후보 + OT
{
  const s = content("METHOD", "4. 재계획 후보 — 4가지 규칙과 추가근무", "긴급일 때만 후보를 계산하고, 정책을 통과한 안을 같은 기준으로 순위를 매긴 뒤 관리자가 승인한다.", 5);
  // col1 rules
  card(s, M, 1.75, 3.0, 4.2, "", "");
  num(s, M + 0.2, 1.92, 1);
  t(s, "규칙 4가지", { x: M + 0.65, y: 1.93, w: 2.2, h: 0.32, fontSize: 14, bold: true, color: C.navy });
  [["FCFS", "먼저 들어온 LOT 우선"], ["EDD", "납기가 가까운 LOT 우선"], ["Slack", "여유시간이 적은 LOT 우선"], ["CR", "긴급도가 높은 LOT 우선"]].forEach((r, i) => {
    const y = 2.45 + i * 0.82;
    box(s, M + 0.2, y, 2.6, 0.7, C.white, C.line);
    t(s, r[0], { x: M + 0.35, y: y + 0.07, w: 2.3, h: 0.28, fontSize: 13, bold: true, color: C.blue });
    t(s, r[1], { x: M + 0.35, y: y + 0.36, w: 2.3, h: 0.26, fontSize: 11, color: C.gray });
  });
  // col2 overtime
  const x2 = M + 3.25;
  box(s, x2, 1.75, 3.6, 4.2, C.amberT, "EBD3A6");
  num(s, x2 + 0.2, 1.92, 2, C.amber);
  t(s, "+ 추가근무 후보 (기말)", { x: x2 + 0.65, y: 1.93, w: 2.8, h: 0.32, fontSize: 14, bold: true, color: C.amber });
  t(s, [
    { text: "규칙마다 “규칙+OT” 안을 같이 계산", options: { bullet: true, breakLine: true } },
    { text: "평일 17~19시, 늦은 Gate에 도움이 되는 날까지만", options: { bullet: true, breakLine: true } },
    { text: "실제로 쓰지 않는 날은 제외", options: { bullet: true, breakLine: true } },
    { text: "KPI = 추가 가동시간 (17시 ~ 창 안 마지막 작업 종료, 대기 포함)", options: { bullet: true, breakLine: true } },
    { text: "승인 시 근무달력(OVERTIME)에 저장 → Forecast와 현장이 같은 시간 사용", options: { bullet: true } },
  ], { x: x2 + 0.2, y: 2.45, w: 3.25, h: 3.3, fontSize: 12, color: C.ink, paraSpaceAfter: 6 });
  // col3 ranking
  const x3 = x2 + 3.85;
  card(s, x3, 1.75, 2.75, 4.2, "", "");
  num(s, x3 + 0.2, 1.92, 3);
  t(s, "순위 기준 (D029)", { x: x3 + 0.65, y: 1.93, w: 2.0, h: 0.32, fontSize: 14, bold: true, color: C.navy });
  ["지연 LOT 수", "총 지연시간", "추가근무", "계획 변경량"].forEach((r, i) => {
    t(s, `${i + 1}   ${r}`, { x: x3 + 0.3, y: 2.5 + i * 0.55, w: 2.3, h: 0.35, fontSize: 13.5, bold: i < 3, color: i === 2 ? C.amber : C.ink });
  });
  t(s, "앞 기준이 같을 때만 다음 기준을 본다. 모두 같으면 공동 순위.", { x: x3 + 0.3, y: 4.85, w: 2.3, h: 0.9, fontSize: 11, color: C.gray });
  // col4 approval
  const x4 = x3 + 3.0;
  box(s, x4, 1.75, W - M - x4, 4.2, C.navy);
  num(s, x4 + 0.2, 1.92, 4, C.white);
  t(s, "4", { x: x4 + 0.2, y: 1.94, w: 0.34, h: 0.3, fontSize: 12, bold: true, color: C.navy, align: "center" });
  t(s, "관리자 승인", { x: x4 + 0.65, y: 1.93, w: 1.7, h: 0.32, fontSize: 14, bold: true, color: C.white });
  t(s, "자동 적용 없음.\n\n긴급 LOT을 뒤로 미루는 안은 비교만 하고 승인할 수 없다.\n\n진행 중인 작업은 중단하지 않는다.", { x: x4 + 0.2, y: 2.5, w: W - M - x4 - 0.4, h: 3.3, fontSize: 12, color: "D6E2EE" });
  dark(s, M, 6.2, W - 2 * M, 0.6, [
    { text: "중간발표에서 ‘Demo 미적용’이던 추가근무 기준이 ", options: {} },
    { text: "기말에서 실제로 계산·승인·실행된다", options: { color: C.gold, bold: true } },
  ], 14);
}

// ---------------------------------------------------------------- 6 폐루프 검증
{
  const s = content("METHOD", "5. 폐루프 검증 — 승인한 계획대로 현장이 움직이는가", "가상 현장은 시스템과 HTTP로만 통신한다. 시스템은 실제 작업시간을 모르고 실적과 작업자 추정만 본다.", 6);
  // loop diagram left
  box(s, M, 1.75, 2.6, 1.2, C.bg, C.line);
  t(s, "가상 현장", { x: M, y: 1.9, w: 2.6, h: 0.35, fontSize: 15, bold: true, align: "center", color: C.navy });
  t(s, "숨은 실제 작업시간\n작업지시 순서대로 작업", { x: M, y: 2.28, w: 2.6, h: 0.6, fontSize: 11, align: "center", color: C.gray });
  box(s, M + 3.5, 1.75, 2.6, 1.2, C.navy);
  t(s, "시스템", { x: M + 3.5, y: 1.9, w: 2.6, h: 0.35, fontSize: 15, bold: true, align: "center", color: C.white });
  t(s, "Forecast · 위험 판단\n후보 계산 · 계획 버전", { x: M + 3.5, y: 2.28, w: 2.6, h: 0.6, fontSize: 11, align: "center", color: "D6E2EE" });
  const lr = (y, txt, rev) => {
    s.addShape(pres.shapes.LINE, { x: M + 2.65, y, w: 0.8, h: 0, line: { color: C.blue, width: 2, endArrowType: rev ? undefined : "triangle", beginArrowType: rev ? "triangle" : undefined } });
  };
  lr(2.1); lr(2.6, "", true);
  const legs = [
    ["① 실적 전송", "시작·완료·합격·불합격 (같은 이벤트 재전송 포함)"],
    ["② 검토 시점", "실행 시작, 매일 아침, 지연 입력, 시험 불합격"],
    ["③ 긴급이면 후보 → 승인", "실험 정책별로 정해진 규칙을 승인 (KEEP은 승인 안 함)"],
    ["④ 작업지시", "현장은 /work-orders가 준 순서대로만 다음 작업 선택"],
  ];
  legs.forEach((l, i) => {
    const y = 3.25 + i * 0.85;
    t(s, l[0], { x: M, y, w: 6.1, h: 0.3, fontSize: 13, bold: true, color: C.blue });
    t(s, l[1], { x: M, y: y + 0.32, w: 6.1, h: 0.4, fontSize: 12, color: C.ink });
  });
  // evidence right
  const x0 = M + 6.6, w0 = W - M - x0;
  t(s, "실행으로 확인한 것 (자동 테스트)", { x: x0, y: 1.75, w: w0, h: 0.3, fontSize: 13, bold: true, color: C.gray });
  const ev = [
    ["승인하면 실행 순서가 바뀐다", "같은 현장에서 승인 전후로 현장이 처리한 LOT 순서가 달라짐", "test_closed_loop.py"],
    ["표준시간이면 Forecast와 일치", "실제 시간 = 표준시간일 때 현장 완료 시각이 승인 시점 Forecast와 같음", "test_closed_loop.py"],
    ["실제 TCP 소켓에서도 동작", "uvicorn 서버 + httpx 클라이언트로 같은 루프, 이벤트 재전송 포함", "test_closed_loop_over_network.py"],
  ];
  ev.forEach((e, i) => {
    const y = 2.15 + i * 1.5;
    box(s, x0, y, w0, 1.35, C.greenT, "BFDFCB");
    t(s, "✓  " + e[0], { x: x0 + 0.2, y: y + 0.12, w: w0 - 0.4, h: 0.32, fontSize: 14, bold: true, color: C.green });
    t(s, e[1], { x: x0 + 0.2, y: y + 0.5, w: w0 - 0.4, h: 0.5, fontSize: 12, color: C.ink });
    t(s, e[2], { x: x0 + 0.2, y: y + 1.02, w: w0 - 0.4, h: 0.25, fontSize: 10, color: C.gray });
  });
}

// ---------------------------------------------------------------- 7 시연
{
  const s = content("RESULT", "6. 시연 — 중간발표 상황에 추가근무를 더하면", "같은 상황: LOT-001의 마지막 튜닝(U030)에 앞으로 480분이 더 필요하다고 입력한다. (시연 시각 10/22 13:17 고정)", 7);
  const cw = 6.0;
  const panel = (x, y, n, head, files) => {
    num(s, x, y, n);
    t(s, head, { x: x + 0.45, y: y + 0.02, w: cw - 0.5, h: 0.32, fontSize: 13, bold: true, color: C.navy });
    let yy = y + 0.45;
    files.forEach(([f, r]) => { const h = img(s, f, x + 0.06, yy, cw - 0.12, r); yy += h + 0.14; });
  };
  panel(M, 1.7, 1, "실적 입력 — U030 잔여 480분", [["b_estimate_form.png", 2480 / 536]]);
  panel(M, 3.55, 2, "긴급 판정 — 출하검사보다 4시간 57분 늦음", [["e_problem.png", 2480 / 114], ["c_metrics_urgent.png", 2480 / 156]]);
  panel(M + 6.25, 1.7, 3, "후보 비교 — 추가근무안이 1위 (2시간 57분)", [["f_ranking.png", 2480 / 636]]);
  panel(M + 6.25, 3.55 + 0.2, 4, "승인 → 계획 v2 (여전히 긴급 1)", [["i_approved_flash.png", 2480 / 114], ["j_metrics_v2.png", 2480 / 156]]);
  dark(s, M, 5.75, W - 2 * M, 0.95, [
    { text: "중간발표: 4시간 57분은 어떤 순서로도 줄지 않았다   →   기말: 10/22 추가근무 2시간으로 ", options: {} },
    { text: "2시간 57분", options: { color: C.gold, bold: true } },
    { text: ". 남은 지연은 평일 17~19시 추가근무로는 없앨 수 없다.", options: {} },
  ], 14);
}

// ---------------------------------------------------------------- 8 영상
{
  page += 1;
  const s = pres.addSlide();
  s.background = { color: C.white };
  t(s, "RESULT   ·   생산진도 관리 및 동적 재계획 시스템", { x: M, y: 0.28, w: 9, h: 0.25, fontSize: 9.5, bold: true, color: C.blue });
  t(s, "실행 시연 영상", { x: M, y: 0.55, w: W - 2 * M, h: 0.6, fontSize: 25, bold: true, color: C.ink, align: "center", valign: "middle" });
  t(s, "실적 입력 → 긴급 판정 → 후보 비교(추가근무 포함) → 관리자 승인 → v2 반영", { x: M, y: 1.17, w: W - 2 * M, h: 0.35, fontSize: 13, color: C.gray, align: "center" });
  box(s, 1.9, 1.75, W - 3.8, 5.1, C.navy);
  s.addShape(pres.shapes.OVAL, { x: W / 2 - 0.6, y: 3.45, w: 1.2, h: 1.2, fill: { color: C.white }, line: { color: C.white } });
  s.addShape(pres.shapes.ISOSCELES_TRIANGLE, { x: W / 2 - 0.2, y: 3.75, w: 0.55, h: 0.6, rotate: 90, fill: { color: C.navy }, line: { color: C.navy } });
  t(s, "MP4 삽입 영역 · 약 45초", { x: 1.9, y: 4.95, w: W - 3.8, h: 0.4, fontSize: 16, bold: true, color: C.white, align: "center" });
  t(s, "촬영 가이드의 장면 순서대로 녹화한 파일을 이 상자 위에 넣는다", { x: 1.9, y: 5.4, w: W - 3.8, h: 0.3, fontSize: 11, color: "B8C7D6", align: "center" });
  t(s, "공프4 기말발표", { x: M, y: H - 0.38, w: 3, h: 0.22, fontSize: 9, color: C.light });
  t(s, String(page), { x: W - M - 1, y: H - 0.38, w: 1, h: 0.22, fontSize: 9, color: C.light, align: "right" });
  s.addNotes(notes[8]);
}

// ---------------------------------------------------------------- 9 실험 설계
{
  const s = content("RESULT", "7. 실험 설계 — 810번의 폐루프 실행", "시나리오 하나가 아니라, 같은 시작 상태에서 교란 조건과 재계획 방법을 바꿔 반복 실행했다.", 9);
  card(s, M, 1.75, 3.9, 2.55, "시작 상태", "중간발표 데모 상태 (10/22 13:00)\n기준계획을 접수순(LOT-001→002→003)으로 둠\n→ 출하검사가 빠른 LOT-003(10/28)이 LOT-002(11/06) 뒤에 배치된, 의도적으로 만든 충돌 상황");
  card(s, M + 4.15, 1.75, 3.9, 2.55, "교란 조건 3가지", "정상: 작업시간 ±15% 수준 변동\n작업시간 +20%: 모든 작업이 평균 1.2배\n작업정지·재작업: 3% 작업에 +240분, 최종시험 8% 불합격 → 재작업");
  card(s, M + 8.3, 1.75, 3.93, 2.55, "재계획 방법 9가지", "KEEP(계획 유지)\nFCFS · EDD · Slack · CR  × 추가근무 끔/켬\n관리자는 시스템이 ‘긴급’이라 할 때만 해당 규칙 승인");
  // equation
  const ey = 4.55;
  const eq = [["3", "조건"], ["×", ""], ["9", "구성"], ["×", ""], ["30", "seed"], ["=", ""], ["810", "실행"]];
  let ex = M + 0.3;
  eq.forEach((e) => {
    const w = e[1] ? 1.25 : 0.5;
    t(s, e[0], { x: ex, y: ey, w, h: 0.7, fontSize: e[1] ? 34 : 26, bold: true, align: "center", color: e[0] === "810" ? C.blue : C.navy });
    if (e[1]) t(s, e[1], { x: ex, y: ey + 0.72, w, h: 0.3, fontSize: 11, align: "center", color: C.gray });
    ex += w + 0.05;
  });
  box(s, M + 7.0, 4.5, W - M - (M + 7.0), 2.2, C.tint, "C9DDF0");
  t(s, "공정한 비교를 위해", { x: M + 7.2, y: 4.65, w: 5, h: 0.32, fontSize: 13.5, bold: true, color: C.blue });
  t(s, [
    { text: "같은 seed면 모든 구성이 같은 실제 작업시간·불합격을 받음 (공통 난수)", options: { bullet: true, breakLine: true } },
    { text: "평균 ± 95% 신뢰구간, KEEP과 같은 seed끼리 짝지은 차이", options: { bullet: true, breakLine: true } },
    { text: "명령 한 줄로 재현, 중단돼도 이어서 실행", options: { bullet: true } },
  ], { x: M + 7.2, y: 5.05, w: W - M - (M + 7.2) - 0.2, h: 1.55, fontSize: 12, color: C.ink, paraSpaceAfter: 5 });
  t(s, "python -m production_control.sim.experiment --reps 30", { x: M + 0.3, y: 5.95, w: 6.3, h: 0.3, fontSize: 11, color: C.gray, fontFace: "Courier New" });
}

// ---------------------------------------------------------------- 10 결과 1
{
  const s = content("RESULT", "8. 결과① — 재계획은 출하검사 진입 지연을 없앴다", "출하검사 진입 지연 = 생산 완료 − 출하검사 예정 시작 (평균, 막대 위 숫자 · 검은 선 95% 신뢰구간, n=30)", 10);
  img(s, "gate_delay.png", M + 0.05, 1.75, 8.9, 2130 / 664);
  const xs = M + 9.3, ws = W - M - xs;
  const stat = (y, big, color, head, body) => {
    t(s, big, { x: xs, y, w: ws, h: 0.6, fontSize: 30, bold: true, color });
    t(s, head, { x: xs, y: y + 0.62, w: ws, h: 0.3, fontSize: 12.5, bold: true, color: C.ink });
    t(s, body, { x: xs, y: y + 0.93, w: ws, h: 0.55, fontSize: 11, color: C.gray });
  };
  stat(1.7, "30 / 30", C.green, "EDD, 정상·작업시간 +20% 조건", "계획 유지 시 평균 190분 · 1,523분");
  stat(3.25, "14.6분", C.amber, "EDD, 작업정지·재작업 조건", "계획 유지 2,433분. 단 30회 중 5회는 지연이 남음");
  stat(4.8, "FCFS ≈ KEEP", C.gray, "정상 조건 차이 −0.9 ± 1.6분", "기준계획이 이미 접수순이라 예상대로 (검증용 대조군)");
  t(s, "공장 규칙 위반 0 · 실패 0 (810회). 원자료: experiments/main30/summary.csv", { x: M, y: 4.75, w: 9, h: 0.3, fontSize: 10.5, color: C.light });
}

// ---------------------------------------------------------------- 11 간트
{
  const s = content("RESULT", "9. 결과② — 무엇이 바뀌었나", "실험 시작 시점(10/22 13:00)에서 시스템이 계산한 두 일정: 계획을 유지한 Forecast(연한 막대)와 EDD 재계획안(진한 막대)", 11);
  img(s, "gantt_replan.png", M + 0.05, 1.75, 8.6, 2052 / 794);
  const xs = M + 9.0, ws = W - M - xs;
  card(s, xs, 1.75, ws, 1.6, "LOT-003을 앞당긴다", "출하검사 10/28 09:00. 유지하면 최종 성능시험이 Gate(검은 선)를 넘는다.", { fill: C.greenT, line: "BFDFCB", headColor: C.green, bodySize: 11.5 });
  card(s, xs, 3.55, ws, 1.6, "LOT-002를 뒤로 보낸다", "출하검사 11/06. 뒤로 밀려도 여유가 충분하다 (Gate가 그림 범위 밖).", { bodySize: 11.5 });
  card(s, xs, 5.35, ws, 1.3, "바꾼 것은 순서뿐", "작업시간·자원은 같고, 병목 장비를 쓰는 순서만 바뀌었다.", { fill: C.tint, line: "C9DDF0", headColor: C.blue, bodySize: 11.5 });
  t(s, "막대는 LOT×공정의 첫 작업 시작~마지막 작업 종료 구간이며, 야간·주말이 포함된 실제 시각 축이다.", { x: M, y: 5.25, w: 8.6, h: 0.3, fontSize: 10.5, color: C.light });
}

// ---------------------------------------------------------------- 12 추가근무
{
  const s = content("RESULT", "10. 결과③ — 추가근무의 효과와 비용", "같은 규칙에서 추가근무를 허용하면(○ → △) 지연은 아래로, 추가 가동시간은 오른쪽으로 움직인다.", 12);
  img(s, "overtime_tradeoff.png", M + 0.05, 1.75, 8.9, 2012 / 580);
  t(s, "정상·작업시간 +20% 조건에서 EDD와 Slack은 같은 점이라 겹쳐 보인다. 추가 가동시간 = 17시 ~ 창 안 마지막 작업 종료(대기 포함).", { x: M, y: 4.45, w: 8.9, h: 0.5, fontSize: 10.5, color: C.light });
  const xs = M + 9.3, ws = W - M - xs;
  card(s, xs, 1.75, ws, 1.45, "효과: 지연이 남는 규칙", "작업정지 CR 117 → 72분\n정상 FCFS 약 190 → 118분", { fill: C.greenT, line: "BFDFCB", headColor: C.green, bodySize: 12 });
  card(s, xs, 3.4, ws, 1.6, "비용: 불필요한 추가근무", "정상 조건 EDD는 이미 0분인데 평균 108분을 연다 (30회 중 27회 사용)", { fill: C.amberT, line: "EBD3A6", headColor: C.amber, bodySize: 12 });
  dark(s, M, 5.3, W - 2 * M, 1.25, [
    { text: "원인: 결정 시점의 Forecast가 실제보다 비관적이다.\n", options: { breakLine: true } },
    { text: "시스템은 예측으로 고르므로, 예측 보정 없이는 ", options: {} },
    { text: "필요 없는 추가근무를 살 수 있다", options: { color: C.gold, bold: true } },
    { text: " — 한계로 보고한다.", options: {} },
  ], 15);
}

// ---------------------------------------------------------------- 13 두 지표
{
  const s = content("RESULT", "11. 두 지표를 나눠 본 결과", "생산 완료가 지켜야 하는 선(출하검사 시작)과 고객이 받는 선(납기)은 다르다.", 13);
  // timeline
  const y = 2.25, x0 = M + 0.4, x1 = W - M - 0.4;
  s.addShape(pres.shapes.LINE, { x: x0, y, w: x1 - x0, h: 0, line: { color: C.line, width: 3 } });
  const marks = [[0.05, "생산 완료", "마지막 최종시험 합격", C.navy], [0.3, "출하검사 시작", "Gate 예정 시각", C.red], [0.68, "출하", "검사 3근무일 후 17:00", C.navy], [0.95, "고객 납기", "Lot.due_at", C.blue]];
  marks.forEach((m) => {
    const x = x0 + (x1 - x0) * m[0];
    s.addShape(pres.shapes.OVAL, { x: x - 0.11, y: y - 0.11, w: 0.22, h: 0.22, fill: { color: m[3] }, line: { color: m[3] } });
    t(s, m[1], { x: x - 1.2, y: y - 0.62, w: 2.4, h: 0.32, fontSize: 13, bold: true, align: "center", color: m[3] });
    t(s, m[2], { x: x - 1.2, y: y + 0.2, w: 2.4, h: 0.3, fontSize: 10.5, align: "center", color: C.gray });
  });
  card(s, M, 3.1, 6.0, 3.5, "출하검사 진입 지연  (시스템의 재계획 KPI)", "", { fill: C.redT, line: "F0C5C1", headColor: C.red });
  t(s, [
    { text: "생산 완료 − 출하검사 예정 시작. 가정 없이 측정", options: { bullet: true, breakLine: true } },
    { text: "중간발표의 ‘4시간 57분’도 이 지표 (고객 납기 지각이 아님)", options: { bullet: true, breakLine: true } },
    { text: "계획 유지 시 평균 190 ~ 2,433분, EDD 0 ~ 15분", options: { bullet: true } },
  ], { x: M + 0.2, y: 3.7, w: 5.6, h: 2.7, fontSize: 13, color: C.ink, paraSpaceAfter: 8 });
  card(s, M + 6.25, 3.1, 5.98, 3.5, "최종 납기 지각", "", { fill: C.tint, line: "C9DDF0", headColor: C.blue });
  t(s, [
    { text: "출하 − 고객 납기. 출하검사는 대시보드와 같은 규칙(Gate 또는 늦으면 완료 후 시작, 시작일 포함 3근무일)", options: { bullet: true, breakLine: true } },
    { text: "810회 모두 0. 가장 빠듯한 경우 납기 당일 17:00 출하 (계획 유지 2회, FCFS 1회)", options: { bullet: true, breakLine: true } },
    { text: "검사 자체의 대기·불합격은 모델링하지 않음 (가정)", options: { bullet: true } },
  ], { x: M + 6.45, y: 3.7, w: 5.6, h: 2.7, fontSize: 13, color: C.ink, paraSpaceAfter: 8 });
}

// ---------------------------------------------------------------- 14 검증
{
  const s = content("RESULT", "12. 검증과 트러블슈팅", "반복 실험은 성능 비교뿐 아니라 버그를 찾는 도구이기도 했다. 고친 문제는 테스트로 고정했다.", 14);
  const st = [["384", "자동 테스트 통과", "CI: Python 3.11 · 3.13"], ["0", "공장 규칙 위반", "810회 실행 전체"], ["0", "실패한 실행 (최종)", "첫 실행 3회 실패 → 원인 수정"]];
  st.forEach((v, i) => {
    const y = 1.75 + i * 1.6;
    box(s, M, y, 3.3, 1.42, C.bg, C.line);
    t(s, v[0], { x: M + 0.25, y: y + 0.12, w: 2.9, h: 0.65, fontSize: 32, bold: true, color: C.blue });
    t(s, v[1], { x: M + 0.25, y: y + 0.78, w: 2.9, h: 0.3, fontSize: 13, bold: true, color: C.ink });
    t(s, v[2], { x: M + 0.25, y: y + 1.07, w: 2.9, h: 0.26, fontSize: 10.5, color: C.gray });
  });
  const rows = [
    [{ text: "발견한 문제", options: { bold: true, color: C.white, fill: { color: C.navy } } }, { text: "원인", options: { bold: true, color: C.white, fill: { color: C.navy } } }, { text: "해결", options: { bold: true, color: C.white, fill: { color: C.navy } } }],
    ["17:00 정각 재계획에서 실패 (810회 중 3회)", "진행 중 작업이 결정 시각에 바로 이어진다고 가정", "다음 근무 개시에 재개하도록 수정, 3회 재실행 성공"],
    ["재작업으로 다시 열린 공정이 후보에서 누락", "승인 계획에 없는 공정을 후보 계산이 찾지 못함", "부모 계획 뒤 순위로 배치, 변경량에서 제외"],
    ["작업지시 계산 중 길이 0 작업 구간 (HTTP 409)", "분 단위 부동소수 오차", "허용 오차(1e-6분) 도입"],
    ["실험과 대시보드의 출하검사 기준 불일치", "실험만 ‘완료 후 24근무시간’ 가정", "규칙을 한 곳으로 통일, 기록 데이터로 재계산"],
  ];
  s.addTable(rows, {
    x: M + 3.6, y: 1.75, w: W - M - (M + 3.6), colW: [3.0, 2.9, 2.68], fontFace: FONT, fontSize: 11.5, color: C.ink,
    border: { type: "solid", pt: 0.75, color: C.line }, valign: "middle", rowH: [0.42, 0.95, 0.95, 0.95, 0.95], margin: 0.08,
  });
  t(s, "실패 기록은 숨기지 않고 experiments/main30/failures_before_3a7ff6e.json에 남겼다.", { x: M + 3.6, y: 6.2, w: 8.6, h: 0.3, fontSize: 10.5, color: C.light });
}

// ---------------------------------------------------------------- 15 결론
{
  const s = content("CONCLUSION", "13. 결론 — 성과, 한계, 향후 과제", "", 15);
  const cols = [
    ["구현 성과", C.greenT, C.green, ["승인된 계획이 작업지시로 내려가는 폐루프를 실행으로 확인", "추가근무 후보의 계산·승인·실행을 하나의 근무달력으로 통일", "810회 반복 실험: EDD가 출하검사 진입 지연을 평균 190~2,433분에서 0~15분으로", "간트차트·실험 결과 화면, 명령 한 줄 재현"]],
    ["한계", C.amberT, C.amber, ["Pico 2 WH 단말 미연동 (가상 단말·화면 입력으로 검증)", "시뮬레이터 작업시간 분포·교란 확률은 가정값", "비관적 예측으로 불필요한 추가근무 선택 가능", "데모 납기 여유가 커 최종 납기 지각 비교는 불가"]],
    ["향후 과제", C.tint, C.blue, ["Pico 단말을 같은 API에 연결", "실적으로 Forecast 보정", "추가근무 비용을 순위에 반영", "실제 현장 데이터로 시뮬레이터 보정"]],
  ];
  const cw = (W - 2 * M - 0.5) / 3;
  cols.forEach((c, i) => {
    const x = M + i * (cw + 0.25);
    box(s, x, 1.45, cw, 4.25, c[1], c[1]);
    pill(s, x + 0.2, 1.62, 1.4, c[0], C.white, c[2]);
    t(s, c[3].map((b, k) => ({ text: b, options: { bullet: true, breakLine: k < c[3].length - 1 } })), { x: x + 0.2, y: 2.1, w: cw - 0.4, h: 3.5, fontSize: 13, color: C.ink, paraSpaceAfter: 9 });
  });
  dark(s, M, 5.95, W - 2 * M, 0.8, [
    { text: "실적을 보여주는 대시보드가 아니라, ", options: {} },
    { text: "실적이 다음 작업지시를 바꾸는 시스템", options: { color: C.gold, bold: true } },
  ], 17);
}

pres.writeFile({ fileName: OUT }).then(() => console.log("wrote", OUT));
