import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { errorText } from "../utils/api"
import { EmptyState, ErrorState, FilterChip, Icon, PageHeader, Skeleton, Th } from "../components/ui"
import { DECISION_LABEL, type DecisionKind, type DecisionRow } from "../utils/decisions"
import { dateTime } from "../utils/format"
import type { IconName } from "../utils/icons"
import { href } from "../utils/router"

type Log = { baris: DecisionRow[]; total: number; rantai_utuh: boolean; rusak_di: number | null }

const ROLE: Record<string, string> = { verifikator: "Verifikator", kepala_cabang: "Kepala cabang", admin: "Admin" }
const KIND: Record<string, string> = { klaim: "Klaim", rs: "RS", laporan: "Laporan", garis: "Garis tarif" }
const TONE: Partial<Record<DecisionKind, { chip: string; icon: IconName }>> = {
  minta_klarifikasi: { chip: "bg-[#FDF4DC] border-[#F1D58E] text-[#6B4A00]", icon: "message-square" },
  setujui_laporan: { chip: "bg-[#FDF4DC] border-[#F1D58E] text-[#6B4A00]", icon: "message-square" },
  ajukan_audit: { chip: "bg-[#EEE8FB] border-[#D3C5F2] text-[#3B1675]", icon: "clipboard-check" },
  masukkan_rencana_audit: { chip: "bg-[#EEE8FB] border-[#D3C5F2] text-[#3B1675]", icon: "clipboard-check" },
  setujui_audit: { chip: "bg-[#EEE8FB] border-[#D3C5F2] text-[#3B1675]", icon: "clipboard-check" },
  aktifkan_garis: { chip: "bg-[#E6F0FC] border-[#BFD7F6] text-biru-tua", icon: "ruler" },
}

function basis(d: Record<string, unknown>) {
  const engines = Array.isArray(d.mesin) ? (d.mesin as string[]).join(" + ") : ""
  const source = d.sumber_bacaan === "llm_lokal" ? "LLM lokal" : d.sumber_bacaan === "aturan" ? "aturan cadangan" : ""
  return [engines, d.versi_model, source].filter(Boolean).join(", ") || "tidak ada"
}

