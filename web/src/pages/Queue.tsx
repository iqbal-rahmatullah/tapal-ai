import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { errorText } from "../utils/api"
import {
  Button,
  ClaimedMini,
  Confidence,
  EmptyState,
  ErrorState,
  FilterChip,
  Icon,
  MachineLabel,
  ModeChip,
  PageHeader,
  RangeMini,
  SampleDataBadge,
  Segmented,
  Skeleton,
  StatusChip,
  Th,
  Tile,
} from "../components/ui"
import { downloadCsv } from "../utils/csv"
import { miliar, num } from "../utils/format"
import { go, href } from "../utils/router"
import type { FlaggedHospital, HandlingStatus, Mode, Queue as QueueData } from "../types"

type Order = "rupiah" | "keyakinan"
const MODE_LABEL: Record<Mode, string> = { fiktif: "Ventilasi fiktif", diperpanjang: "Diperpanjang", rme_meragukan: "RME meragukan" }
const STATUS_LABEL: Record<HandlingStatus, string> = { baru: "Baru", diklarifikasi: "Diklarifikasi", diaudit: "Diaudit", selesai: "Selesai" }
const COLS = "grid grid-cols-[36px_170px_92px_186px_170px_minmax(0,1fr)_112px_128px_28px] items-center px-4"

