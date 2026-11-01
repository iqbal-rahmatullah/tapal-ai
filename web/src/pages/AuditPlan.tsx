import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { errorText } from "../utils/api"
import { Legend } from "../components/charts"
import { Button, ErrorState, HonestNote, Icon, MachineLabels, PageHeader, SampleDataBadge, Segmented, Skeleton, Th } from "../components/ui"
import { downloadCsv } from "../utils/csv"
import { juta, num, rupiah } from "../utils/format"
import type { DataSource } from "../types"

type Row = { nomor_sep: string; kode_rs: string; alasan: "nilai" | "eksplorasi"; pi: number; dipertaruhkan: number; temuan: number }
type Plan = {
  sumber_data: string
  bulan: string
  pengaturan: { anggaran: number; asal_anggaran: string; kebijakan: string; batas_pi: string; catatan_urutan: string }
  daftar: Row[]
  takaran: { total: number; rentang_resmi: [number, number]; rentang_varians_desain: [number, number]; cakupan_varians_desain: number; ht: number; nilai_sebenarnya: number; rupiah_ditemukan: number; porsi_ditemukan: number; ket_ditemukan?: string; skala: number; kaki: string }
  kurva: { bulan: string[]; agen: number[]; statis: number[]; kaki: string; ulangan?: number }
  perbandingan: { kebijakan: string; rupiah_per_100: number; audit_rs_jujur_per_100: number; takaran: string }[]
  kaki_perbandingan: string
  catatan_permintaan: string | null
}

const M = (x: number) => num(x / 1e9, 1)

export default function AuditPlan() {
  const [budget, setBudget] = useState(60)
  const [policy, setPolicy] = useState<"agen" | "statis" | "acak">("agen")
  const [order, setOrder] = useState<"rupiah" | "peluang">("rupiah")
  const [request, setRequest] = useState("?anggaran=60&kebijakan=agen&urutan=rupiah")
  const [all, setAll] = useState(false)
  const q = useQuery<Plan>({ queryKey: [`/audit/rencana${request}`] })

  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <PageHeader
        title={<span className="flex items-center gap-3">Rencana audit <SampleDataBadge data={q.data as DataSource | undefined} /></span>}
        actions={q.data && <span className="flex items-center gap-1.5 rounded-full border border-garis bg-kartu px-2.5 py-1 text-xs font-semibold"><Icon name="calendar" size={13} className="text-tinta-2" />{q.data.bulan}</span>}
      >
        <p className="text-[13px] text-tinta-2">Agen audit memilih klaim tiap bulan dan belajar dari hasil audit. Peluang terpilih (π) dicatat supaya takaran kebocoran tidak bias.</p>
      </PageHeader>

      <section className="grid grid-cols-[260px_1fr_auto_auto] items-center gap-6 rounded-lg border border-garis bg-kartu px-5 py-4">
        <div className="flex flex-col gap-1">
          <span className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">Anggaran audit</span>
          <span className="flex items-center gap-3">
            <span className="font-display text-xl font-bold whitespace-nowrap">{budget} klaim</span>
            <input type="range" min={20} max={200} step={10} value={budget} onChange={(e) => setBudget(Number(e.target.value))} className="w-24 accent-biru" aria-label="Anggaran audit" />
          </span>
          <span className="text-xs text-tinta-2">{q.data?.pengaturan.asal_anggaran ?? ""}</span>
        </div>
        <div className="flex flex-col gap-1.5 border-l border-garis pl-6">
          <span className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">Kebijakan</span>
          <span className="flex gap-4" role="radiogroup">
            {([["agen", "Agen belajar"], ["statis", "Skor statis"], ["acak", "Acak saja"]] as const).map(([v, l]) => (
              <label key={v} className="flex cursor-pointer items-center gap-1.5 text-[13px] font-semibold">
                <input type="radio" name="kebijakan" checked={policy === v} onChange={() => setPolicy(v)} className="size-4 accent-biru" />
                {l}
              </label>
            ))}
          </span>
          <span className="text-xs text-tinta-2">{q.data?.pengaturan.batas_pi}</span>
        </div>
        <div className="flex flex-col gap-1.5 border-l border-garis pl-6">
          <span className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">Dasar urutan</span>
          <Segmented value={order} onChange={setOrder} options={[{ value: "rupiah", label: "Rupiah harapan" }, { value: "peluang", label: "Peluang" }]} />
          <span className="max-w-[220px] text-xs text-tinta-2">{q.data?.pengaturan.catatan_urutan}</span>
        </div>
        <Button variant="primer" icon="list-checks" onClick={() => setRequest(`?anggaran=${budget}&kebijakan=${policy}&urutan=${order}`)}>Buat rencana</Button>
      </section>

      {q.error && <ErrorState message={errorText(q.error)} onRetry={() => q.refetch()} />}
      {q.isPending && <div className="grid grid-cols-[minmax(0,1fr)_340px] gap-4"><Skeleton className="h-[420px] rounded-lg" /><Skeleton className="h-[420px] rounded-lg" /></div>}
      {q.data && (
        <>
          {q.data.catatan_permintaan && <HonestNote label="Catatan">{q.data.catatan_permintaan}</HonestNote>}
          <div className="grid grid-cols-[minmax(0,1fr)_340px] items-start gap-4">
            <AuditList rows={q.data.daftar} all={all} onToggle={() => setAll((v) => !v)} />
            <Estimate t={q.data.takaran} />
          </div>
          <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-4">
            <Curve k={q.data.kurva} />
            <Comparison rows={q.data.perbandingan} note={q.data.kaki_perbandingan} budget={q.data.pengaturan.anggaran} />
          </div>
        </>
      )}
    </div>
  )
}

