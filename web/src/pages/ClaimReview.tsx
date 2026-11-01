import { useQuery, useQueryClient } from "@tanstack/react-query"
import { useState } from "react"
import { errorText, statusOf } from "../utils/api"
import { Button, Card, Crumbs, EmptyState, ErrorState, Icon, MachineLabel, MachineLabels, OdblNote, SampleDataBadge, Skeleton } from "../components/ui"
import { DECISION_LABEL, useDecision, type DecisionKind } from "../utils/decisions"
import { dateTime, num, prob, rupiah, signedRupiah } from "../utils/format"
import { CHECK_ICON, type IconName } from "../utils/icons"
import { href } from "../utils/router"
import type { ClaimReviewData, ClaimRme, RmeQuote } from "../types"

export default function ClaimReview({ sep }: { sep: string }) {
  const claim = useQuery<ClaimReviewData>({ queryKey: [`/klaim/${sep}`] })
  const rme = useQuery<ClaimRme>({ queryKey: [`/klaim/${sep}/bacaan`], enabled: claim.isSuccess, staleTime: 0 })
  const rs = claim.data?.kode_rs ?? sep.split("-").slice(1, 2).map((n) => `RS-${n}`)[0]

  if (claim.error) {
    return (
      <Frame sep={sep} rs={rs}>
        {statusOf(claim.error) === 404 ? (
          <EmptyState icon="file-search" title="Klaim ini tidak ada di dunia DEV">
            Periksa nomor SEP, atau buka klaim dari Profil RS. <a className="font-semibold text-biru" href={href("antrean")}>Kembali ke Antrean kerja</a>.
          </EmptyState>
        ) : (
          <ErrorState message={errorText(claim.error)} onRetry={() => claim.refetch()} />
        )}
      </Frame>
    )
  }
  if (claim.isPending) return <Frame sep={sep} rs={rs}><Skeleton className="h-[640px] rounded-lg" /></Frame>
  const c = claim.data

  return (
    <Frame sep={sep} rs={c.kode_rs}>
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-3 font-mono text-2xl font-semibold">
          {c.nomor_sep}
          <SampleDataBadge data={c} />
        </h1>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Chip>{c.rs_teks}</Chip>
        <Chip>{`Kelas rawat ${c.kelas_rawat}`}</Chip>
        <Chip icon="calendar">{c.periode}</Chip>
        <DecisionChip latest={c.keputusan_terakhir} />
      </div>

      <div className="grid grid-cols-[minmax(0,1fr)_1px_minmax(0,1fr)] gap-5">
        <ClaimSide c={c} />
        <span className="bg-biru" aria-hidden />
        <RmeSide q={rme} />
      </div>

      <DecisionBar c={c} rme={rme.data} />
    </Frame>
  )
}

function Frame({ sep, rs, children }: { sep: string; rs: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 px-8 pt-6 pb-24">
      <Crumbs items={[{ label: "Antrean kerja", href: href("antrean") }, { label: rs, href: href("rs", rs) }, { label: sep }]} />
      {children}
    </div>
  )
}

function Chip({ icon, children }: { icon?: IconName; children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-garis bg-kartu px-2.5 py-1 text-xs font-semibold text-tinta">
      {icon && <Icon name={icon} size={13} className="text-tinta-2" />}
      {children}
    </span>
  )
}

