import { useEffect, useRef } from 'react'
import { createChart, CrosshairMode, type IChartApi } from 'lightweight-charts'

type ChartPoint = {
  name: string
  value: number
}

type MarketChartProps = {
  title: string
  data: ChartPoint[]
}

export default function MarketChart({ title, data }: MarketChartProps) {
  const chartRef = useRef<HTMLDivElement | null>(null)
  const chartInstance = useRef<IChartApi | null>(null)

  useEffect(() => {
    const container = chartRef.current
    if (!container) return

    const chart = createChart(container, {
      width: container.clientWidth,
      height: 340,
      layout: {
        background: { color: '#0f172a' },
        textColor: '#e2e8f0',
      },
      grid: {
        vertLines: { color: '#334155' },
        horzLines: { color: '#334155' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { visible: true, borderColor: '#334155' },
      timeScale: {
        borderColor: '#334155',
        tickMarkFormatter: (time: string | number) => {
          const index = typeof time === 'number' ? time : Number(time)
          return data[index]?.name ?? ''
        },
      },
    })

    const lineSeries = (chart as any).addLineSeries({
      color: '#22d3ee',
      lineWidth: 3,
      priceLineVisible: false,
    })

    lineSeries.setData(
      data.map((item, index) => ({
        time: index,
        value: item.value,
      })),
    )
    chart.timeScale().fitContent()
    chartInstance.current = chart

    const handleResize = () => {
      if (chartRef.current) {
        chart.applyOptions({ width: chartRef.current.clientWidth })
      }
    }

    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
      chart.remove()
    }
  }, [data, title])

  return <div ref={chartRef} className="w-full rounded-3xl border border-slate-800 bg-slate-950/90 p-1 shadow-glow" />
}
