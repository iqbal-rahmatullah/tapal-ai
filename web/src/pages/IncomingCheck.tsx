import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { isAxiosError } from "axios"
import { useEffect, useMemo, useState } from "react"
import { errorText, http, postJson } from "../utils/api"
import { JsonEditor } from "../components/JsonEditor"
import { Button, ErrorState, HonestNote, Icon, MachineLabel, PageHeader, Segmented, Skeleton } from "../components/ui"
import { num, prob, rupiah, seconds, signedRupiah } from "../utils/format"
import type { IconName } from "../utils/icons"
import type { CheckResponse, LlmState, Machine, ValidationIssue } from "../types"

type Example = { kunci: string; label: string; keterangan: string; rs: string; payload: Record<string, unknown> }
type RmeLive = {
  status: "diproses" | "selesai"
  tahap: "antre" | "berjalan" | "selesai" | "gagal"
  detik_berjalan?: number
  verdict?: "mendukung" | "tidak_mendukung" | "tidak_dapat_disimpulkan"
  sumber?: "llm_lokal" | "aturan"
  kutipan_terverifikasi?: number
  kutipan?: { fakta: string; teks: string }[]
  alasan?: string[]
  jam_rme?: number | null
  alat?: string | null
  durasi_ms?: number
  status_klaim?: CheckResponse["status"]
  status_sebelumnya?: CheckResponse["status"] | null
  waktu_proses_ms?: number
}
type Outcome = { kind: "ok"; res: CheckResponse; ms: number; sentAt: number } | { kind: "invalid"; issues: ValidationIssue[]; ms: number }

const CUSTOM = "tempel_json"
const STATUS_TEXT: Record<CheckResponse["status"], string> = { lolos_cepat: "Lolos cepat", periksa_manual: "Periksa manual", didukung_rme: "Didukung RME" }
const VERDICT_TEXT = { mendukung: "Mendukung", tidak_mendukung: "Tidak mendukung", tidak_dapat_disimpulkan: "Tidak dapat disimpulkan" } as const

function pretty(v: unknown) {
  return JSON.stringify(v, null, 2)
}

function flatten(v: unknown, prefix = ""): Record<string, string> {
  if (v === null || typeof v !== "object" || Array.isArray(v)) return { [prefix]: JSON.stringify(v) }
  return Object.entries(v as Record<string, unknown>).reduce((acc, [k, x]) => ({ ...acc, ...flatten(x, prefix ? `${prefix}.${k}` : k) }), {})
}

function changes(before: unknown, after: unknown): string[] {
  const a = flatten(before)
  const b = flatten(after)
  return [...new Set([...Object.keys(a), ...Object.keys(b)])]
    .filter((k) => a[k] !== b[k])
    .map((k) => (k in b ? (k in a ? `${k}: ${a[k]} → ${b[k]}` : `${k}: ditambah ${b[k]}`) : `${k}: dihapus`))
}

// Polls skip the top loading bar on purpose: the RME step shows its own progress, and a bar restarting every 1,5 s for 48 s reads as a glitch.
async function quietGet<T>(path: string, signal: AbortSignal): Promise<T> {
  return (await http.get<T>(path.replace(/^\/api\/v1/, ""), { signal })).data
}

