// 기말발표 기준본 (모핑, 쉬운 설명판). 같은 이름("!!...")의 도형이 다음 장에서 위치·크기·색을 바꾸면 PowerPoint 모핑 전환이 이어서 움직인다.
// 수치는 experiments/main30 원자료와 docs/figures/gantt_replan.json에서 읽는다. 전환은 <OUT>.transitions.json에 적고 morph_post.py가 넣는다.
// BACKUP=1 이면 810개 점 장면을 움직임 없이(제자리 회색 → 색만 페이드) 만드는 백업판을 만든다.
const pptxgen = require("pptxgenjs");
const fs = require("fs");
const path = require("path");

const OUT = process.argv[2] || "final_raw.pptx";
const BACKUP = process.env.BACKUP === "1";
const TR = {}; // slide number -> "morph" | "fade"
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
pres.title = "실적이 다음 작업지시를 바꾸는 시스템 — 공프4 기말발표";
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

function slide(kicker, notes, tr = "fade") {
  page += 1;
  TR[page] = tr;
  const s = pres.addSlide();
  s.background = { color: C.bg };
  if (kicker) T(s, kicker, { ...N("kicker"), x: M, y: 0.38, w: 8, h: 0.25, fontSize: 10, bold: true, color: C.late, charSpacing: 1 });
  T(s, String(page).padStart(2, "0"), { x: W - M - 0.6, y: H - 0.42, w: 0.6, h: 0.22, fontSize: 9, color: C.dim, align: "right", fontFace: MONO });
  s.addNotes(NOTES[page] || notes);
  check(NOTES[page], "note " + page);
  return s;
}
const head = (s, t, sub) => {
  T(s, t, { ...N("head"), x: M, y: 0.7, w: W - 2 * M, h: 0.75, fontSize: 30, bold: true, color: C.white, valign: "middle" });
  if (sub) T(s, sub, { ...N("sub"), x: M, y: 1.45, w: W - 2 * M, h: 0.35, fontSize: 13.5, color: C.muted });
};

// 발표자 노트(=대본). 쉬운 말 먼저, 용어는 뒤에. 수치는 원자료에서 계산.
const NOTES = {
  1: "안녕하십니까, 메카트로닉스공학과 박상현입니다. 제가 만든 가상 공장의 한 장면으로 시작하겠습니다. 10월 22일 오후 1시 17분, 작업자가 입력합니다. U030, 첫 번째 묶음의 30번째 제품이 앞으로 480분 더 걸린다고요.",
  2: "시스템이 바로 다시 계산하니, 이 묶음이 출하검사에 4시간 57분 늦게 들어간다고 나옵니다. 출하검사를 시작하기로 약속한 시각을 Gate라고 부르고, 이보다 늦을 것 같으면 긴급입니다.",
  3: "중간발표 때는 생산 순서만 바꿔 봤습니다. 하지만 늦어진 제품의 작업시간은 줄지 않았고, 잘못 바꾸면 다른 묶음까지 늦어져 합계 549분이 됐습니다.",
  4: "그래서 이번에는 세 질문에 답했습니다. 언제 끝나는지, 약속을 지키는지, 어떻게 덜 늦는지. 그리고 그 답이 다음 작업 순서까지 바꾸게 했습니다.",
  5: "모의 공장입니다. 제품 30개 묶음을 LOT, 제품 하나를 Unit이라 부르고, 세 묶음 90개입니다. 튜닝과 성능시험 장비는 한 대씩이라 줄이 생기는데, 이게 병목입니다. 작업자는 둘, 근무는 평일 9시부터 17시입니다.",
  6: "완료 시각은 세 단계로 계산합니다. 먼저 제품 하나에 걸리는 평균 시간, Pace를 구합니다. 끝난 제품이 세 개 이상이면 실제 평균, 아니면 표준시간입니다. 다음으로 남은 제품 수에 곱하고, 작업 중인 제품은 쓴 시간을 뺍니다. 예상보다 길어지면 작업자에게 묻는데, 480분이 그 답입니다. 마지막으로 장비 한 대에 하나씩, 근무시간 안에 채웁니다. 그렇게 나온 예상 완료 시각이 Forecast입니다.",
  7: "전체 흐름입니다. 현장 실적이 들어오면 서버가 확인해 저장하고 완료 시각을 다시 계산합니다.",
  8: "예상이 약속을 넘으면 긴급으로 보고 해결 후보를 계산합니다.",
  9: "고르는 건 사람입니다. 화면에서 관리자가 직접 승인해야 계획 버전이 올라갑니다.",
  10: "승인된 계획은 작업지시로 내려가고, 현장은 그 순서로 일해 다시 실적을 보냅니다. 이 닫힌 고리가 폐루프입니다. 현장은 가상 현장이 맡았고, Pico 단말은 연동하지 못했습니다.",
  11: "후보는 순서 규칙 네 가지로 만듭니다. FCFS는 먼저 온 묶음부터, EDD는 약속이 빠른 묶음부터, Slack은 여유가 적은 묶음부터, CR은 남은 시간에 비해 일이 많은 묶음부터입니다. 각각에 17시부터 19시 추가근무안을 더해 여덟 개, 계획 유지까지 아홉 가지가 뒤 실험의 방법입니다.",
  12: "시연 상황은 왜 순서로 안 줄었을까요? 시스템이 계산한 예상 일정입니다. U030은 이미 작업 중이라 멈추지 않습니다. 오늘 3시간 43분, 내일 4시간 17분 해서 내일 오후 1시 17분에 튜닝이 끝나고, 40분을 더하면 13시 57분, 약속보다 4시간 57분 늦습니다. 늦어진 게 이 제품 자체라 순서를 바꿔도 그대로입니다.",
  13: "그래서 추가근무안도 비교했습니다. 오늘 저녁 2시간을 더 하면 지연이 2시간 57분으로 줄 것으로 예측되고, 이 안이 1위입니다. 하지만 약속 전 저녁이 오늘뿐이라 여전히 긴급입니다.",
  14: "여기부터는 제가 만든 프로그램의 실제 화면입니다. 실제 공장은 아닙니다. U030에 480분을 입력하면 긴급 묶음이 생깁니다. 이때 현장 작업지시는 LOT-003의 마무리 조립입니다. 재계획 화면에서 후보 순위를 계산하고, 관리자가 1위인 EDD 추가근무안을 승인하면 계획은 버전 2가 됩니다. 같은 작업지시를 다시 열면 LOT-003의 최종 성능시험으로 바뀌었고, 오후 5시 이후 추가근무 작업도 생겼습니다. 현장이 이 지시를 실제로 따르는지는 뒤의 실험에서 확인했습니다.",
  15: "여기부터는 시연과 별개인 반복 실험입니다. 한 번은 우연일 수 있으니까요. 조건은 셋입니다. 작업시간이 조금씩 들쭉날쭉한 날, 모두 20% 느린 날, 일부 작업이 갑자기 4시간 더 걸리거나 재작업하는 날입니다. 아홉 가지 방법을 30번씩, 810번 돌렸습니다. 같은 번호의 실행은 모든 방법이 같은 작업시간을 받습니다. 같은 시험지로 비교하는 셈입니다.",
  16: "810번은 두 역할을 프로그램이 맡았습니다. 가상 현장은 시스템이 모르는 실제 작업시간으로 일하고, 가상 관리자는 긴급일 때 정해진 규칙의 후보를 고릅니다. 승인은 사람이 누를 때와 같은 승인 API로 들어갑니다.",
  17: "실험은 들어온 순서대로의 계획에서 시작합니다. 그런데 출하검사 약속은 LOT-003이 LOT-002보다 빠릅니다. 일부러 만든 충돌입니다.",
  18: "EDD는 LOT-003을 앞으로 보냅니다. 장비 쓰는 순서만 바뀝니다.",
  19: "810번의 실행을 점 하나씩으로 놓겠습니다.",
  20: "점선으로 표시한 계획 유지와 EDD만 보시면 됩니다. 주황은 약속에 늦은 실행, 초록은 지킨 실행입니다. 계획 유지는 모두 주황인데, EDD는 거의 초록이고 돌발 지연이 있는 날만 5번 늦었습니다.",
  21: `숫자로 보면, 한 번 실행에서 늦은 묶음들의 지연을 더해 30번 평균 낸 값입니다. 계획 유지는 ${fmt(m("NORMAL", "KEEP"))}분, ${fmt(m("SLOW", "KEEP"))}분, ${fmt(m("STOPPAGE_REWORK", "KEEP"))}분, EDD는 0분, 0분, ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분입니다. 다섯 번은 남았으니 없앴다가 아니라 크게 줄였다고 말씀드립니다. 여기서 늦음은 고객 납기가 아니라 출하검사 약속 기준입니다. 이번엔 고객 납기 지각은 없었지만, 출하검사가 밀리면 검사 일정이 밀리고 납기가 빠듯한 주문에선 바로 지각이 됩니다.`,
  22: "왜 줄었는지 예상 일정표로 보겠습니다. 막대는 그 공정의 첫 제품 시작부터 마지막 제품 끝까지라서, 중간 대기와 밤도 들어 있습니다. 흰 선이 출하검사 약속입니다. 계획을 유지하면 LOT-003이 10월 28일 12시 15분에 끝날 것으로 예측돼 약속을 넘습니다.",
  23: "EDD로 바꾸면 LOT-003이 10월 23일에 끝날 것으로 예측되고, 여유 있는 LOT-002가 뒤로 갑니다. 다만 EDD가 어디서나 최선이란 뜻은 아닙니다.",
  24: "추가근무는 어땠을까요? 먼저 끈 상태입니다.",
  25: `켜면 지연이 남던 경우는 줄었습니다. 돌발 지연 날 CR은 ${fmt(m("STOPPAGE_REWORK", "CR"))}분에서 ${fmt(m("STOPPAGE_REWORK", "CR+OT"))}분입니다. 오른쪽 막대는 더 돌린 시간인데, 하루 2시간까지 여러 날 쓸 수 있어 합계가 2시간을 넘기도 합니다. 문제는 맨 아래입니다. 평소 EDD는 지연이 0인데도 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분을 더 돌렸습니다. 예측이 비관적이었던 탓으로 추정하고, 한계로 남깁니다.`,
  26: "검증은 두 가지입니다. 자동 테스트 384개는 계산 하나하나를, 810번 실험은 전체가 끝까지 도는지를 봅니다. 첫 실행 3번이 17시 정각 버그로 실패했고, 고친 뒤 모두 성공했습니다.",
  27: "증명하지 않은 것도 있습니다. Pico 단말 연동, 실제 공장 데이터, 출하검사 자체의 대기, 그리고 EDD가 어디서나 최선이라는 점입니다. 돌발 지연도 실제 정지 기능 대신 작업시간을 늘려 흉내 냈습니다.",
  28: "정리하면, 이 시스템은 실적으로 완료 시각을 다시 계산하고 사람이 고른 계획을 작업지시로 내려보냅니다. 가상 환경 810번 실험에서 재계획은 출하검사 지연을 크게 줄였고, 불필요한 추가근무를 줄이는 예측 보정이 다음 과제입니다. 감사합니다.",
};
const card = (s, x, y, w, h, o = {}) => R(s, o.name || null, x, y, w, h, o.fill || C.panel, { round: true, line: o.line || C.line, lw: o.lw });
const numDot = (s, x, y, n, col) => { O(s, null, x + 0.22, y + 0.22, 0.44, col); T(s, String(n), { x, y, w: 0.44, h: 0.44, fontSize: 15, bold: true, color: C.bg, align: "center", valign: "middle" }); };