function AuditList({ rows, all, onToggle }: { rows: Row[]; all: boolean; onToggle: () => void }) {
  const explore = rows.filter((r) => r.alasan === "eksplorasi")
  const shown = all ? rows : [...rows.slice(0, 6), ...explore.slice(-2)]
  const hiddenRows = rows.filter((r) => !shown.includes(r))
  const hiddenExplore = hiddenRows.filter((r) => r.alasan === "eksplorasi").length
  return (
    <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
      <header className="flex items-center gap-2 px-4 pt-3.5">
        <h2 className="flex-1 text-[15px] font-semibold">{`Daftar audit Desember, ${rows.length} klaim`}</h2>
        <MachineLabels kinds={["AI 1", "AI 2", "AI 3"]} />
        <Button icon="download" onClick={() => downloadCsv("rencana-audit.csv", ["nomor_sep", "kode_rs", "alasan", "pi", "dipertaruhkan", "temuan_simulasi"], rows.map((r) => [r.nomor_sep, r.kode_rs, r.alasan, r.pi, r.dipertaruhkan, r.temuan]))}>
          Ekspor daftar (CSV)
        </Button>
      </header>
      <p className="px-4 pt-1.5 pb-3 text-xs text-tinta-2">Urut menurut π; diundi = terpilih lewat undian berbobot. Nilai dipertaruhkan menurut garis yang dikenal; eksplorasi mencari jalur yang belum dikenal.</p>
      <table className="w-full text-[13px]">
        <thead className="border-y border-garis bg-kertas">
          <tr>
            <Th className="pl-4">#</Th>
            <Th>Nomor SEP</Th>
            <Th>RS</Th>
            <Th>Alasan terpilih</Th>
            <Th className="text-right">π</Th>
            <Th className="text-right">Dipertaruhkan</Th>
            <Th className="pr-4 pl-4">Temuan (simulasi)</Th>
          </tr>
        </thead>
        <tbody>
          {shown.map((r, i) => (
            <tr key={r.nomor_sep} className={`border-b border-garis ${i === 6 && !all ? "border-t-2" : ""}`}>
              <td className="py-2 pl-4 font-mono text-xs text-redam">{rows.indexOf(r) + 1}</td>
              <td className="font-mono">{r.nomor_sep}</td>
              <td className="font-mono font-semibold">{r.kode_rs}</td>
              <td>
                {r.alasan === "nilai" ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-biru-muda px-2 py-0.5 text-xs font-semibold text-biru-tua"><Icon name="trending-up" size={12} />Nilai harapan</span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full border border-garis px-2 py-0.5 text-xs font-semibold"><Icon name="shuffle" size={12} />Eksplorasi</span>
                )}
              </td>
              <td className="text-right font-mono">
                {num(r.pi, r.pi < 0.01 ? 3 : 2)}
                {r.pi < 1 && <span className="ml-1 font-sans text-xs text-redam">diundi</span>}
              </td>
              <td className="text-right font-semibold">{rupiah(r.dipertaruhkan)}</td>
              <td className="pr-4 pl-4">
                <span className="flex items-center gap-1.5 text-xs font-semibold">
                  <Icon name={r.temuan ? "circle-alert" : "minus"} size={13} className={r.temuan ? "text-tinta" : "text-redam"} />
                  {r.temuan ? "Pelanggaran ditemukan" : "Tidak ada pelanggaran"}
                </span>
              </td>
            </tr>
          ))}
          {!all && hiddenRows.length > 0 && (
            <tr className="bg-kertas">
              <td colSpan={7} className="py-2 text-center text-xs text-tinta-2">
                <button onClick={onToggle} className="font-semibold text-biru">{`${hiddenRows.length - hiddenExplore} klaim nilai harapan tinggi lain dan ${hiddenExplore} eksplorasi lain: tampilkan semua`}</button>
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </section>
  )
}

function Estimate({ t }: { t: Plan["takaran"] }) {
  const x = (v: number) => `${(v / t.skala) * 100}%`
  const inside = t.nilai_sebenarnya >= t.rentang_resmi[0] && t.nilai_sebenarnya <= t.rentang_resmi[1]
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">Takaran kebocoran</h2>
        <MachineLabels kinds={["AI 3"]} />
      </header>
      <span className="flex w-fit items-center gap-1.5 rounded-full bg-abu-kartu px-2.5 py-1 text-xs font-semibold text-tinta-2"><Icon name="flask-conical" size={13} />Mode simulasi, kunci jawaban dunia uji</span>
      <p className="text-xs text-tinta-2">Perkiraan kelebihan bayar di wilayah, Jan–Des 2025 (skala dalam miliar rupiah)</p>
      <p className="font-display text-[32px] leading-tight font-bold">{`Rp${M(t.total)} miliar`}</p>
      <p className="text-[13px] font-semibold">{`Rentang 95%: Rp${M(t.rentang_resmi[0])}–${M(t.rentang_resmi[1])} miliar`}</p>
      <div className="relative mt-2 h-5">
        <span className="absolute top-2 right-0 left-0 h-px bg-garis" />
        <span className="absolute top-[7px] h-[3px] rounded-full bg-biru" style={{ left: x(t.rentang_resmi[0]), width: `calc(${x(t.rentang_resmi[1])} - ${x(t.rentang_resmi[0])})` }} />
        <span className="absolute top-0.5 h-3.5 w-0.5 bg-jingga" style={{ left: x(t.nilai_sebenarnya) }} title="nilai sebenarnya" />
        <span className="absolute top-1 size-2.5 -translate-x-1/2 rounded-full bg-biru ring-2 ring-white" style={{ left: x(t.total) }} />
      </div>
      <div className="relative h-4 font-mono text-xs text-redam">
        <span className="absolute left-0">0</span>
        <span className="absolute -translate-x-1/2" style={{ left: x(t.rentang_resmi[0]) }}>{M(t.rentang_resmi[0])}</span>
        <span className="absolute -translate-x-1/2" style={{ left: x(t.rentang_resmi[1]) }}>{M(t.rentang_resmi[1])}</span>
        <span className="absolute right-0">{num(t.skala / 1e9, 0)}</span>
      </div>
      <p className="flex items-center gap-2 border-l-2 border-jingga pl-2 text-xs text-tinta-2">
        {`nilai sebenarnya: Rp${M(t.nilai_sebenarnya)} miliar, ${inside ? "di dalam rentang" : "di luar rentang"}`}
        <Icon name={inside ? "check" : "x"} size={13} className={inside ? "text-hijau" : "text-merah"} />
      </p>
      <div className="mt-1 flex flex-col gap-1 border-t border-garis pt-2">
        <span className="text-xs text-tinta-2">Rentang varians desain (pembanding)</span>
        <span className="font-display text-lg font-bold">{`Rp${M(t.rentang_varians_desain[0])}–${M(t.rentang_varians_desain[1])} miliar `}<span className="font-sans text-xs font-normal text-tinta-2">{`kena ${num(t.cakupan_varians_desain * 100)}% kali`}</span></span>
        <span className="text-xs text-tinta-2">{t.ket_ditemukan ? `Rupiah ditemukan setahun, ${t.ket_ditemukan}` : "Rupiah ditemukan tahun ini"}</span>
        <span className="font-display text-lg font-bold">{`Rp${M(t.rupiah_ditemukan)} miliar `}<span className="font-sans text-xs font-normal text-tinta-2">{`${num(t.porsi_ditemukan * 100)}% dari kebocoran sebenarnya`}</span></span>
      </div>
      <p className="text-xs text-tinta-2">{t.kaki}</p>
    </section>
  )
}

