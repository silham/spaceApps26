import { BarChart, CustomChart, LineChart, ScatterChart } from 'echarts/charts'
import { GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent } from 'echarts/components'
import * as echarts from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import { useEffect, useRef } from 'react'

echarts.use([
  BarChart, CustomChart, LineChart, ScatterChart,
  GridComponent, LegendComponent, MarkAreaComponent, MarkLineComponent, TooltipComponent, CanvasRenderer,
])

export type EChartOption = Parameters<ReturnType<typeof echarts.init>['setOption']>[0]

/** Thin ECharts wrapper. `label` is the accessible name: the canvas itself is not readable by assistive tech. */
export function EChart({ option, label, height = 240 }: { option: EChartOption; label: string; height?: number }) {
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!ref.current) return
    const chart = echarts.init(ref.current, undefined, { renderer: 'canvas' })
    chart.setOption(option)
    const ro = new ResizeObserver(() => chart.resize())
    ro.observe(ref.current)
    return () => {
      ro.disconnect()
      chart.dispose()
    }
  }, [option])
  return <div ref={ref} role="img" aria-label={label} className="chart" style={{ height }} />
}
