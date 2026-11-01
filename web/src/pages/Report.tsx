import { useMutation, useQuery } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { errorText, http, postJson } from "../utils/api"
import { Modal } from "../components/dialogs"
import { ReportPage } from "../components/ReportPage"
import { Button, ErrorState, Icon, MachineLabel, PageHeader, SampleDataBadge, Skeleton } from "../components/ui"
import { useDecision } from "../utils/decisions"
import { track } from "../utils/progress"
import { showToast } from "../utils/toast"
import type { ReportData, Story } from "../types"

type Letter = Story & { kode_rs: string; kepada: string; perihal: string; tanggal: string; penutup: string; lampiran: string }

function insertedSummary(): { kode: string; story: Story } | null {
  try {
    const raw = sessionStorage.getItem("tapal-narasi")
    if (!raw) return null
    const v = JSON.parse(raw) as { kode: string; segmen: Story["segmen"]; sumber: Story["sumber"] }
    return { kode: v.kode, story: { sumber: v.sumber, segmen: v.segmen, durasi_ms: 0, catatan: [] } }
  } catch {
    return null
  }
}

export default function Report() {
  const report = useQuery<ReportData>({ queryKey: ["/laporan"] })
  const story = useMutation({ mutationFn: () => postJson<Story>("/laporan/narasi", {}) })
  const [letter, setLetter] = useState(false)
  const [sending, setSending] = useState(false)
  const [extra] = useState(insertedSummary)
  const { mutate: compose } = story

  useEffect(() => {
    compose()
  }, [compose])

  const pdf = useMutation({
    mutationFn: async () => {
      const r = await track(http.get<Blob>("/laporan.pdf", { responseType: "blob", timeout: 90_000 }))
      const url = URL.createObjectURL(r.data)
      Object.assign(document.createElement("a"), { href: url, download: "tapal-laporan-desember-2025.pdf" }).click()
      URL.revokeObjectURL(url)
    },
  })

  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <PageHeader title={<span className="flex items-center gap-3">Laporan kepala cabang <SampleDataBadge data={report.data} /></span>}>
        <p className="text-[13px] text-tinta-2">Satu halaman untuk atasan. Angka dihitung kode; narasi disusun LLM lokal dan bisa disusun ulang.</p>
      </PageHeader>
      <div className="flex items-center gap-2.5">
        <span className="flex items-center gap-2 rounded-md border border-garis bg-kartu px-2.5 py-[7px] text-[13px]">
          <Icon name="calendar" size={15} className="text-tinta-2" />
          <span className="text-redam">Periode</span>
          <span className="font-semibold">{report.data?.periode ?? "Desember 2025"}</span>
        </span>
        <Button icon="refresh-cw" disabled={story.isPending} onClick={() => story.mutate()}>{story.isPending ? "Menyusun narasi…" : "Susun ulang narasi"}</Button>
        <span className="flex-1" />
        {pdf.error && <span className="text-xs text-merah">{errorText(pdf.error)}</span>}
        <Button icon="file-down" disabled={pdf.isPending || !report.data} onClick={() => pdf.mutate()}>{pdf.isPending ? "Mencetak PDF…" : "Unduh PDF"}</Button>
        <Button icon="mail" disabled={!report.data?.surat_rs && report.data?.sumber_data !== "contoh_desain"} onClick={() => setLetter(true)}>Draf surat klarifikasi</Button>
        <Button variant="primer" icon="send" onClick={() => setSending(true)}>Kirim ke kepala cabang</Button>
      </div>
      {report.error && <ErrorState message={errorText(report.error)} onRetry={() => report.refetch()} />}
      {report.isPending && <Skeleton className="mx-auto h-[1123px] w-[794px]" />}
      {report.data && (
        <div className="flex justify-center rounded-lg bg-[#E4E9F1] py-6">
          <ReportPage d={report.data} story={story.data ?? null} extra={extra} />
        </div>
      )}
      {letter && report.data && <LetterModal rs={report.data.surat_rs ?? "RS-092"} onClose={() => setLetter(false)} />}
      {sending && report.data && <SendModal report={report.data} onClose={() => setSending(false)} />}
    </div>
  )
}