export default function DecisionLog() {
  const [role, setRole] = useState("semua")
  const [kind, setKind] = useState("semua")
  const [decision, setDecision] = useState("semua")
  const params = new URLSearchParams({ ...(role !== "semua" && { peran: role }), ...(kind !== "semua" && { objek_jenis: kind }), ...(decision !== "semua" && { keputusan: decision }) })
  const qs = params.toString() ? `?${params}` : ""
  const log = useQuery<Log>({ queryKey: [`/keputusan${qs}`] })
  const byId = new Map((log.data?.baris ?? []).map((r) => [r.id, r]))

  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <PageHeader
        title="Jejak keputusan"
        actions={
          <a href={`/api/v1/keputusan.csv${qs}`} className="inline-flex items-center gap-2 rounded-md border border-garis bg-kartu px-3.5 py-[9px] text-sm font-semibold hover:bg-latar" download>
            <Icon name="download" size={16} className="text-tinta-2" />
            Ekspor CSV
          </a>
        }
      >
        <p className="text-[13px] text-tinta-2">Siapa memutus apa, berdasarkan apa. Setiap keputusan tercatat bersama dasar AI dan sidiknya.</p>
      </PageHeader>

      <div className="flex items-center gap-2.5">
        <FilterChip label="Periode" value="des" onChange={() => undefined} options={[{ value: "des", label: "Desember 2025" }]} />
        <FilterChip label="Peran" value={role} onChange={setRole} options={[{ value: "semua", label: "Semua" }, ...Object.entries(ROLE).map(([value, label]) => ({ value, label }))]} />
        <FilterChip label="Jenis objek" value={kind} onChange={setKind} options={[{ value: "semua", label: "Semua" }, ...Object.entries(KIND).map(([value, label]) => ({ value, label }))]} />
        <FilterChip label="Keputusan" value={decision} onChange={setDecision} options={[{ value: "semua", label: "Semua" }, ...Object.entries(DECISION_LABEL).map(([value, label]) => ({ value, label }))]} />
        <span className="flex-1" />
        {log.data && <span className="text-[13px] text-redam">{`${log.data.baris.length} baris, terbaru di atas`}</span>}
      </div>

      <div className="flex items-center gap-4 text-[13px]">
        <span className="flex items-center gap-2 font-semibold text-tinta-2">
          <Icon name="lock" size={14} className="text-tinta-2" />
          Catatan tidak bisa diubah; koreksi dicatat sebagai baris baru.
        </span>
        {log.data &&
          (log.data.rantai_utuh ? (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-hijau">
              <Icon name="shield-check" size={14} />
              {`Rantai sidik utuh, ${log.data.total} baris diperiksa ulang`}
            </span>
          ) : (
            <span className="flex items-center gap-1.5 text-xs font-semibold text-merah">
              <Icon name="shield-x" size={14} />
              {`Rantai sidik rusak mulai baris ${log.data.rusak_di}`}
            </span>
          ))}
      </div>

      <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
        {log.error ? (
          <ErrorState message={errorText(log.error)} onRetry={() => log.refetch()} />
        ) : log.isPending ? (
          <div className="flex flex-col gap-2 p-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
        ) : log.data.baris.length === 0 ? (
          <EmptyState icon="history" title={log.data.total === 0 ? "Belum ada keputusan tercatat" : "Tidak ada keputusan yang cocok dengan filter"}>
            {log.data.total === 0 ? (
              <>Keputusan dari <a className="font-semibold text-biru" href={href("antrean")}>Pemeriksaan klaim</a>, Profil RS, Pemindai garis, dan Laporan muncul di sini bersama sidiknya.</>
            ) : (
              "Ubah atau kosongkan filter."
            )}
          </EmptyState>
        ) : (
          <table className="w-full text-[13px]">
            <thead className="border-b border-garis bg-kertas">
              <tr>
                <Th className="pl-4">Waktu</Th>
                <Th>Peran</Th>
                <Th>Objek</Th>
                <Th>Keputusan</Th>
                <Th>Catatan</Th>
                <Th>Dasar AI</Th>
                <Th className="pr-4">Sidik</Th>
              </tr>
            </thead>
            <tbody>
              {log.data.baris.map((r) => {
                const t = TONE[r.keputusan] ?? { chip: "bg-kartu border-garis text-tinta-2", icon: r.keputusan === "koreksi" ? ("file-pen-line" as IconName) : ("check" as IconName) }
                const corrected = r.koreksi_untuk ? byId.get(r.koreksi_untuk) : undefined
                return (
                  <tr key={r.id} className="border-b border-garis align-top last:border-b-0">
                    <td className="py-3 pl-4 font-mono text-xs whitespace-nowrap">{dateTime(r.waktu)}</td>
                    <td className="py-3">
                      <span className="flex items-center gap-1.5 whitespace-nowrap">
                        <Icon name={r.peran === "verifikator" ? "user-round" : "user-round-check"} size={14} className="text-tinta-2" />
                        {ROLE[r.peran] ?? r.peran}
                      </span>
                    </td>
                    <td className="py-3">
                      <a href={r.objek_jenis === "klaim" ? href("klaim", r.objek_id) : r.objek_jenis === "rs" ? href("rs", r.objek_id) : r.objek_jenis === "laporan" ? href("laporan") : href("pemindai")}
                         className={`font-semibold hover:underline ${r.objek_jenis === "klaim" || r.objek_jenis === "rs" ? "font-mono" : ""}`}>
                        {r.objek_id}
                      </a>
                    </td>
                    <td className="py-3">
                      <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-xs font-semibold whitespace-nowrap ${t.chip}`}>
                        <Icon name={t.icon} size={13} />
                        {DECISION_LABEL[r.keputusan] ?? r.keputusan}
                      </span>
                    </td>
                    <td className="max-w-[260px] py-3">
                      {r.catatan ? `“${r.catatan}”` : <span className="text-redam">tanpa catatan</span>}
                      {r.koreksi_untuk && (
                        <span className="mt-1 flex w-fit items-center gap-1 rounded-full bg-abu-kartu px-2 py-0.5 text-xs text-tinta-2">
                          <Icon name="corner-down-right" size={12} />
                          {`koreksi atas ${corrected ? corrected.sidik.slice(0, 4) + "…" : `baris ${r.koreksi_untuk}`}`}
                        </span>
                      )}
                    </td>
                    <td className="py-3 text-xs text-tinta-2">{basis(r.dasar_ai)}</td>
                    <td className="py-3 pr-4 font-mono text-xs text-tinta-2" title={r.sidik}>{`${r.sidik.slice(0, 4)}…`}</td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </section>
    </div>
  )
}
