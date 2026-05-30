from __future__ import annotations

import json
from collections.abc import Callable
from math import exp, isfinite, log, log1p

from aqt.qt import QDialog, QVBoxLayout, QWidget
from aqt.webview import AnkiWebView

from .models import AddonFsrsPresetConfig

COST_ADR_PARAMETER_COUNT = 15
COST_ADR_WEIGHT_MIN = 0.0
COST_ADR_WEIGHT_MAX = 1024.0
COST_ADR_DEFAULT_RETENTION_MIN = 0.3
COST_ADR_DEFAULT_RETENTION_MAX = 0.995


class DynamicDesiredRetentionPlotDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        *,
        preset: AddonFsrsPresetConfig,
        initial_desired_retention: float,
        save_desired_retention: Callable[[float], None],
    ) -> None:
        super().__init__(parent)
        self._save_desired_retention = save_desired_retention
        self.setWindowTitle("Dynamic DR Plot")
        self.resize(760, 820)

        self.web = AnkiWebView(self)
        self.web.set_bridge_command(self._on_bridge_command, self)

        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.web)
        self.setLayout(layout)

        self.web.stdHtml(
            _plot_body(_plot_payload(preset, initial_desired_retention)),
            js=[],
            context=self,
        )

    def _on_bridge_command(self, command: str) -> None:
        if command == "close":
            self.reject()
            return
        if not command.startswith("save:"):
            return
        value = float(command.removeprefix("save:"))
        self._save_desired_retention(value)
        self.web.eval("window.markSaved && window.markSaved();")


def target_calibration(
    avg_weights: tuple[float, ...],
    avg_drs: tuple[float, ...],
    fsrs_eq_weights: tuple[float, ...],
    fsrs_eq_drs: tuple[float, ...],
) -> tuple[tuple[float, ...], tuple[float, ...], str]:
    if valid_calibration(fsrs_eq_weights, fsrs_eq_drs):
        return fsrs_eq_weights, fsrs_eq_drs, "FSRS7 Eq. DR"
    return avg_weights, avg_drs, "Avg ADR DR"


def valid_plot_policy(preset: AddonFsrsPresetConfig) -> bool:
    weights, drs, _label = target_calibration(
        preset.fsrs_dynamic_desired_retention_weights,
        preset.fsrs_dynamic_desired_retention_avg_drs,
        preset.fsrs_dynamic_desired_retention_fsrs_eq_weights,
        preset.fsrs_dynamic_desired_retention_fsrs_eq_drs,
    )
    return (
        valid_policy_params(preset.fsrs_dynamic_desired_retention_params)
        and valid_calibration(
            preset.fsrs_dynamic_desired_retention_weights,
            preset.fsrs_dynamic_desired_retention_avg_drs,
        )
        and valid_calibration(weights, drs)
        and valid_retention_bounds(
            preset.fsrs_dynamic_desired_retention_min,
            preset.fsrs_dynamic_desired_retention_max,
        )
    )


def valid_policy_params(params: tuple[float, ...]) -> bool:
    return len(params) == COST_ADR_PARAMETER_COUNT and all(isfinite(value) for value in params)


def valid_calibration(weights: tuple[float, ...], drs: tuple[float, ...]) -> bool:
    return (
        len(weights) == len(drs)
        and len(weights) >= 2
        and all(isfinite(value) and value >= 0 for value in weights)
        and all(isfinite(value) and 0 <= value <= 1 for value in drs)
    )


def valid_retention_bounds(retention_min: float, retention_max: float) -> bool:
    return (
        isfinite(retention_min)
        and isfinite(retention_max)
        and retention_min > 0
        and retention_min < retention_max
        and retention_max < 1
    )


