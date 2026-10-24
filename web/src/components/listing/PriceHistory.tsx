"use client";

import { useState } from "react";

import { formatDate, formatPrice } from "@/lib/format";
import type { PricePoint } from "@/lib/types";
import styles from "./PriceHistory.module.css";

const WIDTH = 560;
const HEIGHT = 160;
const PAD = { top: 16, right: 16, bottom: 28, left: 56 };

/**
 * A step line: a rent holds its value until it changes, so the line stays flat between
 * observations and jumps at each change. One series, so no legend; the list under it is
 * the table view.
 */
export function PriceHistory({ history, lastSeenAt }: { history: PricePoint[]; lastSeenAt: string }) {
  const points = history.filter((p): p is { price: number; observedAt: string } => p.price != null);
  const [hover, setHover] = useState<number | null>(null);
  if (points.length < 2) {
    return (
      <p className={styles.single}>
        {points.length === 1
          ? `Prix inchangé depuis le ${formatDate(points[0].observedAt)} : ${formatPrice(points[0].price)}.`
          : "Aucun prix relevé."}
      </p>
    );
  }

  const start = new Date(points[0].observedAt).getTime();
  const end = Math.max(new Date(lastSeenAt).getTime(), new Date(points[points.length - 1].observedAt).getTime());
  const prices = points.map((p) => p.price);
  const lo = Math.min(...prices);
  const hi = Math.max(...prices);
  const span = hi - lo || hi * 0.1 || 1;
  const yMin = lo - span * 0.25;
  const yMax = hi + span * 0.25;
  const x = (t: number) => PAD.left + ((t - start) / (end - start || 1)) * (WIDTH - PAD.left - PAD.right);
  const y = (v: number) => PAD.top + (1 - (v - yMin) / (yMax - yMin)) * (HEIGHT - PAD.top - PAD.bottom);

  const coords = points.map((p) => ({ x: x(new Date(p.observedAt).getTime()), y: y(p.price), ...p }));
  let path = `M ${coords[0].x} ${coords[0].y}`;
  for (let i = 1; i < coords.length; i++) {
    path += ` H ${coords[i].x} V ${coords[i].y}`;
  }
  path += ` H ${x(end)}`;

  const ticks = [hi, lo];
  const active = hover != null ? coords[hover] : null;

  return (
    <figure className={styles.figure}>
      <div className={styles.chart}>
        <svg viewBox={`0 0 ${WIDTH} ${HEIGHT}`} role="img" aria-label="Évolution du prix" className={styles.svg}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD.left} x2={WIDTH - PAD.right} y1={y(t)} y2={y(t)} className={styles.grid} />
              <text x={PAD.left - 8} y={y(t)} className={styles.tick} textAnchor="end" dominantBaseline="middle">
                {formatPrice(t)}
              </text>
            </g>
          ))}
          <text x={PAD.left} y={HEIGHT - 8} className={styles.tick}>
            {formatDate(points[0].observedAt)}
          </text>
          <text x={WIDTH - PAD.right} y={HEIGHT - 8} className={styles.tick} textAnchor="end">
            {new Date(end).toDateString() === new Date().toDateString() ? "Aujourd'hui" : formatDate(new Date(end).toISOString())}
          </text>
          <path d={path} className={styles.line} />
          {coords.map((c, i) => (
            <g key={c.observedAt}>
              <circle cx={c.x} cy={c.y} r={5} className={styles.marker} data-active={hover === i || undefined} />
              <circle
                cx={c.x}
                cy={c.y}
                r={16}
                className={styles.hit}
                tabIndex={0}
                aria-label={`${formatPrice(c.price)} le ${formatDate(c.observedAt)}`}
                onMouseEnter={() => setHover(i)}
                onMouseLeave={() => setHover(null)}
                onFocus={() => setHover(i)}
                onBlur={() => setHover(null)}
              />
            </g>
          ))}
        </svg>
        {active && (
          <div
            className={styles.tooltip}
            style={{ left: `${(active.x / WIDTH) * 100}%`, top: `${(active.y / HEIGHT) * 100}%` }}
            role="status"
          >
            <strong>{formatPrice(active.price)}</strong>
            <span>{formatDate(active.observedAt)}</span>
          </div>
        )}
      </div>
      <figcaption>
        <ol className={styles.changes}>
          {points.map((p, i) => {
            const previous = i > 0 ? points[i - 1].price : null;
            const diff = previous != null ? p.price - previous : null;
            return (
              <li key={p.observedAt}>
                <span>{formatDate(p.observedAt)}</span>
                <span className={styles.value}>{formatPrice(p.price)}</span>
                {diff != null && (
                  <span className={styles.diff} data-direction={diff < 0 ? "down" : "up"}>
                    {diff < 0 ? "−" : "+"}
                    {formatPrice(Math.abs(diff))}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </figcaption>
    </figure>
  );
}