function Curve({ k }: { k: Plan["kurva"] }) {
  const top = Math.max(...k.agen, ...k.statis)
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center gap-3">
        <h2 className="flex-1 text-[15px] font-semibold">Kurva belajar</h2>
        <Legend items={[{ label: "Agen belajar", color: "#2A78D6" }, { label: "Skor statis", color: "#898781" }]} />
        <MachineLabels kinds={["AI 3"]} />
      </header>
      <p className="text-xs text-tinta-2">{`Rupiah ditemukan per bulan (juta), rata-rata ${k.ulangan ?? 500} simulasi dengan RS beradaptasi`}</p>
      <div className="flex h-24 items-end gap-2 border-b border-garis">
        {k.bulan.map((b, i) => (
          <div key={b} className="flex flex-1 items-end justify-center gap-0.5" title={`${b}: agen ${juta(k.agen[i] * 1e6)}, statis ${juta(k.statis[i] * 1e6)}`}>
            <span className="w-3 rounded-t-[2px] bg-biru" style={{ height: `${(k.agen[i] / top) * 88}px` }} />
            <span className="w-3 rounded-t-[2px] bg-redam" style={{ height: `${(k.statis[i] / top) * 88}px` }} />
          </div>
        ))}
      </div>
      <div className="flex gap-2">{k.bulan.map((b) => <span key={b} className="flex-1 text-center text-xs text-redam">{b}</span>)}</div>
      <p className="text-xs text-tinta-2">{k.kaki}</p>
    </section>
  )
}

function Comparison({ rows, note, budget }: { rows: Plan["perbandingan"]; note: string; budget: number }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">{`Perbandingan kebijakan, ${budget} audit per bulan`}</h2>
        <MachineLabels kinds={["AI 3"]} />
      </header>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-garis">
            <Th className="pl-0">Kebijakan</Th>
            <Th className="text-right">Rupiah per 100 audit</Th>
            <Th className="text-right">Audit di RS jujur per 100</Th>
            <Th className="pr-0 text-right">Takaran</Th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={r.kebijakan} className={`border-b border-garis last:border-b-0 ${i === 0 ? "bg-biru-muda/40 font-semibold" : ""}`}>
              <td className="py-2">{r.kebijakan}</td>
              <td className="text-right">{juta(r.rupiah_per_100)}</td>
              <td className="text-right">{r.audit_rs_jujur_per_100}</td>
              <td className="text-right">{r.takaran}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-tinta-2">{note}</p>
    </section>
  )
}