// ================================================================ ACT 1 — 한 순간
// 1
{
  const s = slide(null, "10월 22일 오후 1시 17분입니다. 제품 90개를 만드는 공장에서 한 작업자가 단말에 이렇게 입력합니다. U030, 이 제품은 앞으로 480분, 8시간이 더 걸립니다.");
  T(s, "모의 생산환경  ·  10/22  13:17  ·  튜닝 장비 앞", { ...N("clock"), x: M, y: 2.3, w: 8, h: 0.4, fontSize: 16, color: C.muted, fontFace: MONO });
  T(s, "U030,  480분 더.", { ...N("big"), x: M - 0.05, y: 2.85, w: 12, h: 1.6, fontSize: 80, bold: true, color: C.white });
  T(s, "가상 공장 시나리오 · U030 = 첫 번째 묶음(LOT-001)의 30번째 제품 · 작업자가 남은 작업시간을 입력", { ...N("cap"), x: M, y: 4.6, w: 12, h: 0.4, fontSize: 16, color: C.muted });
  R(s, "scan", M, 5.3, 0.02, 0.04, C.late);
}
// 2
{
  const s = slide(null, "시스템은 바로 다시 계산합니다. 이 제품이 속한 묶음, LOT-001이 출하검사에 4시간 57분 늦게 들어간다고 나옵니다. 출하검사는 제품을 내보내기 전 마지막 검사이고, 들어갈 시각이 미리 약속돼 있습니다. 이 약속 시각을 Gate라고 부르고, Gate보다 늦을 것 같으면 긴급으로 표시합니다.", "morph");
  T(s, "모의 생산환경  ·  10/22  13:17  ·  완료 시각 다시 계산", { ...N("clock"), x: M, y: 1.3, w: 8, h: 0.4, fontSize: 16, color: C.muted, fontFace: MONO });
  T(s, "4h 57m", { ...N("big"), x: M - 0.08, y: 1.85, w: 12, h: 2.6, fontSize: 150, bold: true, color: C.late, fontFace: MONO });
  T(s, "LOT-001이 출하검사 약속 시각(Gate)보다 늦게 끝난다  →  긴급(URGENT)", { ...N("cap"), x: M, y: 4.6, w: 12, h: 0.45, fontSize: 19, bold: true, color: C.white });
  R(s, "scan", M, 5.3, W - 2 * M, 0.04, C.late);
}
// bars (slide 3)
const BX = M + 4.3, BW = 6.6, BMAX = 600, BY = 2.2, BS = 1.0;
const bar = (s, name, i, val, color, label, sub, subColor) => {
  const y = BY + i * BS;
  T(s, label, { ...N(name + "_l"), x: M, y: y + 0.02, w: 4.0, h: 0.38, fontSize: 15, bold: true, color: C.white });
  T(s, sub, { ...N(name + "_s"), x: M, y: y + 0.42, w: 4.0, h: 0.3, fontSize: 11.5, color: subColor || C.muted });
  R(s, name, BX, y + 0.05, (BW * val) / BMAX, 0.6, color, { round: true, r: 0.06 });
  T(s, String(val), { ...N(name + "_v"), x: BX + (BW * val) / BMAX + 0.15, y: y + 0.05, w: 1.2, h: 0.6, fontSize: 24, bold: true, color: C.white, valign: "middle", fontFace: MONO });
};
// 3
{
  const s = slide("중간발표의 벽", "중간발표 때는 생산 순서를 네 가지 방식으로 바꿔 봤습니다. 세 방식은 297분 그대로였고, 한 방식은 다른 묶음까지 늦어져 합계 549분이 됐습니다. 순서만 바꿔서는 줄지 않는 지연이었습니다.");
  head(s, "생산 순서를 바꿔도 줄지 않았다", "중간발표 결과 · 총 출하검사 진입 지연 (분, 늦은 묶음별 지연의 합계)");
  bar(s, "b_seq", 0, 297, C.grey, "순서 바꾸기 3가지", "297분 그대로");
  bar(s, "b_fcfs", 1, 549, C.dim, "순서 바꾸기 1가지", "다른 묶음까지 늦어져 합계 549분");
  L(s, "b_ref", BX + (BW * 297) / BMAX, BY - 0.15, 0, 2.2, C.late, { dash: "dash", w: 1 });
  T(s, "이미 늦어진 제품의 작업시간은 순서로 줄지 않는다 → 이번엔 추가근무까지 비교", { x: M, y: 5.2, w: 11, h: 0.5, fontSize: 20, bold: true, color: C.late });
}
// 4 title
{
  const s = slide(null, "안녕하십니까, 메카트로닉스공학과 박상현입니다. 이런 순간 관리자가 알고 싶은 건 세 가지입니다. 언제 끝나는지, 약속을 지킬 수 있는지, 어떻게 하면 덜 늦는지. 기말에서는 이 질문에 답하고, 그 답이 실제 다음 작업 순서까지 바꾸는 시스템을 완성했습니다.");
  T(s, "4h 57m", { x: W - M - 3.2, y: 0.5, w: 3.2, h: 0.6, fontSize: 26, bold: true, color: C.late, fontFace: MONO, align: "right" });
  T(s, "공학프로젝트4 · 기말발표", { x: M, y: 1.35, w: 8, h: 0.3, fontSize: 12, bold: true, color: C.late, charSpacing: 1 });
  T(s, "실적이 다음 작업지시를\n바꾸는 시스템", { x: M, y: 1.8, w: 11, h: 2.2, fontSize: 52, bold: true, color: C.white, lineSpacingMultiple: 1.05 });
  T(s, "현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템", { x: M, y: 4.05, w: 11, h: 0.4, fontSize: 16, color: C.muted });
  [["언제 끝나나", "완료 시각 예측"], ["약속을 지키나", "출하검사 위험 판정"], ["어떻게 덜 늦나", "재계획 → 작업지시"]].forEach((q, i) => {
    const x = M + i * 3.2;
    card(s, x, 4.75, 3.0, 0.95);
    T(s, `${i + 1}  ${q[0]}`, { x: x + 0.22, y: 4.86, w: 2.7, h: 0.38, fontSize: 15, bold: true, color: C.white });
    T(s, q[1], { x: x + 0.22, y: 5.27, w: 2.7, h: 0.3, fontSize: 11.5, color: C.muted });
  });
  T(s, "12233707  박상현  ·  메카트로닉스공학과", { x: M, y: 6.1, w: 8, h: 0.35, fontSize: 14, bold: true, color: C.text });
  T(s, "FastAPI · SQLite · Streamlit · 가상 현장 시뮬레이터 · Pico 2 WH 단말 미연동", { x: M, y: 6.5, w: 11, h: 0.3, fontSize: 11, color: C.dim });
}