function DecisionChip({ latest }: { latest: ClaimReviewData["keputusan_terakhir"] }) {
  if (!latest) return <Chip icon="circle-dashed">Belum diputus</Chip>
  const tone = latest.keputusan === "minta_klarifikasi" ? "bg-[#FDF4DC] border-[#F1D58E] text-[#6B4A00]" : latest.keputusan === "ajukan_audit" ? "bg-[#EEE8FB] border-[#D3C5F2] text-[#3B1675]" : "bg-[#F1F2F4] border-[#DADDE2] text-[#4B5563]"
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${tone}`}>
      <Icon name={latest.keputusan === "minta_klarifikasi" ? "message-square" : latest.keputusan === "ajukan_audit" ? "clipboard-check" : "check"} size={13} />
      {latest.keputusan === "minta_klarifikasi" ? "Diklarifikasi" : DECISION_LABEL[latest.keputusan as DecisionKind] ?? latest.keputusan}
    </span>
  )
}

function SideLabel({ title, note, labels, aside }: { title: string; note?: string; labels?: ("AI 1" | "AI 2" | "Kode")[]; aside?: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">{title}</span>
      {note && <span className="text-xs text-redam">{note}</span>}
      {labels && <MachineLabels kinds={labels} />}
      <span className="flex-1" />
      {aside}
    </div>
  )
}

function ClaimSide({ c }: { c: ClaimReviewData }) {
  const top = Math.max(...c.tangga.anak.map((a) => a.tarif))
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <SideLabel title="Yang diklaim" note="data E-Klaim" />
      <Card title="Data E-Klaim">
        <dl className="grid grid-cols-[96px_1fr_96px_1fr] gap-x-3 gap-y-1.5 text-[13px]">
          {c.eklaim.map(([k, v]) => (
            <div key={k} className="contents">
              <dt className="text-redam">{k}</dt>
              <dd className="font-semibold">{v}</dd>
            </div>
          ))}
          <dt className="text-redam">Prosedur</dt>
          <dd className="col-span-3 flex items-center gap-2">
            <span className="rounded bg-biru-muda px-1.5 font-mono font-semibold text-biru-tua">{c.prosedur.kode}</span>
            <span className="text-tinta-2">{c.prosedur.keterangan}</span>
          </dd>
          <dt className="text-redam">Ventilator</dt>
          <dd className="col-span-3 flex items-center gap-2">
            <span className="font-semibold">{c.ventilator.jam} jam</span>
            <span className="font-mono text-xs text-tinta-2">{c.ventilator.rentang}</span>
          </dd>
        </dl>
      </Card>

      <Card title="Tangga tarif" labels={["Kode"]}>
        <p className="text-sm font-semibold">{`${signedRupiah(c.tangga.selisih)} (×${c.tangga.kali}) karena kode ${c.tangga.kode}`}</p>
        <div className="mt-3 grid grid-cols-3 items-end gap-2">
          {c.tangga.anak.map((a) => (
            <div key={a.label} className="flex flex-col gap-1">
              <span className={`text-[13px] font-semibold ${a.diklaim ? "text-biru-tua" : "text-tinta"}`}>{rupiah(a.tarif)}</span>
              <span className={`rounded-[2px] ${a.diklaim ? "bg-biru" : "border border-garis"}`} style={{ height: 8 + (a.tarif / top) * 40 }} />
              <span className={`text-xs ${a.diklaim ? "font-semibold text-biru-tua" : "text-redam"}`}>{a.label}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Biaya vs tipikal pasien serupa (garis = 100%)" labels={["Kode"]}>
        <div className="flex flex-col gap-1.5">
          {c.biaya.map(([k, r, t]) => (
            <div key={k} className="grid grid-cols-[110px_160px_1fr] items-center gap-3 text-[13px]">
              <span className="text-tinta-2">{k}</span>
              <span className="relative h-2">
                <span className="absolute top-0 left-0 h-1 translate-y-0.5 rounded-full bg-biru" style={{ width: `${Math.min(r, 1.6) / 1.6 * 100}%` }} />
                <span className="absolute -top-1 h-4 w-0.5 bg-tinta" style={{ left: `${(1 / 1.6) * 100}%` }} aria-label="tipikal" />
              </span>
              <span className="font-semibold">{t}</span>
            </div>
          ))}
        </div>
      </Card>

      <Card title="Peluang didukung bukti" labels={["AI 1"]}>
        <div className="flex items-center gap-4">
          <span className="font-display text-[32px] leading-none font-bold text-biru-tua">{prob(c.ai1.peluang)}</span>
          <span className="flex flex-1 flex-col gap-1.5">
            <span className="relative h-2 rounded-full bg-abu-kartu">
              <span className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-biru ring-2 ring-white" style={{ left: `${c.ai1.peluang * 100}%` }} />
            </span>
            <span className="text-xs text-tinta-2">{c.ai1.keterangan}</span>
          </span>
        </div>
        {c.ai1.alasan.length > 0 ? (
          <ul className="mt-2.5 grid grid-cols-2 gap-x-4 gap-y-1">
            {c.ai1.alasan.map(([dir, text]) => (
              <li key={text} className="flex items-center gap-1.5 text-[13px]">
                <Icon name={dir === "turun" ? "arrow-down" : "arrow-up"} size={14} className={dir === "turun" ? "text-biru" : "text-tinta-2"} />
                {text}
              </li>
            ))}
          </ul>
        ) : (
          <p className="mt-2 text-[13px] text-tinta-2">{c.ai1.tanpa_alasan}</p>
        )}
        <p className="mt-2 text-xs text-redam">{c.ai1.catatan ?? "Panah turun menurunkan peluang, panah naik menaikkan; dihitung dari model, bukan ditebak LLM."}</p>
      </Card>
    </div>
  )
}

function SourceBadge({ r }: { r: ClaimRme }) {
  return r.sumber === "llm_lokal" ? (
    <span className="flex items-center gap-1.5 text-xs font-semibold text-tinta-2" title={r.catatan_sumber}>
      <span className="size-2 rounded-full bg-biru" />
      {`LLM lokal, ${num(r.durasi_ms / 1000, 1)} detik, data tidak keluar server${r.catatan_sumber ? ", bacaan tersimpan" : ""}`}
    </span>
  ) : (
    <span className="flex items-center gap-1.5 rounded-full bg-jingga-muda px-2.5 py-1 text-xs font-semibold text-tinta-2" title={r.catatan_sumber}>
      <span className="size-2 rounded-full border-[1.5px] border-redam" />
      {`Aturan cadangan, ${r.durasi_ms} ms, ${r.catatan_sumber ? "belum dibaca LLM" : "LLM lokal tidak aktif"}`}
    </span>
  )
}

function RmeSide({ q }: { q: { data?: ClaimRme; error: unknown; isPending: boolean; refetch: () => void } }) {
  const [doc, setDoc] = useState<string | null>(null)
  if (q.error) return <div className="flex flex-col gap-3"><SideLabel title="Yang tertulis di RME" labels={["AI 2"]} /><ErrorState message={errorText(q.error)} onRetry={q.refetch} /></div>
  if (q.isPending || !q.data) return <Reading />
  const r = q.data
  const active = r.dokumen.find((d) => d.id === (doc ?? r.dokumen_aktif)) ?? r.dokumen[0]
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <SideLabel title="Yang tertulis di RME" labels={[r.sumber === "aturan" ? "Kode" : "AI 2"]} aside={<SourceBadge r={r} />} />
      {r.jenis === "aturan" && (
        <div className="flex items-center gap-3 rounded-lg border border-[#F1D58E] bg-[#FDF4DC] px-3 py-2 text-[13px] text-[#6B4A00]">
          <Icon name="triangle-alert" size={16} />
          <span className="flex-1"><b>{r.catatan_sumber ? "Klaim ini belum dibaca LLM lokal, dibaca dengan aturan cadangan." : "LLM lokal tidak aktif, dibaca dengan aturan cadangan."}</b> Hanya pencarian kata kunci; keyakinan lebih rendah.</span>
          {!r.catatan_sumber && <Button icon="refresh-cw" onClick={q.refetch}>Coba lagi</Button>}
        </div>
      )}
      {active && <DocViewer docs={r.dokumen} active={active.id} onPick={setDoc} />}
      {r.jenis === "aturan" ? <RulesResult r={r} /> : <ReadResult r={r} />}
      {r.asersi && <AssertionCard a={r.asersi} />}
      {r.fisiologi && <PhysiologyCard f={r.fisiologi} />}
      {r.kemiripan && <SimilarityWarning k={r.kemiripan} />}
      {r.jejak && <TrailWarning j={r.jejak} />}
      {r.kutipan && r.jenis !== "asal_meragukan" && <Quotes r={r} />}
      {r.cek && (
        <div className="flex flex-wrap gap-x-5 gap-y-1">
          {r.cek.map(([icon, text]) => (
            <span key={text} className="flex items-center gap-1.5 text-xs text-tinta-2">
              <Icon name={CHECK_ICON[icon] ?? "info"} size={13} className="text-tinta-2" />
              {text}
            </span>
          ))}
        </div>
      )}
      {r.verdict_akhir && (
        <div className="flex items-center gap-2.5 rounded-lg border-2 border-tinta px-3 py-2.5 text-sm font-semibold">
          <Icon name="shield-x" size={16} />
          {r.verdict_akhir}
        </div>
      )}
    </div>
  )
}

function Reading() {
  return (
    <div className="flex min-w-0 flex-col gap-3" aria-busy="true">
      <SideLabel title="Yang tertulis di RME" labels={["AI 2"]} aside={<span className="flex items-center gap-1.5 text-xs font-semibold text-tinta-2"><Icon name="loader" size={13} className="animate-spin text-biru" />LLM lokal, sedang membaca…</span>} />
      <Skeleton className="h-40 rounded-lg" />
      <section className="flex flex-col gap-2 rounded-lg border border-garis bg-kartu p-4">
        <p className="flex items-center gap-2 text-sm font-semibold"><Icon name="loader" size={16} className="animate-spin text-biru" />Membaca dokumen RME…</p>
        {[0, 1, 2].map((i) => <Skeleton key={i} className="h-4 w-full" />)}
        <p className="text-xs text-redam">Kutipan akan muncul setelah semua dokumen dibaca dan dicocokkan.</p>
      </section>
    </div>
  )
}

function highlight(text: string, marks: string[]) {
  if (!marks.length) return text
  const parts: (string | React.JSX.Element)[] = []
  let rest = text
  let k = 0
  while (rest) {
    const hit = marks.map((m) => ({ m, i: rest.indexOf(m) })).filter((x) => x.i >= 0).sort((a, b) => a.i - b.i)[0]
    if (!hit) {
      parts.push(rest)
      break
    }
    parts.push(rest.slice(0, hit.i), <mark key={k++} className="rounded-[3px] bg-biru-muda px-0.5 font-semibold text-tinta">{hit.m}</mark>)
    rest = rest.slice(hit.i + hit.m.length)
  }
  return parts
}

function DocViewer({ docs, active, onPick }: { docs: ClaimRme["dokumen"]; active: string; onPick: (id: string) => void }) {
  const d = docs.find((x) => x.id === active)!
  return (
    <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
      <h2 className="px-4 pt-3 text-[15px] font-semibold">Dokumen RME klaim ini</h2>
      <nav className="mt-2 flex gap-1 overflow-x-auto border-b border-garis px-3" role="tablist">
        {docs.map((x) => (
          <button key={x.id} role="tab" aria-selected={x.id === active} onClick={() => onPick(x.id)}
                  className={`flex items-center gap-1.5 border-b-2 px-2 py-2 text-[13px] whitespace-nowrap ${x.id === active ? "border-biru font-semibold text-tinta" : "border-transparent text-tinta-2 hover:text-tinta"}`}>
            <Icon name="file-text" size={13} className={x.id === active ? "text-biru" : "text-redam"} />
            {x.label}
          </button>
        ))}
      </nav>
      <div className="bg-kertas px-4 py-3">
        <p className="mb-1 text-xs text-redam">{d.judul}</p>
        <p className="text-sm leading-6 text-tinta">{highlight(d.teks, d.sorot)}</p>
      </div>
    </section>
  )
}

function ReadResult({ r }: { r: ClaimRme }) {
  const h = r.hasil
  const tone = h.verdict_jenis === "tidak_dapat_disimpulkan" ? "border-[#F1D58E] bg-[#FDF4DC]" : "border-tinta"
  return (
    <Card title="Hasil baca" labels={["AI 2"]}>
      {h.alat && (
        <div className="grid grid-cols-[130px_1fr] items-center gap-y-2 text-[13px]">
          <span className="text-redam">Alat bantu napas</span>
          <span className="flex flex-wrap items-center gap-1.5">
            {h.alat.map((a, i) => (
              <span key={a} className="flex items-center gap-1.5">
                {i > 0 && <Icon name="arrow-right" size={13} className="text-redam" />}
                <span className="rounded-full bg-abu-kartu px-2.5 py-1 text-xs font-semibold">{a}</span>
              </span>
            ))}
          </span>
          {h.baris?.map(([k, v]) => (
            <div key={k} className="contents">
              <span className="text-redam">{k}</span>
              <span className="font-semibold">{v}</span>
            </div>
          ))}
        </div>
      )}
      <div className={`mt-3 flex w-fit items-center gap-2 rounded-lg border-2 px-3 py-2 text-sm font-semibold ${tone}`}>
        <Icon name={h.verdict_jenis === "mendukung" ? "file-check" : h.verdict_jenis === "tidak_dapat_disimpulkan" ? "circle-question-mark" : "file-x"} size={16} />
        {h.verdict}
      </div>
      {h.alasan && <p className="mt-2 text-[13px] text-tinta-2">{h.alasan}</p>}
      {h.aturan && <p className="mt-1 flex items-center gap-1.5 text-xs text-redam"><MachineLabel kind="Kode" />{h.aturan}</p>}
    </Card>
  )
}

function RulesResult({ r }: { r: ClaimRme }) {
  return (
    <Card title="Hasil aturan cadangan" labels={["Kode"]}>
      <div className="flex flex-col gap-2 text-[13px]">
        {r.kata?.map(([group, words]) => (
          <div key={group} className="flex items-center gap-3">
            <span className="w-[130px] text-redam">{group}</span>
            <span className="flex flex-wrap gap-1.5">
              {words.map(([w, n]) => (
                <span key={w} className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${n ? "bg-biru-muda text-biru-tua" : "bg-abu-kartu text-redam"}`}>{`${w}, ${n}`}</span>
              ))}
            </span>
          </div>
        ))}
        <div className="flex items-center gap-3">
          <span className="w-[130px] text-redam">Jam ventilator</span>
          <span className="font-semibold">{r.jam}</span>
        </div>
      </div>
      <div className="mt-3 flex w-fit items-center gap-2 rounded-lg border-2 border-tinta px-3 py-2 text-sm font-semibold">
        <Icon name={r.hasil.verdict_jenis === "mendukung" ? "file-check" : r.hasil.verdict_jenis === "tidak_dapat_disimpulkan" ? "circle-question-mark" : "file-x"} size={16} />
        {r.hasil.verdict}
      </div>
      <p className="mt-2 text-xs text-tinta-2">{r.peringatan_aturan}</p>
    </Card>
  )
}