function LetterModal({ rs, onClose }: { rs: string; onClose: () => void }) {
  const q = useQuery<Letter>({ queryKey: [`/laporan/surat/${rs}`], queryFn: ({ signal }) => postJson<Letter>(`/laporan/surat/${rs}`, {}, signal), staleTime: 0, gcTime: 0 })
  const [editing, setEditing] = useState(false)
  const decision = useDecision(onClose)
  const l = q.data
  const body = l?.segmen.map((s) => s.teks).join("") ?? ""
  return (
    <Modal title={<span className="flex items-center gap-2">{`Draf surat klarifikasi, ${rs}`} {l && (l.sumber === "llm_lokal" ? <MachineLabel kind="LLM narasi" /> : <span className="rounded-full border border-garis px-2 py-0.5 font-sans text-xs font-semibold text-tinta-2">Templat</span>)}</span>} onClose={onClose} width={780}>
      <p className="text-xs text-tinta-2">{l?.sumber === "llm_lokal" ? `Disusun LLM lokal dari Profil ${rs}. Angka dalam kotak biru disisipkan kode.` : "Kalimat templat karena LLM lokal tidak aktif atau keluarannya ditolak; angka disisipkan kode."}</p>
      {q.isPending && <div className="flex flex-col gap-2">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-4 w-full" />)}</div>}
      {q.error && <ErrorState message={errorText(q.error)} onRetry={() => q.refetch()} />}
      {l && (
        <article contentEditable={editing} suppressContentEditableWarning className={`flex flex-col gap-3 rounded-lg border bg-kertas p-6 text-[13px] leading-6 ${editing ? "border-biru outline-hidden" : "border-garis"}`}>
          <header className="border-b border-tinta pb-2">
            <p className="font-display text-base font-bold">KANTOR CABANG CONTOH</p>
            <p className="text-xs text-tinta-2">Wilayah Uji, kop netral untuk contoh</p>
          </header>
          <div className="flex justify-between text-xs"><span>Nomor: ……………</span><span>{l.tanggal}</span></div>
          <p className="text-xs">Perihal: <b>{l.perihal}</b></p>
          <p>{`Kepada Yth. ${l.kepada}`}<br />di tempat</p>
          <p>
            {l.segmen.map((s, i) => s.token ? <span key={i} className="mx-px rounded-[4px] bg-biru-muda px-1 font-mono text-[12px] font-semibold text-biru-tua">{s.teks}</span> : <span key={i}>{s.teks}</span>)}
          </p>
          <p>{l.penutup}</p>
          <p>Hormat kami,<br /><br />Kepala Kantor Cabang Contoh</p>
          <p className="text-xs text-tinta-2">{l.lampiran}</p>
        </article>
      )}
      <p className="text-xs text-redam">Draf disusun di laptop ini; periksa sebelum dikirim. TAPAL tidak mengirim surat.</p>
      {decision.error && <p className="text-xs text-merah">{errorText(decision.error)}</p>}
      <footer className="flex justify-end gap-2">
        <Button icon="pencil" onClick={() => setEditing((v) => !v)}>{editing ? "Selesai mengedit" : "Edit"}</Button>
        <Button icon="copy" onClick={() => { navigator.clipboard.writeText(body); showToast("Draf surat disalin") }}>Salin</Button>
        <Button variant="primer" icon="history" disabled={!l || decision.isPending}
                onClick={() => decision.mutate({ objek_jenis: "laporan", objek_id: `Draf surat ${rs}`, keputusan: "draf_surat", catatan: `Draf surat klarifikasi ${rs} disusun dan diperiksa`,
                                                 dasar_ai: { mesin: ["AI 1", "Statistik", l?.sumber === "llm_lokal" ? "LLM narasi" : "Templat"], versi_model: "tapal-1.0" } })}>
          Masukkan ke Jejak keputusan
        </Button>
      </footer>
    </Modal>
  )
}

function SendModal({ report, onClose }: { report: ReportData; onClose: () => void }) {
  const [note, setNote] = useState("")
  const decision = useDecision(onClose)
  return (
    <Modal title="Kirim ke kepala cabang?" onClose={onClose} width={520}>
      <p className="text-sm text-tinta-2">{`Laporan ${report.periode} (sidik dokumen ${report.sidik_dokumen}) dicatat sebagai terkirim ke kepala cabang. TAPAL tidak mengirim surel; pengiriman dilakukan lewat saluran kantor.`}</p>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold">
        Catatan (opsional)
        <textarea value={note} onChange={(e) => setNote(e.target.value)} rows={2} className="rounded-md border border-garis px-3 py-2 text-sm font-normal outline-hidden focus:border-biru" />
      </label>
      {decision.error && <p className="text-xs text-merah">{errorText(decision.error)}</p>}
      <footer className="flex justify-end gap-2">
        <Button onClick={onClose}>Batal</Button>
        <Button variant="primer" icon="send" disabled={decision.isPending}
                onClick={() => decision.mutate({ objek_jenis: "laporan", objek_id: `Laporan ${report.periode}`, keputusan: "kirim_laporan", catatan: note.trim(),
                                                 dasar_ai: { mesin: ["AI 1", "AI 2", "Statistik"], versi_model: "tapal-1.0" }, bukti: { sidik_dokumen: report.sidik_dokumen } })}>
          Catat sebagai terkirim
        </Button>
      </footer>
    </Modal>
  )
}