// ================================================================ ACT 2 — 공장과 계산 원리
// 5 plant
{
  const s = slide("모의 생산환경", "먼저 공장입니다. 제품 30개를 한 묶음으로 만들고, 이 묶음을 LOT, 제품 하나를 Unit이라고 부릅니다. 세 묶음, 모두 90개입니다. 튜닝 장비와 성능시험 장비는 한 대씩뿐이라 한 번에 한 제품만 들어갑니다. 그래서 여기서 줄이 생기고, 이런 곳을 병목이라고 합니다. 작업자는 두 명, 근무는 평일 9시부터 17시입니다.");
  head(s, "모의 공장: 제품 90개, 장비는 한 대씩", "제품 30개 = 1 LOT(묶음) · 제품 1개 = Unit · 표준시간은 로직 검증용 가정값");
  const procs = [["테이핑", "10분/개", 0], ["일반 조립", "10분/개", 0], ["튜닝", "25분/개 · 장비 1대", 1], ["마무리 조립", "10분/개", 0], ["최종 성능시험", "30분/개 · 장비 1대", 1], ["출하검사", "약속 시각 = Gate", 2]];
  const pw = 1.83, pg = 0.2, py = 2.3, ph = 1.2;
  procs.forEach((p, i) => {
    const x = M + i * (pw + pg), col = p[2] === 1 ? C.late : p[2] === 2 ? C.blue : C.line;
    R(s, null, x, py, pw, ph, p[2] === 1 ? "2A1A12" : C.panel, { round: true, line: col, lw: p[2] ? 1.5 : 0.75 });
    T(s, p[0], { x, y: py + 0.18, w: pw, h: 0.35, fontSize: 15, bold: true, color: p[2] === 1 ? C.late : C.white, align: "center" });
    T(s, p[1], { x, y: py + ph - 0.45, w: pw, h: 0.3, fontSize: 10.5, color: C.muted, align: "center" });
    if (i < procs.length - 1) T(s, "›", { x: x + pw, y: py + 0.3, w: pg, h: 0.5, fontSize: 18, color: C.dim, align: "center" });
  });
  T(s, "↑ 병목: 한 대뿐이라 한 번에 한 제품 → 줄이 생긴다", { x: M + 2 * (pw + pg), y: 3.62, w: 6, h: 0.35, fontSize: 13, bold: true, color: C.late });
  [["3 LOT × 30개 = 90개", "LOT-001 · LOT-002 · LOT-003"], ["작업자 2명", "평일 09–17시 근무"], ["외부 피드 본딩", "LOT 단위 외부 리드타임 (일반 조립 전)"]].forEach((f, i) => {
    const x = M + i * 4.1;
    card(s, x, 4.45, 3.9, 1.15);
    T(s, f[0], { x: x + 0.25, y: 4.6, w: 3.5, h: 0.4, fontSize: 17, bold: true, color: C.white });
    T(s, f[1], { x: x + 0.25, y: 5.08, w: 3.5, h: 0.3, fontSize: 11.5, color: C.muted });
  });
  T(s, "K = 9: 튜닝이 9개 끝나면 마무리 조립을 시작할 수 있다", { x: M, y: 6.1, w: 12, h: 0.3, fontSize: 11, color: C.dim });
}
// 6 forecast
{
  const s = slide("언제 끝날지 계산하는 법", "그럼 언제 끝날지는 어떻게 계산할까요? 세 단계입니다. 먼저 속도를 구합니다. 끝난 제품이 세 개 이상이면 실제로 걸린 시간의 평균을, 아니면 미리 정한 표준시간을 씁니다. 이걸 Pace라고 합니다. 다음으로 남은 제품 수에 Pace를 곱해 남은 일을 구합니다. 작업 중인 제품이 예상보다 길어지면 작업자에게 남은 시간을 묻는데, 아까 480분이 그 답입니다. 마지막으로 이 일을 장비와 근무시간 안에 채워 넣습니다. 장비 한 대는 한 번에 하나씩, 17시에 멈췄다가 다음 날 9시에 이어 갑니다. 이걸 유한용량 스케줄링이라고 하고, 그렇게 나온 예상 완료 시각이 Forecast입니다.");
  head(s, "언제 끝나나: 평균 작업시간 × 남은 수 → 일정 배치", "결과로 나온 예상 완료 시각 = Forecast · 출하검사 약속(Gate)보다 늦으면 긴급");
  const cw = 3.85, cy = 2.2, ch = 3.55;
  [["제품 1개당 평균 시간 (Pace)", C.blue], ["남은 일 계산", C.ot], ["일정에 배치 (유한용량)", C.ok]].forEach((c, i) => {
    const x = M + i * (cw + 0.3);
    card(s, x, cy, cw, ch);
    numDot(s, x + 0.2, cy + 0.2, i + 1, c[1]);
    T(s, c[0], { x: x + 0.8, y: cy + 0.24, w: cw - 0.9, h: 0.38, fontSize: 15, bold: true, color: c[1] });
    if (i < 2) T(s, "→", { x: x + cw, y: cy + ch / 2 - 0.3, w: 0.3, h: 0.5, fontSize: 20, color: C.dim, align: "center" });
  });
  // ① pace
  let x = M;
  T(s, "끝난 제품 3개 이상 → 실제 걸린 시간의 평균\n3개 미만 → 미리 정한 표준시간", { x: x + 0.25, y: cy + 0.85, w: cw - 0.45, h: 0.8, fontSize: 12, color: C.text, lineSpacingMultiple: 1.3 });
  [26, 24, 28].forEach((v, k) => { R(s, null, x + 0.35, cy + 1.95 + k * 0.38, (v / 30) * 2.2, 0.26, C.blue, { tr: 30 }); T(s, `${v}분`, { x: x + 0.45 + (v / 30) * 2.2, y: cy + 1.93 + k * 0.38, w: 0.8, h: 0.3, fontSize: 11, color: C.text, fontFace: MONO }); });
  T(s, "예시) 평균 26분/개 = Pace", { x: x + 0.35, y: cy + 3.08, w: cw - 0.5, h: 0.3, fontSize: 11.5, bold: true, color: C.blue });
  // ② remaining
  x = M + cw + 0.3;
  T(s, "남은 제품 수 × Pace", { x: x + 0.25, y: cy + 0.9, w: cw - 0.45, h: 0.45, fontSize: 19, bold: true, color: C.white });
  T(s, "작업 중인 제품은 이미 쓴 시간을 빼고,\n예상보다 길어지면 작업자에게 묻는다", { x: x + 0.25, y: cy + 1.6, w: cw - 0.45, h: 0.7, fontSize: 12, color: C.text, lineSpacingMultiple: 1.3 });
  card(s, x + 0.25, cy + 2.5, cw - 0.5, 0.75, { fill: "2B2410", line: C.ot });
  T(s, "U030: \"앞으로 480분\"", { x: x + 0.25, y: cy + 2.5, w: cw - 0.5, h: 0.75, fontSize: 15, bold: true, color: C.ot, align: "center", valign: "middle" });
  // ③ calendar
  x = M + 2 * (cw + 0.3);
  T(s, "장비 1대 = 한 번에 하나\n17시에 멈추고 다음 날 9시에 이어서", { x: x + 0.25, y: cy + 0.85, w: cw - 0.45, h: 0.8, fontSize: 12, color: C.text, lineSpacingMultiple: 1.3 });
  ["1일차", "2일차"].forEach((d, k) => {
    const yy = cy + 1.9 + k * 0.62, lx = x + 0.95, lw = cw - 1.25;
    T(s, d, { x: x + 0.25, y: yy, w: 0.7, h: 0.35, fontSize: 11, color: C.muted, valign: "middle" });
    R(s, null, lx, yy, lw, 0.35, C.panel2, { round: true, r: 0.04 });
    const blocks = k === 0 ? [[0, 0.33], [0.36, 0.7], [0.73, 1]] : [[0, 0.42]];
    blocks.forEach((b, j) => R(s, null, lx + lw * b[0], yy + 0.05, lw * (b[1] - b[0]) - 0.03, 0.25, k === 1 && j === 0 ? C.ok : C.blue, { round: true, r: 0.03 }));
  });
  T(s, "09시                         17시", { x: x + 0.95, y: cy + 3.15, w: cw - 1.25, h: 0.25, fontSize: 9.5, color: C.dim, fontFace: MONO });
  // bottom
  card(s, M, 6.05, W - 2 * M, 0.7, { fill: C.panel2 });
  T(s, "예상 완료 시각 (Forecast)   vs   출하검사 약속 시각 (Gate)   →   늦으면 긴급, 재계획 후보 계산", { x: M, y: 6.05, w: W - 2 * M, h: 0.7, fontSize: 15, bold: true, color: C.white, align: "center", valign: "middle" });
}

// loop 7-10
const LOOP = [
  ["현장", "작업 · 실적 보고"],
  ["실적 API", "검증 후 저장 · 중복 무시"],
  ["Forecast", "완료 시각 다시 계산"],
  ["위험 판정", "Gate보다 늦으면 긴급"],
  ["재계획 후보", "순서 4규칙 × 추가근무"],
  ["관리자 승인", "사람이 선택 · 계획 버전 +1"],
  ["작업지시 API", "다음에 할 작업 순서"],
];
const LCX = W / 2, LCY = 4.35, LRX = 4.75, LRY = 2.1;
const lpos = (i) => { const a = Math.PI + (i * 2 * Math.PI) / LOOP.length; return [LCX + LRX * Math.cos(a), LCY + LRY * Math.sin(a)]; };
function loopSlide(step, notes, caption) {
  const s = slide("시스템 전체 흐름 · 폐루프", notes, step === 0 ? "fade" : "morph");
  head(s, ["실적이 들어오면 다시 계산한다", "늦을 것 같으면 후보를 만든다", "고르는 건 사람이다", "고른 계획이 현장으로 돌아간다"][step], caption);
  s.addShape(pres.shapes.OVAL, { objectName: "!!ring", x: LCX - LRX, y: LCY - LRY, w: 2 * LRX, h: 2 * LRY, fill: { color: C.bg }, line: { color: C.line, width: 2, dashType: "dash" } });
  const active = [[0, 1, 2], [2, 3, 4], [4, 5], [5, 6, 0]][step];
  LOOP.forEach((n, i) => {
    const [x, y] = lpos(i), w = 2.35, h = 1.0, on = active.includes(i), isNew = step === 3 && (i === 6 || i === 0);
    R(s, "n" + i, x - w / 2, y - h / 2, w, h, on ? C.panel2 : C.panel, { round: true, line: isNew ? C.late : on ? C.blue : C.line, lw: on ? 1.75 : 0.75 });
    T(s, n[0], { ...N("nt" + i), x: x - w / 2, y: y - h / 2 + 0.12, w, h: 0.36, fontSize: 15, bold: true, color: isNew ? C.late : on ? C.white : C.muted, align: "center" });
    T(s, n[1], { ...N("ns" + i), x: x - w / 2 + 0.08, y: y - h / 2 + 0.52, w: w - 0.16, h: 0.4, fontSize: 10.5, color: on ? C.text : C.dim, align: "center" });
  });
  const [px, py] = lpos([1, 3, 5, 6][step]);
  O(s, "pulse", px, py - 0.62, 0.26, C.late);
  T(s, ["실적", "긴급", "v2", "작업지시"][step], { ...N("pulse_t"), x: px - 0.8, y: py - 1.02, w: 1.6, h: 0.28, fontSize: 11, bold: true, color: C.late, align: "center" });
  T(s, step === 3 ? "기말에서 닫은 고리" : "폐루프", { ...N("loop_c"), x: LCX - 1.8, y: LCY - 0.25, w: 3.6, h: 0.5, fontSize: 20, bold: true, color: step === 3 ? C.late : C.dim, align: "center" });
}
loopSlide(0, "이제 전체 흐름입니다. 현장에서 작업 시작, 완료, 합격, 불합격이 들어오면 서버가 확인해 저장하고, 방금 본 방법으로 완료 시각을 다시 계산합니다.", "작업 시작·완료·합격·불합격 → 서버가 검증해 저장 → Forecast 다시 계산");
loopSlide(1, "예상 완료가 Gate를 넘으면 긴급으로 판정하고, 해결 후보를 계산합니다.", "예상 완료가 Gate를 넘으면 긴급 → 재계획 후보 계산");
loopSlide(2, "후보를 고르는 건 사람입니다. 관리자가 비교해서 승인해야만 계획이 바뀌고, 계획 버전이 하나 올라갑니다.", "자동 적용 없음 · 관리자가 승인해야 계획 버전이 올라간다");
loopSlide(3, "기말에서 새로 이은 부분이 여기입니다. 승인된 계획이 작업지시로 현장에 내려가고, 현장은 그 순서대로 다음 일을 합니다. 그 결과가 다시 실적으로 들어오니 고리가 닫힙니다. 이걸 폐루프라고 합니다. 현장 역할은 가상 현장이 맡았고, Pico 단말은 연동하지 못했습니다.", "승인 계획 → 작업지시 API → 현장이 그 순서대로 작업 → 다시 실적 · Pico 단말은 미연동");

