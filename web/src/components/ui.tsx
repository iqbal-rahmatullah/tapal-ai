import type { ReactNode } from "react"
import { ICONS, type IconName } from "../utils/icons"
import type { Confidence as ConfidenceLevel, DataSource, HandlingStatus, Machine, Mode } from "../types"

export function Icon({ name, size = 16, className = "" }: { name: IconName; size?: number; className?: string }) {
  const Glyph = ICONS[name]
  return <Glyph size={size} strokeWidth={2} aria-hidden className={`shrink-0 ${className}`} />
}

const MACHINE_STYLE: Record<Machine, string> = {
  "AI 1": "bg-biru-muda text-biru-tua",
  "AI 2": "bg-biru-muda text-biru-tua",
  "AI 3": "bg-biru-muda text-biru-tua",
  "AI 4": "bg-biru-muda text-biru-tua",
  Statistik: "bg-abu-kartu text-tinta-2",
  Kode: "border border-garis text-tinta-2",
  "LLM narasi": "border border-biru text-biru",
  Manusia: "bg-tinta text-white",
  Admin: "bg-tinta text-white",
}

export function MachineLabel({ kind }: { kind: Machine }) {
  return (
    <span className={`inline-flex h-6 shrink-0 items-center rounded-full px-2 text-xs font-semibold whitespace-nowrap ${MACHINE_STYLE[kind]}`}>
      {kind}
    </span>
  )
}

export function MachineLabels({ kinds }: { kinds: Machine[] }) {
  return (
    <span className="flex items-center gap-1.5">
      {kinds.map((k) => (
        <MachineLabel key={k} kind={k} />
      ))}
    </span>
  )
}

const MODES: Record<Mode, { text: string; icon: IconName }> = {
  fiktif: { text: "Ventilasi fiktif", icon: "ban" },
  diperpanjang: { text: "Diperpanjang ≥96 jam", icon: "timer" },
  rme_meragukan: { text: "RME meragukan", icon: "circle-alert" },
}

export function ModeChip({ mode }: { mode: Mode }) {
  const m = MODES[mode]
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-abu-kartu px-2.5 py-1 text-xs font-semibold whitespace-nowrap text-tinta">
      <Icon name={m.icon} size={14} className="text-tinta-2" />
      {m.text}
    </span>
  )
}

const STATUS: Record<HandlingStatus, { text: string; icon: IconName; chip: string; tint: string }> = {
  baru: { text: "Baru", icon: "circle-dot", chip: "bg-[#E6F0FC] border-[#BFD7F6] text-biru-tua", tint: "text-biru" },
  diklarifikasi: { text: "Diklarifikasi", icon: "message-square", chip: "bg-[#FDF4DC] border-[#F1D58E] text-[#6B4A00]", tint: "text-[#C99118]" },
  diaudit: { text: "Diaudit", icon: "clipboard-check", chip: "bg-[#EEE8FB] border-[#D3C5F2] text-[#3B1675]", tint: "text-[#4C1D95]" },
  selesai: { text: "Selesai", icon: "check", chip: "bg-[#F1F2F4] border-[#DADDE2] text-[#4B5563]", tint: "text-[#9CA3AF]" },
}

