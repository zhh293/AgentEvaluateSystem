import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { RadarChart } from "echarts/charts";
import { TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([RadarChart, TooltipComponent, CanvasRenderer]);

export default function RadarScore({ scores }: { scores: number[] }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption({
      backgroundColor: "transparent",
      radar: { indicator: ["RESULT", "TRAJECTORY", "EFFICIENCY", "SECURITY"].map(name => ({ name, max: 100 })), splitNumber: 4, axisName: { color: "#9ba59d", fontSize: 10 }, splitLine: { lineStyle: { color: "#2d3832" } }, splitArea: { areaStyle: { color: ["transparent"] } }, axisLine: { lineStyle: { color: "#39453f" } } },
      series: [{ type: "radar", data: [{ value: scores }], symbol: "circle", symbolSize: 5, lineStyle: { color: "#d7ff3f", width: 2 }, itemStyle: { color: "#d7ff3f" }, areaStyle: { color: "rgba(215,255,63,.16)" } }],
    });
    const resize = () => chart.resize(); window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [scores]);
  return <div ref={ref} style={{ height: 310 }} aria-label="Four-dimensional evaluation radar chart" />;
}
