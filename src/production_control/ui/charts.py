"""Altair chart definitions shared by the dashboard and the exported figures.

One definition per chart keeps the dashboard and the report/slide figures
identical: ``production_control.sim.figures`` renders these same charts to PNG.
"""

from collections.abc import Mapping, Sequence

import altair as alt

from production_control.ui.display_labels import process_label
from production_control.ui.gantt_model import (
    CANDIDATE_LAYER,
    FORECAST_LAYER,
    PLAN_LAYER,
    PROCESS_ORDER,
)

# Categorical slots in fixed order (validated: adjacent CVD dE >= 11.8 light).
SERIES = ("#257de0", "#f47230", "#00b894", "#f2a600", "#ee7fac", "#008a17")
BASELINE_GRAY = "#8c8c8c"

CONDITION_LABELS = {
    "NORMAL": "정상",
    "SLOW": "작업시간 +20%",
    "STOPPAGE_REWORK": "작업정지·재작업",
}
CONDITION_ORDER = tuple(CONDITION_LABELS.values())
RULES = ("KEEP", "FCFS", "EDD", "SLACK", "CR")
RULE_COLORS = (BASELINE_GRAY, *SERIES[:4])
CONFIG_ORDER = (
    "KEEP",
    "FCFS",
    "FCFS+OT",
    "EDD",
    "EDD+OT",
    "SLACK",
    "SLACK+OT",
    "CR",
    "CR+OT",
)
OVERTIME_LABELS = {False: "정규 근무", True: "추가근무 허용"}
CONFIG_AXIS = alt.Axis(labelAngle=-45, labelOverlap=False)


def _row_label(lot_label: str, process_code: str) -> str:
    return f"{lot_label} · {process_label(process_code)}"


def gantt_chart(
    bars: Sequence[Mapping[str, str]],
    *,
    markers: Sequence[Mapping[str, str]] = (),
    now: str | None = None,
    layers: Sequence[str] = (PLAN_LAYER, FORECAST_LAYER),
    row_height: int = 34,
    margin_hours: int = 12,
) -> alt.LayerChart:
    """One row per LOT x process, one sub-row per layer, bars coloured by process.

    The first layer is drawn faint (the reference), the second solid. The time
    axis ends ``margin_hours`` after the last bar; a Gate later than that is not
    drawn.
    """

    order = {code: index for index, code in enumerate(PROCESS_ORDER)}
    rows = sorted(
        {(row["lot_label"], row["process_code"]) for row in bars},
        key=lambda item: (item[0], order.get(item[1], 99)),
    )
    row_labels = [_row_label(lot, code) for lot, code in rows]
    values = [{**row, "row": _row_label(row["lot_label"], row["process_code"])} for row in bars]
    starts = [row["start"] for row in bars] + ([now] if now else [])
    first = min(starts) if starts else None
    last = max((row["end"] for row in bars), default=None)
    domain = None
    if first and last:
        from datetime import datetime, timedelta

        end = datetime.fromisoformat(last) + timedelta(hours=margin_hours)
        domain = [first, end.isoformat(timespec="minutes")]
    x_scale = alt.Scale(domain=domain) if domain else alt.Undefined
    opacity_range = [0.4, 1.0][: len(layers)]
    bar_layer = (
        alt.Chart(alt.Data(values=values))
        .mark_bar(cornerRadius=3, stroke="white", strokeWidth=1, clip=True)
        .encode(
            y=alt.Y(
                "row:N",
                title=None,
                sort=row_labels,
                scale=alt.Scale(domain=row_labels),
                axis=alt.Axis(labelLimit=220),
            ),
            yOffset=alt.YOffset("layer:N", sort=list(layers), scale=alt.Scale(domain=list(layers))),
            x=alt.X(
                "start:T",
                title="시각 (Asia/Seoul · 야간·휴일 포함, 작업은 근무시간에만 진행)",
                axis=alt.Axis(format="%m/%d %H시"),
                scale=x_scale,
            ),
            x2="end:T",
            color=alt.Color(
                "process_label:N",
                title="공정",
                scale=alt.Scale(
                    domain=[process_label(code) for code in PROCESS_ORDER], range=list(SERIES)
                ),
                legend=alt.Legend(orient="bottom", columns=6),
            ),
            opacity=alt.Opacity(
                "layer:N",
                title="구분",
                scale=alt.Scale(domain=list(layers), range=opacity_range),
                legend=alt.Legend(orient="bottom"),
            ),
            tooltip=[
                alt.Tooltip("lot_label:N", title="LOT"),
                alt.Tooltip("process_label:N", title="공정"),
                alt.Tooltip("layer:N", title="구분"),
                alt.Tooltip("start:T", title="시작", format="%m/%d %H:%M"),
                alt.Tooltip("end:T", title="완료", format="%m/%d %H:%M"),
            ],
        )
    )
    charts: list[alt.Chart] = [bar_layer]
    lots_drawn = {lot for lot, _ in rows}
    gate_rows = []
    for marker in markers:
        if marker["lot_label"] not in lots_drawn:
            continue
        lot_rows = [label for label in row_labels if label.startswith(f"{marker['lot_label']} · ")]
        gate_rows.extend({**marker, "row": label} for label in lot_rows)
    if gate_rows:
        charts.append(
            alt.Chart(alt.Data(values=gate_rows))
            .mark_tick(color="#191919", thickness=2.5, clip=True)
            .encode(
                y=alt.Y("row:N", sort=row_labels),
                x="at:T",
                tooltip=[
                    alt.Tooltip("lot_label:N", title="LOT"),
                    alt.Tooltip("label:N", title="Gate"),
                    alt.Tooltip("at:T", title="예정", format="%m/%d %H:%M"),
                ],
            )
        )
    if now is not None:
        charts.append(
            alt.Chart(alt.Data(values=[{"at": now}]))
            .mark_rule(strokeDash=[4, 4], color="#666666", strokeWidth=1.5)
            .encode(x="at:T", tooltip=[alt.Tooltip("at:T", title="기준시각", format="%m/%d %H:%M")])
        )
    return alt.layer(*charts).properties(height=max(1, len(rows)) * row_height)