export default function Queue() {
  const { data, error, isPending, refetch } = useQuery<QueueData>({ queryKey: ["/antrean"] })
  const [order, setOrder] = useState<Order>("rupiah")
  const [mode, setMode] = useState<Mode | "semua">("semua")
  const [kelas, setKelas] = useState<string>("semua")
  const [status, setStatus] = useState<HandlingStatus | "semua">("semua")
  const [showThin, setShowThin] = useState(false)

  if (error) return <Frame><ErrorState message={errorText(error)} onRetry={() => refetch()} /></Frame>
  if (isPending) return <Frame><QueueSkeleton /></Frame>

  const s = data.ringkasan
  const ranked = order === "rupiah" ? data.rs : data.urutan_keyakinan.map((k) => data.rs.find((r) => r.kode_rs === k)!).filter(Boolean)
  const rows = ranked.filter((r) => (mode === "semua" || r.modus === mode) && (kelas === "semua" || r.kelas === kelas) && (status === "semua" || r.status_penanganan === status))
  const filtered = mode !== "semua" || kelas !== "semua" || status !== "semua"
  const scale = Math.max(2e9, ...data.rs.map((r) => r.rupiah_atas ?? r.rupiah))

  return (
    <Frame>
      <PageHeader
        title={<span className="flex items-center gap-3">Antrean kerja <SampleDataBadge data={data} /></span>}
        actions={<Button icon="download" onClick={() => exportRows(rows)}>Ekspor CSV</Button>}
      >
        <p className="flex flex-wrap items-center gap-3.5 text-[13px]">
          <Period k="Penilaian RS:" v={data.periode.penilaian} />
          <span className="h-3.5 w-px bg-garis" />
          <Period k="Klaim yang diperiksa:" v={data.periode.klaim_diperiksa} />
          <span className="h-3.5 w-px bg-garis" />
          <Period k="Diperbarui:" v={data.periode.diperbarui} />
        </p>
      </PageHeader>

      <div className="flex gap-4">
        <Tile value={num(s.n_ditandai)} unit={`dari ${num(s.n_rs)} RS`} caption={`RS ditandai: ${perMachine(s.per_mesin)}`} labels={["Statistik"]} source={`dikoreksi untuk ${s.n_rs} RS`} />
        <Tile value={miliar(s.total_rupiah, 1)} caption={`perkiraan kelebihan bayar 12 bulan, jumlah rentang per RS Rp${num(s.total_bawah / 1e9, 1)}–${num(s.total_atas / 1e9, 1)} miliar`} labels={["AI 1", "Kode"]} source="tarif Permenkes 3/2023" />
        <Tile value={num(s.menunggu_rme)} unit={s.klaim_desember ? `dari ${num(s.klaim_desember)} klaim` : "klaim"} caption="klaim Desember belum dibaca LLM lokal; lapis cepat sudah membaca semua" labels={["AI 2"]} source="dibaca LLM lokal di server" />
        <Tile value={num(s.audit_terpakai)} unit={`dari ${s.audit_kapasitas}`} caption="kapasitas audit Desember terpakai" labels={["AI 3"]} source="klaim berkeputusan Ajukan audit" progress={s.audit_terpakai / s.audit_kapasitas} />
      </div>

      <div className="flex items-center gap-2.5">
        <span className="text-[13px] text-tinta-2">Urutkan</span>
        <Segmented<Order> value={order} onChange={setOrder} options={[{ value: "rupiah", label: "Rupiah harapan" }, { value: "keyakinan", label: "Keyakinan" }]} />
        <span className="h-6 w-px bg-garis" />
        <FilterChip label="Modus" value={mode} onChange={setMode} options={[{ value: "semua", label: "Semua" }, ...(Object.keys(MODE_LABEL) as Mode[]).map((m) => ({ value: m, label: MODE_LABEL[m] }))]} />
        <FilterChip label="Kelas RS" value={kelas} onChange={setKelas} options={[{ value: "semua", label: "Semua" }, ...["A", "B", "C", "D"].map((k) => ({ value: k, label: k }))]} />
        <FilterChip label="Status" value={status} onChange={setStatus} options={[{ value: "semua", label: "Semua" }, ...(Object.keys(STATUS_LABEL) as HandlingStatus[]).map((k) => ({ value: k, label: STATUS_LABEL[k] }))]} />
        <span className="flex-1" />
        <span className="text-[13px] text-redam">
          {filtered ? `${rows.length} dari ${data.rs.length} RS ditandai` : `${data.rs.length} RS ditandai`}, urut menurut {order === "rupiah" ? "perkiraan rupiah" : "keyakinan"}
        </span>
      </div>

      <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
        <div className={`${COLS} h-9 border-b border-garis bg-kertas`} role="row">
          {["#", "Rumah sakit", "Penanda", "Modus", "Diakui vs wajar", "Perkiraan kelebihan", "Keyakinan", "Status", ""].map((h) => (
            <Th key={h} className="!p-0">{h}</Th>
          ))}
        </div>
        {data.rs.length === 0 ? (
          <EmptyState icon="list-checks" title="Tidak ada RS yang ditandai pada periode ini">
            Ini hasil yang sah, bukan galat: tidak ada RS yang selisih diakui dan wajarnya lolos uji setelah koreksi.
          </EmptyState>
        ) : rows.length === 0 ? (
          <EmptyState icon="search" title="Tidak ada RS yang cocok dengan filter">Ubah atau kosongkan filter Modus, Kelas RS, dan Status.</EmptyState>
        ) : (
          rows.map((r, i) => <Row key={r.kode_rs} r={r} n={i + 1} scale={scale} />)
        )}
        <div className="border-t border-garis bg-kertas">
          <button onClick={() => setShowThin((v) => !v)} className="flex w-full items-center gap-2 px-4 py-3 text-left text-[13px] text-tinta-2">
            <Icon name={showThin ? "chevron-down" : "chevron-right"} size={14} className="text-redam" />
            <span className="flex-1">
              {data.n_data_tidak_cukup} RS dengan data tidak cukup (kurang dari 30 klaim layak). TAPAL tidak memberi kesimpulan untuk RS ini.
            </span>
            <span className="font-semibold text-biru">{showThin ? "Sembunyikan" : "Tampilkan"}</span>
          </button>
          {showThin && (
            <p className="px-10 pb-3 text-[13px] text-redam">
              {data.data_tidak_cukup.length > 0
                ? data.data_tidak_cukup.map((d) => `${d.kode_rs} (${d.n_layak} klaim)`).join(", ")
                : "Data contoh desain hanya memuat jumlahnya."}
            </p>
          )}
        </div>
      </section>
    </Frame>
  )
}

function Frame({ children }: { children: React.ReactNode }) {
  return <div className="flex flex-col gap-3 px-8 py-6">{children}</div>
}

function Period({ k, v }: { k: string; v: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span className="text-redam">{k}</span>
      <span className="font-semibold text-tinta-2">{v}</span>
    </span>
  )
}