export default function IncomingCheck() {
  const client = useQueryClient()
  const examples = useQuery<Example[]>({ queryKey: ["/klaim/contoh"], staleTime: Infinity })
  const llm = useQuery<LlmState>({ queryKey: ["/llm"] })
  const [choice, setChoice] = useState<string>("bukti_lemah")
  const [tab, setTab] = useState<"ringkasan" | "json">("ringkasan")
  const [draft, setDraft] = useState<string | null>(null)
  const [outcome, setOutcome] = useState<Outcome | null>(null)
  const [firstOfExample, setFirstOfExample] = useState<Record<string, CheckResponse>>({})
  const [elapsed, setElapsed] = useState(0)

  const list = examples.data ?? []
  const base = list.find((e) => e.kunci === (choice === CUSTOM ? "bukti_lengkap" : choice))
  const basePretty = base ? pretty(base.payload) : ""
  const text = choice === CUSTOM ? (draft ?? basePretty) : basePretty
  const parsed = useMemo(() => {
    try {
      return { ok: true as const, value: JSON.parse(text) as Record<string, unknown> }
    } catch (e) {
      return { ok: false as const, error: (e as Error).message }
    }
  }, [text])
  const diff = choice === CUSTOM && parsed.ok && base ? changes(base.payload, parsed.value) : []

  const toggleLlm = useMutation({
    mutationFn: (aktif: boolean) => http.put<LlmState>("/llm", { aktif }).then((r) => r.data),
    onSuccess: (state) => client.setQueryData(["/llm"], state),
  })

  const send = useMutation({
    mutationFn: async (body: Record<string, unknown>) => {
      const t0 = performance.now()
      try {
        const res = await postJson<CheckResponse>("/klaim/periksa", body)
        return { kind: "ok", res, ms: Math.round(performance.now() - t0), sentAt: Date.now() } satisfies Outcome
      } catch (e) {
        if (isAxiosError(e) && e.response?.status === 422 && e.response.data?.galat) {
          return { kind: "invalid", issues: e.response.data.galat as ValidationIssue[], ms: Math.round(performance.now() - t0) } satisfies Outcome
        }
        throw e
      }
    },
    onSuccess: (o) => {
      setOutcome(o)
      if (o.kind === "ok" && choice !== CUSTOM) setFirstOfExample((m) => ({ ...m, [choice]: o.res }))
    },
  })

  const res = outcome?.kind === "ok" ? outcome.res : null
  const rmeUrl = res?.rme.status === "diproses" ? (res.rme.hasil ?? null) : null
  const rme = useQuery<RmeLive>({
    queryKey: ["rme", rmeUrl, outcome?.kind === "ok" ? outcome.sentAt : 0],
    queryFn: ({ signal }) => quietGet<RmeLive>(rmeUrl!, signal),
    enabled: rmeUrl !== null,
    refetchInterval: (q) => (q.state.data?.status === "selesai" ? false : 1500),
    staleTime: 0,
  })
  const rmeDone = rme.data?.status === "selesai" ? rme.data : null

  useEffect(() => {
    if (!res || rmeDone || res.rme.status !== "diproses" || outcome?.kind !== "ok") return
    const start = outcome.sentAt
    const t = setInterval(() => setElapsed(Math.round((Date.now() - start) / 1000)), 1000)
    return () => clearInterval(t)
  }, [res, rmeDone, outcome])

  const pick = (key: string) => {
    setChoice(key)
    setOutcome(null)
    setElapsed(0)
    setDraft(null)
    if (key === CUSTOM) setTab("json")
  }

  const finalStatus = rmeDone?.status_klaim ?? res?.status
  const original = choice === CUSTOM ? firstOfExample["bukti_lengkap"] : null

  return (
    <div className="flex flex-col gap-3 px-8 py-6">
      <PageHeader
        title="Cek klaim masuk"
        actions={
          <>
            <span className="flex items-center gap-1.5 rounded-full border border-garis bg-kartu px-2.5 py-1 text-xs font-semibold text-tinta-2">
              <Icon name="server" size={13} className="text-tinta-2" />
              API v1, model tapal-1.0
            </span>
            <a href="/docs" target="_blank" rel="noreferrer" className="inline-flex items-center gap-2 rounded-md border border-garis bg-kartu px-3.5 py-[9px] text-sm font-semibold hover:bg-latar">
              <Icon name="code" size={16} className="text-tinta-2" />
              Buka dokumentasi API
            </a>
          </>
        }
      >
        <p className="text-[13px] text-tinta-2">Sistem verifikasi memanggil TAPAL saat klaim masuk: AI 1 menjawab seketika, AI 2 membaca RME menyusul.</p>
      </PageHeader>

      <div className="grid grid-cols-[440px_minmax(0,1fr)] items-start gap-4">
        <div className="flex flex-col gap-3">
          <p className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">
            Klaim masuk <span className="ml-1 font-normal tracking-normal normal-case">contoh dari dunia sintetis DEV</span>
          </p>
          <section className="flex flex-col gap-2.5 rounded-lg border border-garis bg-kartu p-4">
            <h2 className="text-[15px] font-semibold">Pilih contoh</h2>
            {examples.isPending && [0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-[52px] rounded-lg" />)}
            {examples.error && <ErrorState message={errorText(examples.error)} onRetry={() => examples.refetch()} />}
            {list.map((e) => (
              <Option key={e.kunci} active={choice === e.kunci} onClick={() => pick(e.kunci)} title={e.label}
                      line={e.kunci === "data_rusak" ? `${e.payload.nomor_sep as string}, ${e.keterangan}` : `${e.payload.nomor_sep as string}, ${e.rs}, ${e.payload.procedure as string}`} />
            ))}
            {list.length > 0 && <Option active={choice === CUSTOM} onClick={() => pick(CUSTOM)} title="Tempel JSON sendiri" line="sunting permintaan JSON, lalu periksa; tidak disimpan" />}
          </section>

          <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
            <header className="flex items-center justify-between">
              <h2 className="text-[15px] font-semibold">Klaim terpilih</h2>
              <Segmented value={tab} onChange={setTab} options={[{ value: "ringkasan", label: "Ringkasan" }, { value: "json", label: "JSON permintaan" }]} />
            </header>
            {tab === "ringkasan" ? (
              parsed.ok && base ? <Summary claim={parsed.value} rs={base.rs} /> : <p className="text-[13px] text-merah">JSON tidak sah; buka tab JSON permintaan untuk memperbaikinya.</p>
            ) : (
              <>
                <JsonEditor value={text} baseline={choice === CUSTOM ? basePretty : undefined} readOnly={choice !== CUSTOM} onChange={(t) => setDraft(t)} />
                <div className="flex items-center justify-between text-xs">
                  {parsed.ok ? (
                    <span className="flex items-center gap-1.5 text-tinta-2">
                      <Icon name="circle-check" size={14} className="text-hijau" />
                      JSON sah; skema diperiksa server saat dikirim
                    </span>
                  ) : (
                    <span className="flex items-center gap-1.5 text-merah">
                      <Icon name="circle-x" size={14} />
                      JSON tidak sah: {parsed.error}
                    </span>
                  )}
                  {choice === CUSTOM && (
                    <span className="flex gap-3">
                      <button className="font-semibold text-biru" onClick={() => parsed.ok && setDraft(pretty(parsed.value))}>Format</button>
                      <button className="font-semibold text-biru" onClick={() => setDraft(null)}>Kembalikan contoh</button>
                    </span>
                  )}
                </div>
                {choice === CUSTOM && (
                  <div className="rounded-md bg-latar px-3 py-2.5">
                    <p className="text-[13px] font-semibold">{diff.length ? `${diff.length} perubahan dari contoh Bukti lengkap` : "Belum ada perubahan dari contoh Bukti lengkap"}</p>
                    {diff.slice(0, 6).map((d) => (
                      <p key={d} className="font-mono text-xs text-tinta-2">{d}</p>
                    ))}
                  </div>
                )}
              </>
            )}
          </section>

          <section className="flex flex-col gap-2.5 rounded-lg border border-garis bg-kartu p-4">
            <Button variant="primer" icon="send" className="justify-center" disabled={!parsed.ok || send.isPending} onClick={() => parsed.ok && send.mutate(parsed.value)}>
              {send.isPending ? "Memeriksa…" : "Periksa klaim"}
            </Button>
            <p className="font-mono text-xs text-tinta-2">POST /api/v1/klaim/periksa</p>
            <label className="flex cursor-pointer items-start gap-3 border-t border-garis pt-3">
              <input
                type="checkbox"
                role="switch"
                className="peer sr-only"
                checked={llm.data ? !llm.data.sakelar : false}
                onChange={(e) => toggleLlm.mutate(!e.target.checked)}
              />
              <span className="relative mt-0.5 h-5 w-9 shrink-0 rounded-full bg-garis transition-colors peer-checked:bg-biru peer-focus-visible:ring-2 peer-focus-visible:ring-biru">
                <span className={`absolute top-0.5 size-4 rounded-full bg-white shadow-sm transition-all ${llm.data && !llm.data.sakelar ? "left-[18px]" : "left-0.5"}`} />
              </span>
              <span className="flex flex-col">
                <span className="text-sm font-semibold">Matikan LLM lokal (uji cadangan)</span>
                <span className="text-xs text-tinta-2">
                  {llm.data && !llm.data.tersedia ? "Ollama tidak terjangkau; AI 2 memakai aturan kata kunci." : "AI 2 diganti aturan kata kunci; respons tetap keluar."}
                </span>
              </span>
            </label>
          </section>
        </div>

        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <p className="text-xs font-semibold tracking-[0.8px] text-redam uppercase">
              Hasil <span className="ml-1 font-normal tracking-normal normal-case">respons TAPAL</span>
            </p>
            {outcome && (
              <span className={`rounded-full border px-2.5 py-1 font-mono text-xs font-semibold ${outcome.kind === "ok" ? "border-garis bg-kartu text-tinta-2" : "border-merah/40 bg-[#FBEAEA] text-merah"}`}>
                {outcome.kind === "ok" ? `200 OK, ${outcome.ms} ms${rmeUrl && !rmeDone ? ", RME menyusul" : ""}` : `422, ${outcome.ms} ms`}
              </span>
            )}
          </div>

          {send.error && <section className="rounded-lg border border-garis bg-kartu"><ErrorState message={errorText(send.error)} /></section>}
          {!outcome && !send.error && (
            <section className="flex flex-col items-center gap-2 rounded-lg border border-dashed border-garis bg-kartu px-6 py-16 text-center">
              <Icon name="scan-search" size={22} className="text-redam" />
              <p className="text-[15px] font-semibold">Pilih contoh, lalu tekan Periksa klaim</p>
              <p className="max-w-md text-sm text-tinta-2">Permintaan dikirim ke API sungguhan. AI 1 menjawab dalam hitungan milidetik; AI 2 membaca RME dengan LLM lokal di laptop ini.</p>
            </section>
          )}

          {outcome?.kind === "invalid" && <Invalid issues={outcome.issues} />}

          {res && (
            <>
              <Steps res={res} rme={rmeDone} elapsed={elapsed} llmOn={llm.data?.aktif ?? true} />
              <ResultCard res={res} rme={rmeDone} />
              <ResponseJson res={res} rme={rmeDone} />
              {rmeDone?.status_sebelumnya && <Compare title="Dibanding respons awal" left={`Respons awal, ${res.waktu_proses_ms} ms`} right={`Setelah RME dibaca, ${seconds(rmeDone.durasi_ms ?? 0)}`}
                rows={[["Status", STATUS_TEXT[rmeDone.status_sebelumnya], STATUS_TEXT[rmeDone.status_klaim!]], ["Peluang didukung", prob(res.peluang_didukung_bukti), prob(res.peluang_didukung_bukti)],
                       ["Isi RME", "Sedang diproses", `${VERDICT_TEXT[rmeDone.verdict!]}, ${rmeDone.kutipan_terverifikasi} kutipan`]]} />}
              {choice === CUSTOM && original && finalStatus && <Compare title="Dibanding contoh asli" left="Contoh asli, Bukti lengkap" right="Setelah disunting"
                rows={[["Status", STATUS_TEXT[original.status], STATUS_TEXT[finalStatus]], ["Peluang didukung", prob(original.peluang_didukung_bukti), prob(res.peluang_didukung_bukti)],
                       ["Waktu proses", `${original.waktu_proses_ms} ms, RME menyusul`, rmeDone ? `${seconds(rmeDone.waktu_proses_ms ?? 0)}, RME selesai` : `${res.waktu_proses_ms} ms, RME menyusul`]]} />}
              <HonestNote>
                {choice === CUSTOM
                  ? "JSON sunting hanya untuk uji: tidak disimpan dan tidak masuk Jejak keputusan."
                  : finalStatus === "lolos_cepat"
                    ? "Lolos cepat tidak berarti bebas pemeriksaan: klaim tetap masuk analisis RS bulanan dan sampel acak audit."
                    : "Periksa manual bukan penolakan; klaim tetap dibayar bila buktinya cukup."}
              </HonestNote>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function Option({ active, onClick, title, line }: { active: boolean; onClick: () => void; title: string; line: string }) {
  return (
    <button onClick={onClick} role="radio" aria-checked={active} className={`flex items-center gap-3 rounded-lg border px-3 py-2 text-left ${active ? "border-biru bg-biru-muda/25 ring-1 ring-biru" : "border-garis hover:bg-latar"}`}>
      <span className={`grid size-5 shrink-0 place-items-center rounded-full border-2 ${active ? "border-biru" : "border-garis"}`}>{active && <span className="size-2.5 rounded-full bg-biru" />}</span>
      <span className="flex min-w-0 flex-col">
        <span className="text-sm font-semibold">{title}</span>
        <span className="truncate text-xs text-tinta-2">{line}</span>
      </span>
    </button>
  )
}

function Summary({ claim, rs }: { claim: Record<string, unknown>; rs: string }) {
  const procs = String(claim.procedure ?? "").split("#").filter(Boolean)
  const vent = procs.filter((p) => ["96.70", "96.71", "96.72"].includes(p))
  const tarif = (claim.tarif_rs ?? {}) as Record<string, number>
  const date = (v: unknown) => (typeof v === "string" ? v.slice(0, 10).split("-").reverse().join("-") : "tidak diisi")
  const rows: [string, React.ReactNode][] = [
    ["RS", rs],
    ["Kelas rawat", String(claim.kelas_rawat ?? "")],
    ["Tanggal", `${date(claim.tgl_masuk)} → ${date(claim.tgl_pulang)}, ICU ${claim.icu_los ?? 0} hari`],
    ["Diagnosis", String(claim.diagnosa ?? "").split("#").join(", ")],
    ["Prosedur", <span key="p" className="flex flex-wrap items-center gap-1.5">{vent.map((v) => <span key={v} className="rounded bg-biru-muda px-1.5 font-mono text-[13px] font-semibold text-biru-tua">{v}</span>)}<span className="text-tinta-2">{procs.filter((p) => !vent.includes(p)).join(", ") || "tanpa kode lain"}</span></span>],
    ["Ventilator", `${claim.ventilator_hour ?? 0} jam`],
    ["Sewa alat", rupiah(tarif.sewa_alat ?? 0)],
    ["Status pulang", ({ 1: "Sehat", 2: "Dirujuk", 3: "Atas permintaan sendiri", 4: "Meninggal", 5: "Lain-lain" } as Record<string, string>)[String(claim.discharge_status)] ?? "tidak diisi"],
  ]
  return (
    <dl className="grid grid-cols-[120px_1fr] gap-x-4 gap-y-2 text-[13px]">
      {rows.map(([k, v]) => (
        <div key={k} className="contents">
          <dt className="text-redam">{k}</dt>
          <dd className="font-semibold text-tinta">{v}</dd>
        </div>
      ))}
    </dl>
  )
}

function Steps({ res, rme, elapsed, llmOn }: { res: CheckResponse; rme: RmeLive | null; elapsed: number; llmOn: boolean }) {
  const rmeStep = res.langkah.find((s) => s.nama === "Baca RME")
  const steps = [
    ...res.langkah.filter((s) => s.nama !== "Baca RME").map((s) => ({ name: s.nama, machine: s.mesin as Machine, time: `${s.waktu_ms} ms`, state: "selesai" as const })),
    ...(rmeStep
      ? [{ name: rme?.tahap === "gagal" ? "Baca RME gagal" : rme?.sumber === "aturan" ? "Aturan cadangan" : "Baca RME", machine: "AI 2" as Machine,
           time: rme ? (rme.tahap === "gagal" ? "gagal" : rme.sumber === "aturan" ? `${rme.durasi_ms} ms` : seconds(rme.durasi_ms ?? 0)) : `${elapsed} dtk`,
           state: rme ? ("selesai" as const) : ("berjalan" as const) }]
      : res.rme.status === "dilewati" ? [{ name: "Baca RME", machine: "AI 2" as Machine, time: "dilewati", state: "dilewati" as const }] : []),
    { name: "Respons", machine: null, time: "200", state: "selesai" as const },
  ]
  const reason =
    res.status === "lolos_cepat"
      ? `Jalur dipilih: lolos cepat, karena peluang didukung ${prob(res.peluang_didukung_bukti)} di atas ambang dan lapis cepat RME bersih.`
      : res.rme.status === "dilewati"
        ? "Klaim di luar populasi garis ventilator; AI 2 tidak membaca RME."
        : `Jalur dipilih: periksa manual, karena ${res.alasan_rinci?.some((a) => a.mesin === "AI 2") ? "lapis cepat RME menahan" : "peluang didukung di bawah ambang jalur cepat"}.`
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
      <header className="flex items-center justify-between">
        <h2 className="text-[15px] font-semibold">Langkah pipa</h2>
        <span className="text-xs text-redam">waktu per langkah</span>
      </header>
      <ol className="relative grid" style={{ gridTemplateColumns: `repeat(${steps.length}, minmax(0, 1fr))` }}>
        <span className="absolute top-3 right-[8%] left-[8%] h-0.5 bg-biru" aria-hidden />
        {steps.map((s) => (
          <li key={s.name} className="relative flex flex-col items-center gap-1.5 text-center">
            <span className={`grid size-6 place-items-center rounded-full ${s.state === "selesai" ? "bg-biru text-white" : s.state === "dilewati" ? "border-2 border-garis bg-kartu text-redam" : "border-2 border-biru bg-kartu text-biru"}`}>
              <Icon name={s.state === "selesai" ? "check" : s.state === "dilewati" ? "minus" : "loader"} size={14} className={s.state === "berjalan" ? "animate-spin" : ""} />
            </span>
            <span className="text-xs font-semibold">{s.name}</span>
            <span className="flex items-center gap-1.5">
              {s.machine && <MachineLabel kind={s.machine} />}
              <span className="font-mono text-xs text-tinta-2">{s.time}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="flex items-start gap-2 rounded-md bg-latar px-3 py-2 text-xs text-tinta-2">
        <Icon name="git-branch" size={14} className="mt-px text-tinta-2" />
        <span>
          {reason}{" "}
          {rmeStep && !rme && (llmOn ? `Membaca RME, sedang diproses (batas tunggu LLM 120 detik sebelum aturan cadangan dipakai).` : "LLM lokal dimatikan; AI 2 memakai aturan cadangan.")}
          {rme?.status_sebelumnya && " Hasil AI 2 mengubah status."}
        </span>
      </p>
    </section>
  )
}

const BANNER: Record<CheckResponse["status"], { tone: string; icon: IconName; body: (r: CheckResponse) => string }> = {
  lolos_cepat: { tone: "border-[#BFD7F6] bg-[#E6F0FC] text-biru-tua", icon: "fast-forward", body: (r) => `Peluang didukung ${prob(r.peluang_didukung_bukti)}. Dibayar lewat jalur biasa.` },
  periksa_manual: { tone: "border-[#F1D58E] bg-[#FDF4DC] text-[#6B4A00]", icon: "file-search", body: () => "Tidak lewat jalur cepat. Klaim masuk antrean verifikator dengan bukti terlampir." },
  didukung_rme: { tone: "border-[#BFD7F6] bg-[#E6F0FC] text-biru-tua", icon: "file-check", body: () => "Bukti di klaim kurang, tetapi RME mendukung. Dibayar lewat jalur biasa." },
}

function ResultCard({ res, rme }: { res: CheckResponse; rme: RmeLive | null }) {
  const status = rme?.status_klaim ?? res.status
  const b = BANNER[status]
  const title = status === "periksa_manual" && rme?.verdict === "tidak_mendukung" && rme.status_sebelumnya ? "Periksa manual, RME tidak mendukung" : STATUS_TEXT[status]
  const body = rme?.status_sebelumnya === "lolos_cepat" ? "Status awal lolos cepat dicabut: data klaim tampak lengkap, tetapi RME tidak mendukung." : b.body(res)
  const pctl = res.alasan_rinci?.filter((a) => a.mesin === "AI 1").length ?? 0
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
      <div className={`flex items-center gap-3 rounded-lg border px-4 py-3 ${b.tone}`}>
        <span className="grid size-9 place-items-center rounded-full bg-white/70">
          <Icon name={b.icon} size={18} />
        </span>
        <span className="flex flex-col">
          <span className="font-display text-lg font-bold">{title}</span>
          <span className="text-[13px]">{body}</span>
        </span>
      </div>
      <div className="grid grid-cols-3 gap-3">
        <Mini title="Peluang didukung" label="AI 1" value={prob(res.peluang_didukung_bukti)} note={pctl ? `${pctl} alasan dari model` : "tanpa alasan menonjol"} />
        <Mini title="Isi RME" label="AI 2"
              value={rme ? (rme.tahap === "gagal" ? "Gagal dibaca" : VERDICT_TEXT[rme.verdict!]) : res.rme.status === "dilewati" ? "Dilewati" : "Sedang dibaca"}
              note={rme ? (rme.tahap === "gagal" ? "periksa dokumen langsung" : `${rme.sumber === "llm_lokal" ? "LLM lokal" : "aturan cadangan"}, kutipan cocok ${rme.kutipan_terverifikasi ?? 0}`)
                        : res.rme.status === "dilewati" ? "di luar populasi" : "hasil menyusul lewat GET"} />
        <Mini title="Selisih dipertaruhkan" label="Kode" value={signedRupiah(res.selisih_tarif_dipertaruhkan)} note="tarif diklaim vs tanpa kode pemicu" />
      </div>
      {res.alasan.length > 0 && (
        <ul className="flex flex-col gap-1 border-t border-garis pt-2.5">
          {(res.alasan_rinci ?? []).slice(0, 6).map((a) => (
            <li key={a.teks} className="flex items-center gap-2 text-xs text-tinta-2">
              <Icon name={a.arah === "naik" ? "arrow-up" : a.arah === "turun" ? "arrow-down" : "info"} size={13} className={a.arah === "turun" ? "text-biru" : "text-tinta-2"} />
              <span className="flex-1">{a.teks}</span>
              <MachineLabel kind={(a.mesin ?? "AI 1") as Machine} />
            </li>
          ))}
        </ul>
      )}
      {rme?.alasan && rme.alasan.length > 0 && (
        <p className="text-xs text-tinta-2">
          <span className="font-semibold text-tinta">Alasan AI 2: </span>
          {rme.alasan.slice(0, 3).join("; ")}
        </p>
      )}
    </section>
  )
}

function Mini({ title, label, value, note }: { title: string; label: Machine; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-garis px-3 py-2.5">
      <span className="flex items-center justify-between text-xs text-tinta-2">
        {title}
        <MachineLabel kind={label} />
      </span>
      <span className="font-display text-xl font-bold">{value}</span>
      <span className="text-xs text-tinta-2">{note}</span>
    </div>
  )
}

function ResponseJson({ res, rme }: { res: CheckResponse; rme: RmeLive | null }) {
  const [open, setOpen] = useState(true)
  const body = rme
    ? { ...res, status: rme.status_klaim, ...(rme.status_sebelumnya ? { status_sebelumnya: rme.status_sebelumnya } : {}),
        rme: { status: "selesai", verdict: rme.verdict, sumber: rme.sumber, kutipan_terverifikasi: rme.kutipan_terverifikasi }, waktu_proses_ms: rme.waktu_proses_ms }
    : res
  const { langkah: _steps, alasan_rinci: _detail, ...shown } = body as CheckResponse
  void _steps
  void _detail
  const text = JSON.stringify(shown, null, 2)
  return (
    <section className="overflow-hidden rounded-lg border border-garis bg-kartu">
      <header className="flex items-center gap-2 px-4 py-2.5">
        <button onClick={() => setOpen((v) => !v)} className="flex items-center gap-2 text-sm font-semibold" aria-expanded={open}>
          <Icon name={open ? "chevron-down" : "chevron-right"} size={14} className="text-tinta-2" />
          Respons JSON
        </button>
        <span className="font-mono text-xs text-redam">application/json</span>
        <span className="flex-1" />
        <button onClick={() => navigator.clipboard.writeText(text)} className="flex items-center gap-1.5 text-xs font-semibold text-biru">
          <Icon name="copy" size={13} />
          Salin
        </button>
      </header>
      {open && <pre className="max-h-72 overflow-auto border-t border-garis bg-kertas px-4 py-3 font-mono text-xs leading-5 text-tinta">{text}</pre>}
    </section>
  )
}

function Compare({ title, left, right, rows }: { title: string; left: string; right: string; rows: [string, string, string][] }) {
  return (
    <section className="rounded-lg border border-garis bg-kartu p-4">
      <h2 className="mb-2 text-sm font-semibold">{title}</h2>
      <table className="w-full text-[13px]">
        <thead>
          <tr className="border-b border-garis text-xs text-redam">
            <th className="py-1.5 text-left font-normal" />
            <th className="py-1.5 text-left font-normal">{left}</th>
            <th className="py-1.5 text-left font-normal">{right}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([k, a, b]) => (
            <tr key={k} className="border-b border-garis last:border-b-0">
              <td className="py-2 text-tinta-2">{k}</td>
              <td className="py-2">{a}</td>
              <td className="py-2 font-semibold">{b}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  )
}

function Invalid({ issues }: { issues: ValidationIssue[] }) {
  return (
    <section className="flex flex-col gap-3 rounded-lg border border-garis bg-kartu p-4">
      <div className="flex items-center gap-3 rounded-lg border border-merah/30 bg-[#FBEAEA] px-4 py-3 text-merah">
        <span className="grid size-9 place-items-center rounded-full bg-white/70">
          <Icon name="circle-x" size={18} />
        </span>
        <span className="flex flex-col">
          <span className="font-display text-lg font-bold">Data tidak valid (422)</span>
          <span className="text-[13px]">Data ditolak di pintu masuk; tidak ada yang diproses.</span>
        </span>
      </div>
      <ul className="flex flex-col gap-2">
        {issues.map((i) => (
          <li key={i.kolom + i.pesan} className="flex items-center gap-2.5 rounded-md border border-garis px-3 py-2 text-[13px]">
            <Icon name="x" size={14} className="text-merah" />
            <code className="rounded bg-latar px-1.5 font-mono text-xs font-semibold">{i.kolom}</code>
            <span className="flex-1">{i.pesan}</span>
            <span className="font-mono text-xs text-redam">diterima {JSON.stringify(i.nilai_diterima)}</span>
          </li>
        ))}
      </ul>
      <p className="text-xs text-tinta-2">{`${num(issues.length)} kolom gagal validasi skema; AI 1 dan AI 2 tidak dijalankan.`}</p>
    </section>
  )
}