def gantt_layers_for_candidate() -> tuple[str, str]:
    return (FORECAST_LAYER, CANDIDATE_LAYER)


def summary_records(rows: Sequence[Mapping[str, str]]) -> list[dict[str, object]]:
    """``summary.csv`` rows with numbers parsed and display fields added."""

    out: list[dict[str, object]] = []
    for row in rows:
        policy = str(row["policy"])
        rule, _, suffix = policy.partition("+")
        mean = float(row["gate_delay_minutes_mean"])
        half = float(row["gate_delay_minutes_ci95"])
        out.append(
            {
                "condition": row["condition"],
                "condition_label": CONDITION_LABELS.get(row["condition"], row["condition"]),
                "policy": policy,
                "rule": rule,
                "overtime": suffix == "OT",
                "overtime_label": OVERTIME_LABELS[suffix == "OT"],
                "n": int(row["n"]),
                "gate_delay": mean,
                "gate_delay_low": max(0.0, mean - half),
                "gate_delay_high": mean + half,
                "gate_delay_ci": half,
                "due_tardiness": float(row["due_tardiness_minutes_mean"]),
                "due_tardiness_ci": float(row["due_tardiness_minutes_ci95"]),
                "overtime_minutes": float(row["overtime_minutes_mean"]),
                "approvals": float(row["approvals_mean"]),
                "late_gate_lots": float(row["late_gate_lots_mean"]),
                "vs_keep": float(row["gate_delay_minutes_vs_keep_mean"]),
                "vs_keep_ci": float(row["gate_delay_minutes_vs_keep_ci95"]),
                "label": f"{mean:.0f}",
            }
        )
    return out


def gate_delay_chart(
    records: Sequence[Mapping[str, object]], *, width: int = 260
) -> alt.FacetChart:
    """Mean shipping-inspection entry delay with 95% CI, one panel per condition."""

    base = alt.Chart().encode(
        x=alt.X("policy:N", sort=list(CONFIG_ORDER), title=None, axis=CONFIG_AXIS),
    )
    bars = base.mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
        y=alt.Y("gate_delay:Q", title="출하검사 진입 지연 (분, 평균)"),
        color=alt.Color(
            "rule:N",
            title="재계획 방법",
            scale=alt.Scale(domain=list(RULES), range=list(RULE_COLORS)),
        ),
        opacity=alt.Opacity(
            "overtime_label:N",
            title="근무",
            scale=alt.Scale(domain=list(OVERTIME_LABELS.values()), range=[1.0, 0.55]),
        ),
        tooltip=[
            alt.Tooltip("condition_label:N", title="조건"),
            alt.Tooltip("policy:N", title="구성"),
            alt.Tooltip("gate_delay:Q", title="평균 지연(분)", format=".1f"),
            alt.Tooltip("gate_delay_ci:Q", title="95% CI ±", format=".1f"),
            alt.Tooltip("overtime_minutes:Q", title="추가 가동(분)", format=".0f"),
            alt.Tooltip("n:Q", title="반복"),
        ],
    )
    errors = base.mark_rule(color="#191919", strokeWidth=1.5).encode(
        y="gate_delay_low:Q", y2="gate_delay_high:Q"
    )
    labels = base.mark_text(dy=-8, fontSize=10, color="#191919").encode(
        y="gate_delay_high:Q", text="label:N"
    )
    return (
        alt.layer(bars, errors, labels, data=alt.Data(values=list(records)))
        .properties(width=width, height=240)
        .facet(
            column=alt.Column(
                "condition_label:N", title=None, sort=list(CONDITION_ORDER),
                header=alt.Header(labelFontSize=13, labelFontWeight="bold"),
            )
        )
        .resolve_scale(y="independent")
    )  # fmt: skip