def cost_weight_for_desired_retention(
    target: float,
    weights: tuple[float, ...],
    drs: tuple[float, ...],
) -> float | None:
    if not isfinite(target) or not valid_calibration(weights, drs):
        return None
    calibration = sorted(zip(weights, drs, strict=True))
    for (left_weight, left_dr), (right_weight, right_dr) in zip(
        calibration,
        calibration[1:],
        strict=False,
    ):
        if (left_dr - target) * (right_dr - target) > 0:
            continue
        if abs(left_dr - right_dr) < 1e-12:
            return left_weight
        t = _clamp((target - left_dr) / (right_dr - left_dr), 0.0, 1.0)
        left_log = log1p(left_weight)
        right_log = log1p(right_weight)
        return exp(left_log + (right_log - left_log) * t) - 1
    return None


def _plot_payload(
    preset: AddonFsrsPresetConfig,
    initial_desired_retention: float,
) -> dict[str, object]:
    target_weights, target_drs, target_label = target_calibration(
        preset.fsrs_dynamic_desired_retention_weights,
        preset.fsrs_dynamic_desired_retention_avg_drs,
        preset.fsrs_dynamic_desired_retention_fsrs_eq_weights,
        preset.fsrs_dynamic_desired_retention_fsrs_eq_drs,
    )
    return {
        "params": list(preset.fsrs_dynamic_desired_retention_params),
        "avgWeights": list(preset.fsrs_dynamic_desired_retention_weights),
        "avgDrs": list(preset.fsrs_dynamic_desired_retention_avg_drs),
        "targetWeights": list(target_weights),
        "targetDrs": list(target_drs),
        "targetLabel": target_label,
        "retentionMin": preset.fsrs_dynamic_desired_retention_min
        or COST_ADR_DEFAULT_RETENTION_MIN,
        "retentionMax": preset.fsrs_dynamic_desired_retention_max
        or COST_ADR_DEFAULT_RETENTION_MAX,
        "initialTarget": initial_desired_retention,
    }


