// 기말 보고서 DOCX 생성: 수치는 experiments/main30/summary.csv에서 직접 읽는다.
const fs = require("fs");
const path = require("path");
const {
  Document, Packer, Paragraph, TextRun, ImageRun, Table, TableRow, TableCell,
  AlignmentType, WidthType, ShadingType, BorderStyle, LevelFormat, HeadingLevel,
  Footer, PageNumber,
} = require("docx");

const OUT = process.argv[2];
const DIR = __dirname;
const REPO = "/home/claude/project4_manufacturing_logic";
const FONT = "맑은 고딕";

// ---------- data
const rows = fs.readFileSync(path.join(REPO, "experiments/main30/summary.csv"), "utf8").trim().split(/\r?\n/);
const head = rows[0].split(",");
const S = {};
for (const line of rows.slice(1)) {
  const v = line.split(",");
  const r = Object.fromEntries(head.map((h, i) => [h, v[i]]));
  S[`${r.condition}|${r.policy}`] = r;
}
const runs = fs.readFileSync(path.join(REPO, "experiments/main30/runs.csv"), "utf8").trim().split(/\r?\n/);
const rh = runs[0].split(",");
const lateRuns = {}, otUsed = {};
for (const line of runs.slice(1)) {
  const v = line.split(",");
  const r = Object.fromEntries(rh.map((h, i) => [h, v[i]]));
  const k = `${r.condition}|${r.policy}${r.overtime === "True" ? "+OT" : ""}`;
  if (+r.gate_delay_minutes > 0) lateRuns[k] = (lateRuns[k] || 0) + 1;
  if (+r.overtime_minutes > 0) otUsed[k] = (otUsed[k] || 0) + 1;
}
const g = (c, p, f = "gate_delay_minutes") => +S[`${c}|${p}`][`${f}_mean`];
const ci = (c, p, f = "gate_delay_minutes") => +S[`${c}|${p}`][`${f}_ci95`];
const f1 = (x) => (Math.abs(x) < 0.05 ? "0" : x.toLocaleString("en-US", { minimumFractionDigits: 1, maximumFractionDigits: 1 }));
const f0 = (x) => Math.round(x).toLocaleString("en-US");
const CONDS = ["NORMAL", "SLOW", "STOPPAGE_REWORK"];
const CL = { NORMAL: "정상", SLOW: "작업시간 +20%", STOPPAGE_REWORK: "작업정지·재작업" };

// 본문에서 쓰는 수치는 데이터에서 확인한다 (어긋나면 생성 중단)
const expect = (cond, msg) => { if (!cond) throw new Error("data check failed: " + msg); };
expect(lateRuns["STOPPAGE_REWORK|EDD"] === 5, "EDD late runs 5");
expect(!lateRuns["NORMAL|EDD"] && !lateRuns["SLOW|EDD"], "EDD 0 in NORMAL/SLOW");
expect(otUsed["NORMAL|EDD+OT"] === 27, "EDD+OT used 27");
expect(Math.round(g("NORMAL", "EDD+OT", "overtime_minutes")) === 108, "108 min");
for (const k of Object.keys(S)) expect(+S[k].due_tardiness_minutes_mean === 0 && +S[k].violations === 0, "due/violations " + k);