def overtime_tradeoff_chart(
    records: Sequence[Mapping[str, object]], *, width: int = 240
) -> alt.FacetChart:
    """For each rule: delay and extra operating time without and with overtime."""

    rows = [row for row in records if row["rule"] != "KEEP"]
    base = alt.Chart().encode(
        x=alt.X("overtime_minutes:Q", title="추가 가동시간 (분, 평균)"),
        y=alt.Y("gate_delay:Q", title="출하검사 진입 지연 (분, 평균)"),
        color=alt.Color(
            "rule:N", title="재계획 방법",
            scale=alt.Scale(domain=list(RULES[1:]), range=list(RULE_COLORS[1:])),
        ),
    )  # fmt: skip
    lines = base.mark_line(strokeWidth=2).encode(detail="rule:N", order="overtime:O")
    points = base.mark_point(size=90, filled=True, opacity=1).encode(
        shape=alt.Shape(
            "overtime_label:N",
            title="근무",
            scale=alt.Scale(domain=list(OVERTIME_LABELS.values()), range=["circle", "triangle-up"]),
        ),
        tooltip=[
            alt.Tooltip("condition_label:N", title="조건"),
            alt.Tooltip("policy:N", title="구성"),
            alt.Tooltip("gate_delay:Q", title="평균 지연(분)", format=".1f"),
            alt.Tooltip("overtime_minutes:Q", title="추가 가동(분)", format=".0f"),
        ],
    )  # fmt: skip
    return (
        alt.layer(lines, points, data=alt.Data(values=rows))
        .properties(width=width, height=220)
        .facet(
            column=alt.Column(
                "condition_label:N", title=None, sort=list(CONDITION_ORDER),
                header=alt.Header(labelFontSize=13, labelFontWeight="bold"),
            )
        )
        .resolve_scale(x="independent", y="independent")
    )  # fmt: skip


def run_distribution_chart(
    runs: Sequence[Mapping[str, object]], *, width: int = 260
) -> alt.FacetChart:
    """Every run's entry delay (one dot per seed), to show spread behind the means."""

    rows = []
    for row in runs:
        overtime = str(row["overtime"]).lower() in {"true", "1"}
        policy = f"{row['policy']}{'+OT' if overtime else ''}"
        rows.append(
            {
                "condition_label": CONDITION_LABELS.get(str(row["condition"]), row["condition"]),
                "policy": policy,
                "rule": row["policy"],
                "seed": int(row["seed"]),
                "gate_delay": float(row["gate_delay_minutes"]),
                # Deterministic horizontal spread so exported figures are stable.
                "jitter": (int(row["seed"]) * 7 % 30) / 30,
            }
        )
    return (
        alt.Chart(alt.Data(values=rows))
        .mark_circle(size=40, opacity=0.6)
        .encode(
            x=alt.X("policy:N", sort=list(CONFIG_ORDER), title=None, axis=CONFIG_AXIS),
            xOffset=alt.XOffset("jitter:Q"),
            y=alt.Y("gate_delay:Q", title="출하검사 진입 지연 (분, 실행별)"),
            color=alt.Color(
                "rule:N", title="재계획 방법",
                scale=alt.Scale(domain=list(RULES), range=list(RULE_COLORS)),
            ),
            tooltip=[
                alt.Tooltip("policy:N", title="구성"),
                alt.Tooltip("seed:Q", title="seed"),
                alt.Tooltip("gate_delay:Q", title="지연(분)", format=".0f"),
            ],
        )
        .properties(width=width, height=240)
        .facet(
            column=alt.Column(
                "condition_label:N", title=None, sort=list(CONDITION_ORDER),
                header=alt.Header(labelFontSize=13, labelFontWeight="bold"),
            )
        )
        .resolve_scale(y="independent")
    )  # fmt: skip
