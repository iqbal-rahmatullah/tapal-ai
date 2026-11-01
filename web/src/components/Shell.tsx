import type { ReactNode } from "react"
import type { IconName } from "../utils/icons"
import { href, type Route } from "../utils/router"
import { Icon } from "./ui"

const MENU: { group: string; items: { page: Route["page"]; label: string; icon: IconName }[] }[] = [
  {
    group: "Pemeriksaan",
    items: [
      { page: "antrean", label: "Antrean kerja", icon: "list-checks" },
      { page: "cek", label: "Cek klaim masuk", icon: "scan-search" },
      { page: "pemindai", label: "Pemindai garis", icon: "ruler" },
      { page: "audit", label: "Rencana audit", icon: "clipboard-list" },
    ],
  },
  {
    group: "Pelaporan",
    items: [
      { page: "laporan", label: "Laporan", icon: "file-text" },
      { page: "jejak", label: "Jejak keputusan", icon: "history" },
    ],
  },
]

function activePage(route: Route): Route["page"] {
  return route.page === "rs" || route.page === "klaim" ? "antrean" : route.page
}

export function Logo({ className = "", ink = false }: { className?: string; ink?: boolean }) {
  return (
    <svg viewBox="22 34 694.2 182" className={className} role="img" aria-label="TAPAL">
      <path
        fill={ink ? "#0D366B" : "#FFFFFF"}
        d="M28,70 L102,70 L102,116 L28,116 Z M154,40 L228,40 L228,86 L154,86 Z M102,116 L154,86 L154,210 L102,210 Z M307.92 177V91.85H281.54V73H355.52V91.85H329.56V177Z M350.92,177 L386.09,73 L414.85,73 L450.03,177 L426.44,177 L403.4,87.8 L397.54,87.8 L374.37,177 Z M459.1 177V73H499.03Q509.78 73 518.08 76.77Q526.39 80.54 531.14 87.94Q535.88 95.34 535.88 106.22Q535.88 116.83 531.07 124.23Q526.25 131.63 517.94 135.47Q509.64 139.31 499.03 139.31H480.74V177ZM480.74 120.46H499.17Q503.77 120.46 507.12 118.65Q510.48 116.83 512.36 113.62Q514.24 110.41 514.24 106.22Q514.24 101.9 512.36 98.69Q510.48 95.48 507.12 93.66Q503.77 91.85 499.17 91.85H480.74Z M535.74,177 L570.92,73 L599.68,73 L634.86,177 L611.26,177 L588.23,87.8 L582.37,87.8 L559.19,177 Z M643.09 177V73H664.73V158.15H708.7V177Z"
      />
      <path fill="#EB6834" d="M102,70 L154,40 L102,116 Z M356.11,161.64 L444.84,161.64 L438.22,142.1 L362.72,142.1 Z M551.56,130.23 L619.04,130.23 L612.43,110.69 L558.17,110.69 Z" />
      <path fill="#C24E1C" d="M154,40 L154,86 L102,116 Z" />
      {ink && <path fill="#0A2A55" d="M102,116 L154,86 L154,102 Z" />}
    </svg>
  )
}

export function Sidebar({ route, queueCount }: { route: Route; queueCount: number | null }) {
  const active = activePage(route)
  return (
    <aside className="flex h-full w-60 shrink-0 flex-col gap-0.5 bg-biru-tua px-4 py-6">
      <a href={href("antrean")} className="px-2 pb-5" aria-label="TAPAL, ke Antrean kerja">
        <Logo className="h-9 w-[137px]" />
      </a>
      {MENU.map((g) => (
        <div key={g.group} className="flex flex-col gap-0.5">
          <p className="px-3 pt-3.5 pb-1.5 text-xs font-semibold tracking-[0.8px] text-biru-terang uppercase">{g.group}</p>
          {g.items.map((it) => (
            <MenuItem key={it.page} href={href(it.page)} icon={it.icon} active={it.page === active}>
              {it.label}
              {it.page === "antrean" && queueCount !== null && (
                <span className="rounded-full bg-biru px-[7px] py-px text-xs font-semibold text-white">{queueCount}</span>
              )}
            </MenuItem>
          ))}
        </div>
      ))}
      <span className="flex-1" />
      <MenuItem href="/docs" icon="code" external>
        Dokumentasi API
      </MenuItem>
      <p className="px-2.5 pt-2.5 text-xs text-biru-terang">Versi tapal-1.0</p>
    </aside>
  )
}

function MenuItem({ href, icon, active = false, external = false, children }: { href: string; icon: IconName; active?: boolean; external?: boolean; children: ReactNode }) {
  return (
    <a
      href={href}
      target={external ? "_blank" : undefined}
      rel={external ? "noreferrer" : undefined}
      aria-current={active ? "page" : undefined}
      className={`relative flex items-center gap-2.5 rounded-md px-3 py-[9px] text-sm ${active ? "bg-white/10 font-semibold text-white" : "font-medium text-white/72 hover:bg-white/5 hover:text-white"}`}
    >
      {active && <span className="absolute top-[9px] left-0 h-5 w-[3px] rounded-[2px] bg-biru-terang" />}
      <Icon name={icon} size={18} className={active ? "text-white" : "text-white/72"} />
      <span className="flex flex-1 items-center justify-between gap-2">{children}</span>
    </a>
  )
}

export function TopBar({ onSearch }: { onSearch: (text: string) => void }) {
  return (
    <header className="flex h-16 shrink-0 items-center gap-3 border-b border-garis bg-kartu px-6">
      <Picker icon="map-pin" value="Wilayah Uji" extra="data sintetis" />
      <Picker icon="calendar" label="Pembebanan" value="Des 2025" />
      <span className="flex-1" />
      <form
        className="flex w-60 items-center gap-2 rounded-md bg-latar px-3 py-2"
        onSubmit={(e) => {
          e.preventDefault()
          onSearch(String(new FormData(e.currentTarget).get("q") ?? ""))
        }}
      >
        <Icon name="search" size={15} className="text-redam" />
        <input name="q" placeholder="Cari RS atau nomor SEP" className="w-full bg-transparent text-[13px] text-tinta outline-hidden placeholder:text-redam" />
      </form>
      <span className="h-7 w-px bg-garis" />
      <div className="flex items-center gap-2.5">
        <span className="grid size-8 place-items-center rounded-full bg-biru-muda">
          <Icon name="user-round" size={16} className="text-biru-tua" />
        </span>
        <span className="flex flex-col leading-tight">
          <span className="text-[13px] font-semibold text-tinta">Verifikator</span>
          <span className="text-xs text-redam">Kantor Cabang Contoh</span>
        </span>
      </div>
    </header>
  )
}

function Picker({ icon, label, value, extra }: { icon: IconName; label?: string; value: string; extra?: string }) {
  return (
    <span className="flex items-center gap-2 rounded-md border border-garis px-2.5 py-[7px] text-[13px]" title="Satu wilayah dan satu bulan tersedia di data sintetis">
      <Icon name={icon} size={15} className="text-tinta-2" />
      {label && <span className="text-redam">{label}</span>}
      <span className="font-semibold text-tinta">{value}</span>
      {extra && <span className="text-redam">{extra}</span>}
      <Icon name="chevron-down" size={14} className="text-tinta-2" />
    </span>
  )
}
