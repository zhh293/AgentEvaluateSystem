type Props = { label: string; value: string; delta?: string; tone?: "good" | "warn" | "neutral" };
export default function MetricCard({ label, value, delta, tone = "neutral" }: Props) {
  return <article className={`metric-card ${tone}`}><span>{label}</span><strong>{value}</strong>{delta && <small>{delta}</small>}<i /></article>;
}
