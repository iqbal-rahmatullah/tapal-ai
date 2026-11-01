import { useEffect, useRef } from "react"
import { num } from "../utils/format"

const INK = "#0B0B0B"
const MUTED = "#898781"
const PEER = "#C3C2B7"
const BLUE = "#2A78D6"
const LINE = "#E1E0D9"

function Tick({ x, y, label, anchor = "middle" }: { x: number; y: number; label: string; anchor?: "start" | "middle" | "end" }) {
  return (
    <text x={x} y={y} textAnchor={anchor} fontSize={12} fill={MUTED} fontFamily="JetBrains Mono, monospace">
      {label}
    </text>
  )
}

export function Legend({ items }: { items: { label: string; color: string; shape?: "box" | "dot" | "line" }[] }) {
  return (
    <span className="flex items-center gap-3">
      {items.map((it) => (
        <span key={it.label} className="flex items-center gap-1.5 text-xs text-tinta-2">
          <span
            className={it.shape === "dot" ? "size-2 rounded-full" : it.shape === "line" ? "h-0.5 w-3.5" : "size-[9px] rounded-[2px]"}
            style={{ background: it.color }}
          />
          {it.label}
        </span>
      ))}
    </span>
  )
}

export function ProbabilityHistogram({ rs, peers }: { rs: number[]; peers: number[] }) {
  const W = 528, H = 96, top = Math.max(...rs, ...peers), group = W / rs.length
  const h = (v: number) => (v / top) * (H - 4)
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="w-full" role="img" aria-label="Sebaran peluang didukung bukti per kelompok 0,1">
      {rs.map((v, i) => {
        const cx = group * i + group / 2
        return (
          <g key={i}>
            <rect x={cx - 17.5} y={H - h(v)} width={16} height={h(v)} rx={2} fill={BLUE}>
              <title>{`${num(i / 10, 1)}–${num((i + 1) / 10, 1)}: ${v}% klaim RS ini`}</title>
            </rect>
            <rect x={cx + 1.5} y={H - h(peers[i])} width={16} height={h(peers[i])} rx={2} fill={PEER}>
              <title>{`${num(i / 10, 1)}–${num((i + 1) / 10, 1)}: ${peers[i]}% klaim RS sekelas`}</title>
            </rect>
          </g>
        )
      })}
      <line x1={0} x2={W} y1={H + 0.5} y2={H + 0.5} stroke={LINE} />
      <Tick x={2} y={H + 15} label="0" anchor="start" />
      <Tick x={W / 2} y={H + 15} label="0,5" />
      <Tick x={W - 2} y={H + 15} label="1,0" anchor="end" />
    </svg>
  )
}

export function PeerDotPlot({ peers, rs, band, domain = [0.6, 1.9] }: { peers: { rasio: number; y: number }[]; rs: { kode: string; rasio: number }; band: [number, number]; domain?: [number, number] }) {
  const W = 528, H = 96, pad = 16
  const x = (v: number) => pad + ((Math.min(Math.max(v, domain[0]), domain[1]) - domain[0]) / (domain[1] - domain[0])) * (W - 2 * pad)
  // Ticks sit on a grid anchored at 1,0 (supported by evidence), so the band reads the same on every RS.
  const step = domain[1] - domain[0] > 2 ? 0.5 : 0.4
  const first = Math.ceil((domain[0] - 1) / step - 1e-9)
  const ticks = Array.from({ length: Math.floor((domain[1] - 1) / step + 1e-9) - first + 1 }, (_, i) => Math.round((1 + (first + i) * step) * 10) / 10)
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="w-full" role="img" aria-label={`Rasio diakui dibanding wajar, ${rs.kode} ${num(rs.rasio, 2)}`}>
      <rect x={x(band[0])} y={0} width={x(band[1]) - x(band[0])} height={H} fill="#F0EFEC" />
      <text x={x(band[0]) + 6} y={14} fontSize={12} fill={MUTED}>
        rentang wajar
      </text>
      {peers.map((p, i) => (
        <circle key={i} cx={x(p.rasio)} cy={p.y * H} r={4} fill={PEER} stroke="#fff" strokeWidth={1.5}>
          <title>{`RS sekelas: ${num(p.rasio, 2)}`}</title>
        </circle>
      ))}
      <circle cx={x(rs.rasio)} cy={H * 0.54} r={5.5} fill={BLUE} stroke="#fff" strokeWidth={2} />
      <text x={x(rs.rasio) - 10} y={H * 0.54 - 14} textAnchor="end" fontSize={12} fontWeight={600} fill={INK}>
        {`${rs.kode}, ${num(rs.rasio, 2)}`}
      </text>
      <line x1={pad} x2={W - pad} y1={H + 0.5} y2={H + 0.5} stroke={LINE} />
      {ticks.map((t) => (
        <g key={t}>
          <line x1={x(t)} x2={x(t)} y1={H} y2={H + 4} stroke={PEER} />
          <Tick x={x(t)} y={H + 16} label={num(t, 1)} />
        </g>
      ))}
    </svg>
  )
}