// 11 candidates
{
  const s = slide("재계획 후보", "후보는 이렇게 만듭니다. 순서를 정하는 규칙이 네 가지입니다. FCFS는 먼저 들어온 묶음부터, 은행 번호표 순서입니다. EDD는 약속 시각이 빠른 묶음부터, 마감이 급한 숙제부터 하는 것과 같습니다. Slack은 남은 여유가 가장 적은 묶음부터, CR은 남은 시간에 비해 남은 일이 많은 묶음부터입니다. 여기에 평일 17시부터 19시까지 추가근무하는 안을 하나씩 더해 후보는 여덟 개입니다. 순위는 늦는 묶음 수, 총 지연시간, 추가근무 시간, 계획 변경량 순서로 비교합니다.");
  head(s, "순서 규칙 4개 × 추가근무 = 후보 8개", "앞 기준이 같을 때만 다음 기준을 본다 · 지연이 같으면 추가근무가 적은 안이 앞선다");
  [["FCFS", "먼저 들어온 묶음부터", "은행 번호표"], ["EDD", "약속(Gate)이 빠른 묶음부터", "마감 급한 숙제부터"], ["Slack", "여유가 가장 적은 묶음부터", "여유 = 남은 시간 − 남은 일"], ["CR", "남은 시간 대비 일이 많은 묶음부터", "비율 = 남은 시간 ÷ 남은 일"]].forEach((r, i) => {
    const y = 2.15 + i * 1.02;
    card(s, M, y, 4.4, 0.88);
    T(s, r[0], { x: M + 0.2, y: y + 0.1, w: 1.1, h: 0.38, fontSize: 16, bold: true, color: C.white });
    T(s, r[1], { x: M + 1.3, y: y + 0.12, w: 3.0, h: 0.35, fontSize: 12.5, bold: true, color: C.text });
    T(s, r[2], { x: M + 1.3, y: y + 0.5, w: 3.0, h: 0.28, fontSize: 10.5, color: C.muted });
    card(s, M + 4.55, y, 2.0, 0.88, { fill: "2B2410", line: C.ot });
    T(s, "+ 추가근무", { x: M + 4.55, y: y + 0.1, w: 2.0, h: 0.38, fontSize: 13, bold: true, color: C.ot, align: "center" });
    T(s, "평일 17~19시", { x: M + 4.55, y: y + 0.5, w: 2.0, h: 0.28, fontSize: 10.5, color: C.muted, align: "center" });
  });
  const fx = 7.75;
  T(s, "순위 기준", { x: fx, y: 2.15, w: 4, h: 0.35, fontSize: 13, bold: true, color: C.muted });
  ["늦는 묶음 수", "총 지연시간", "추가근무 시간", "계획 변경량"].forEach((c, i) => {
    const w = 4.9 - i * 0.55, x = fx + (4.9 - w) / 2, y = 2.6 + i * 0.86;
    R(s, null, x, y, w, 0.7, i === 2 ? "2B2410" : C.panel2, { round: true, line: i === 2 ? C.ot : C.line });
    T(s, `${i + 1}  ${c}`, { x, y, w, h: 0.7, fontSize: 15, bold: true, color: i === 2 ? C.ot : C.white, align: "center", valign: "middle" });
  });
  T(s, "추가근무 시간 = 17시부터 그날 마지막 작업이 끝날 때까지 (중간 대기 포함) · 후보 8개 + 계획 유지 1 = 실험의 9가지 방법", { x: M, y: 6.35, w: 12.1, h: 0.3, fontSize: 11.5, color: C.muted });
}