// ---------- helpers
const run = (text, o = {}) => new TextRun({ text, font: FONT, size: o.size || 20, bold: o.bold, italics: o.italics, color: o.color });
const P = (children, o = {}) => new Paragraph({
  children: (Array.isArray(children) ? children : [children]).map((c) => (typeof c === "string" ? run(c, o) : c)),
  alignment: o.align || AlignmentType.LEFT,
  spacing: { after: o.after ?? 100, before: o.before ?? 0, line: o.line || 300 },
  indent: o.indent, keepNext: o.keepNext,
});
const H1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [run(t, { size: 24, bold: true, color: "14213D" })] });
const H2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [run(t, { size: 21, bold: true, color: "2F7DBD" })] });
const B = (parts) => new Paragraph({
  numbering: { reference: "bul", level: 0 },
  children: (Array.isArray(parts) ? parts : [parts]).map((c) => (typeof c === "string" ? run(c) : c)),
  spacing: { after: 60, line: 290 },
});
const bold = (t) => run(t, { bold: true });
const PAGE_W = 11906 - 2 * 1440; // A4, 좌우 2.54cm
const img = (file, widthIn, caption) => {
  const buf = fs.readFileSync(path.join(DIR, file));
  const w = buf.readUInt32BE(16), h = buf.readUInt32BE(20);
  const wpx = widthIn * 96;
  return [
    new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 80, after: 40 }, keepNext: true,
      children: [new ImageRun({ type: "png", data: buf, transformation: { width: wpx, height: wpx * h / w },
        altText: { title: caption, description: caption, name: file } })] }),
    P(caption, { size: 17, align: AlignmentType.CENTER, after: 160, color: "596B7A" }),
  ];
};
const border = { style: BorderStyle.SINGLE, size: 4, color: "C7D3DE" };
const borders = { top: border, bottom: border, left: border, right: border };
const table = (widths, header, body, caption) => {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (t, w, hdr, align) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: hdr ? { fill: "14213D", type: ShadingType.CLEAR, color: "auto" } : undefined,
    margins: { top: 50, bottom: 50, left: 90, right: 90 },
    children: [new Paragraph({ alignment: align || (hdr ? AlignmentType.CENTER : AlignmentType.LEFT), spacing: { after: 0, line: 260 },
      children: [run(String(t), { size: 17, bold: hdr, color: hdr ? "FFFFFF" : "222222" })] })],
  });
  const out = [];
  if (caption) out.push(P(caption, { size: 17, bold: true, after: 60, keepNext: true, align: AlignmentType.LEFT }));
  out.push(new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [
      new TableRow({ tableHeader: true, children: header.map((h, i) => cell(h, widths[i], true)) }),
      ...body.map((r) => new TableRow({ children: r.map((c, i) => cell(c, widths[i], false, i > 0 && /^[\d−\-.,±\s/()분회]+$/.test(String(c)) ? AlignmentType.CENTER : undefined)) })),
    ],
  }));
  out.push(P("", { after: 120 }));
  return out;
};

// ---------- result table
const POL = [["KEEP", "계획 유지(KEEP)"], ["FCFS", "FCFS"], ["FCFS+OT", "FCFS + 추가근무"], ["EDD", "EDD"], ["EDD+OT", "EDD + 추가근무"],
  ["SLACK", "Slack"], ["SLACK+OT", "Slack + 추가근무"], ["CR", "CR"], ["CR+OT", "CR + 추가근무"]];
const resultRows = POL.map(([p, label]) => [label, ...CONDS.map((c) => `${f1(g(c, p))} ± ${f1(ci(c, p))}`),
  ...CONDS.map((c) => f0(g(c, p, "overtime_minutes")))]);