def _plot_body(payload: dict[str, object]) -> str:
    data = json.dumps(payload, separators=(",", ":"))
    return f"""
<style>
body {{
    margin: 0;
    color: var(--fg);
    background: var(--canvas);
}}
.toolbar {{
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: 10px;
    padding: 12px;
    border-bottom: 1px solid var(--border);
    font-size: 13px;
}}
.toolbar label {{
    display: flex;
    align-items: center;
    gap: 8px;
}}
#targetRange {{
    width: 260px;
}}
#targetNumber {{
    width: 82px;
}}
#plot {{
    display: block;
    width: 100%;
    height: min(72vh, 680px);
    min-height: 560px;
    cursor: grab;
}}
#plot:active {{
    cursor: grabbing;
}}
button {{
    padding: 5px 10px;
}}
.muted {{
    color: var(--fg-faint);
}}
.axis-line {{
    stroke: var(--fg);
    stroke-width: 1.2;
}}
.axis-label,
.legend-label,
.plot-empty {{
    fill: var(--fg);
    font-size: 12px;
}}
</style>
<div class="toolbar">
    <label>
        Target <span id="targetLabel"></span>
        <input id="targetRange" type="range" step="0.001">
    </label>
    <input id="targetNumber" type="number" step="0.001">
    <span id="targetPercent"></span>
    <span id="weightText"></span>
    <button id="saveButton" type="button">Save DR</button>
    <button id="closeButton" type="button">Close</button>
    <span id="saveState" class="muted"></span>
</div>
<svg id="plot" role="img"></svg>
<script>
const data = {data};
const COST_ADR_WEIGHT_MIN = 0;
const COST_ADR_WEIGHT_MAX = 1024;
const S_MIN = 0.0001;
const S_MAX = 36500;
const D_MIN = 1;
const D_MAX = 10;
let yaw = -42;
let pitch = 24;
let lastX = 0;
let lastY = 0;
let target = Number(data.initialTarget);

const svg = document.getElementById("plot");
const range = document.getElementById("targetRange");
const number = document.getElementById("targetNumber");
const targetLabel = document.getElementById("targetLabel");
const targetPercent = document.getElementById("targetPercent");
const weightText = document.getElementById("weightText");
const saveButton = document.getElementById("saveButton");
const saveState = document.getElementById("saveState");

const selectorMin = Math.min(...data.targetDrs);
const selectorMax = Math.max(...data.targetDrs);
range.min = selectorMin;
range.max = selectorMax;
number.min = selectorMin;
number.max = selectorMax;
targetLabel.textContent = data.targetLabel;

range.addEventListener("input", () => setTarget(Number(range.value)));
number.addEventListener("change", () => setTarget(Number(number.value)));
saveButton.addEventListener("click", () => {{
    if (currentWeight() === null) {{
        return;
    }}
    pycmd(`save:${{target.toFixed(6)}}`);
}});
document.getElementById("closeButton").addEventListener("click", () => pycmd("close"));

svg.addEventListener("mousedown", (event) => {{
    lastX = event.clientX;
    lastY = event.clientY;
    svg.dataset.dragging = "1";
}});
svg.addEventListener("mousemove", (event) => {{
    if (svg.dataset.dragging !== "1") {{
        return;
    }}
    yaw += (event.clientX - lastX) * 0.45;
    pitch = clamp(pitch - (event.clientY - lastY) * 0.35, -70, 70);
    lastX = event.clientX;
    lastY = event.clientY;
    render();
}});
window.addEventListener("mouseup", () => {{
    svg.dataset.dragging = "0";
}});
window.addEventListener("resize", render);
window.markSaved = () => {{
    saveState.textContent = "Saved to selected row";
}};

setTarget(target, false);

function setTarget(value, clearSaved = true) {{
    if (Number.isFinite(value)) {{
        target = clamp(value, selectorMin, selectorMax);
    }}
    range.value = target;
    number.value = target.toFixed(4);
    targetPercent.textContent = `${{(target * 100).toFixed(1)}}%`;
    const weight = currentWeight();
    weightText.textContent = weight === null ? "Weight: n/a" : `Weight: ${{weight.toFixed(2)}}`;
    saveButton.disabled = weight === null;
    if (clearSaved) {{
        saveState.textContent = "";
    }}
    render();
}}

function currentWeight() {{
    return costWeightForDesiredRetention(target, data.targetWeights, data.targetDrs);
}}

function render() {{
    while (svg.firstChild) {{
        svg.removeChild(svg.firstChild);
    }}
    const rect = svg.getBoundingClientRect();
    const width = rect.width || 760;
    const height = rect.height || 680;
    svg.setAttribute("viewBox", `0 0 ${{width}} ${{height}}`);
    const weight = currentWeight();
    if (weight === null) {{
        text(width / 2, height / 2, "Target DR is outside the calibrated range.", "plot-empty", svg, "middle");
        return;
    }}

    const stabilityCount = 34;
    const difficultyCount = 24;
    const logSMin = Math.log(0.1);
    const logSMax = Math.log(1000);
    const surface = [];
    for (let y = 0; y < difficultyCount; y++) {{
        const difficulty = 1 + (9 * y) / (difficultyCount - 1);
        const row = [];
        for (let x = 0; x < stabilityCount; x++) {{
            const stability = Math.exp(logSMin + ((logSMax - logSMin) * x) / (stabilityCount - 1));
            row.push({{
                x: (x / (stabilityCount - 1) - 0.5) * 2,
                y: (y / (difficultyCount - 1) - 0.5) * 2,
                z: ((evaluateDynamicDesiredRetention(data.params, stability, difficulty, weight, data.retentionMin, data.retentionMax) - data.retentionMin) / (data.retentionMax - data.retentionMin)) * 1.6,
                stability,
                difficulty,
            }});
        }}
        surface.push(row);
    }}

    const projected = surface.map((row) => row.map(project));
    const cells = [];
    for (let y = 0; y < difficultyCount - 1; y++) {{
        for (let x = 0; x < stabilityCount - 1; x++) {{
            const points = [projected[y][x], projected[y][x + 1], projected[y + 1][x + 1], projected[y + 1][x]];
            const source = surface[y][x];
            cells.push({{
                points,
                depth: points.reduce((total, point) => total + point.depth, 0) / points.length,
                dr: evaluateDynamicDesiredRetention(data.params, source.stability, source.difficulty, weight, data.retentionMin, data.retentionMax),
            }});
        }}
    }}
    cells.sort((a, b) => a.depth - b.depth);

    const plot = group(svg, `translate(${{width / 2}},${{height / 2 + 28}})`);
    for (const cell of cells) {{
        polygon(cell.points, retentionColor(cell.dr), plot);
    }}
    drawAxes(plot);
    drawLegend(svg, width, height);
}}

function drawAxes(parent) {{
    const axes = [
        [{{ x: -1.08, y: 1.08, z: 0 }}, {{ x: 1.08, y: 1.08, z: 0 }}, "S"],
        [{{ x: -1.08, y: -1.08, z: 0 }}, {{ x: -1.08, y: 1.08, z: 0 }}, "D"],
        [{{ x: -1.08, y: 1.08, z: 0 }}, {{ x: -1.08, y: 1.08, z: 1.75 }}, "DR"],
    ];
    for (const [start, end, label] of axes) {{
        const a = project(start);
        const b = project(end);
        line(a.x, a.y, b.x, b.y, "axis-line", parent);
        text(b.x, b.y, label, "axis-label", parent);
    }}
}}

function drawLegend(parent, width, height) {{
    const legendWidth = 180;
    const legendHeight = 10;
    const x = width - legendWidth - 28;
    const y = height - 38;
    for (let i = 0; i < legendWidth; i++) {{
        const retention = data.retentionMin + (i / (legendWidth - 1)) * (data.retentionMax - data.retentionMin);
        rect(x + i, y, 1, legendHeight, retentionColor(retention), parent);
    }}
    text(x, y - 6, formatPercent(data.retentionMin), "legend-label", parent);
    text(x + legendWidth, y - 6, formatPercent(data.retentionMax), "legend-label", parent, "end");
}}

function costWeightForDesiredRetention(targetDr, weights, drs) {{
    const calibration = weights.map((weight, index) => ({{ weight, dr: drs[index] }}))
        .sort((a, b) => a.weight - b.weight);
    for (let i = 0; i < calibration.length - 1; i++) {{
        const left = calibration[i];
        const right = calibration[i + 1];
        if ((left.dr - targetDr) * (right.dr - targetDr) > 0) {{
            continue;
        }}
        if (Math.abs(left.dr - right.dr) < Number.EPSILON) {{
            return left.weight;
        }}
        const t = clamp((targetDr - left.dr) / (right.dr - left.dr), 0, 1);
        const leftLog = Math.log1p(left.weight);
        const rightLog = Math.log1p(right.weight);
        return Math.expm1(leftLog + (rightLog - leftLog) * t);
    }}
    return null;
}}

function evaluateDynamicDesiredRetention(params, stability, difficulty, costWeight, retentionMin, retentionMax) {{
    const phi = stateFeatures(stability, difficulty);
    const z = normalizedCostWeight(costWeight);
    const base = dot(params.slice(0, 5), phi);
    const zEffect = softplus(dot(params.slice(5, 10), phi)) * z;
    const z2Effect = softplus(dot(params.slice(10, 15), phi)) * z * z;
    return retentionMin + (retentionMax - retentionMin) * sigmoid(base - zEffect - z2Effect);
}}

function stateFeatures(stability, difficulty) {{
    const s = clamp(stability, S_MIN, S_MAX);
    const d = clamp(difficulty, D_MIN, D_MAX);
    const logSMin = Math.log(S_MIN);
    const logSSpan = Math.log(S_MAX) - logSMin;
    const xS = clamp((Math.log(s) - logSMin) / logSSpan, 0, 1);
    const xD = clamp((d - D_MIN) / (D_MAX - D_MIN), 0, 1);
    return [1, xS, xD, xS * xD, xS * xS];
}}

function normalizedCostWeight(costWeight) {{
    const weight = clamp(costWeight, COST_ADR_WEIGHT_MIN, COST_ADR_WEIGHT_MAX);
    const lo = Math.log1p(COST_ADR_WEIGHT_MIN);
    const hi = Math.log1p(COST_ADR_WEIGHT_MAX);
    return clamp((Math.log1p(weight) - lo) / (hi - lo), 0, 1);
}}

function dot(lhs, rhs) {{
    return lhs.reduce((total, value, index) => total + value * rhs[index], 0);
}}

function sigmoid(value) {{
    if (value >= 0) {{
        const z = Math.exp(-value);
        return 1 / (1 + z);
    }}
    const z = Math.exp(value);
    return z / (1 + z);
}}

function softplus(value) {{
    if (value > 20) {{
        return value;
    }}
    if (value < -20) {{
        return Math.exp(value);
    }}
    return Math.log1p(Math.exp(value));
}}

function project(point) {{
    const yawRad = (yaw * Math.PI) / 180;
    const pitchRad = (pitch * Math.PI) / 180;
    const cy = Math.cos(yawRad);
    const sy = Math.sin(yawRad);
    const cp = Math.cos(pitchRad);
    const sp = Math.sin(pitchRad);
    const x1 = point.x * cy - point.y * sy;
    const y1 = point.x * sy + point.y * cy;
    const y2 = y1 * cp - point.z * sp;
    const z2 = y1 * sp + point.z * cp;
    const scale = 190;
    return {{ x: x1 * scale, y: y2 * scale, depth: z2 }};
}}

function group(parent, transform) {{
    const node = document.createElementNS("http://www.w3.org/2000/svg", "g");
    node.setAttribute("transform", transform);
    parent.appendChild(node);
    return node;
}}

function polygon(points, fill, parent) {{
    const node = document.createElementNS("http://www.w3.org/2000/svg", "polygon");
    node.setAttribute("points", points.map((point) => `${{point.x}},${{point.y}}`).join(" "));
    node.setAttribute("fill", fill);
    node.setAttribute("stroke", "rgba(0,0,0,.18)");
    node.setAttribute("stroke-width", "0.35");
    parent.appendChild(node);
}}

function line(x1, y1, x2, y2, className, parent) {{
    const node = document.createElementNS("http://www.w3.org/2000/svg", "line");
    node.setAttribute("x1", x1);
    node.setAttribute("y1", y1);
    node.setAttribute("x2", x2);
    node.setAttribute("y2", y2);
    node.setAttribute("class", className);
    parent.appendChild(node);
}}

function rect(x, y, width, height, fill, parent) {{
    const node = document.createElementNS("http://www.w3.org/2000/svg", "rect");
    node.setAttribute("x", x);
    node.setAttribute("y", y);
    node.setAttribute("width", width);
    node.setAttribute("height", height);
    node.setAttribute("fill", fill);
    parent.appendChild(node);
}}

function text(x, y, value, className, parent, anchor = "start") {{
    const node = document.createElementNS("http://www.w3.org/2000/svg", "text");
    node.setAttribute("x", x);
    node.setAttribute("y", y);
    node.setAttribute("class", className);
    node.setAttribute("text-anchor", anchor);
    node.textContent = value;
    parent.appendChild(node);
}}

function retentionColor(retention) {{
    const t = clamp((retention - data.retentionMin) / (data.retentionMax - data.retentionMin), 0, 1);
    const hue = 260 - 200 * t;
    return `hsl(${{hue}}, 78%, 48%)`;
}}

function formatPercent(value) {{
    return `${{(value * 100).toFixed(1)}}%`;
}}

function clamp(value, min, max) {{
    return Math.min(max, Math.max(min, value));
}}
</script>
"""


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return min(maximum, max(minimum, value))