function QuoteCard({ q }: { q: RmeQuote }) {
  return (
    <div className={`flex items-end justify-between gap-3 rounded-lg border px-3 py-2 ${q.cocok ? "border-garis bg-kartu" : "border-merah/40 bg-[#FBEAEA]"}`}>
      <span className="flex flex-col gap-0.5">
        <span className="text-[13px]">
          “{q.sebelum}
          <mark className={`rounded-[3px] px-0.5 font-semibold ${q.cocok ? "bg-biru-muda" : "bg-transparent text-merah line-through decoration-1"}`}>{q.sorot}</mark>
          {q.sesudah}”
        </span>
        <span className="font-mono text-xs text-redam">{q.dokumen}</span>
      </span>
      <span className={`flex shrink-0 items-center gap-1 text-xs font-semibold ${q.cocok ? "text-hijau" : "text-merah"}`}>
        <Icon name={q.cocok ? "check" : "x"} size={14} />
        {q.cocok ? "cocok persis" : "tidak ditemukan di dokumen"}
      </span>
    </div>
  )
}

function Quotes({ r }: { r: ClaimRme }) {
  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-semibold">{r.jenis === "aturan" ? "Temuan kata kunci" : "Kutipan"}</span>
        {r.kutipan_ringkas && (
          <span className={`flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-semibold ${r.kutipan_semua_cocok ? "border-hijau/30 bg-[#EAF3EA] text-hijau" : "border-merah/30 bg-[#FBEAEA] text-merah"}`}>
            <Icon name={r.kutipan_semua_cocok ? "check" : "x"} size={12} />
            {r.kutipan_ringkas}
          </span>
        )}
        {r.jenis === "aturan" && <span className="text-xs text-redam">kutipan LLM tidak tersedia</span>}
      </div>
      {r.kutipan!.map((q) => (
        <QuoteCard key={q.sorot + q.dokumen} q={q} />
      ))}
    </div>
  )
}

