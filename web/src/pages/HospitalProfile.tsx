import { useQuery } from "@tanstack/react-query"
import { useState } from "react"
import { errorText, postJson, statusOf } from "../utils/api"
import { HoursHistogram, Legend, PeerDotPlot, ProbabilityHistogram, SimilarityMatrix, WriteTimeline } from "../components/charts"
import { Drawer, NoteDialog } from "../components/dialogs"
import {
  Button,
  Card,
  Confidence,
  Crumbs,
  EmptyState,
  ErrorState,
  HonestNote,
  Icon,
  MachineLabel,
  MachineLabels,
  ModeChip,
  SampleDataBadge,
  Skeleton,
  StatusChip,
  Th,
} from "../components/ui"
import { useDecision, type DecisionKind } from "../utils/decisions"
import { miliar, num, prob, signedRupiah } from "../utils/format"
import { CHECK_ICON, type IconName } from "../utils/icons"
import { go, href } from "../utils/router"
import type { Profile, ProfileChart, ProfileClaim, ShortProfile, Summary } from "../types"

export default function HospitalProfile({ kode }: { kode: string }) {
  const { data, error, isPending, refetch } = useQuery<Profile | ShortProfile>({ queryKey: [`/rs/${kode}`] })
  const [drawer, setDrawer] = useState(false)
  const [asking, setAsking] = useState<DecisionKind | null>(null)
  const decision = useDecision(() => setAsking(null))

  if (error) {
    return (
      <Frame kode={kode}>
        {statusOf(error) === 404 ? (
          <EmptyState icon="search" title={`${kode} tidak ada di antrean kerja`}>
            RS ini tidak ditandai pada periode ini, atau kodenya salah ketik. <a className="font-semibold text-biru" href={href("antrean")}>Kembali ke Antrean kerja</a>.
          </EmptyState>
        ) : (
          <ErrorState message={errorText(error)} onRetry={() => refetch()} />
        )}
      </Frame>
    )
  }
  if (isPending) return <Frame kode={kode}><ProfileSkeleton /></Frame>

  const machines = data.modus === "rme_meragukan" ? ["AI 2"] : ["AI 1", "Statistik"]
  const actions = (
    <>
      {"kartu_diakui" in data && <Button icon="text-quote" onClick={() => setDrawer(true)}>Ringkas kasus</Button>}
      <Button icon="message-square" onClick={() => setAsking("minta_klarifikasi")}>Minta klarifikasi RS</Button>
      <Button icon="file-plus" onClick={() => go("laporan")}>Buat laporan</Button>
      <Button variant="primer" icon="clipboard-list" onClick={() => setAsking("masukkan_rencana_audit")}>Masukkan ke rencana audit</Button>
    </>
  )

  return (
    <Frame kode={kode}>
      <div className="flex items-center justify-between gap-4">
        <h1 className="flex items-center gap-3 font-display text-[28px] font-bold text-tinta">
          {data.kode_rs}
          <SampleDataBadge data={data} />
        </h1>
        <div className="flex items-center gap-2">{actions}</div>
      </div>
      <div className="flex flex-wrap items-center gap-2.5">
        <span className="rounded-full border border-garis bg-kartu px-2.5 py-1 text-xs font-semibold text-tinta">{`Kelas ${data.kelas}, ${data.kepemilikan}, Regional ${data.regional}`}</span>
        <ModeChip mode={data.modus} />
        <Confidence level={data.keyakinan} detail={data.keterangan_keyakinan} />
        <StatusChip status={data.status_penanganan} />
        {"ringkas_data" in data && <span className="text-[13px] text-tinta-2">{data.ringkas_data}</span>}
      </div>

      {"kartu_diakui" in data ? <FullProfile p={data} /> : <ShortBody p={data} />}

      {drawer && "kartu_diakui" in data && <CaseDrawer kode={data.kode_rs} onClose={() => setDrawer(false)} />}
      {asking && (
        <NoteDialog
          title={asking === "minta_klarifikasi" ? "Minta klarifikasi RS" : "Masukkan ke rencana audit"}
          subject={data.kode_rs}
          confirm={asking === "minta_klarifikasi" ? "Catat permintaan klarifikasi" : "Masukkan ke rencana"}
          pending={decision.isPending}
          error={decision.error}
          onClose={() => setAsking(null)}
          onSubmit={(catatan) =>
            decision.mutate({ objek_jenis: "rs", objek_id: data.kode_rs, keputusan: asking, catatan, dasar_ai: { mesin: machines, versi_model: "tapal-1.0" } })
          }
        />
      )}
    </Frame>
  )
}

