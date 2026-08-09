export default function SpanDetail({ span }: { span: Record<string, unknown> }) { return <div className="code-block"><pre>{JSON.stringify(span, null, 2)}</pre></div>; }
