import type { SeverityLevel } from "../types";

const LABEL: Record<SeverityLevel, string> = {
  high: "High priority",
  medium: "Medium priority",
  low: "Low priority",
};

export function SeverityBadge({ level }: { level: string | undefined }) {
  const lvl = (level ?? "low") as SeverityLevel;
  return <span className={`badge badge-${lvl}`}>{LABEL[lvl] ?? level}</span>;
}