function perMachine(m: Record<string, number>) {
  return Object.entries(m).map(([k, v]) => `${v} oleh ${k}`).join(", ")
}

function Row({ r, n, scale }: { r: FlaggedHospital; n: number; scale: number }) {
  return (
    <div
      role="row"
      onClick={() => go("rs", r.kode_rs)}
      className={`${COLS} h-[43px] cursor-pointer border-b border-garis last:border-b-0 hover:bg-biru-muda/40`}
    >
      <span className="font-mono text-xs text-redam">{n}</span>
      <span className="flex flex-col gap-0.5 leading-tight">
        <a href={href("rs", r.kode_rs)} onClick={(e) => e.stopPropagation()} className="font-mono text-[13px] font-semibold text-tinta hover:underline">
          {r.kode_rs}
        </a>
        <span className="text-xs text-redam">{`${r.kelas}, ${r.kepemilikan}, Regional ${r.regional}`}</span>
      </span>
      <span><MachineLabel kind={r.mesin_penanda} /></span>
      <span><ModeChip mode={r.modus} /></span>
      {r.diakui !== null && r.wajar !== null ? (
        <span className="flex flex-col gap-[5px]">
          <span className="flex items-end gap-1.5 leading-none">
            <span className="text-[13px] font-semibold">{r.diakui}</span>
            <span className="text-xs text-redam">vs wajar {r.wajar}</span>
          </span>
          <ClaimedMini claimed={r.diakui} fair={r.wajar} fairLo={r.wajar_bawah!} fairHi={r.wajar_atas!} max={r.diakui} />
        </span>
      ) : (
        <span className="flex flex-col gap-0.5 leading-tight">
          <span className="text-[13px] font-semibold">tidak ditandai AI 1</span>
          <span className="text-xs text-redam">bukti di klaim lengkap</span>
        </span>
      )}
      {r.rupiah_bawah !== null && r.rupiah_atas !== null ? (
        <span className="flex flex-col gap-[5px]">
          <span className="flex items-end gap-1.5 leading-none">
            <span className="text-[13px] font-semibold">{miliar(r.rupiah)}</span>
            <span className="font-mono text-xs text-redam">{`${num(r.rupiah_bawah / 1e9, 2)}–${num(r.rupiah_atas / 1e9, 2)}`}</span>
          </span>
          <RangeMini lo={r.rupiah_bawah} mid={r.rupiah} hi={r.rupiah_atas} max={scale} />
        </span>
      ) : (
        <span className="flex flex-col gap-0.5 leading-tight">
          <span className="text-[13px] font-semibold">{miliar(r.rupiah)}</span>
          <span className="text-xs text-redam">nilai dipertaruhkan, {r.n_klaim_dipertaruhkan} klaim</span>
        </span>
      )}
      <Confidence level={r.keyakinan} detail={r.keterangan_keyakinan} />
      <span><StatusChip status={r.status_penanganan} /></span>
      <Icon name="chevron-right" size={16} className="justify-self-end text-redam" />
    </div>
  )
}

function exportRows(rows: FlaggedHospital[]) {
  downloadCsv(
    "antrean-kerja.csv",
    ["kode_rs", "kelas", "kepemilikan", "regional", "mesin_penanda", "modus", "diakui", "wajar", "wajar_bawah", "wajar_atas", "rupiah", "rupiah_bawah", "rupiah_atas", "keyakinan", "status_penanganan"],
    rows.map((r) => [r.kode_rs, r.kelas, r.kepemilikan, r.regional, r.mesin_penanda, r.modus, r.diakui, r.wajar, r.wajar_bawah, r.wajar_atas, r.rupiah, r.rupiah_bawah, r.rupiah_atas, r.keyakinan, r.status_penanganan]),
  )
}

function QueueSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Memuat antrean kerja">
      <Skeleton className="h-8 w-56" />
      <Skeleton className="h-4 w-[560px]" />
      <div className="flex gap-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-[148px] flex-1 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-9 w-[640px]" />
      <div className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
        {Array.from({ length: 9 }, (_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    </div>
  )
}