export function HoursHistogram({ start, step, rs, peers, line, placebo }: { start: number; step: number; rs: number[]; peers: number[]; line: number; placebo: number[] }) {
  const W = 528, H = 96, left = 8, right = 8
  const end = start + step * rs.length
  const x = (hour: number) => left + ((hour - start) / (end - start)) * (W - left - right)
  const top = Math.max(...rs, ...peers)
  const h = (v: number) => (v / top) * (H - 16)
  const path = peers.reduce((acc, v, i) => acc + `${i === 0 ? `M${x(start)},${H - h(v)}` : `V${H - h(v)}`} H${x(start + step * (i + 1))} `, "")
  return (
    <svg viewBox={`0 0 ${W} ${H + 20}`} className="w-full" role="img" aria-label="Histogram jam ventilator tercatat dengan garis tarif 96 jam">
      {rs.map((v, i) => (
        <rect key={i} x={x(start + step * i) + 3} y={H - h(v)} width={x(start + step) - x(start) - 6} height={h(v)} rx={2} fill={BLUE}>
          <title>{`${start + step * i}–${start + step * (i + 1)} jam: ${v} klaim`}</title>
        </rect>
      ))}
      <path d={path} fill="none" stroke={MUTED} strokeWidth={2} />
      {placebo.map((p) => (
        <g key={p}>
          <line x1={x(p)} x2={x(p)} y1={12} y2={H} stroke={PEER} strokeWidth={2} strokeDasharray="2 4" />
          <text x={p === start ? x(p) + 6 : x(p) - 6} y={10} textAnchor={p === start ? "start" : "end"} fontSize={12} fill={MUTED}>
            plasebo
          </text>
        </g>
      ))}
      <line x1={x(line)} x2={x(line)} y1={10} y2={H} stroke={INK} strokeWidth={2} strokeDasharray="6 4" />
      <text x={x(line) + 6} y={10} fontSize={12} fontWeight={600} fill={INK}>
        garis tarif 96 jam
      </text>
      <line x1={left} x2={W - right} y1={H + 0.5} y2={H + 0.5} stroke={LINE} />
      {[start, start + 12, line, line + 12, end].map((t) => (
        <Tick key={t} x={x(t)} y={H + 16} label={String(t)} />
      ))}
    </svg>
  )
}

export function WriteTimeline({ others, waves, months }: { others: { hari: number; y: number }[]; waves: { hari: number; tanggal: string; jam: string; n: number }[]; months: string[] }) {
  const W = 528, H = 96, left = 10, perDay = (W - left - 6) / (months.length * 30.6)
  const x = (day: number) => left + day * perDay
  return (
    <svg viewBox={`0 0 ${W} ${H + 18}`} className="w-full" role="img" aria-label="Tanggal catatan ICU ditulis di server, satu titik per pasien">
      {others.map((o, i) => (
        <circle key={i} cx={x(o.hari)} cy={o.y * H} r={3.5} fill={PEER} />
      ))}
      {waves.map((w) => (
        <g key={w.hari}>
          {Array.from({ length: Math.min(w.n, 14) }, (_, k) => (
            <circle key={k} cx={x(w.hari)} cy={H - 8 - k * 4.4} r={3.5} fill={BLUE}>
              <title>{`${w.n} klaim`}</title>
            </circle>
          ))}
          {w.tanggal && (
            <>
              <text x={x(w.hari) - 12} y={12} fontSize={12} fontWeight={600} fill={INK} textAnchor="start">
                {w.tanggal}
              </text>
              <text x={x(w.hari) - 8} y={26} fontSize={12} fill={MUTED} fontFamily="JetBrains Mono, monospace">
                {w.jam}
              </text>
            </>
          )}
        </g>
      ))}
      <line x1={left} x2={W} y1={H + 0.5} y2={H + 0.5} stroke={LINE} />
      {months.map((m, i) => (
        <g key={m}>
          <line x1={x(i * 30.6)} x2={x(i * 30.6)} y1={H} y2={H + 4} stroke={PEER} />
          <text x={x(i * 30.6) + 4} y={H + 16} fontSize={12} fill={MUTED}>
            {m}
          </text>
        </g>
      ))}
    </svg>
  )
}

export function SimilarityMatrix({ n, twins, median }: { n: number; twins: number; median: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const ctx = ref.current?.getContext("2d")
    if (!ctx) return
    // Deterministic noise so the picture is the same on every render; only the block size and median come from the data.
    let seed = 7
    const rand = () => ((seed = (seed * 16807) % 2147483647) / 2147483647)
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const s = i === j ? 1 : i < twins && j < twins ? median - 0.03 + rand() * 0.04 : 0.15 + rand() * 0.3
        ctx.fillStyle = `rgba(42, 120, 214, ${Math.min(1, Math.max(0.04, (s - 0.1) / 0.9))})`
        ctx.fillRect(i, j, 1, 1)
      }
    }
  }, [n, twins, median])
  return <canvas ref={ref} width={n} height={n} className="size-28 rounded-[4px] border border-garis [image-rendering:pixelated]" aria-label={`Matriks kemiripan ${n} pasien`} />
}
