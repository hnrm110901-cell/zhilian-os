import React, { useRef, useEffect } from 'react';

interface DataPoint {
  label:   string;
  value:   number;
  value2?: number;  // optional second series (e.g. target/benchmark)
}

interface ChartTrendProps {
  data:        DataPoint[];
  height?:     number;
  color?:      string;
  color2?:     string;
  unit?:       string;
  showDots?:   boolean;
}

/**
 * 轻量趋势折线图（原生 Canvas，不依赖 ECharts）。
 * 适合小屏卡片内嵌场景，无外部依赖。
 */
export default function ChartTrend({
  data,
  height    = 80,
  color     = 'var(--accent)',
  color2    = '#007AFF',
  unit      = '',
  showDots  = false,
}: ChartTrendProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !data.length) return;

    const dpr = window.devicePixelRatio || 1;
    const W   = canvas.offsetWidth;
    const H   = canvas.offsetHeight;
    canvas.width  = W * dpr;
    canvas.height = H * dpr;

    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.scale(dpr, dpr);

    const pad = { top: 8, right: 8, bottom: 20, left: 36 };
    const chartW = W - pad.left - pad.right;
    const chartH = H - pad.top - pad.bottom;

    const allVals = data.flatMap(d => [d.value, ...(d.value2 !== undefined ? [d.value2] : [])]);
    const minVal  = Math.min(...allVals);
    const maxVal  = Math.max(...allVals);
    const range   = maxVal - minVal || 1;

    const xPos = (i: number) => pad.left + (i / Math.max(data.length - 1, 1)) * chartW;
    const yPos = (v: number) => pad.top + chartH - ((v - minVal) / range) * chartH;

    // Resolve CSS vars (canvas doesn't inherit CSS vars)
    const style = getComputedStyle(canvas);
    const resolvedColor  = color.startsWith('var') ? style.getPropertyValue(color.slice(4, -1).trim()).trim() || '#FF6B2C' : color;
    const resolvedColor2 = color2.startsWith('var') ? style.getPropertyValue(color2.slice(4, -1).trim()).trim() || '#007AFF' : color2;
    const textColor      = style.getPropertyValue('--text-tertiary').trim() || '#999';

    // Draw gridline at max
    ctx.strokeStyle = 'rgba(0,0,0,0.06)';
    ctx.lineWidth   = 1;
    ctx.setLineDash([3, 3]);
    ctx.beginPath();
    ctx.moveTo(pad.left, pad.top);
    ctx.lineTo(W - pad.right, pad.top);
    ctx.stroke();
    ctx.setLineDash([]);

    // Draw axis labels
    ctx.font        = `11px -apple-system, sans-serif`;
    ctx.fillStyle   = textColor;
    ctx.textAlign   = 'right';
    ctx.fillText(`${maxVal.toFixed(0)}${unit}`, pad.left - 4, pad.top + 4);
    ctx.fillText(`${minVal.toFixed(0)}${unit}`, pad.left - 4, pad.top + chartH + 4);

    // X labels (first and last only)
    ctx.textAlign = 'center';
    ctx.fillText(data[0].label, xPos(0), H - 4);
    if (data.length > 1) ctx.fillText(data[data.length - 1].label, xPos(data.length - 1), H - 4);

    // Helper: draw one series
    const drawLine = (values: number[], clr: string) => {
      ctx.strokeStyle = clr;
      ctx.lineWidth   = 2;
      ctx.lineJoin    = 'round';
      ctx.beginPath();
      values.forEach((v, i) => {
        const x = xPos(i);
        const y = yPos(v);
        if (i === 0) { ctx.moveTo(x, y); } else { ctx.lineTo(x, y); }
      });
      ctx.stroke();

      if (showDots) {
        values.forEach((v, i) => {
          ctx.beginPath();
          ctx.arc(xPos(i), yPos(v), 3, 0, Math.PI * 2);
          ctx.fillStyle = clr;
          ctx.fill();
        });
      }
    };

    // Fill area under first series
    ctx.beginPath();
    data.forEach(({ value }, i) => {
      const x = xPos(i);
      const y = yPos(value);
      if (i === 0) { ctx.moveTo(x, y); } else { ctx.lineTo(x, y); }
    });
    ctx.lineTo(xPos(data.length - 1), pad.top + chartH);
    ctx.lineTo(xPos(0), pad.top + chartH);
    ctx.closePath();
    const grad = ctx.createLinearGradient(0, pad.top, 0, pad.top + chartH);
    grad.addColorStop(0, resolvedColor + '40');
    grad.addColorStop(1, resolvedColor + '00');
    ctx.fillStyle = grad;
    ctx.fill();

    drawLine(data.map(d => d.value), resolvedColor);
    if (data.some(d => d.value2 !== undefined)) {
      drawLine(data.map(d => d.value2 ?? d.value), resolvedColor2);
    }
  }, [data, color, color2, unit, showDots, height]);

  return (
    <canvas
      ref={canvasRef}
      style={{ width: '100%', height, display: 'block' }}
    />
  );
}
