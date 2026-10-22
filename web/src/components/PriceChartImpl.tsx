import { useEffect, useRef } from 'react';
import * as echarts from 'echarts';
import type { EChartsOption, MarkAreaComponentOption, MarkLineComponentOption } from 'echarts';
import type { SeriesPoint } from '../lib/types';
import { formatPrice, formatShortDateTime, formatDiscount } from '../lib/format';

export interface PriceChartProps {
  points: SeriesPoint[];
  currency: string;
  atlCents: number | null;
  recordStartedAt: string | null;
}

interface TooltipParam {
  dataIndex: number;
  seriesName?: string;
}

export default function PriceChartImpl({ points, currency, atlCents, recordStartedAt }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = echarts.init(el, undefined, { renderer: 'canvas' });
    chartRef.current = chart;
    const observer = new ResizeObserver(() => chart.resize());
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    const xLabels = points.map((point) => formatShortDateTime(point.t));
    const finalValues = points.map((point) => (point.available && point.final > 0 ? point.final / 100 : null));
    const initialValues = points.map((point) => (point.initial > 0 ? point.initial / 100 : null));

    // 打折区间：连续 discount > 0 的点合并为一段
    const markAreas: Array<[{ xAxis: string }, { xAxis: string }]> = [];
    let areaStart: number | null = null;
    points.forEach((point, index) => {
      const discounting = point.discount > 0;
      if (discounting && areaStart === null) areaStart = index;
      if (!discounting && areaStart !== null) {
        markAreas.push([{ xAxis: xLabels[areaStart] }, { xAxis: xLabels[index] }]);
        areaStart = null;
      }
    });
    if (areaStart !== null) {
      markAreas.push([{ xAxis: xLabels[areaStart] }, { xAxis: xLabels[xLabels.length - 1] }]);
    }

    const markLineData: NonNullable<MarkLineComponentOption['data']> = [];
    if (atlCents && atlCents > 0) {
      markLineData.push({
        yAxis: atlCents / 100,
        lineStyle: { color: '#4ade80', type: 'dashed', width: 1.2, opacity: 0.8 },
        label: {
          formatter: `历史最低 ${formatPrice(atlCents, currency)}`,
          position: 'insideEndTop',
          color: '#4ade80',
          fontSize: 11,
        },
      });
    }
    if (recordStartedAt && xLabels.length > 0) {
      const startedIndex = points.findIndex((point) => point.t >= recordStartedAt);
      const anchorLabel = finishedLabel(startedIndex, xLabels);
      if (anchorLabel) {
        markLineData.push({
          xAxis: anchorLabel,
          lineStyle: { color: '#8b9bb0', type: 'dotted', width: 1 },
          label: {
            formatter: '记录起点',
            position: 'insideEndBottom',
            color: '#8b9bb0',
            fontSize: 10,
          },
        });
      }
    }

    const option: EChartsOption = {
      animationDuration: 300,
      backgroundColor: 'transparent',
      grid: { left: 12, right: 18, top: 36, bottom: 8, containLabel: true },
      legend: {
        top: 0,
        right: 0,
        itemWidth: 14,
        itemHeight: 8,
        textStyle: { color: '#8b9bb0', fontSize: 11 },
        data: ['现价', '原价'],
      },
      tooltip: {
        trigger: 'axis',
        backgroundColor: 'rgba(14,20,27,0.96)',
        borderColor: '#2a3a4a',
        padding: [8, 10],
        textStyle: { color: '#e6edf3', fontSize: 12 },
        axisPointer: { type: 'line', lineStyle: { color: '#2a3a4a' } },
        formatter: (raw: unknown) => {
          const list = Array.isArray(raw) ? (raw as TooltipParam[]) : [raw as TooltipParam];
          const index = list[0]?.dataIndex ?? 0;
          const point = points[index];
          if (!point) return '';
          const rows = [
            `<div style="color:#8b9bb0;font-size:11px;margin-bottom:4px">${formatShortDateTime(point.t)}</div>`,
            `<div style="display:flex;justify-content:space-between;gap:16px"><span>现价</span><span style="color:#66c0f4;font-weight:600">${point.available ? formatPrice(point.final, currency) : '不可用'}</span></div>`,
            point.discount > 0
              ? `<div style="display:flex;justify-content:space-between;gap:16px"><span>原价</span><span style="text-decoration:line-through;color:#8b9bb0">${formatPrice(point.initial, currency)}</span></div><div style="display:flex;justify-content:space-between;gap:16px"><span>折扣</span><span style="color:#fbbf24">${formatDiscount(point.discount)}</span></div>`
              : '',
          ];
          return rows.join('');
        },
      },
      xAxis: {
        type: 'category',
        boundaryGap: false,
        data: xLabels,
        axisLine: { lineStyle: { color: '#1e2a36' } },
        axisTick: { show: false },
        axisLabel: { color: '#5f7186', fontSize: 10, hideOverlap: true },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: '#5f7186',
          fontSize: 10,
          formatter: (value: number) => `${currencySymbolOf(currency)}${value >= 1000 ? `${Math.round(value / 100) / 10}k` : value}`,
        },
        splitLine: { lineStyle: { color: '#1e2a36', type: 'dashed', opacity: 0.7 } },
      },
      series: [
        {
          name: '现价',
          type: 'line',
          step: 'end',
          data: finalValues,
          connectNulls: false,
          symbol: 'circle',
          symbolSize: 5,
          showSymbol: false,
          lineStyle: { color: '#66c0f4', width: 2.2 },
          itemStyle: { color: '#66c0f4' },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: 'rgba(102,192,244,0.22)' },
              { offset: 1, color: 'rgba(102,192,244,0.01)' },
            ]),
          },
          markLine: { silent: true, symbol: 'none', data: markLineData, emphasis: { disabled: true } },
          markArea:
            markAreas.length > 0
              ? ({
                  silent: true,
                  itemStyle: { color: 'rgba(251,191,36,0.07)' },
                  data: markAreas,
                } satisfies MarkAreaComponentOption)
              : undefined,
        },
        {
          name: '原价',
          type: 'line',
          step: 'end',
          data: initialValues,
          symbol: 'none',
          showSymbol: false,
          lineStyle: { color: '#5f7186', width: 1, type: 'dashed', opacity: 0.7 },
        },
      ],
    };

    chart.setOption(option, true);
  }, [points, currency, atlCents, recordStartedAt]);

  return <div ref={containerRef} className="h-72 w-full sm:h-80" role="img" aria-label="价格历史阶梯图" />;
}

function finishedLabel(index: number, labels: string[]): string | null {
  if (labels.length === 0) return null;
  if (index <= 0) return labels[0];
  if (index >= labels.length) return labels[labels.length - 1];
  return labels[index];
}

function currencySymbolOf(currency: string): string {
  const map: Record<string, string> = { CNY: '¥', USD: '$', EUR: '€', GBP: '£', JPY: '¥' };
  return map[currency] ?? '';
}
