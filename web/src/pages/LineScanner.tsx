import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { errorText } from "../utils/api"
import { NoteDialog } from "../components/dialogs"
import { Button, ErrorState, HonestNote, Icon, MachineLabel, MachineLabels, PageHeader, SampleDataBadge, Skeleton, Th, Tile } from "../components/ui"
import { useDecision } from "../utils/decisions"
import { num } from "../utils/format"
import type { DataSource, Machine } from "../types"

type Line = { id: string; nama: string; jenis: string; grup: string; kali: string; menyala: boolean; uji: string; rupiah: string | null; rentang: string | null; status: "aktif" | "temuan" | "ditolak"; fakta?: string[]; judul?: string; rincian?: boolean }
type Lines = {
  sumber_data: string
  subjudul: string
  cakupan: string
  ubin: { nilai: string; satuan: string; keterangan: string; label: Machine[]; asal: string }[]
  garis: Line[]
  kaki_tabel: string
  terpilih: string
  t24: { judul: string; jalur: [string, boolean][]; catatan: string }
  n_garis?: number
  rincian_jam: { fakta: string[]; titik: [number, number, number, number][]; keterangan: string; catatan: string }
  catatan_jujur: string
}

export default function LineScanner() {
  const q = useQuery<Lines>({ queryKey: ["/pemindai"] })
  const [selected, setSelected] = useState<string | null>(null)
  const [local, setLocal] = useState<Record<string, Line["status"]>>({})
  const [asking, setAsking] = useState<"aktifkan_garis" | "tolak_garis" | null>(null)
  const decision = useDecision((row) => {
    setLocal((m) => ({ ...m, [row.objek_id]: row.keputusan === "aktifkan_garis" ? "aktif" : "ditolak" }))
    setAsking(null)
  })

  if (q.error) return <div className="px-8 py-6"><ErrorState message={errorText(q.error)} onRetry={() => q.refetch()} /></div>
  if (q.isPending) return <div className="flex flex-col gap-3 px-8 py-6"><Skeleton className="h-8 w-60" /><Skeleton className="h-[148px] rounded-lg" /><Skeleton className="h-[520px] rounded-lg" /></div>
  const d = q.data
  const pick = selected ?? d.terpilih
  const line = d.garis.find((g) => g.id === pick)!
  const status = (g: Line) => local[g.id] ?? g.status

  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <PageHeader title={<span className="flex items-center gap-3">Pemindai garis <SampleDataBadge data={d as DataSource} /></span>}
                  actions={<span className="rounded-full border border-garis bg-kartu px-2.5 py-1 text-xs font-semibold text-tinta-2">{d.cakupan}</span>}>
        <p className="text-[13px] text-tinta-2">{d.subjudul}</p>
      </PageHeader>
      <div className="flex gap-4">
        {d.ubin.map((t) => <Tile key={t.keterangan} value={t.nilai} unit={t.satuan} caption={t.keterangan} labels={t.label} source={t.asal} />)}
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_400px] items-start gap-4">
        <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
          <header className="flex items-center gap-2 px-4 pt-3.5">
            <h2 className="flex-1 text-[15px] font-semibold">Garis temuan AI 4, diurutkan menurut rupiah</h2>
            <MachineLabel kind="AI 4" />
          </header>
          <p className="px-4 pt-1 pb-3 text-xs text-tinta-2">Kelipatan = median kenaikan tarif saat kode atau ambang dipenuhi (tabel Permenkes 3/2023). Rupiah = perkiraan kelebihan bayar di RS yang ditandai, dengan rentang 95%.</p>
          <table className="w-full text-[13px]">
            <thead className="border-y border-garis bg-kertas">
              <tr>
                <Th className="pl-4">Garis</Th>
                <Th>Grup asal → tujuan</Th>
                <Th>Kelipatan</Th>
                <Th>Uji</Th>
                <Th>Rupiah</Th>
                <Th className="pr-4">Status</Th>
              </tr>
            </thead>
            <tbody>
              {d.garis.map((g) => (
                <tr key={g.id} onClick={() => g.fakta || g.rincian ? setSelected(g.id) : undefined}
                    className={`border-b border-garis last:border-b-0 ${g.fakta || g.rincian ? "cursor-pointer hover:bg-biru-muda/30" : ""} ${g.id === pick ? "bg-biru-muda/40" : ""}`}>
                  <td className="py-2.5 pl-4">
                    <span className="block font-semibold">{g.nama}</span>
                    <span className="text-xs text-redam">{g.jenis}</span>
                  </td>
                  <td className="font-mono text-xs">{g.grup}</td>
                  <td className="font-semibold">{g.kali}</td>
                  <td>
                    <span className={`flex items-center gap-1.5 text-xs font-semibold ${g.menyala ? "text-tinta" : "text-redam"}`}>
                      <Icon name={g.menyala ? "zap" : "minus"} size={13} className={g.menyala ? "text-jingga" : "text-redam"} />
                      {g.menyala ? "Menyala" : "Tidak menyala"}
                    </span>
                    <span className="text-xs text-tinta-2">{g.uji}</span>
                  </td>
                  <td>
                    {g.rupiah ? (
                      <>
                        <span className="block font-semibold">{g.rupiah}</span>
                        <span className="text-xs whitespace-nowrap text-tinta-2">{g.rentang}</span>
                      </>
                    ) : (
                      <span className="text-xs text-redam">tidak ada</span>
                    )}
                  </td>
                  <td className="pr-4"><LineStatus s={status(g)} /></td>
                </tr>
              ))}
            </tbody>
          </table>
          <footer className="flex items-center justify-between border-t border-garis bg-kertas px-4 py-2.5 text-xs text-tinta-2">
            {d.kaki_tabel}
            <span className="font-semibold text-redam" title="Daftar lengkap belum ditampilkan di layar ini">{`${d.n_garis ?? d.garis.length} garis`}</span>
          </footer>
        </section>

        <div className="flex flex-col gap-3">
          {line.rincian ? (
            <HoursDetail r={d.rincian_jam} onClose={() => setSelected(d.terpilih)} />
          ) : (
            <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
              <header className="flex items-center justify-between">
                <h2 className="text-[15px] font-semibold">Setujui garis temuan</h2>
                <MachineLabel kind="Admin" />
              </header>
              <div className="flex items-center gap-2">
                <span className="font-semibold">{line.judul ?? line.nama}</span>
                <LineStatus s={status(line)} />
              </div>
              <ul className="flex flex-col gap-2">
                {(line.fakta ?? []).map((f) => (
                  <li key={f} className="flex gap-2 text-[13px] text-tinta-2">
                    <Icon name="info" size={14} className="mt-0.5 text-tinta-2" />
                    {f}
                  </li>
                ))}
              </ul>
              {status(line) === "temuan" ? (
                <div className="flex gap-2">
                  <Button variant="primer" icon="check" onClick={() => setAsking("aktifkan_garis")}>Setujui jadi garis aktif</Button>
                  <Button icon="x" onClick={() => setAsking("tolak_garis")}>Tolak</Button>
                </div>
              ) : (
                <p className="text-[13px] font-semibold">{status(line) === "aktif" ? "Garis ini aktif dan ikut uji per RS bulanan." : "Garis ini ditolak; alasannya ada di Jejak keputusan."}</p>
              )}
              <p className="text-xs text-redam">Keputusan dan alasannya tercatat di Jejak keputusan.</p>
            </section>
          )}
          <section className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
            <header className="flex items-center justify-between">
              <h2 className="text-[15px] font-semibold">Data Sampel Reguler, agregat</h2>
              <MachineLabel kind="AI 4" />
            </header>
            <p className="text-[13px] text-tinta-2">{d.t24.judul}</p>
            {d.t24.jalur.map(([j, found]) => (
              <div key={j} className="flex items-center justify-between border-b border-garis py-1.5 text-[13px] last:border-b-0">
                <span className="font-mono">{j}</span>
                <span className={`flex items-center gap-1 text-xs font-semibold ${found ? "text-hijau" : "text-tinta-2"}`}><Icon name={found ? "check" : "x"} size={13} />{found ? "ditemukan" : "tidak ditemukan"}</span>
              </div>
            ))}
            <p className="text-xs text-redam">{d.t24.catatan}</p>
          </section>
        </div>
      </div>
      <HonestNote>{d.catatan_jujur}</HonestNote>

      {asking && (
        <NoteDialog
          title={asking === "aktifkan_garis" ? "Setujui jadi garis aktif" : "Tolak garis temuan"}
          subject={line.judul ?? line.nama}
          confirm={asking === "aktifkan_garis" ? "Setujui garis" : "Tolak garis"}
          pending={decision.isPending}
          error={decision.error}
          onClose={() => setAsking(null)}
          onSubmit={(catatan) => decision.mutate({ peran: "admin", objek_jenis: "garis", objek_id: line.id, keputusan: asking, catatan, dasar_ai: { mesin: ["AI 4", "Statistik"], versi_model: "tapal-1.0" } })}
        />
      )}
    </div>
  )
}