// 12-13 demo timeline (night collapsed: 10/22 13:00–19:00 | 10/23 09:00–15:00)
const TX0 = M + 0.3, TXW = W - 2 * M - 0.6, GAP = 0.7, HALF = (TXW - GAP) / 2;
const tX = (day, hh, mm = 0) => { const h = hh + mm / 60; return day === 22 ? TX0 + (HALF * (h - 13)) / 6 : TX0 + HALF + GAP + (HALF * (h - 9)) / 6; };
function demoTimeline(ot) {
  const s = slide("시연 상황 다시 보기", ot
    ? "그래서 추가근무 후보가 필요합니다. 오늘 17시부터 19시까지 2시간을 더 하면 튜닝이 다음 날 11시 17분에 끝나고, 지연은 2시간 57분으로 줄어 1위가 됩니다. 관리자가 승인하면 계획은 버전 2가 됩니다. 하지만 약속 전에 추가근무를 할 수 있는 저녁은 오늘 하루뿐이라, 여전히 긴급입니다."
    : "그럼 왜 순서로는 안 줄었을까요? U030은 튜닝에 480분이 더 필요합니다. 오늘 17시까지 3시간 43분을 하고, 나머지 4시간 17분은 내일 9시부터 해서 13시 17분에 끝납니다. 마무리 조립과 최종 시험 40분을 더하면 13시 57분, 약속 9시보다 4시간 57분 늦습니다. 늦어진 게 이 제품 자체라서, 다른 묶음 순서를 바꿔도 이 시각은 그대로입니다.", ot ? "morph" : "fade");
  head(s, ot ? "2시간 더 일해서 2시간 줄였다. 그래도 긴급" : "왜 순서를 바꿔도 안 줄었나", ot ? "추가근무 후보의 예상 일정 · 10/22 17~19시 · 승인하면 계획 v2 · 근무달력에 저장" : "시스템이 계산한 예상 일정 (Forecast) · U030은 이미 작업 중이라 중간에 멈추지 않는다");
  const ty = 3.0;
  // day panels
  T(s, "10/22 (오늘)", { x: TX0, y: 1.98, w: 3, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  T(s, "10/23 (내일)", { x: TX0 + HALF + GAP, y: 1.98, w: 3, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  R(s, null, tX(22, 13), ty - 0.15, tX(22, 17) - tX(22, 13), 1.6, C.panel);
  R(s, "otzone", tX(22, 17), ty - 0.15, tX(22, 19) - tX(22, 17), 1.6, ot ? "2B2410" : C.bg, { line: ot ? C.ot : C.line, lw: 0.75 });
  T(s, ot ? "추가근무 17~19시" : "근무 끝", { ...N("otzone_t"), x: tX(22, 17), y: ty - 0.45, w: tX(22, 19) - tX(22, 17), h: 0.28, fontSize: 10.5, bold: true, color: ot ? C.ot : C.dim, align: "center" });
  R(s, null, tX(23, 9), ty - 0.15, tX(23, 15) - tX(23, 9), 1.6, C.panel);
  T(s, "밤", { x: TX0 + HALF, y: ty + 0.45, w: GAP, h: 0.4, fontSize: 12, color: C.dim, align: "center" });
  T(s, "≈", { x: TX0 + HALF, y: ty + 0.05, w: GAP, h: 0.4, fontSize: 16, color: C.dim, align: "center" });
  [[22, 13], [22, 15], [22, 17], [22, 19], [23, 9], [23, 11], [23, 13], [23, 15]].forEach(([d, h]) => T(s, `${h}시`, { x: tX(d, h) - 0.35, y: ty + 1.5, w: 0.7, h: 0.25, fontSize: 10, color: C.muted, align: "center", fontFace: MONO }));
  // now marker
  L(s, null, tX(22, 13, 17), ty - 0.3, 0, 1.9, C.blue, { w: 1.5 });
  T(s, "지금 13:17", { x: tX(22, 13, 17) - 0.2, y: ty - 0.6, w: 1.4, h: 0.28, fontSize: 10.5, bold: true, color: C.blue });
  // U030 tuning blocks
  const endA = ot ? [22, 19] : [22, 17], endB = ot ? [23, 11, 17] : [23, 13, 17], fin = ot ? [23, 11, 57] : [23, 13, 57];
  R(s, "tuneA", tX(22, 13, 17), ty + 0.1, tX(...endA) - tX(22, 13, 17), 0.5, C.late, { round: true, r: 0.05 });
  T(s, ot ? "튜닝 5시간 43분" : "튜닝 3시간 43분", { ...N("tuneA_t"), x: tX(22, 13, 17), y: ty + 0.1, w: tX(...endA) - tX(22, 13, 17), h: 0.5, fontSize: 12, bold: true, color: C.bg, align: "center", valign: "middle" });
  R(s, "tuneB", tX(23, 9), ty + 0.1, tX(...endB) - tX(23, 9), 0.5, C.late, { round: true, r: 0.05 });
  T(s, ot ? "튜닝 2시간 17분" : "튜닝 4시간 17분", { ...N("tuneB_t"), x: tX(23, 9), y: ty + 0.1, w: tX(...endB) - tX(23, 9), h: 0.5, fontSize: 12, bold: true, color: C.bg, align: "center", valign: "middle" });
  R(s, "post", tX(...endB), ty + 0.75, tX(...fin) - tX(...endB), 0.4, C.ok, { round: true, r: 0.04 });
  T(s, "마무리·시험 40분", { ...N("post_t"), x: tX(...endB) - 2.65, y: ty + 0.75, w: 2.55, h: 0.4, fontSize: 11, bold: true, color: C.ok, valign: "middle", align: "right" });
  // gate + delay
  L(s, null, tX(23, 9), ty - 0.3, 0, 2.0, C.white, { w: 2.5 });
  T(s, "약속(Gate) 09:00", { x: tX(23, 9) - 0.75, y: ty - 0.6, align: "center", w: 1.5, h: 0.28, fontSize: 10.5, bold: true, color: C.white });
  R(s, "delay", tX(23, 9), ty + 1.95, tX(...fin) - tX(23, 9), 0.1, C.late);
  T(s, ot ? "예상 2시간 57분 늦음 (177분)" : "예상 4시간 57분 늦음 (297분)", { ...N("delay_t"), x: tX(23, 9), y: ty + 2.1, w: 4.5, h: 0.4, fontSize: 17, bold: true, color: C.late });
  // bottom message
  if (!ot) {
    card(s, M, 6.0, W - 2 * M, 0.75, { fill: C.panel2 });
    T(s, "늦어진 것은 U030 자체 → 다른 묶음의 순서를 바꿔도 13:57은 그대로 (EDD·Slack·CR = 297분)", { x: M, y: 6.0, w: W - 2 * M, h: 0.75, fontSize: 14, bold: true, color: C.white, align: "center", valign: "middle" });
  } else {
    [["EDD · Slack · CR + 추가근무", "177분 · 추가 120분 · 공동 1위", C.ok], ["FCFS + 추가근무", "177분 · 추가 360분 · 4위", C.ot]].forEach((r, i) => {
      const x = M + i * 6.15;
      card(s, x, 6.0, 5.95, 0.75, { fill: C.panel2 });
      T(s, r[0], { x: x + 0.25, y: 6.0, w: 2.9, h: 0.75, fontSize: 13.5, bold: true, color: r[2], valign: "middle" });
      T(s, r[1], { x: x + 2.9, y: 6.0, w: 2.85, h: 0.75, fontSize: 12.5, color: C.text, valign: "middle", align: "right" });
    });
  }
}
demoTimeline(false);
demoTimeline(true);

// 14 video
{
  const s = slide("실행 시연", "실제 화면입니다. 작업자 화면에서 U030의 남은 시간 480분을 입력하면, 생산현황에서 긴급 LOT가 하나로 바뀝니다. 재계획 화면에서 후보와 순위를 계산하고, 1위인 EDD 추가근무안을 관리자가 직접 승인합니다. 계획이 버전 2로 올라가지만, LOT-001은 여전히 긴급으로 남습니다.");
  head(s, "프로그램 시연 (약 60초)", "실적 입력 → 긴급 판정 → 후보 비교 → 관리자 승인 → 계획 v2 → 현장 작업지시가 바뀐다");
  R(s, null, 1.4, 2.0, W - 2.8, 4.95, C.panel, { round: true, line: C.line });
  O(s, null, W / 2, 4.2, 1.2, C.late);
  s.addShape(pres.shapes.ISOSCELES_TRIANGLE, { x: W / 2 - 0.2, y: 3.92, w: 0.5, h: 0.56, rotate: 90, fill: { color: C.bg }, line: { color: C.bg } });
  T(s, "MP4 삽입 영역 · 약 60초 · 자동 재생 · 소리 없음 (발표자가 설명)", { x: 1.4, y: 5.05, w: W - 2.8, h: 0.4, fontSize: 16, bold: true, color: C.white, align: "center" });
}

// ================================================================ ACT 3 — 810번 실험
// 15 design
{
  const s = slide("반복 실험", "그런데 한 번 잘 된 건 우연일 수도 있습니다. 그래서 같은 상황을 여러 번 만들어 비교했습니다. 조건은 세 가지입니다. 작업시간이 평소처럼 조금씩 들쭉날쭉한 날, 모든 작업이 20% 느린 날, 가끔 작업이 멈추거나 불합격으로 다시 하는 날입니다. 방법은 계획 유지 하나와, 규칙 네 개에 추가근무를 켜고 끈 여덟 개, 모두 아홉 가지입니다. 각각 30번씩, 모두 810번입니다. 같은 번호의 실행에서는 모든 방법이 똑같은 작업시간을 받습니다. 같은 시험지로 비교하는 것과 같습니다.");
  head(s, "여기부터 별도의 반복 실험: 810번", "시연(480분 입력, 297분)과 다른 실험 · 시작 10/22 13:00 · 같은 번호(seed) = 같은 실제 작업시간 → 공정한 비교");
  const eq = [["3", "조건", C.white], ["×", "", C.dim], ["9", "방법", C.white], ["×", "", C.dim], ["30", "반복", C.white], ["=", "", C.dim], ["810", "실행", C.late]];
  let ex = M + 0.3;
  eq.forEach((e) => {
    const w = e[1] ? 1.75 : 0.55;
    T(s, e[0], { x: ex, y: 2.05, w, h: 1.0, fontSize: e[1] ? 56 : 36, bold: true, align: "center", valign: "middle", color: e[2], fontFace: MONO });
    if (e[1]) T(s, e[1], { x: ex, y: 3.05, w, h: 0.3, fontSize: 12, align: "center", color: C.muted });
    ex += w + 0.06;
  });
  card(s, 8.15, 2.1, W - M - 8.15, 1.3, { fill: C.panel2 });
  T(s, "방법 9가지", { x: 8.35, y: 2.2, w: 4, h: 0.3, fontSize: 12, bold: true, color: C.muted });
  T(s, "계획 유지 1 + 앞의 후보 8개", { x: 8.35, y: 2.55, w: 4.4, h: 0.4, fontSize: 15, bold: true, color: C.white });
  T(s, "후보 8 = 규칙 4 × 추가근무 끔·켬 2", { x: 8.35, y: 2.98, w: 4.4, h: 0.3, fontSize: 11, color: C.muted });
  [["평소", "작업시간이 조금씩 들쭉날쭉", "표준시간 × 로그정규 잡음 σ=0.15\n(±15% 한계 아님) · 작업자 추정 오차 σ=0.2", C.blue],
   ["느린 날", "모든 작업이 20% 느림", "평균 1.2배 (작업시간 +20%)", C.ot],
   ["돌발 지연·재작업", "일부 작업이 4시간 더 · 불합격 재작업", "작업 시도 3%에 +240분 (작업시간 연장으로 흉내,\n실제 HOLD 이벤트 아님) · 최종시험 8% 불합격", C.late]].forEach((c, i) => {
    const x = M + i * 4.1, y = 3.85, w = 3.9;
    card(s, x, y, w, 2.45);
    R(s, null, x, y, w, 0.06, c[3]);
    T(s, c[0], { x: x + 0.22, y: y + 0.22, w: w - 0.4, h: 0.38, fontSize: 17, bold: true, color: c[3] });
    T(s, c[1], { x: x + 0.22, y: y + 0.7, w: w - 0.4, h: 0.35, fontSize: 13.5, bold: true, color: C.white });
    T(s, c[2], { x: x + 0.22, y: y + 1.2, w: w - 0.4, h: 1.1, fontSize: 11, color: C.muted, lineSpacingMultiple: 1.25 });
  });
  T(s, "평소 · 느린 날 · 돌발 지연·재작업 = 원자료의 NORMAL · SLOW · STOPPAGE_REWORK (보고서: 정상 · 작업시간 +20% · 작업정지·재작업)", { x: M, y: 6.5, w: 12, h: 0.3, fontSize: 10.5, color: C.dim });
}
// 16 virtual roles
{
  const s = slide("실험 속 현장과 관리자", "810번을 사람이 직접 할 수는 없어서, 두 역할을 프로그램이 맡았습니다. 가상 현장은 시스템이 모르는 실제 작업시간으로 일하고, 실적을 같은 API로 보냅니다. 가상 관리자는 시스템이 긴급이라고 할 때만 후보를 받아, 미리 정한 규칙의 후보를 고릅니다. 추가근무안은 순위가 더 좋을 때만 고릅니다. 그리고 사람이 누르는 것과 같은 승인 API를 호출합니다. 실제 화면에서는 사람이 직접 비교하고 승인합니다.");
  head(s, "810번은 프로그램이 대신 일하고 승인했다", "시스템(서버)은 그대로 · 사람 역할 두 개만 프로그램으로 바꿨다");
  const by = 2.2, bh = 2.35;
  const bw = 3.25;
  card(s, M, by, bw, bh, { line: C.blue, lw: 1.5 });
  T(s, "가상 현장", { x: M + 0.25, y: by + 0.2, w: 3, h: 0.4, fontSize: 17, bold: true, color: C.blue });
  T(s, "시스템이 모르는 ‘실제 작업시간’으로 일한다\n작업지시가 정한 순서대로만 작업\n길어지면 남은 시간을 추정해 입력", { x: M + 0.25, y: by + 0.75, w: bw - 0.4, h: 1.5, fontSize: 11.5, color: C.text, lineSpacingMultiple: 1.35 });
  const sx = M + bw + 1.35, sw = W - 2 * M - 2 * bw - 2.7;
  card(s, sx, by, sw, bh, { fill: C.panel2, line: C.white, lw: 1.5 });
  T(s, "우리 시스템", { x: sx, y: by + 0.2, w: sw, h: 0.4, fontSize: 17, bold: true, color: C.white, align: "center" });
  T(s, "실적 저장 · Forecast\n위험 판정 · 후보 8개 계산\n승인 → 계획 버전 · 근무달력\n작업지시", { x: sx + 0.2, y: by + 0.75, w: sw - 0.4, h: 1.5, fontSize: 11.5, color: C.text, align: "center", lineSpacingMultiple: 1.35 });
  const vx = W - M - bw;
  card(s, vx, by, bw, bh, { line: C.ot, lw: 1.5 });
  T(s, "가상 관리자", { x: vx + 0.25, y: by + 0.2, w: 3, h: 0.4, fontSize: 17, bold: true, color: C.ot });
  T(s, "긴급일 때만 후보를 요청\n정해진 규칙(예: EDD)의 후보 선택\n추가근무안은 순위가 더 좋을 때만", { x: vx + 0.25, y: by + 0.75, w: bw - 0.4, h: 1.5, fontSize: 11.5, color: C.text, lineSpacingMultiple: 1.35 });
  [[M + bw, sx, by + 0.7, "실적 API →", C.blue], [M + bw, sx, by + 1.6, "← 작업지시 API", C.blue], [sx + sw, vx, by + 0.7, "긴급·후보 →", C.ot], [sx + sw, vx, by + 1.6, "← 승인 API", C.ot]].forEach((a) => {
    L(s, null, a[0] + 0.05, a[2] + 0.35, a[1] - a[0] - 0.1, 0, a[4], { w: 1.25 });
    T(s, a[3], { x: a[0], y: a[2], w: a[1] - a[0], h: 0.3, fontSize: 10.5, bold: true, color: a[4], align: "center" });
  });
  [["실제 관리자 화면", "사람이 후보 8개를 비교해 직접 고르고 승인", C.white], ["810회 반복 실험", "가상 관리자가 같은 규칙으로 같은 승인 API를 호출 → 방법끼리 공정하게 비교", C.ot]].forEach((c, i) => {
    const x = M + i * 6.15;
    card(s, x, 5.0, 5.95, 1.35, { fill: C.panel2 });
    T(s, c[0], { x: x + 0.25, y: 5.15, w: 5.4, h: 0.35, fontSize: 14, bold: true, color: c[2] });
    T(s, c[1], { x: x + 0.25, y: 5.6, w: 5.5, h: 0.6, fontSize: 12, color: C.text });
  });
  T(s, "근거: src/production_control/sim/manager.py · 승인은 화면과 같은 서버 승인 경로로 들어간다", { x: M, y: 6.55, w: 12, h: 0.3, fontSize: 10.5, color: C.dim });
}
// 17-18 conflict chips
function chipSlide(stage) {
  const s = slide("실험의 출발점", stage === 0
    ? "실험의 출발점은 10월 22일 13시이고, 계획은 들어온 순서, LOT-001, 002, 003입니다. 그런데 약속 시각은 LOT-003이 10월 28일, LOT-002가 11월 6일입니다. 약속이 빠른 LOT-003이 병목 장비를 늦게 받는, 재계획이 고칠 수 있도록 일부러 만든 상황입니다."
    : "EDD는 약속이 빠른 LOT-003을 LOT-002보다 앞으로 보냅니다. 장비를 늘리는 게 아니라 장비를 쓰는 순서만 바꾸는 겁니다. 이 움직임을 기억해 주세요.", stage === 0 ? "fade" : "morph");
  head(s, stage === 0 ? "출하검사 약속이 빠른 LOT-003이 뒤에 서 있다" : "EDD: 출하검사 약속이 빠른 묶음부터", stage === 0 ? "계획 유지(KEEP) = 들어온 순서 그대로 병목 장비를 쓴다" : "LOT-003(10/28)이 LOT-002(11/06) 앞으로 · 장비 수는 그대로");
  T(s, "튜닝·최종시험 장비를 쓰는 순서", { ...N("ordlab"), x: M, y: 2.3, w: 6, h: 0.35, fontSize: 14, bold: true, color: C.muted });
  const lots = [["LOT-001", "출하검사 약속 10/23", C.text], ["LOT-002", "출하검사 약속 11/06", C.late], ["LOT-003", "출하검사 약속 10/28", C.ok]];
  const order = stage === 0 ? [0, 1, 2] : [0, 2, 1];
  lots.forEach((l, i) => {
    const slot = order.indexOf(i), x = M + slot * 4.1, y = 2.9;
    R(s, "lot" + i, x, y, 3.7, 1.6, C.panel, { round: true, line: l[2], lw: 2 });
    T(s, l[0], { ...N("lott" + i), x, y: y + 0.25, w: 3.7, h: 0.55, fontSize: 26, bold: true, color: l[2], align: "center" });
    T(s, l[1], { ...N("lots" + i), x, y: y + 0.95, w: 3.7, h: 0.4, fontSize: 15, color: C.muted, align: "center" });
    if (slot < 2) T(s, "→", { x: x + 3.7, y: y + 0.5, w: 0.4, h: 0.6, fontSize: 24, color: C.dim, align: "center" });
  });
  T(s, stage === 0 ? "LOT-003은 10/28이 약속인데 11/06이 약속인 LOT-002를 기다린다" : "여유가 많은 LOT-002는 뒤로 가도 약속(11/06) 안에 끝난다", { ...N("chip_msg"), x: M, y: 5.0, w: 12, h: 0.45, fontSize: 18, bold: true, color: stage === 0 ? C.late : C.ok });
  T(s, "LOT-001은 막바지 작업만 남아 있다 · 의도적으로 만든 충돌이므로 EDD의 일반적 우월성은 주장하지 않는다", { x: M, y: 6.3, w: 12, h: 0.3, fontSize: 11, color: C.dim });
}
chipSlide(0);
chipSlide(1);
// dots
const ORDERED = [];
CONDS.forEach((c) => CFGS.forEach((k) => RUNS.filter((r) => r.cond === c && r.cfg === k).sort((a, b) => a.seed - b.seed).forEach((r) => ORDERED.push(r))));
const WF = { gx: M + 1.8, top: 2.3, ds: 0.15, cellH: 1.3 };
WF.cellW = (W - M - WF.gx) / 9;
const wafflePos = (idx) => {
  const ci = Math.floor(idx / 270), k = Math.floor((idx % 270) / 30), n = idx % 30;
  return [WF.gx + k * WF.cellW + (n % 6) * WF.ds, WF.top + ci * WF.cellH + Math.floor(n / 6) * WF.ds];
};
const CLs = { NORMAL: "평소", SLOW: "느린 날", STOPPAGE_REWORK: "돌발 지연·재작업" };
const waffleFrame = (s) => {
  CFGS.forEach((k, j) => {
    const ot = k.endsWith("+OT");
    T(s, ot ? "+OT" : k, { x: WF.gx + j * WF.cellW, y: WF.top - 0.4, w: 6 * WF.ds, h: 0.3, fontSize: ot ? 10 : 11, bold: true, color: ot ? C.ot : C.white, align: "center" });
  });
  CONDS.forEach((c, i) => T(s, CLs[c], { x: M, y: WF.top + i * WF.cellH + 0.25, w: 1.7, h: 0.5, fontSize: 13, bold: true, color: C.text, valign: "middle" }));
};
// 19 grey
{
  const s = slide("810번, 한 점이 한 번", "810번의 실행을 점 하나씩으로 놓겠습니다.");
  head(s, "810번의 실행", "점 하나 = 실행 1회");
  if (BACKUP) {
    waffleFrame(s);
    ORDERED.forEach((r, i) => { const [x, y] = wafflePos(i); s.addShape(pres.shapes.RECTANGLE, { x, y, w: WF.ds - 0.03, h: WF.ds - 0.03, fill: { color: C.grey }, line: { color: C.grey, width: 0 } }); });
  } else {
    const cols = 54, ds = 0.17, x0 = (W - cols * ds) / 2, y0 = 2.6;
    ORDERED.forEach((r, i) => s.addShape(pres.shapes.RECTANGLE, { objectName: "!!d" + i, x: x0 + (i % cols) * ds, y: y0 + Math.floor(i / cols) * ds, w: ds - 0.04, h: ds - 0.04, fill: { color: C.grey }, line: { color: C.grey, width: 0 } }));
    T(s, "810", { ...N("n810"), x: W / 2 - 2, y: 5.4, w: 4, h: 1.0, fontSize: 54, bold: true, color: C.white, align: "center", fontFace: MONO });
  }
}
// 20 waffle
{
  const s = slide("810번, 한 점이 한 번", "조건과 방법별로 나누면 이렇습니다. 주황은 출하검사에 늦게 들어간 실행, 초록은 늦지 않은 실행입니다. 계획을 유지하면 세 조건 모두 30번 전부 늦었습니다. EDD는 평소와 느린 날에는 한 번도 늦지 않았고, 멈추는 날에는 30번 중 5번 늦었습니다.", BACKUP ? "fade" : "morph");
  head(s, "어디서 늦었나", "주황 = 출하검사에 늦게 들어간 실행 · 초록 = 늦지 않음 · 같은 위치 = 같은 번호(seed)");
  waffleFrame(s);
  CONDS.forEach((c, i) => CFGS.forEach((k, j) => {
    const late = lateCount(c, k);
    T(s, `${late}/30`, { x: WF.gx + j * WF.cellW, y: WF.top + i * WF.cellH + 5 * WF.ds + 0.06, w: 6 * WF.ds, h: 0.22, fontSize: 9, color: late ? C.late : C.ok, align: "center", fontFace: MONO });
  }));
  ORDERED.forEach((r, i) => {
    const [x, y] = wafflePos(i), col = r.delay > 0 ? C.late : C.ok;
    s.addShape(pres.shapes.RECTANGLE, { objectName: BACKUP ? undefined : "!!d" + i, x, y, w: WF.ds - 0.03, h: WF.ds - 0.03, fill: { color: col }, line: { color: col, width: 0 } });
  });
  [0, 3].forEach((j) => s.addShape(pres.shapes.RECTANGLE, { x: WF.gx + j * WF.cellW - 0.08, y: WF.top - 0.45, w: 6 * WF.ds + 0.13, h: 3 * WF.cellH + 0.25, fill: { type: "none" }, line: { color: C.white, width: 1.5, dashType: "dash" } }));
  T(s, "먼저 계획 유지와 EDD만 비교: 주황(늦음) → 초록(지킴) · EDD는 돌발 지연·재작업 조건에서만 5/30 늦음", { x: M, y: 6.35, w: 12.1, h: 0.35, fontSize: 12, bold: true, color: C.text });
}
// 21 numbers
{
  const s = slide("결과 ① 얼마나 줄었나", `평균으로 보면 계획 유지는 ${fmt(m("NORMAL", "KEEP"))}분, ${fmt(m("SLOW", "KEEP"))}분, ${fmt(m("STOPPAGE_REWORK", "KEEP"))}분 늦었고, EDD는 0분, 0분, ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분이었습니다. 멈추는 날 5번은 지연이 남았으니, 없앴다가 아니라 크게 줄였다고 말씀드립니다. 여기서 지연은 출하검사 약속 기준이고, 고객 납기 지각은 출하검사가 3근무일 걸린다고 가정하면 810번 모두 0이었습니다.`);
  head(s, "재계획은 출하검사 진입 지연을 크게 줄였다", "한 번 실행에서 늦은 묶음들의 지연을 더한 값의 30회 평균 (분) · 묶음별 max(0, 생산 완료 − 출하검사 약속)");
  CONDS.forEach((c, i) => {
    const y = 2.2 + i * 1.3;
    card(s, M, y, W - 2 * M, 1.12);
    T(s, CLs[c], { x: M + 0.3, y, w: 2.6, h: 1.12, fontSize: 18, bold: true, color: C.text, valign: "middle" });
    T(s, fmt(m(c, "KEEP")), { x: M + 3.0, y, w: 3.1, h: 1.12, fontSize: 44, bold: true, color: C.late, valign: "middle", align: "right", fontFace: MONO });
    T(s, "→", { x: M + 6.25, y, w: 0.8, h: 1.12, fontSize: 32, color: C.dim, valign: "middle", align: "center" });
    const e = m(c, "EDD");
    T(s, e < 0.05 ? "0" : fmt(e, 1), { x: M + 7.1, y, w: 2.6, h: 1.12, fontSize: 44, bold: true, color: C.ok, valign: "middle", fontFace: MONO });
    T(s, `분 · EDD 늦은 횟수 ${lateCount(c, "EDD")}/30`, { x: M + 9.5, y, w: 2.6, h: 1.12, fontSize: 13, color: C.muted, valign: "middle" });
  });
  card(s, M, 6.15, W - 2 * M, 0.6, { fill: C.panel2 });
  T(s, "늦음 = 출하검사 시작 약속을 넘김 (고객에게 늦게 보냈다는 뜻 아님) · 고객 납기 지각은 810회 모두 0 (출하검사 3근무일 가정)", { x: M + 0.25, y: 6.15, w: W - 2 * M - 0.5, h: 0.6, fontSize: 12.5, color: C.text, valign: "middle" });
}
// 22-23 gantt
const GT0 = Date.parse("2026-10-22T09:00"), GT1 = Date.parse("2026-10-29T00:00");
const GX = M + 2.0, GW = W - M - GX - 0.1;
const GXf = (iso) => GX + (GW * (Date.parse(iso) - GT0)) / (GT1 - GT0);
const PROCS = ["튜닝", "마무리 조립", "최종 성능시험"];
const PCOL = { "튜닝": C.late, "마무리 조립": C.blue, "최종 성능시험": C.ok };
function ganttSlide(layer, notes) {
  const keep = layer === "현재 Forecast";
  const s = slide("결과 ② 왜 줄었나", notes, keep ? "fade" : "morph");
  head(s, keep ? "계획을 유지하면 LOT-003이 약속을 넘는다" : "EDD는 LOT-003을 앞당긴다", keep ? "실험 시작(10/22 13:00)에 계산한 예상 일정 (Forecast) · 계획 유지" : "같은 시점에 계산한 EDD 재계획안의 예상 일정 · 바뀐 것은 병목 장비를 쓰는 순서뿐");
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
    T(s, `약속 ${gate.at.slice(5, 10).replace("-", "/")} ${gate.at.slice(11)}`, { x: M + 0.15, y: y0 + 0.55, w: 1.8, h: 0.25, fontSize: 10, color: C.muted });
    PROCS.forEach((p, k) => {
      const b = GANTT.bars.find((x) => x.lot_label === lot && x.layer === layer && x.process_label === p);
      if (!b) return;
      const xa = GXf(b.start), xb = Math.max(GXf(b.end), xa + 0.05);
      R(s, `g_${lot}_${k}`, xa, y0 + 0.15 + k * 0.3, Math.min(xb, GX + GW) - xa, 0.22, PCOL[p], { round: true, r: 0.04 });
    });
    if (lot === "LOT-003") s.addShape(pres.shapes.RECTANGLE, { x: M - 0.04, y: y0 - 0.04, w: W - 2 * M + 0.08, h: laneH - 0.04, fill: { type: "none" }, line: { color: keep ? C.late : C.ok, width: 1.75 } });
    if (Date.parse(gate.at) < GT1) L(s, "gate" + i, GXf(gate.at), y0 + 0.02, 0, laneH - 0.16, C.white, { w: 2.25 });
    else T(s, "약속 11/06 → 그림 밖", { x: GX + GW - 2.2, y: y0 + 0.05, w: 2.2, h: 0.22, fontSize: 9.5, color: C.muted, align: "right" });
  });
  const tb = GANTT.bars.find((x) => x.lot_label === "LOT-003" && x.layer === layer && x.process_label === "최종 성능시험");
  const label = `LOT-003 최종시험 ${tb.end.slice(5, 10).replace("-", "/")} ${tb.end.slice(11)} 완료 예상${keep ? " → 약속 10/28 09:00 초과" : " · 약속 안쪽"}`;
  T(s, label, { ...N("g_label"), x: keep ? GXf(tb.end) - 6.6 : GXf(tb.end) + 0.15, y: top - 0.42, w: 6.4, h: 0.3, fontSize: 12, bold: true, color: keep ? C.late : C.ok, align: keep ? "right" : "left" });
  PROCS.forEach((p, k) => { R(s, null, M + k * 2.0, 6.78, 0.3, 0.14, PCOL[p]); T(s, p, { x: M + 0.4 + k * 2.0, y: 6.71, w: 1.5, h: 0.28, fontSize: 10.5, color: C.muted }); });
  T(s, "흰 선 = 출하검사 약속 · 막대 = 그 공정의 첫 제품 시작 ~ 마지막 제품 종료 범위\n(중간 대기·야간 포함 → 장비를 계속 쓴다는 뜻 아님)", { x: M + 5.6, y: 6.6, w: 6.6, h: 0.5, fontSize: 10.5, color: C.muted, align: "right" });
}
ganttSlide("현재 Forecast", "왜 줄었는지 일정표로 보겠습니다. 흰 선이 출하검사 약속입니다. 계획을 유지하면 LOT-003의 최종 시험이 10월 28일 12시 15분에 끝나 약속 9시를 넘습니다.");
ganttSlide("재계획안", "EDD로 바꾸면 LOT-003이 앞으로 당겨져 10월 23일에 끝나고, 여유가 많은 LOT-002가 뒤로 갑니다. 아까 본 순서 바꾸기가 일정에서는 이렇게 보입니다. 다만 일부러 만든 충돌이라, EDD가 어디서나 최선이라는 뜻은 아닙니다.");
// 24-25 overtime
const OTC = [["STOPPAGE_REWORK", "CR"], ["STOPPAGE_REWORK", "EDD"], ["SLOW", "CR"], ["NORMAL", "FCFS"], ["NORMAL", "CR"], ["NORMAL", "EDD"]];
function otSlide(on, notes) {
  const s = slide("결과 ③ 추가근무", notes, on ? "morph" : "fade");
  head(s, on ? "남은 지연엔 효과, 없는 지연엔 부담" : "추가근무를 끈 상태", on ? "켰을 때 평균 지연(●) · 오른쪽 = 실행당 추가 가동시간 합계의 평균 (하루 최대 120분, 여러 날 합산) · n=30" : "방법별 평균 출하검사 진입 지연 (n=30)");
  const lx = M + 2.8, lw = 5.4, max = 220, ox = lx + lw + 1.1, ow = W - M - ox - 0.75, omax = 400;
  T(s, "출하검사 진입 지연 (분)", { x: lx, y: 1.95, w: lw, h: 0.28, fontSize: 11, bold: true, color: C.muted });
  if (on) T(s, "추가 가동시간 (분)", { x: ox, y: 1.95, w: 3, h: 0.28, fontSize: 11, bold: true, color: C.ot });
  [0, 100, 200].forEach((v) => { const x = lx + (lw * v) / max; L(s, null, x, 2.3, 0, 3.85, C.line, { w: 0.75 }); T(s, String(v), { x: x - 0.3, y: 6.18, w: 0.6, h: 0.22, fontSize: 9.5, color: C.dim, align: "center", fontFace: MONO }); });
  OTC.forEach(([c, p], i) => {
    const y = 2.6 + i * 0.6, a = m(c, p), b = m(c, p + "+OT"), ot = m(c, p + "+OT", "overtime_minutes"), waste = a < 0.05;
    T(s, `${CLs[c]} · ${p}`, { x: M, y: y - 0.16, w: 2.7, h: 0.32, fontSize: 12.5, bold: true, color: on && waste ? C.ot : C.white, valign: "middle" });
    const xa = lx + (lw * a) / max, xb = lx + (lw * (on ? b : a)) / max;
    s.addShape(pres.shapes.OVAL, { x: xa - 0.11, y: y - 0.11, w: 0.22, h: 0.22, fill: { color: C.bg }, line: { color: C.muted, width: 1.5 } });
    O(s, "otd" + i, xb, y, 0.22, on ? (waste ? C.ot : C.ok) : C.muted);
    T(s, on ? (waste ? "0 → 0" : `${fmt(a)} → ${fmt(b)}`) : fmt(a), { ...N("otv" + i), x: Math.max(xa, xb) + 0.2, y: y - 0.15, w: 1.4, h: 0.3, fontSize: 11, color: C.text, valign: "middle", fontFace: MONO });
    R(s, "otb" + i, ox, y - 0.13, on ? (ow * ot) / omax : 0.01, 0.26, C.ot, on ? { tr: !waste ? 40 : 0 } : { tr: 100, ltr: 100 });
    if (on) T(s, fmt(ot), { x: ox + (ow * ot) / omax + 0.08, y: y - 0.15, w: 0.7, h: 0.3, fontSize: 11, bold: true, color: C.ot, valign: "middle", fontFace: MONO });
  });
  if (on) {
    R(s, null, M, 6.42, W - 2 * M, 0.5, "2B2410", { round: true, line: C.ot });
    T(s, `평소·EDD: 지연이 이미 0인데 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분 추가 가동 발생 (30회 중 27회, 관찰) · 원인은 비관적 예측으로 추정 · 부담 = 금액이 아니라 추가 가동시간`, { x: M + 0.25, y: 6.42, w: W - 2 * M - 0.5, h: 0.5, fontSize: 11.5, color: C.text, valign: "middle" });
  }
}
otSlide(false, "그럼 추가근무는 어땠을까요? 먼저 추가근무 없이 남은 평균 지연입니다.");
otSlide(true, `추가근무를 켜면 지연이 남아 있던 경우는 줄었습니다. 멈추는 날 CR은 ${fmt(m("STOPPAGE_REWORK", "CR"))}분에서 ${fmt(m("STOPPAGE_REWORK", "CR+OT"))}분, 평소 FCFS는 ${fmt(m("NORMAL", "FCFS"))}분에서 ${fmt(m("NORMAL", "FCFS+OT"))}분입니다. 반대로 평소 EDD는 이미 지연이 0인데도 평균 ${fmt(m("NORMAL", "EDD+OT", "overtime_minutes"))}분의 추가 가동시간이 생겼습니다. 결정하는 순간의 예측이 실제보다 비관적이었기 때문으로 추정하고, 한계로 보고합니다.`);
// 26 verification
{
  const s = slide("검증", "자동 테스트 384개가 통과하고, 공장 규칙 위반은 0건입니다. 실험은 버그를 찾는 데도 쓰였습니다. 첫 실행에서 810번 중 3번이 17시 정각 재계획 버그로 실패했고, 고친 뒤 다시 돌려 모두 성공했습니다. 실패 기록도 지우지 않고 남겼습니다.");
  head(s, "두 가지 검증, 그리고 실험이 찾은 버그", "자동 테스트 = 계산 하나하나 확인 · 810회 실험 = 전체가 맞물려 끝까지 도는지 확인 · 실패 기록은 지우지 않았다");
  [["384", "자동 테스트", "Python 3.11 · 3.13 CI"], ["810", "폐루프 실행", "3조건 × 9방법 × 30회"], ["0", "공장 규칙 위반", "중복·용량·선후·근무시간"], ["0", "최종 실패", "첫 실행 3회 실패 → 수정"]].forEach((v, i) => {
    const x = M + i * 3.07;
    card(s, x, 2.05, 2.9, 1.7);
    T(s, v[0], { x: x + 0.25, y: 2.15, w: 2.5, h: 0.85, fontSize: 44, bold: true, color: i < 2 ? C.white : C.ok, fontFace: MONO });
    T(s, v[1], { x: x + 0.25, y: 3.0, w: 2.5, h: 0.3, fontSize: 13, bold: true, color: C.text });
    T(s, v[2], { x: x + 0.25, y: 3.32, w: 2.5, h: 0.28, fontSize: 10, color: C.muted });
  });
  [["17:00 정각 재계획 실패 (810회 중 3회)", "진행 중 작업이 결정 시각에 바로 이어진다고 가정", "다음 근무 시작에 재개 → 재실행 성공"],
   ["재작업으로 다시 열린 공정 누락", "승인 계획에 없는 공정을 후보가 찾지 못함", "부모 계획 뒤 순위로 배치"],
   ["실험·대시보드 출하검사 기준 불일치", "실험만 '완료 후 24근무시간' 가정", "한 모듈로 통일, 기록 재계산"]].forEach((b, i) => {
    const x = M + i * 4.1, w = 3.9, y = 4.2;
    card(s, x, y, w, 2.5);
    T(s, b[0], { x: x + 0.22, y: y + 0.18, w: w - 0.4, h: 0.6, fontSize: 13, bold: true, color: C.late });
    T(s, "원인  " + b[1], { x: x + 0.22, y: y + 0.9, w: w - 0.4, h: 0.65, fontSize: 11.5, color: C.text });
    T(s, "해결  " + b[2], { x: x + 0.22, y: y + 1.65, w: w - 0.4, h: 0.65, fontSize: 11.5, color: C.ok });
  });
}
// 27 limits
{
  const s = slide("한계", "증명하지 않은 것도 말씀드립니다. Pico 단말 연동, 실제 공장 데이터, 출하검사 자체의 대기와 불합격, 그리고 EDD가 어디서나 최선이라는 점입니다. 작업 정지는 작업시간이 240분 늘어나는 방식으로 단순화했습니다.");
  head(s, "증명한 것과 증명하지 않은 것", "결론을 읽을 때 함께 봐야 하는 범위");
  [["증명한 것 (실행·테스트 근거)", C.ok, "✓", ["승인한 계획이 작업지시로 내려가 현장 순서를 바꾼다", "실제 시간 = 표준시간이면 현장 결과가 Forecast와 일치", "추가근무 승인이 달력·Forecast·현장에 함께 반영", "810회(가상 환경): 이 충돌 상황에서 재계획이 진입 지연을 크게 줄임", "평소 조건 EDD+OT에서 지연 개선 없이 평균 108분 추가 가동 발생"]],
   ["증명하지 않은 것", C.late, "✕", ["Pico 2 WH 단말 연동 (TCP는 localhost만, Wi-Fi 아님)", "실제 공장 데이터 (작업시간 분포·교란 확률은 가정값)", "돌발 지연 = 작업시간 240분 연장 모델 (HOLD/RESUME API는 있으나 실험엔 미사용)", "출하검사 자체의 대기·불합격 (3근무일 가정)", "EDD가 일반 현장에서 최선이라는 것 (의도적 충돌 상황)"]]].forEach((c, i) => {
    const x = M + i * 6.15, w = 5.95, y = 2.0;
    card(s, x, y, w, 4.8);
    T(s, c[0], { x: x + 0.3, y: y + 0.22, w: w - 0.6, h: 0.4, fontSize: 16, bold: true, color: c[1] });
    c[3].forEach((b, k) => {
      const yy = y + 0.85 + k * 0.77;
      T(s, c[2], { x: x + 0.3, y: yy, w: 0.35, h: 0.4, fontSize: 15, bold: true, color: c[1] });
      T(s, b, { x: x + 0.7, y: yy + 0.02, w: w - 1.0, h: 0.65, fontSize: 12.5, color: C.text });
    });
  });
}
// 28 close
{
  const s = slide(null, "정리하겠습니다. 이 시스템은 실적을 보여주기만 하는 게 아니라, 실적으로 언제 끝날지 다시 계산하고, 사람이 고른 계획을 다음 작업 순서로 내려보냅니다. 810번의 실험에서 재계획은 출하검사 지연을 크게 줄였습니다. 불필요한 추가근무를 줄이도록 예측을 보정하는 것이 다음 과제입니다. 감사합니다.");
  T(s, "실적을 보여주는 대시보드가 아니라,", { x: M, y: 1.5, w: 12, h: 0.7, fontSize: 30, bold: true, color: C.muted });
  T(s, "실적이 다음 작업지시를\n바꾸는 시스템", { x: M, y: 2.2, w: 12, h: 2.0, fontSize: 50, bold: true, color: C.white, lineSpacingMultiple: 1.05 });
  R(s, null, M, 4.5, W - 2 * M, 0.04, C.late);
  [["4h 57m → 2h 57m", "시연 예측: 추가근무 2시간, 여전히 긴급", C.late], [`${fmt(m("STOPPAGE_REWORK", "KEEP"))} → ${fmt(m("STOPPAGE_REWORK", "EDD"), 1)}분`, "돌발 지연·재작업 조건 평균 진입 지연 (계획 유지 → EDD)", C.ok], ["108분", "지연 0인데 생긴 추가 가동 → 예측 보정이 다음 과제", C.ot]].forEach((v, i) => {
    const x = M + i * 4.1;
    T(s, v[0], { x, y: 4.8, w: 3.95, h: 0.75, fontSize: 28, bold: true, color: v[2], fontFace: MONO });
    T(s, v[1], { x, y: 5.6, w: 3.8, h: 0.5, fontSize: 12, color: C.muted });
  });
  T(s, "가상 생산환경 · 일부러 만든 충돌 상황에서 검증한 결과입니다", { x: M, y: 6.2, w: 9, h: 0.3, fontSize: 11.5, color: C.dim });
  T(s, "감사합니다", { x: M, y: 6.55, w: 4, h: 0.45, fontSize: 18, bold: true, color: C.late });
}

check(page === 28, "28 slides");
pres.writeFile({ fileName: OUT }).then(() => { fs.writeFileSync(OUT + ".transitions.json", JSON.stringify(TR)); console.log("wrote", OUT, page, "slides", BACKUP ? "(backup)" : ""); });