function Frame({ kode, children }: { kode: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <Crumbs items={[{ label: "Antrean kerja", href: href("antrean") }, { label: kode }]} />
      {children}
    </div>
  )
}

function ShortBody({ p }: { p: ShortProfile }) {
  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        <Card title="Diakui vs wajar" labels={["AI 1", "Statistik"]}>
          <p className="font-display text-3xl font-bold">
            {p.diakui} <span className="text-biru">{p.wajar}</span>
          </p>
          <p className="text-[13px] text-tinta-2">{`diakui, wajar menurut bukti (${p.wajar_bawah}–${p.wajar_atas}); ${p.keterangan_keyakinan}`}</p>
        </Card>
        <Card title="Perkiraan kelebihan bayar" labels={["Kode"]}>
          <p className="font-display text-3xl font-bold">{miliar(p.rupiah)}</p>
          {p.rupiah_bawah !== null && <p className="text-[13px] font-semibold text-tinta">{`Rentang 95%: Rp${num(p.rupiah_bawah / 1e9, 2)}–${num(p.rupiah_atas! / 1e9, 2)} miliar`}</p>}
        </Card>
        <Card title="Bukti RME" labels={["AI 2"]}>
          <p className="text-[13px] text-tinta-2">Bacaan RME untuk RS ini belum masuk ke data contoh.</p>
        </Card>
      </div>
      <HonestNote>Profil lengkap (grafik pembanding, klaim teratas, bukti RME) untuk RS ini menunggu keluaran mesin disambungkan ke API; data contoh desain hanya memuat RS-092, RS-117, dan RS-140.</HonestNote>
    </>
  )
}