export function StatusChip({ status }: { status: HandlingStatus }) {
  const s = STATUS[status]
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold whitespace-nowrap ${s.chip}`}>
      <Icon name={s.icon} size={14} className={s.tint} />
      {s.text}
    </span>
  )
}

const LEVEL: Record<ConfidenceLevel, { text: string; bars: number }> = {
  kuat: { text: "Kuat", bars: 3 },
  sedang: { text: "Sedang", bars: 2 },
  lemah: { text: "Lemah", bars: 1 },
  pola_kuat: { text: "Pola kuat", bars: 3 },
}

export function Confidence({ level, detail }: { level: ConfidenceLevel; detail: string }) {
  const l = LEVEL[level]
  return (
    <span className="flex items-center gap-2">
      <span className="flex items-end gap-0.5" aria-hidden>
        {[6, 10, 14].map((h, i) => (
          <span key={h} style={{ height: h }} className={`w-1 rounded-[1px] ${i < l.bars ? "bg-biru" : "bg-garis"}`} />
        ))}
      </span>
      <span className="flex flex-col gap-px leading-tight">
        <span className="text-[13px] font-semibold text-tinta">{l.text}</span>
        <span className="font-mono text-xs text-redam">{detail}</span>
      </span>
    </span>
  )
}

export function RangeMini({ lo, mid, hi, max, width = 120 }: { lo: number; mid: number; hi: number; max: number; width?: number }) {
  const x = (v: number) => `${Math.min(100, Math.max(0, (v / max) * 100))}%`
  return (
    <span className="relative block h-3.5" style={{ width }} aria-label="rentang 95%">
      <span className="absolute top-1.5 right-0 left-0 h-px bg-garis" />
      <span className="absolute top-1.5 h-0.5 bg-biru" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
      <span className="absolute top-[3px] size-2 -translate-x-1/2 rounded-full bg-biru ring-2 ring-white" style={{ left: x(mid) }} />
    </span>
  )
}

export function ClaimedMini({ claimed, fair, fairLo, fairHi, max, width = 110 }: { claimed: number; fair: number; fairLo: number; fairHi: number; max: number; width?: number }) {
  const w = (v: number) => `${(v / max) * 100}%`
  return (
    <span className="relative block h-3.5" style={{ width }}>
      <span className="absolute top-px left-0 h-2 rounded-[2px] bg-biru-muda" style={{ width: w(claimed) }} />
      <span className="absolute top-px left-0 h-2 rounded-l-[2px] bg-biru" style={{ width: w(fair) }} />
      <span className="absolute top-3 h-0.5 bg-tinta-2" style={{ left: w(fairLo), width: `calc(${w(fairHi)} - ${w(fairLo)})` }} />
    </span>
  )
}

type ButtonProps = {
  variant?: "primer" | "sekunder" | "teks"
  icon?: IconName
  children: ReactNode
  onClick?: () => void
  disabled?: boolean
  type?: "button" | "submit"
  className?: string
  title?: string
}

export function Button({ variant = "sekunder", icon, children, onClick, disabled, type = "button", className = "", title }: ButtonProps) {
  const look = {
    primer: "bg-biru text-white hover:bg-[#2369BF] disabled:bg-biru/50",
    sekunder: "bg-kartu text-tinta border border-garis hover:bg-latar disabled:text-redam",
    teks: "text-biru hover:underline disabled:text-redam",
  }[variant]
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      title={title}
      className={`inline-flex items-center gap-2 rounded-md text-sm font-semibold whitespace-nowrap transition-colors ${variant === "teks" ? "" : "px-3.5 py-[9px]"} ${look} ${className}`}
    >
      {icon && <Icon name={icon} size={16} className={variant === "primer" ? "text-white" : "text-tinta-2"} />}
      {children}
    </button>
  )
}

export function Segmented<T extends string>({ options, value, onChange }: { options: { value: T; label: string }[]; value: T; onChange: (v: T) => void }) {
  return (
    <span role="radiogroup" className="inline-flex items-center gap-0.5 rounded-lg bg-segmen p-[3px]">
      {options.map((o) => (
        <button
          key={o.value}
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={`rounded-md px-3 py-1.5 text-[13px] ${o.value === value ? "bg-kartu font-semibold text-tinta shadow-[0_1px_2px_rgba(11,11,11,0.1)]" : "font-medium text-tinta-2 hover:text-tinta"}`}
        >
          {o.label}
        </button>
      ))}
    </span>
  )
}

export function FilterChip<T extends string>({ label, value, options, onChange }: { label: string; value: T; options: { value: T; label: string }[]; onChange: (v: T) => void }) {
  const current = options.find((o) => o.value === value)?.label ?? value
  return (
    <label className="relative inline-flex cursor-pointer items-center gap-1.5 rounded-md border border-garis bg-kartu px-2.5 py-1.5 text-[13px] hover:bg-latar">
      <span className="text-tinta-2">{label}:</span>
      <span className="font-semibold text-tinta">{current}</span>
      <Icon name="chevron-down" size={14} className="text-tinta-2" />
      <select value={value} onChange={(e) => onChange(e.target.value as T)} className="absolute inset-0 cursor-pointer opacity-0" aria-label={label}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  )
}

export function HonestNote({ children, label = "Catatan jujur", className = "" }: { children: ReactNode; label?: string; className?: string }) {
  return (
    <div className={`flex items-center gap-3 border-l-4 border-jingga bg-abu-kartu px-3.5 py-2.5 ${className}`}>
      <span className="shrink-0 text-xs font-semibold tracking-[0.8px] text-redam uppercase">{label}</span>
      <span className="text-[13px] text-tinta-2">{children}</span>
    </div>
  )
}

export function Card({ title, labels, aside, children, className = "", bodyClass = "" }: { title?: ReactNode; labels?: Machine[]; aside?: ReactNode; children: ReactNode; className?: string; bodyClass?: string }) {
  return (
    <section className={`flex flex-col rounded-lg border border-garis bg-kartu ${className}`}>
      {(title || labels || aside) && (
        <header className="flex items-center justify-between gap-3 px-4 pt-3.5">
          <h2 className="text-[15px] font-semibold text-tinta">{title}</h2>
          <span className="flex items-center gap-1.5">
            {aside}
            {labels && <MachineLabels kinds={labels} />}
          </span>
        </header>
      )}
      <div className={`flex flex-col px-4 pt-2.5 pb-3.5 ${bodyClass}`}>{children}</div>
    </section>
  )
}

export function Tile({ value, unit, caption, labels, source, progress }: { value: string; unit?: string; caption: string; labels: Machine[]; source: string; progress?: number }) {
  return (
    <section className="flex h-[148px] min-w-0 flex-1 flex-col gap-1.5 rounded-lg border border-garis bg-kartu px-4 py-3.5">
      <div className="flex items-end gap-1.5">
        <span className="font-display text-[30px] leading-none font-bold text-tinta">{value}</span>
        {unit && <span className="pb-0.5 text-sm font-medium text-tinta-2">{unit}</span>}
      </div>
      <p className="text-[13px] text-tinta-2">{caption}</p>
      {progress !== undefined && (
        <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-abu-kartu">
          <span className="block h-full rounded-full bg-biru" style={{ width: `${Math.round(progress * 100)}%` }} />
        </span>
      )}
      <span className="flex-1" />
      <footer className="flex items-center gap-1.5 border-t border-garis pt-2">
        <MachineLabels kinds={labels} />
        <span className="truncate text-xs text-redam">{source}</span>
      </footer>
    </section>
  )
}

export function SampleDataBadge({ data }: { data?: DataSource }) {
  const parts = data?.bagian_contoh ?? []
  const whole = data?.sumber_data === "contoh_desain"
  if (!data || (!whole && parts.length === 0)) return null
  return (
    <span
      title={whole ? "Angka di halaman ini adalah contoh desain, belum keluaran mesin." : `Bagian yang masih contoh desain: ${parts.join(", ")}.`}
      className="inline-flex items-center gap-1.5 rounded-full border border-dashed border-redam px-2.5 py-1 font-sans text-xs font-semibold whitespace-nowrap text-tinta-2"
    >
      <Icon name="flask-conical" size={13} className="text-redam" />
      {whole ? "Data contoh desain" : "Sebagian data contoh"}
    </span>
  )
}

const PHYSIONET = [
  { name: "eICU-CRD Demo v2.0.1", url: "https://physionet.org/content/eicu-crd-demo/2.0.1/" },
  { name: "MIMIC-IV Clinical Database Demo v2.2", url: "https://physionet.org/content/mimic-iv-demo/2.2/" },
  { name: "Open Database License v1.0", url: "https://opendatacommons.org/licenses/odbl/1-0/" },
]

// ODbL 4.3 asks for a notice wherever the physiology reader is shown in public; printed copies also carry the addresses.
export function OdblNote({ print = false, className = "" }: { print?: boolean; className?: string }) {
  const link = (i: number) => (
    <a href={PHYSIONET[i].url} target="_blank" rel="noreferrer" className="underline decoration-garis underline-offset-2">
      {PHYSIONET[i].name}
      {print && ` (${PHYSIONET[i].url})`}
    </a>
  )
  return (
    <p className={`text-xs text-tinta-2 ${className}`}>
      Pembaca fisiologi dilatih dengan {link(0)} dan divalidasi dengan {link(1)} dari PhysioNet; keduanya berlisensi {link(2)}.
    </p>
  )
}

export function Skeleton({ className = "" }: { className?: string }) {
  return <span className={`kerangka block ${className}`} />
}

export function EmptyState({ icon = "info", title, children }: { icon?: IconName; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 px-6 py-12 text-center">
      <span className="grid size-10 place-items-center rounded-full bg-latar">
        <Icon name={icon} size={18} className="text-tinta-2" />
      </span>
      <p className="text-[15px] font-semibold text-tinta">{title}</p>
      {children && <p className="max-w-md text-sm text-tinta-2">{children}</p>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center justify-center gap-3 px-6 py-12 text-center">
      <span className="flex items-center gap-2 text-sm font-semibold text-merah">
        <Icon name="circle-x" size={18} />
        Gagal memuat data
      </span>
      <p className="max-w-md text-sm text-tinta-2">{message}</p>
      {onRetry && (
        <Button icon="refresh-cw" onClick={onRetry}>
          Coba lagi
        </Button>
      )}
    </div>
  )
}

export function PageHeader({ title, children, actions }: { title: ReactNode; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <div className="flex min-w-0 flex-col gap-1">
        <h1 className="font-display text-2xl font-bold text-tinta">{title}</h1>
        {children}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  )
}

export function Crumbs({ items }: { items: { label: string; href?: string }[] }) {
  return (
    <nav className="flex items-center gap-1.5 text-[13px]" aria-label="Jejak halaman">
      {items.map((it, i) => (
        <span key={it.label} className="flex items-center gap-1.5">
          {i === 0 && <Icon name="chevron-left" size={14} className="text-biru" />}
          {it.href ? (
            <a href={it.href} className={i === 0 ? "font-semibold text-biru hover:underline" : "text-tinta-2 hover:underline"}>
              {it.label}
            </a>
          ) : (
            <span className="text-tinta-2">{it.label}</span>
          )}
          {i < items.length - 1 && <Icon name="chevron-right" size={13} className="text-redam" />}
        </span>
      ))}
    </nav>
  )
}

export function Th({ children, className = "" }: { children?: ReactNode; className?: string }) {
  return <th className={`px-3 py-2.5 text-left text-xs font-semibold tracking-[0.6px] whitespace-nowrap text-redam uppercase ${className}`}>{children}</th>
}

export function Toast({ children }: { children: ReactNode }) {
  return (
    <div role="status" className="fixed top-[76px] left-1/2 z-50 flex -translate-x-1/2 items-center gap-2 rounded-lg bg-tinta px-4 py-2 text-sm font-medium text-white shadow-kartu">
      <Icon name="circle-check" size={16} className="text-white" />
      {children}
    </div>
  )
}
