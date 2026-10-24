import { Fragment } from "react";

import styles from "./Description.module.css";

/** "**bold**" inside a line, the only inline markup the sources use. */
function inline(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : <Fragment key={i}>{part}</Fragment>,
  );
}

const BULLET = /^\s*(?:[-•*·]|\d+[.)])\s+/;

/**
 * Some sources write their descriptions in a Markdown subset (headings, bold, dashes),
 * others in plain text with runs of blank lines. Both read as paragraphs here.
 */
export function Description({ text }: { text: string }) {
  const blocks = text
    .replace(/\r\n/g, "\n")
    .split(/\n\s*\n+/)
    .map((b) => b.trim())
    .filter(Boolean);

  return (
    <div className={styles.description}>
      {blocks.map((block, i) => {
        const lines = block.split("\n").map((l) => l.trim()).filter(Boolean);
        if (lines.length === 1 && /^#{1,6}\s+/.test(lines[0])) {
          return (
            <h3 key={i} className={styles.heading}>
              {inline(lines[0].replace(/^#{1,6}\s+/, ""))}
            </h3>
          );
        }
        if (lines.every((l) => BULLET.test(l))) {
          return (
            <ul key={i} className={styles.list}>
              {lines.map((l, j) => (
                <li key={j}>{inline(l.replace(BULLET, ""))}</li>
              ))}
            </ul>
          );
        }
        return (
          <p key={i}>
            {lines.map((l, j) => (
              <Fragment key={j}>
                {j > 0 && <br />}
                {inline(l.replace(/^#{1,6}\s+/, ""))}
              </Fragment>
            ))}
          </p>
        );
      })}
    </div>
  );
}