function SimilarityWarning({ k }: { k: NonNullable<ClaimRme["kemiripan"]> }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-jingga/40 bg-jingga-muda p-3.5">
      <p className="flex items-center gap-2 text-sm font-semibold"><Icon name="copy" size={16} className="text-jingga" />{k.judul}</p>
      <div className="grid grid-cols-2 gap-2">
        {k.pasangan.map((p) => (
          <div key={p.sep} className="rounded-md border border-garis bg-kartu px-3 py-2 text-xs">
            <p className="font-mono font-semibold">{p.sep}</p>
            <p className="text-tinta-2">{p.pasien}</p>
            <p className="mt-1 font-mono">{p.teks}<b className="text-jingga">{p.beda}</b></p>
          </div>
        ))}
      </div>
      <p className="text-xs text-tinta-2">{k.catatan}</p>
    </section>
  )
}

function TrailWarning({ j }: { j: NonNullable<ClaimRme["jejak"]> }) {
  return (
    <section className="flex flex-col gap-2 rounded-lg border border-jingga/40 bg-jingga-muda p-3.5">
      <p className="flex items-center gap-2 text-sm font-semibold"><Icon name="history" size={16} className="text-jingga" />{j.judul}</p>
      <div className="grid grid-cols-[110px_1fr] items-center gap-y-2 text-xs">
        <span className="text-tinta-2">Layanan</span>
        <span className="flex items-center gap-2"><span className="h-2 w-16 rounded-full bg-biru" />{j.layanan}</span>
        <span className="text-tinta-2">Ditulis server</span>
        <span className="flex items-center gap-2"><span className="ml-24 h-2 w-3 rounded-full bg-jingga" />{j.tulis}</span>
      </div>
      <p className="text-xs text-tinta-2">{j.catatan}</p>
    </section>
  )
}