function LineStatus({ s }: { s: Line["status"] }) {
  const look = { aktif: "bg-[#E6F0FC] border-[#BFD7F6] text-biru-tua", temuan: "bg-kartu border-garis text-tinta-2", ditolak: "bg-[#F1F2F4] border-[#DADDE2] text-[#4B5563]" }[s]
  return <span className={`inline-flex rounded-full border px-2.5 py-0.5 text-xs font-semibold ${look}`}>{{ aktif: "Aktif", temuan: "Temuan", ditolak: "Ditolak" }[s]}</span>
}

function HoursDetail({ r, onClose }: { r: Lines["rincian_jam"]; onClose: () => void }) {
  const W = 340, H = 160, top = 0.45
  const y = (v: number) => H / 2 - (v / top) * (H / 2 - 8)
  const x = (i: number) => 40 + i * 44
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">Rincian, Jam ventilasi ≥96</h2>
        <MachineLabels kinds={["Statistik"]} />
      </header>
      <ul className="flex flex-col gap-1.5">
        {r.fakta.map((f) => (
          <li key={f} className="flex gap-2 text-[13px] text-tinta-2"><Icon name="info" size={14} className="mt-0.5" />{f}</li>
        ))}
      </ul>
      <svg viewBox={`0 0 ${W} ${H + 24}`} className="w-full" role="img" aria-label="S(L) dengan rentang 95% di tujuh garis jam">
        {[0.4, 0, -0.4].map((t) => (
          <text key={t} x={30} y={y(t) + 4} textAnchor="end" fontSize={11} fill="#898781" fontFamily="JetBrains Mono, monospace">{t === 0 ? "0,0" : `${t > 0 ? "+" : "−"}${num(Math.abs(t), 1)}`}</text>
        ))}
        <line x1={36} x2={W} y1={y(0)} y2={y(0)} stroke="#C3C2B7" strokeDasharray="6 4" />
        {r.titik.map(([hour, s, lo, hi], i) => {
          const hot = hour === 96
          return (
            <g key={hour}>
              <line x1={x(i)} x2={x(i)} y1={y(hi)} y2={y(lo)} stroke={hot ? "#2A78D6" : "#898781"} strokeWidth={2} />
              <circle cx={x(i)} cy={y(s)} r={hot ? 5.5 : 4.5} fill={hot ? "#2A78D6" : "#898781"} stroke="#fff" strokeWidth={1.5}>
                <title>{`${hour} jam: S ${num(s, 2)} (${num(lo, 2)} sampai ${num(hi, 2)})`}</title>
              </circle>
              {hot && <text x={x(i) + 8} y={y(s) + 4} fontSize={12} fontWeight={600} fill="#0B0B0B">{`${s >= 0 ? "+" : "−"}${num(Math.abs(s), 2)}`}</text>}
              <text x={x(i)} y={H + 6} textAnchor="middle" fontSize={11} fill="#0B0B0B" fontFamily="JetBrains Mono, monospace">{hour}</text>
              {(hot || hour === 120 || hour === 144) && <text x={x(i)} y={H + 20} textAnchor="middle" fontSize={11} fill={hot ? "#2A78D6" : "#898781"}>{hot ? "bertarif" : "plasebo"}</text>}
            </g>
          )
        })}
      </svg>
      <p className="text-xs text-tinta-2">{r.keterangan}</p>
      <HonestNote label="Catatan">{r.catatan}</HonestNote>
      <Button icon="x" onClick={onClose} className="w-fit">Tutup rincian</Button>
    </section>
  )
}
