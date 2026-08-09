import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { evaluationsApi } from "../lib/api";

export default function TracePage() {
  const { id = "" } = useParams(); const [spans, setSpans] = useState<Array<Record<string, unknown>>>([]); const [active, setActive] = useState(0); const [error, setError] = useState("");
  useEffect(() => { evaluationsApi.trace(id).then(trace => setSpans(trace.spans ?? [])).catch(error => setError(error.message)); }, [id]);
  const span = spans[active];
  return <section className="page trace-page reveal"><div className="page-heading compact"><div><span className="section-number">04—TRACE REPLAY</span><h1>Execution <em>evidence.</em></h1></div>{spans.length > 0 && <div className="trace-controls"><button onClick={() => setActive(Math.max(0, active - 1))}>← PREV</button><span>{active + 1} / {spans.length}</span><button onClick={() => setActive(Math.min(spans.length - 1, active + 1))}>NEXT →</button></div>}</div>
    {!span ? <p className="empty-state">{error || "No trace spans are available."}</p> : <div className="trace-layout"><article className="panel timeline"><div className="panel-head"><h2>Span timeline</h2><span>{spans.length} SPANS</span></div>{spans.map((item, i) => <button className={`span-row ${active === i ? "active" : ""}`} onClick={() => setActive(i)} key={String(item.span_id ?? i)}><i /><span><small>{String(item.span_id ?? "").slice(0, 8)}</small><b>{String(item.span_type ?? item.operation ?? "SPAN")}</b><em>{String(item.operation ?? "")}</em></span><strong>{Number(item.duration_ms ?? 0).toFixed(1)}ms</strong><mark>{String(item.status ?? "ok")}</mark></button>)}</article><article className="panel inspector"><div className="panel-head"><h2>Inspector</h2><span>{String(span.span_id ?? "").slice(0, 8)}</span></div><div className="code-block"><small>SPAN TYPE</small><b>{String(span.span_type ?? span.operation)}</b><small>STATUS</small><b>{String(span.status ?? "ok")}</b><small>DURATION</small><b>{Number(span.duration_ms ?? 0).toFixed(2)} ms</b><small>ATTRIBUTES</small><pre>{JSON.stringify(span.attributes ?? {}, null, 2)}</pre></div></article></div>}
  </section>;
}