// ---------- content
const children = [
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 80 }, children: [run("현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템", { size: 32, bold: true, color: "14213D" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 60 }, children: [run("— 승인한 재계획이 현장 작업지시로 돌아가는 폐루프와 반복 실험 검증 (기말 보고서) —", { size: 20, color: "596B7A" })] }),
  new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [run("메카트로닉스공학과 12233707 박상현", { size: 20 })] }),
  ...img("system_diagram.png", 6.2, "그림 1. 시스템 구성도. 현장 실적이 Forecast와 재계획 후보를 거쳐, 관리자가 승인한 계획이 작업지시 API로 현장에 되돌아간다(점선, 기말 추가)."),
  P([run("요약", { size: 18, bold: true })], { after: 40 }),
  ...[
    "1. 중간발표 시스템(실적 입력 → Forecast → 출하검사 Gate 위험 판정 → 재계획 후보 비교·승인)에 작업지시 API를 더해, 승인한 계획이 현장 작업 순서를 바꾸는 폐루프를 만들었다.",
    "2. 시스템이 모르는 실제 작업시간으로 움직이는 가상 현장 시뮬레이터를 만들고, HTTP API만으로 시스템과 통신하게 했다. Pico 2 WH 단말은 연동하지 못했다.",
    "3. 4가지 우선순위 규칙(FCFS·EDD·Slack·CR) 후보에 평일 17~19시 추가근무 후보를 더했고, 승인하면 근무달력에 저장되어 Forecast와 현장이 같은 시간을 쓴다.",
    "4. 3개 교란 조건 × 9개 재계획 구성 × 30 seed = 810회 폐루프 실행을 공통 난수로 비교했다. 실패 0, 공장 규칙 위반 0.",
    `5. 계획 유지 시 출하검사 진입 지연 평균 ${f0(g("NORMAL", "KEEP"))}~${f0(g("STOPPAGE_REWORK", "KEEP"))}분이 EDD 재계획으로 0~${f1(g("STOPPAGE_REWORK", "EDD"))}분으로 크게 줄었다. 단, 작업정지·재작업 조건에서는 30회 중 5회 지연이 남았다.`,
    `6. 추가근무는 지연이 남는 규칙에서 효과가 있었으나, 정상 조건 EDD에서는 지연이 이미 0인데도 평균 ${f0(g("NORMAL", "EDD+OT", "overtime_minutes"))}분을 열었다. 예측이 비관적이면 불필요한 추가근무를 고를 수 있다는 한계로 본다.`,
  ].map((t) => P(t, { size: 18, after: 20, line: 260 })),
  P([run("Abstract", { size: 18, bold: true })], { before: 120, after: 40 }),
  P("This project extends a shop-floor progress monitoring and replanning system into a closed loop. Unit-level work events update a finite-capacity forecast; when a LOT is forecast to miss its shipping-inspection gate, the system ranks FCFS, EDD, Slack and CR replanning candidates, now also with a weekday 17:00–19:00 overtime option, and the plan approved by a manager is issued back to the floor through a work-order API. A virtual plant with hidden true durations and noisy operator estimates exercises the loop over HTTP. In 810 closed-loop runs (3 disturbance conditions × 9 configurations × 30 common-random-number seeds), EDD replanning reduced the mean gate-entry delay from 190–2,433 minutes to 0–15 minutes, with no rule violations or failed runs. Overtime helped rules that still left delay but was also bought where it was unnecessary, apparently because decision-time forecasts were pessimistic. Hardware terminal (Pico 2 WH) integration was not completed.", { size: 18, line: 260, after: 60 }),
  P([run("Keywords: ", { size: 18, bold: true }), run("생산진도 관리, 유한용량 Forecast, 동적 재계획, 우선순위 규칙, 추가근무, 폐루프 시뮬레이션, 공통 난수", { size: 18 })], { after: 200 }),

  H1("1. 서론"),
  P("중간발표에서는 작업실적 입력부터 재계획 승인까지의 흐름을 관리자 화면에서 보였다. 그러나 승인한 계획이 실제 현장 순서를 바꾸는지, 하나의 시나리오를 넘어서도 효과가 있는지, 추가근무 같은 용량 대안은 어떻게 다루는지는 확인하지 못했다. 또한 중간발표 시연에서 LOT-001의 출하검사 진입 지연 4시간 57분은 어떤 순서 규칙으로도 줄지 않았다."),
  P("기말에서는 이 질문들을 (1) 작업지시 API와 가상 현장으로 폐루프를 닫고, (2) 추가근무 후보를 재계획에 넣고, (3) 반복 실험으로 효과와 비용을 측정하는 방식으로 다뤘다. 모든 주장은 자동 테스트나 실험 원자료로 확인할 수 있게 저장소의 docs/verification.md에 근거를 연결했다. Pico 2 WH 단말 연동은 이번 기간에 하지 못했으며, 같은 HTTP API를 쓰는 가상 단말과 화면 입력으로 대신 검증했다."),

  H1("2. 시스템 구성"),
  H2("2.1 모의 생산환경"),
  P("모의 생산환경은 중간발표와 같다. 3개 LOT(각 30 Unit, 총 90대)가 테이핑 → 외부 피드 본딩(LOT 단위 외부 리드타임) → 일반 조립 → 튜닝 → 마무리 조립 → 최종 성능시험을 거친 뒤 출하검사 Gate로 들어간다. 작업자 2명은 공용이고 튜닝장비·시험장비는 각 1대라 두 장비가 병목이다. 근무는 평일 9~17시다."),
  ...table([2200, 1700, 1700, 3426], ["공정", "표준시간", "자원", "비고"], [
    ["테이핑 / 일반 조립 / 마무리 조립", "각 10분/대", "작업자 2명 공용", ""],
    ["튜닝", "25분/대", "튜닝장비 1대", "병목"],
    ["최종 성능시험", "30분/대", "시험장비 1대", "병목, 불합격 시 튜닝 재작업"],
    ["외부 피드 본딩", "LOT 단위", "외부", "외부 리드타임으로 처리"],
  ], "표 1. 공정과 자원 (표준시간은 로직 검증용 가정값)"),
  H2("2.2 Forecast와 위험 판정"),
  P("Forecast는 완료된 Unit의 실적으로 LOT × 공정 속도(Pace)를 구하고, 남은 작업을 작업자·장비·근무시간 제약 안에서 이벤트 단위로 배치한다(유한용량 스케줄링). 마지막 최종 성능시험 완료 예상과 출하검사 Gate 예정 시각의 차이를 여유(slack)로 계산해, 0 이하이면 긴급(URGENT)으로 판정한다. 작업자가 입력한 잔여시간 추정은 Pace보다 우선해 반영된다."),
  H2("2.3 재계획 후보와 추가근무 (기말 추가)"),
  P("긴급이 되면 FCFS(접수순), EDD(Gate가 빠른 LOT 우선), Slack(여유가 적은 LOT 우선), CR(긴급도 비율이 높은 LOT 우선)으로 남은 작업을 다시 배치한 후보를 만든다. 기말에서는 각 규칙마다 평일 17~19시를 추가로 연 '+추가근무' 후보를 함께 계산한다. 후보 안에서 실제로 쓰지 않는 날은 창에서 빼고, 쓰는 날은 17시부터 창 안 마지막 작업 종료까지를 추가 가동시간으로 센다(대기 포함)."),
  P("후보 순위는 지연 LOT 수 → 총 지연시간 → 추가 가동시간 → 계획 변경량 순서의 사전식 비교다(D029). 따라서 지연이 같으면 추가근무가 적은 안이 앞선다. 관리자가 추가근무안을 승인하면 그 시간이 근무달력의 OVERTIME 예외로 저장되고, 이후 Forecast와 현장 작업지시가 같은 달력을 쓴다."),
  H2("2.4 작업지시 API와 폐루프 (기말 추가)"),
  P("승인된 계획 버전을 현장 작업 순서로 내려주는 작업지시 API(/work-orders)를 추가했다. 현장은 이 API가 준 순서대로만 다음 작업을 고르고, 실적(시작·완료·합격·불합격)을 다시 FastAPI로 보낸다. 같은 event_id의 재전송은 한 번만 반영된다."),

  H1("3. 폐루프 검증 환경"),
  P("가상 현장 시뮬레이터는 시스템이 모르는 실제 작업시간(표준시간에 로그정규 잡음)을 갖고, 작업자는 오차가 있는 잔여시간을 입력한다. 관리자 정책은 실행 시작, 매일 아침, 지연 입력, 시험 불합격 시점에 Forecast를 확인하고, 긴급이면 정해진 규칙의 후보를 승인한다(KEEP은 승인하지 않음). 추가근무가 켜진 구성에서는 같은 규칙의 추가근무안이 D029 순위로 더 나을 때만 그것을 고른다. 이 가상 관리자는 관리자 화면과 같은 승인 API를 호출하므로, 실험과 실제 운영의 차이는 누가 후보를 고르는가뿐이다(실제 화면에서는 사람이 후보를 비교해 직접 승인한다). 시뮬레이터와 시스템은 HTTP API로만 통신한다."),
  ...table([3600, 5426], ["확인한 것", "근거 (자동 테스트)"], [
    ["승인 전후로 현장 완료 순서가 바뀐다", "test_closed_loop.py::test_approval_changes_the_executed_order"],
    ["실제 시간 = 표준시간이면 현장 결과가 승인 시점 Forecast와 일치", "test_closed_loop.py::test_deterministic_plant_realises_the_plan_forecast"],
    ["잡음·재작업·이벤트 재전송에서도 끝까지 동작", "test_closed_loop.py::test_noisy_plant_with_rework_and_resent_events_completes"],
    ["localhost의 실제 TCP 소켓(uvicorn + httpx)에서도 같은 루프 (Pico Wi-Fi 통신은 검증하지 않음)", "test_closed_loop_over_network.py"],
    ["추가근무 승인이 달력·Forecast·현장에 같이 반영", "test_overtime_replan.py (3개)"],
  ], "표 2. 폐루프 동작 검증"),

  H1("4. 시연: 중간발표 상황에 추가근무를 더하면"),
  P("시연 상황은 중간발표와 같다(10/22 13:17). LOT-001의 마지막 튜닝(U030)에 앞으로 480분이 더 필요하다고 입력하면 LOT-001이 출하검사 시작보다 4시간 57분 늦어 긴급이 된다. 중간발표에서는 EDD·Slack·CR 모두 297분(4시간 57분), FCFS는 549분이라 어떤 순서로도 줄지 않았다. 추가근무 옵션을 켜면 EDD·Slack·CR + 추가근무안이 10/22 하루 2시간(120분)을 열어 177분(2시간 57분)으로 공동 1위가 되고, FCFS + 추가근무안은 같은 177분이지만 360분을 써서 뒤로 밀린다. EDD + 추가근무안을 승인하면 계획 v2가 되며, LOT-001은 여전히 긴급이다. 즉 허용한 평일 17~19시 추가근무만으로는 이 지연을 모두 없앨 수 없다(tests/integration/test_demo_overtime_option.py로 검증)."),

  H1("5. 반복 실험"),
  H2("5.1 실험 설계"),
  P("시작 상태는 중간발표 데모 상태(10/22 13:00)이며, 기준계획을 접수순(LOT-001 → 002 → 003)으로 두었다. 이 때문에 Gate가 10/28 09:00인 LOT-003이 Gate가 11/06 09:00인 LOT-002 뒤에 놓인다. 이는 재계획 효과를 보기 위해 의도적으로 만든 충돌 상황이며, 결과를 일반적인 공장 성능으로 해석해서는 안 된다."),
  ...table([2300, 6726], ["항목", "내용"], [
    ["교란 조건 (3)", "정상: 표준시간 × 로그정규 잡음(σ=0.15, ±15% 범위를 뜻하지 않음), 작업자 추정 오차 σ=0.2 / 작업시간 +20%: 모든 작업 평균 1.2배 / 작업정지·재작업: 작업 시도의 3%에 +240분(HOLD/RESUME 이벤트가 아닌 작업시간 연장 모델), 최종 성능시험 8% 불합격 → 튜닝 재작업"],
    ["재계획 구성 (9)", "KEEP(계획 유지), FCFS·EDD·Slack·CR 각각 추가근무 끔/켬"],
    ["반복", "구성마다 seed 1~30, 총 810회. 같은 seed는 모든 구성이 같은 실제 작업시간·불합격을 받음(공통 난수)"],
    ["지표", "출하검사 진입 지연 = max(0, 생산 완료 − Gate 예정 시작)의 LOT 합; 추가 가동시간; 최종 납기 지각; 공장 규칙 위반"],
    ["통계", "평균 ± 95% 신뢰구간(t분포), KEEP과 같은 seed끼리 짝지은 차이"],
    ["재현", "python -m production_control.sim.experiment --reps 30 (중단 후 이어서 실행 가능)"],
  ], "표 3. 실험 설계 (experiments/main30/config.json)"),
  H2("5.2 결과: 출하검사 진입 지연"),
  ...table([1830, 1600, 1600, 1600, 800, 800, 796], ["구성", "정상", "작업시간 +20%", "작업정지·재작업", "OT 정상", "OT +20%", "OT 정지·재작업"], resultRows,
    "표 4. 출하검사 진입 지연(분, 평균 ± 95% CI)과 평균 추가 가동시간(분), n=30 (experiments/main30/summary.csv)"),
  ...img("gate_delay.png", 6.3, "그림 2. 조건별 출하검사 진입 지연 평균과 95% 신뢰구간 (n=30)"),
  P([bold("재계획 효과. "), `계획을 유지하면 평균 지연이 ${f1(g("NORMAL", "KEEP"))}, ${f1(g("SLOW", "KEEP"))}, ${f1(g("STOPPAGE_REWORK", "KEEP"))}분이다. EDD로 재계획하면 정상과 작업시간 +20% 조건에서 30회 모두 지연 0이고, 작업정지·재작업 조건에서도 평균 ${f1(g("STOPPAGE_REWORK", "EDD"))}분으로 줄었다. 다만 이 조건에서는 30회 중 5회 지연이 남았다. Slack은 작업정지·재작업 조건에서 평균 ${f1(g("STOPPAGE_REWORK", "SLACK"))}분이고 30회 중 ${lateRuns["STOPPAGE_REWORK|SLACK"]}회 지연이 남았다(최대 약 1,600분인 실행 포함). CR은 실행당 평균 3.2~4.3회 승인하며 정상 조건에서도 ${f1(g("NORMAL", "CR"))}분의 지연이 남았다.`]),
  P([bold("대조군. "), `FCFS는 기준계획과 같은 접수순이므로 계획 유지와 거의 같다(정상 조건 짝지은 차이 ${f1(+S["NORMAL|FCFS"].gate_delay_minutes_vs_keep_mean)} ± ${f1(+S["NORMAL|FCFS"].gate_delay_minutes_vs_keep_ci95)}분). 이는 실험 장치가 순서를 바꾸지 않으면 결과도 바뀌지 않음을 보여 주는 확인용 결과다.`]),
  ...img("gantt_replan.png", 6.3, "그림 3. 실험 시작 시점(10/22 13:00)의 두 일정: 계획 유지 Forecast(연한 막대)와 EDD 재계획안(진한 막대). 세로선은 Gate 예정 시각."),
  P("그림 3에서 EDD는 Gate가 10/28인 LOT-003의 튜닝·시험을 앞당기고, Gate가 11/06으로 여유가 많은 LOT-002를 뒤로 보낸다. 작업시간과 자원은 같고 병목 장비를 쓰는 순서만 바뀌었다. 이 결과는 의도적으로 만든 순서 충돌 상황에서 EDD가 효과적이었다는 것이며, EDD가 일반적인 제조 현장에서 가장 우수하다는 뜻은 아니다."),
  H2("5.3 결과: 추가근무의 효과와 비용"),
  ...img("overtime_tradeoff.png", 6.3, "그림 4. 같은 규칙에서 추가근무를 켰을 때(○ → △) 지연과 추가 가동시간의 변화"),
  P(`추가근무는 지연이 남는 규칙에서 효과가 있었다. 작업정지·재작업 조건의 CR은 ${f1(g("STOPPAGE_REWORK", "CR"))} → ${f1(g("STOPPAGE_REWORK", "CR+OT"))}분, 정상 조건의 FCFS는 ${f1(g("NORMAL", "FCFS"))} → ${f1(g("NORMAL", "FCFS+OT"))}분이 되었다. 반대로 정상 조건의 EDD와 Slack은 추가근무 없이도 지연이 0인데, 추가근무를 켜면 평균 ${f1(g("NORMAL", "EDD+OT", "overtime_minutes"))}분을 열었고 30회 중 27회 실제로 사용했다. 결정 시점의 Forecast가 실제보다 비관적이어서 필요 없는 추가근무를 고른 것으로 보이며, 현재 순위 규칙은 지연을 먼저 줄이므로 예측이 비관적이면 이런 선택을 피할 수 없다. 이를 시스템의 한계로 보고한다.`),
  H2("5.4 두 지표의 구분"),
  P("출하검사 진입 지연은 LOT별로 생산 완료가 출하검사 시작(Gate 예정)보다 늦은 시간(0 이상)을 더한 값이며, 중간발표의 4시간 57분도 이 지표다. 최종 납기 지각은 출하검사가 시작일 포함 3근무일(셋째 날 17시)에 끝난다고 가정했을 때, 출하 시각이 고객 납기보다 늦은 시간(LOT별 0 이상의 합)이다. 출하검사 규칙은 대시보드와 실험이 같은 코드(core/shipping_inspection.py)를 쓴다. 이 가정하에서 810회 모두 최종 납기 지각은 0이었고, 가장 빠듯한 경우도 납기 당일 17시 출하였다(KEEP 2회, FCFS 1회). 이 데모는 고객 납기에 여유가 있어 실제로 지켜야 하는 선은 출하검사 시작이었다. 출하검사 자체의 대기·불합격은 모델링하지 않았다."),

  H1("6. 검증과 트러블슈팅"),
  P("자동 테스트 384개가 Python 3.11과 3.13에서 통과한다(GitHub Actions). 810회 실행에서 공장 규칙 위반(같은 작업 중복 시작, 자원 용량 초과, 선행 공정 완료 전 시작, 근무시간 밖 시작) 0건, 실패 0회다. 반복 실험은 버그를 찾는 데도 쓰였으며, 찾은 문제는 회귀 테스트와 함께 고쳤다."),
  ...table([3000, 3000, 3026], ["발견한 문제", "원인", "해결"], [
    ["17:00 정각 재계획에서 실행 실패 (810회 중 3회, HTTP 409)", "진행 중 작업이 결정 시각에 바로 이어진다고 가정", "다음 근무 시작에 재개하도록 수정, 3회 재실행 성공 (PR #50)"],
    ["실험과 대시보드의 출하검사 기준 불일치", "실험만 '완료 후 24근무시간' 가정", "규칙을 한 모듈로 통일, 기록 데이터 재계산 (PR #51)"],
    ["시연 화면이 실제 날짜 기준으로 모든 LOT를 지연 표시", "화면이 현재 시계를 사용", "시연 시각 고정 옵션 추가"],
  ], "표 5. 반복 실험·통합 검증에서 찾은 문제"),
  P("실패 기록은 숨기지 않고 experiments/main30/failures_before_3a7ff6e.json에 남겼다. 수정 전후로 같은 seed의 다른 실행은 결과가 그대로 재현됨을 확인했다.", { size: 19 }),

  H1("7. 결론과 한계"),
  P("실적이 다음 작업지시를 바꾸는 폐루프를 구현하고 실행으로 확인했으며, 810회 반복 실험에서 재계획이 출하검사 진입 지연을 크게 줄이는 것을 보였다. 추가근무는 순서만으로 해결되지 않는 지연을 줄였지만, 예측이 비관적이면 불필요한 추가근무를 고르는 것도 확인했다."),
  ...table([2400, 6626], ["구분", "내용"], [
    ["구현·검증함", "실적 API, 유한용량 Forecast, Gate 위험 판정, 4개 규칙 + 추가근무 후보, 승인과 계획 버전, 작업지시 API, 가상 현장 폐루프, 반복 실험, 간트차트·실험 결과 화면"],
    ["하지 못함", "Pico 2 WH 단말 연동(가상 단말·화면 입력으로 대체), 실제 공장 데이터로 시뮬레이터 보정(작업시간 분포·교란 확률은 가정값), 출하검사 자체의 대기·불합격 모델링, 실험에서 HOLD/RESUME 이벤트, 인증·권한"],
    ["향후 과제", "Pico 단말을 같은 API에 연결, 실적으로 Forecast 편향 보정, 추가근무 비용을 순위에 반영, 실제 현장 데이터로 시뮬레이터 보정"],
  ], "표 6. 구현 범위와 한계"),
  P("재현: 저장소 README의 빠른 시작과 docs/verification.md(주장 → 근거 표)를 따르면 테스트, 시연 화면, 실험 결과와 그림을 모두 다시 만들 수 있다.", { size: 19 }),
];

const doc = new Document({
  creator: "박상현",
  title: "현장 작업실적 기반 생산진도 관리 및 동적 재계획 시스템 — 기말 보고서",
  styles: {
    default: { document: { run: { font: FONT, size: 20 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 24, bold: true }, paragraph: { spacing: { before: 280, after: 120 }, keepNext: true, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { font: FONT, size: 21, bold: true }, paragraph: { spacing: { before: 180, after: 80 }, keepNext: true, outlineLevel: 1 } },
    ],
  },
  numbering: { config: [{ reference: "bul", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT,
    style: { paragraph: { indent: { left: 400, hanging: 240 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1701, bottom: 1440, left: 1440, right: 1440 } } },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER,
      children: [new TextRun({ children: [PageNumber.CURRENT], font: FONT, size: 16, color: "8C8C8C" })] })] }) },
    children,
  }],
});
Packer.toBuffer(doc).then((b) => { fs.writeFileSync(OUT, b); console.log("wrote", OUT); });
