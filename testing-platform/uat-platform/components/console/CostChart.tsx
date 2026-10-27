import { formatMoney, monthLabel } from "@/lib/format";

export type ChartSeries = { id: string; name: string; color: string; values: number[] };

type Props = {
  titleId: string; // id of the visible heading that names the chart
  months: string[];
  series: ChartSeries[];
  currency: string;
  width?: number;
  height?: number;
  shortMonths?: boolean; // "Apr" instead of "Apr 2026", for narrow charts
  budgetLine?: number; // a dashed line at the budget amount, as in the cost trend of the capture
};

// Categorical slots, validated on white. Color follows the project, never its
// position in a filtered list, so a scope change never repaints a project.
const SERIES_COLORS = ["var(--color-series-1)", "var(--color-series-2)"];

export function projectColor(allProjectIds: string[], projectId: string) {
  return SERIES_COLORS[allProjectIds.indexOf(projectId)] ?? "var(--color-muted)";
}

function niceAxis(maxValue: number) {
  if (maxValue <= 0) return { max: 100, step: 25 };
  const raw = maxValue / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? raw;
  return { max: Math.ceil(maxValue / step) * step, step };
}

const GAP = 2; // surface gap between stacked segments
const RADIUS = 4; // rounded data end, top of the stack only

export function CostChart({
  titleId,
  months,
  series,
  currency,
  width = 640,
  height = 220,
  shortMonths = false,
  budgetLine,
}: Props) {
  const pad = { top: 12, right: 12, bottom: 28, left: 64 };
  const plotWidth = width - pad.left - pad.right;
  const plotHeight = height - pad.top - pad.bottom;
  const totals = months.map((_, i) => series.reduce((sum, s) => sum + s.values[i], 0));
  const axis = niceAxis(Math.max(0, budgetLine ?? 0, ...totals));
  const ticks = Array.from({ length: Math.round(axis.max / axis.step) + 1 }, (_, i) => i * axis.step);
  const slot = plotWidth / months.length;
  const barWidth = Math.min(32, slot * 0.5);
  const y = (value: number) => pad.top + plotHeight - (value / axis.max) * plotHeight;

  return (
    <figure>
      <div className="mb-2 flex gap-4 text-[12px] text-muted">
        {series.map((s) => (
          <span key={s.id} className="inline-flex items-center gap-1.5">
            <span className="size-2.5 rounded-sm" style={{ background: s.color }} />
            {s.name}
          </span>
        ))}
      </div>
      <svg width={width} height={height} role="img" aria-labelledby={titleId}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(tick)}
              y2={y(tick)}
              stroke="var(--color-grid)"
            />
            <text
              x={pad.left - 8}
              y={y(tick)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--color-muted)"
            >
              {formatMoney(tick, currency, 0)}
            </text>
          </g>
        ))}
        {budgetLine !== undefined && budgetLine > 0 && (
          <g>
            <line
              x1={pad.left}
              x2={width - pad.right}
              y1={y(budgetLine)}
              y2={y(budgetLine)}
              stroke="var(--color-error)"
              strokeWidth={1.5}
              strokeDasharray="6 4"
            />
            <rect x={pad.left + 4} y={y(budgetLine) - 9} width={56} height={18} rx={3} fill="var(--color-error)" />
            <text
              x={pad.left + 32}
              y={y(budgetLine)}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={11}
              fill="#ffffff"
            >
              {formatMoney(budgetLine, currency, 0)}
            </text>
          </g>
        )}
        {months.map((month, i) => {
          const x = pad.left + slot * i + (slot - barWidth) / 2;
          const drawn = series.filter((s) => s.values[i] > 0);
          let base = 0;
          return (
            <g key={month}>
              {drawn.map((s, index) => {
                const value = s.values[i];
                const top = y(base + value);
                const bottom = y(base) - (index > 0 ? GAP : 0);
                base += value;
                if (bottom - top <= 0) return null;
                if (index < drawn.length - 1) {
                  return (
                    <rect key={s.id} x={x} y={top} width={barWidth} height={bottom - top} fill={s.color} />
                  );
                }
                const r = Math.min(RADIUS, (bottom - top) / 2);
                const d = `M${x},${bottom} V${top + r} Q${x},${top} ${x + r},${top} H${x + barWidth - r} Q${x + barWidth},${top} ${x + barWidth},${top + r} V${bottom} Z`;
                return <path key={s.id} d={d} fill={s.color} />;
              })}
              <text
                x={pad.left + slot * i + slot / 2}
                y={height - 8}
                textAnchor="middle"
                fontSize={12}
                fill="var(--color-muted)"
              >
                {shortMonths ? monthLabel(month).split(" ")[0] : monthLabel(month)}
              </text>
            </g>
          );
        })}
      </svg>
    </figure>
  );
}