function AssertionCard({ a }: { a: NonNullable<ClaimRme["asersi"]> }) {
  return (
    <Card title="Model asersi" labels={["AI 2"]} aside={<>
      <span className="rounded-full bg-biru-muda px-2 py-0.5 text-xs font-semibold text-biru-tua">{a.ringkas}</span>
      <span className={`flex items-center gap-1 text-xs font-semibold ${a.sama ? "text-hijau" : "text-tinta-2"}`}><Icon name={a.sama ? "check" : "x"} size={13} />{a.sama ? "sama dengan bacaan RME" : "berbeda dengan bacaan RME"}</span>
    </>}>
      <div className="flex flex-col gap-1.5">
        {a.sebutan.map(([t, text, device, assertion]) => (
          <div key={t + text} className="grid grid-cols-[80px_1fr_auto_auto] items-center gap-2 text-xs">
            <span className="font-mono text-redam">{t}</span>
            <span className="truncate">“{text}”</span>
            <span className="rounded-full border border-garis px-2 py-0.5">{device}</span>
            <span className={`rounded-full px-2 py-0.5 font-semibold ${assertion === "terpasang" ? "bg-biru-muda text-biru-tua" : "bg-abu-kartu text-tinta-2"}`}>{assertion}</span>
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-redam">{a.kaki}</p>
    </Card>
  )
}

function PhysiologyCard({ f }: { f: NonNullable<ClaimRme["fisiologi"]> }) {
  const W = 480, H = 60
  const bw = W / f.per_jam.length
  return (
    <Card title="Lembar tanda vital, pembaca fisiologi" labels={["AI 2"]} aside={<span className="rounded-full bg-jingga-muda px-2 py-0.5 text-xs font-semibold text-tinta">{f.ringkas}</span>}>
      <p className="text-xs text-tinta-2">{f.judul}</p>
      {f.pita_teks && <p className="text-xs text-biru-tua">{f.pita_teks}</p>}
      <svg viewBox={`0 0 ${W} ${H + 16}`} className="mt-1 w-full" role="img" aria-label="Peluang ventilasi invasif per jam">
        <rect x={f.jam_tertulis[0] * bw} y={0} width={(f.jam_tertulis[1] - f.jam_tertulis[0]) * bw} height={H} fill="rgba(205,226,251,0.4)" />
        {!f.pita_teks && <text x={f.jam_tertulis[0] * bw + 4} y={12} fontSize={11} fill="#0D366B">{`tertulis di RME dan diklaim, ${f.jam_tertulis[1] - f.jam_tertulis[0]} jam`}</text>}
        {f.per_jam.map((p, i) => (
          <rect key={i} x={i * bw + 1} y={H - p * H} width={bw - 2} height={p * H} fill="#2A78D6">
            <title>{`jam ke-${i}: ${num(p, 2)}`}</title>
          </rect>
        ))}
        <line x1={0} x2={W} y1={H * (1 - f.ambang)} y2={H * (1 - f.ambang)} stroke="#0B0B0B" strokeDasharray="4 3" strokeWidth={1.5} />
        <text x={W - 4} y={H * (1 - f.ambang) - 4} textAnchor="end" fontSize={11} fill="#0B0B0B">ambang 0,5</text>
        <line x1={0} x2={W} y1={H + 0.5} y2={H + 0.5} stroke="#E1E0D9" />
        {f.hari.map(([d, i]) => (
          <text key={d} x={i * bw} y={H + 13} fontSize={11} fill="#898781" fontFamily="JetBrains Mono, monospace">{d}</text>
        ))}
      </svg>
      <p className="mt-1 text-xs text-tinta-2">{f.catatan}</p>
      <p className="mt-1 text-xs text-redam">{f.kaki}</p>
      <OdblNote className="mt-1" />
    </Card>
  )
}

const BUTTONS: { kind: DecisionKind; icon: IconName }[] = [
  { kind: "setujui", icon: "check" },
  { kind: "ajukan_audit", icon: "clipboard-list" },
  { kind: "minta_klarifikasi", icon: "message-square" },
]

function DecisionBar({ c, rme }: { c: ClaimReviewData; rme?: ClaimRme }) {
  const client = useQueryClient()
  const [note, setNote] = useState("")
  const [correcting, setCorrecting] = useState(false)
  const decision = useDecision(() => {
    setNote("")
    setCorrecting(false)
    client.invalidateQueries({ queryKey: [`/klaim/${c.nomor_sep}`] })
  })
  const primary = rme?.tombol_utama ?? "minta_klarifikasi"
  const latest = c.keputusan_terakhir
  const basis = { mesin: rme?.sumber === "aturan" ? ["AI 1", "AI 2 (aturan cadangan)"] : ["AI 1", "AI 2"], versi_model: "tapal-1.0", sumber_bacaan: rme?.sumber ?? "belum dibaca" }
  const send = (kind: DecisionKind) =>
    decision.mutate({ objek_jenis: "klaim", objek_id: c.nomor_sep, keputusan: correcting ? "koreksi" : kind, catatan: note.trim(), dasar_ai: basis,
                      koreksi_untuk: correcting && latest ? latest.id : null, bukti: { peluang: c.ai1.peluang, rme: rme?.hasil.verdict_jenis ?? null } })

  return (
    <footer className="fixed right-0 bottom-0 left-60 z-20 flex min-w-[1200px] items-center gap-4 border-t border-garis bg-kartu px-8 py-3">
      <MachineLabel kind="Manusia" />
      {latest && !correcting ? (
        <>
          <span className="flex flex-col leading-tight">
            <span className="text-sm font-semibold">Keputusan tercatat</span>
            <span className="text-xs text-tinta-2">{`${latest.peran === "verifikator" ? "Verifikator" : latest.peran}, ${dateTime(latest.waktu)}, sidik ${latest.sidik.slice(0, 4)}…`}</span>
          </span>
          <span className="flex-1 truncate text-sm text-tinta-2">“{latest.catatan}”</span>
          <span className="rounded-full border border-garis px-2.5 py-1 text-xs font-semibold">{DECISION_LABEL[latest.keputusan as DecisionKind] ?? latest.keputusan}</span>
          <Button icon="pencil" onClick={() => setCorrecting(true)}>Koreksi</Button>
          <a href={href("jejak")} className="text-sm font-semibold text-biru">Lihat di Jejak keputusan</a>
        </>
      ) : (
        <>
          <span className="flex flex-col leading-tight">
            <span className="text-sm font-semibold">{correcting ? "Koreksi keputusan" : "Keputusan verifikator"}</span>
            <span className="text-xs text-tinta-2">{correcting ? "Baris lama tetap; koreksi dicatat sebagai baris baru." : "TAPAL tidak menolak klaim. Keputusan ada di verifikator."}</span>
          </span>
          <label className="flex flex-1 items-center gap-2 rounded-md border border-garis bg-latar px-3 py-2">
            <Icon name="pencil" size={14} className="text-redam" />
            <input value={note} onChange={(e) => setNote(e.target.value)} placeholder="Catatan wajib: alasan keputusan…" className="w-full bg-transparent text-sm outline-hidden placeholder:text-redam" />
          </label>
          {decision.error && <span className="text-xs text-merah">{errorText(decision.error)}</span>}
          {correcting ? (
            <>
              <Button onClick={() => setCorrecting(false)}>Batal</Button>
              <Button variant="primer" icon="check" disabled={!note.trim() || decision.isPending} onClick={() => send("koreksi")}>Catat koreksi</Button>
            </>
          ) : (
            BUTTONS.map((b) => (
              <Button key={b.kind} variant={b.kind === primary ? "primer" : "sekunder"} icon={b.icon} disabled={!note.trim() || decision.isPending} onClick={() => send(b.kind)}
                      title={note.trim() ? undefined : "Isi catatan dulu"}>
                {DECISION_LABEL[b.kind]}
              </Button>
            ))
          )}
        </>
      )}
    </footer>
  )
}