function FullProfile({ p }: { p: Profile }) {
  const d = p.kartu_diakui
  const r = p.kartu_rupiah
  const top = Math.max(...p.kartu_rme.hitungan.map(([, n]) => n))
  return (
    <>
      <div className="grid grid-cols-3 gap-4">
        <Card title="Diakui vs wajar" labels={d.label} className="min-h-[218px]">
          <div className="flex items-end gap-10">
            <span className="flex flex-col">
              <span className="font-display text-[30px] leading-tight font-bold">{d.diakui}</span>
              <span className="text-xs text-tinta-2">{d.diakui_teks}</span>
            </span>
            <span className="flex flex-col">
              <span className="font-display text-[30px] leading-tight font-bold text-biru">{d.wajar}</span>
              <span className="text-xs text-tinta-2">{`wajar menurut bukti (${d.wajar_bawah}–${d.wajar_atas})`}</span>
            </span>
          </div>
          <div className="relative mt-3 h-[18px] rounded-[3px] bg-biru-muda">
            <span className="absolute inset-y-0 left-0 rounded-l-[3px] bg-biru" style={{ width: `${(d.wajar / d.diakui) * 100}%` }} />
            {d.kelebihan_teks && (
              <span className="absolute inset-y-0 flex items-center pl-2 text-xs font-semibold text-biru-tua" style={{ left: `${(d.wajar / d.diakui) * 100}%` }}>
                {d.kelebihan_teks}
              </span>
            )}
          </div>
          <div className="relative h-2">
            <span className="absolute top-1 h-0.5 bg-tinta-2" style={{ left: `${(d.wajar_bawah / d.diakui) * 100}%`, width: `${((d.wajar_atas - d.wajar_bawah) / d.diakui) * 100}%` }} />
          </div>
          <p className="mt-2 text-xs text-tinta-2">{d.catatan}</p>
          {d.catatan_jujur && <HonestNote className="mt-2">{d.catatan_jujur}</HonestNote>}
        </Card>

        <Card title={r.judul} labels={["Kode"]} className="min-h-[218px]">
          <p className="font-display text-[30px] leading-tight font-bold">{miliar(r.nilai)}</p>
          {r.bawah !== null && r.atas !== null && r.skala !== null ? (
            <>
              <BigRange lo={r.bawah} mid={r.nilai} hi={r.atas} max={r.skala} />
              <p className="text-[13px] font-semibold text-tinta">{`Rentang 95%: Rp${num(r.bawah / 1e9, 2)}–${num(r.atas / 1e9, 2)} miliar`}</p>
            </>
          ) : (
            <p className="mt-1 text-[13px] font-semibold text-tinta">{r.subjudul}</p>
          )}
          <p className="mt-2 text-xs text-tinta-2">{r.rincian}</p>
          {r.catatan && <p className="mt-1 text-xs font-semibold text-tinta-2">{r.catatan}</p>}
        </Card>

        <Card title="Bukti RME" labels={["AI 2"]} className="min-h-[218px]">
          <p className="text-[13px] font-semibold text-tinta">{p.kartu_rme.judul}</p>
          <div className="mt-2 flex flex-col gap-2">
            {p.kartu_rme.hitungan.map(([label, n]) => (
              <div key={label} className="grid grid-cols-[1fr_100px_32px] items-center gap-3 text-[13px] text-tinta-2">
                <span>{label}</span>
                <span className="h-2 rounded-[2px] bg-biru" style={{ width: `${Math.max(4, (n / top) * 100)}%`, opacity: n === top ? 1 : 0.35 }} />
                <span className="text-right font-semibold text-tinta">{n}</span>
              </div>
            ))}
          </div>
          <div className="mt-3 flex flex-col gap-1.5 border-t border-garis pt-2.5">
            {p.kartu_rme.status.map(([icon, text]) => (
              <p key={text} className="flex items-start gap-2 text-xs text-tinta-2">
                <Icon name={CHECK_ICON[icon] ?? "info"} size={14} className="mt-px text-tinta-2" />
                {text}
              </p>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <ChartCard chart={p.grafik_kiri} kode={p.kode_rs} />
        <ChartCard chart={p.grafik_kanan} kode={p.kode_rs} />
      </div>

      <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
        <header className="flex items-center gap-3 px-4 py-3">
          <h2 className="text-[15px] font-semibold">{p.klaim_judul}</h2>
          <span className="text-xs text-redam">{p.klaim_keterangan}</span>
          <span className="flex-1" />
          <span className="text-[13px] font-semibold text-redam" title="Daftar lengkap belum ditampilkan di layar ini">{`${p.klaim_total} klaim`}</span>
        </header>
        <table className="w-full border-t border-garis text-[13px]">
          <thead className="bg-kertas">
            <tr className="border-b border-garis">
              <Th className="pl-4">Nomor SEP</Th>
              <Th>Tanggal</Th>
              <Th>Diagnosis</Th>
              <Th>Prosedur</Th>
              <Th>Jam</Th>
              <Th>Peluang</Th>
              <Th>Alasan utama</Th>
              <Th className="text-right">Selisih tarif</Th>
              <Th>Status RME</Th>
              <Th />
            </tr>
          </thead>
          <tbody>
            {p.klaim.map((c, i) => (
              <ClaimRow key={c.nomor_sep} c={c} first={i === 0} />
            ))}
          </tbody>
        </table>
      </section>
    </>
  )
}

function BigRange({ lo, mid, hi, max }: { lo: number; mid: number; hi: number; max: number }) {
  const x = (v: number) => `${(v / max) * 100}%`
  const step = [0.1e9, 0.25e9, 0.5e9, 1e9, 2e9, 5e9].find((s) => max / s <= 5) ?? 5e9
  const ticks = Array.from({ length: Math.round(max / step) + 1 }, (_, i) => i * step)
  return (
    <div className="mt-3 mb-1">
      <div className="relative mx-2 h-6">
        <span className="absolute top-3 right-0 left-0 h-px bg-garis" />
        {ticks.map((t) => (
          <span key={t} className="absolute top-2 h-2.5 w-px bg-[#C3C2B7]" style={{ left: x(t) }} />
        ))}
        <span className="absolute top-[11px] h-[3px] rounded-full bg-biru" style={{ left: x(lo), width: `calc(${x(hi)} - ${x(lo)})` }} />
        <span className="absolute top-[7px] size-[11px] -translate-x-1/2 rounded-full bg-biru ring-2 ring-white" style={{ left: x(mid) }} />
      </div>
      <div className="relative mx-2 h-4 font-mono text-xs text-redam">
        {ticks.map((t, i) => (
          <span key={t} className="absolute -translate-x-1/2 whitespace-nowrap" style={{ left: x(t) }}>
            {`${num(t / 1e9, Number.isInteger(Math.round(t / 1e7) / 100) ? 0 : step === 0.25e9 ? 2 : 1)}${i === ticks.length - 1 ? " M" : ""}`}
          </span>
        ))}
      </div>
    </div>
  )
}

function ChartCard({ chart, kode }: { chart: ProfileChart; kode: string }) {
  const legend =
    chart.jenis === "peluang" || chart.jenis === "jam"
      ? [{ label: chart.seri[0], color: "#2A78D6" }, { label: chart.seri[1], color: chart.jenis === "jam" ? "#898781" : "#C3C2B7", shape: chart.jenis === "jam" ? ("line" as const) : ("box" as const) }]
      : chart.jenis === "pembanding"
        ? [{ label: "RS lain", color: "#C3C2B7", shape: "dot" as const }, { label: kode, color: "#2A78D6", shape: "dot" as const }]
        : chart.jenis === "waktu_tulis"
          ? [{ label: chart.seri[0], color: "#2A78D6", shape: "dot" as const }, { label: chart.seri[1], color: "#C3C2B7", shape: "dot" as const }]
          : []
  return (
    <section className="flex flex-col gap-1.5 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center gap-2">
        <h2 className="flex-1 text-sm font-semibold">{chart.judul}</h2>
        {legend.length > 0 && <Legend items={legend} />}
        <MachineLabels kinds={chart.label} />
      </header>
      <p className="text-xs text-tinta-2">{chart.temuan}</p>
      {chart.jenis === "peluang" && <ProbabilityHistogram rs={chart.rs} peers={chart.lain} />}
      {chart.jenis === "pembanding" && <PeerDotPlot peers={chart.lain} rs={chart.rs} band={chart.rentang_wajar} domain={chart.domain} />}
      {chart.jenis === "jam" && <HoursHistogram start={chart.awal} step={chart.lebar} rs={chart.rs} peers={chart.lain} line={chart.garis_tarif} placebo={chart.plasebo} />}
      {chart.jenis === "waktu_tulis" && <WriteTimeline others={chart.lain} waves={chart.gelombang} months={chart.bulan} />}
      {chart.jenis === "kemiripan" && (
        <div className="flex items-center gap-5 py-2">
          <SimilarityMatrix n={chart.n_pasien} twins={chart.n_kembar} median={chart.median_kembar} />
          <div className="flex flex-col gap-1">
            <span className="font-display text-2xl font-bold">{chart.n_kembar} pasien</span>
            <span className="text-xs text-tinta-2">{chart.keterangan}</span>
            <span className="mt-2 flex items-center gap-2 text-xs text-redam">
              0
              <span className="h-2 w-28 rounded-full bg-[linear-gradient(90deg,rgba(42,120,214,0.05),rgba(42,120,214,1))]" />1 kemiripan
            </span>
          </div>
        </div>
      )}
    </section>
  )
}

const RME_STATUS: Record<ProfileClaim["status_rme"], { text: string; icon: IconName }> = {
  tidak_mendukung: { text: "Tidak mendukung", icon: "file-x" },
  tidak_dapat_disimpulkan: { text: "Tak dapat disimpulkan", icon: "circle-question-mark" },
  belum_dibaca: { text: "Belum dibaca", icon: "file" },
  asal_meragukan: { text: "Asal meragukan", icon: "shield-x" },
  mendukung: { text: "Mendukung", icon: "file-check" },
}

function ClaimRow({ c, first }: { c: ProfileClaim; first: boolean }) {
  const s = RME_STATUS[c.status_rme]
  return (
    <tr onClick={() => go("klaim", c.nomor_sep)} className={`cursor-pointer border-b border-garis last:border-b-0 hover:bg-biru-muda/40 ${first ? "bg-biru-muda/25" : ""}`}>
      <td className="py-2.5 pr-3 pl-4">
        <a href={href("klaim", c.nomor_sep)} onClick={(e) => e.stopPropagation()} className="font-mono text-[13px] font-semibold whitespace-nowrap hover:underline">
          {c.nomor_sep}
        </a>
      </td>
      <td className="px-3 whitespace-nowrap text-tinta-2">{c.tanggal}</td>
      <td className="px-3 font-mono">{c.diagnosis}</td>
      <td className="px-3 font-mono font-semibold">{c.prosedur}</td>
      <td className="px-3 whitespace-nowrap text-tinta-2">{c.jam} jam</td>
      <td className="px-3 font-mono text-biru">{prob(c.peluang)}</td>
      <td className="px-3">
        <span className="flex gap-1.5">
          {c.alasan.map((a) => (
            <span key={a} className="rounded-full bg-abu-kartu px-2 py-0.5 text-xs whitespace-nowrap text-tinta-2">
              {a}
            </span>
          ))}
        </span>
      </td>
      <td className="px-3 text-right font-semibold">{signedRupiah(c.selisih_tarif)}</td>
      <td className="px-3">
        <span className="inline-flex items-center gap-1.5 rounded-full border border-garis px-2.5 py-1 text-xs font-semibold whitespace-nowrap">
          <Icon name={s.icon} size={13} className="text-tinta-2" />
          {s.text}
        </span>
      </td>
      <td className="pr-4">
        <Icon name="chevron-right" size={16} className={first ? "text-biru" : "text-redam"} />
      </td>
    </tr>
  )
}

function CaseDrawer({ kode, onClose }: { kode: string; onClose: () => void }) {
  const summary = useQuery<Summary>({ queryKey: [`/rs/${kode}/ringkasan`], queryFn: ({ signal }) => postJson<Summary>(`/rs/${kode}/ringkasan`, {}, signal), staleTime: 0, gcTime: 0 })
  const s = summary.data
  const llm = s?.sumber === "llm_lokal"
  const plain = s?.segmen.map((x) => x.teks).join("") ?? ""
  return (
    <Drawer onClose={onClose}>
      <header className="flex items-center gap-2">
        <h2 className="flex-1 font-display text-lg font-bold">{`Ringkas kasus ${kode}`}</h2>
        {s && (llm ? <MachineLabel kind="LLM narasi" /> : <span className="rounded-full border border-garis px-2 py-0.5 text-xs font-semibold text-tinta-2">Templat</span>)}
        <button onClick={onClose} aria-label="Tutup" className="rounded-md p-1 text-tinta-2 hover:bg-latar">
          <Icon name="x" size={18} />
        </button>
      </header>

      {summary.isPending && (
        <div className="flex flex-col gap-3" aria-busy="true">
          <span className="flex items-center gap-2 text-[13px] text-tinta-2">
            <Icon name="loader" size={16} className="animate-spin text-biru" />
            Menyusun ringkasan dengan LLM lokal…
          </span>
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-5 w-full" />
          ))}
        </div>
      )}
      {summary.error && <ErrorState message={errorText(summary.error)} onRetry={() => summary.refetch()} />}

      {s && (
        <>
          <span className={`flex w-fit items-center gap-2 rounded-full px-2.5 py-1.5 text-xs font-semibold text-tinta-2 ${llm ? "bg-latar" : "bg-jingga-muda"}`}>
            <span className={`size-2 rounded-full ${llm ? "bg-biru" : "border-[1.5px] border-redam"}`} />
            {llm
              ? `LLM lokal, ${num(s.durasi_ms / 1000, 1)} detik, data tidak keluar server`
              : s.catatan.some((c) => c.includes("tidak tersedia")) || s.catatan.length <= 1
                ? "Aturan cadangan: LLM lokal tidak aktif"
                : "Templat: keluaran LLM ditolak pemeriksa angka"}
          </span>
          <div className="rounded-lg border border-garis bg-kertas p-4 text-sm leading-[26px] text-tinta">
            {s.segmen.map((seg, i) =>
              seg.token ? (
                <span key={i} title={seg.asal ?? ""} className="mx-px cursor-help rounded-[4px] bg-biru-muda px-[5px] py-px font-mono text-[13px] font-semibold text-biru-tua">
                  {seg.teks}
                </span>
              ) : (
                <span key={i}>{seg.teks}</span>
              ),
            )}
            {!llm && (
              <p className="pt-2.5 text-xs leading-normal text-tinta-2">
                {s.catatan.some((c) => c.includes("tidak tersedia")) || s.catatan.length <= 1
                  ? "Narasi templat karena LLM lokal tidak aktif. Angkanya sama persis; hanya kalimatnya lebih kaku. Sistem tetap berjalan."
                  : `Narasi templat karena keluaran LLM ditolak (${s.catatan[0]}). Angkanya sama persis dengan versi LLM.`}
              </p>
            )}
          </div>
          <h3 className="text-[13px] font-semibold">Asal setiap angka</h3>
          <div className="flex flex-col rounded-lg border border-garis">
            {s.asal_angka.map((a) => (
              <div key={a.angka + a.asal} className="flex items-center gap-2.5 border-b border-garis px-3 py-2 last:border-b-0">
                <span className="w-[120px] font-mono text-xs font-semibold">{a.angka}</span>
                <span className="flex-1 text-xs text-tinta-2">{a.asal}</span>
                <MachineLabels kinds={a.label} />
              </div>
            ))}
          </div>
          <p className="text-xs text-tinta-2">Angka disisipkan kode; LLM hanya menyusun kalimat dan tidak menulis angka sendiri. Periksa sebelum dipakai.</p>
          <footer className="flex gap-2">
            <Button icon="copy" onClick={() => navigator.clipboard.writeText(plain)}>Salin</Button>
            <Button
              variant="primer"
              icon="file-plus"
              onClick={() => {
                try {
                  sessionStorage.setItem("tapal-narasi", JSON.stringify({ kode, segmen: s.segmen, sumber: s.sumber }))
                } catch {
                  // Storage can be blocked; the report then keeps its own narrative.
                }
                go("laporan")
              }}
            >
              Masukkan ke laporan
            </Button>
          </footer>
        </>
      )}
    </Drawer>
  )
}

function ProfileSkeleton() {
  return (
    <div className="flex flex-col gap-3" aria-busy="true" aria-label="Memuat profil RS">
      <Skeleton className="h-9 w-40" />
      <Skeleton className="h-6 w-[640px]" />
      <div className="grid grid-cols-3 gap-4">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-[218px] rounded-lg" />
        ))}
      </div>
      <div className="grid grid-cols-2 gap-4">
        {[0, 1].map((i) => (
          <Skeleton key={i} className="h-[196px] rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-48 rounded-lg" />
    </div>
  )
}
