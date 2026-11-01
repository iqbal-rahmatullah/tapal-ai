import { rupiah } from "../utils/format"
import type { Mode, ReportData, Story } from "../types"
import { Logo } from "./Shell"
import { MachineLabel, OdblNote, Skeleton } from "./ui"

const MODE: Record<Mode, string> = { fiktif: "Ventilasi fiktif", diperpanjang: "Diperpanjang ≥96 jam", rme_meragukan: "RME meragukan" }

function Tokens({ story }: { story: Story }) {
  return (
    <>
      {story.segmen.map((s, i) =>
        s.token ? (
          <span key={i} title={s.asal ?? ""} className="mx-px rounded-[4px] bg-biru-muda px-[5px] py-px font-mono text-[12px] font-semibold text-biru-tua">{s.teks}</span>
        ) : (
          <span key={i}>{s.teks}</span>
        ),
      )}
    </>
  )
}

export function ReportPage({ d, story, extra }: { d: ReportData; story: Story | null; extra?: { kode: string; story: Story } | null }) {
  return (
    <article className="flex h-[1122px] w-[794px] shrink-0 overflow-hidden flex-col gap-3 bg-kertas px-14 pt-11 pb-6 text-tinta shadow-kartu print:shadow-none">
      <header className="flex items-start justify-between">
        <Logo ink className="h-9 w-[137px]" />
        <div className="text-right text-xs">
          <p className="font-semibold">{d.kepala.wilayah}</p>
          <p className="text-tinta-2">{d.kepala.dianalisis}</p>
        </div>
      </header>
      <div>
        <h1 className="font-display text-[22px] font-bold">{d.kepala.judul}</h1>
        <p className="text-xs text-tinta-2">{d.kepala.sub}</p>
      </div>
      <hr className="border-t-2 border-tinta" />
      <div className="grid grid-cols-3 gap-3">
        {d.angka.map((a) => (
          <div key={a.label} className="rounded-lg border border-garis bg-kartu px-3 py-2.5">
            <p className="font-display text-xl font-bold">{a.nilai}</p>
            <p className="text-xs font-semibold">{a.label}</p>
            <p className="text-xs text-tinta-2">{a.sub}</p>
          </div>
        ))}
      </div>
      <h2 className="text-sm font-semibold">Lima RS teratas</h2>
      <table className="w-full text-xs">
        <thead>
          <tr className="border-b border-tinta text-left text-redam uppercase">
            {["RS", "Modus", "Diakui vs wajar", "Perkiraan (rentang)", "Bukti utama", "Tindak lanjut"].map((h) => <th key={h} className="py-1.5 pr-2 font-semibold tracking-[0.4px]">{h}</th>)}
          </tr>
        </thead>
        <tbody>
          {d.rs.map((r) => (
            <tr key={r.kode_rs} className="border-b border-garis align-top">
              <td className="py-1.5 pr-2 font-semibold whitespace-nowrap">{r.kode_rs}</td>
              <td className="pr-2">{MODE[r.modus]}</td>
              <td className="pr-2">{r.diakui}</td>
              <td className="pr-2"><b>{r.perkiraan}</b><br /><span className="text-tinta-2">{r.rentang}</span></td>
              <td className="pr-2">{r.bukti}</td>
              <td className="font-semibold">{r.tindak}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <h2 className="flex items-center gap-2 text-sm font-semibold">
        Narasi
        {story && (story.sumber === "llm_lokal" ? <MachineLabel kind="LLM narasi" /> : <span className="rounded-full border border-garis px-2 py-0.5 text-xs text-tinta-2">Templat</span>)}
      </h2>
      {story ? <p className="text-[13px] leading-6"><Tokens story={story} /></p> : <div className="flex flex-col gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-4 w-full" />)}</div>}
      {extra && (
        <p className="border-l-2 border-biru pl-3 text-[13px] leading-6">
          <span className="mb-0.5 block text-xs font-semibold text-tinta-2">{`Dari Ringkas kasus ${extra.kode}`}</span>
          <Tokens story={extra.story} />
        </p>
      )}
      <p className="text-xs text-redam">Angka dalam kotak biru disisipkan kode dari hasil AI 1, AI 2, dan tarif Permenkes 3/2023; LLM tidak menulis angka.</p>
      <h2 className="text-sm font-semibold">Lampiran, klaim teratas per RS <span className="text-xs font-normal text-tinta-2">{d.ket_lampiran}</span></h2>
      {/* Attachment rows give way first, so the sources, licence notice, and footer always stay on the page. */}
      <div className="min-h-0 shrink overflow-hidden">
        <table className="w-full text-xs">
          <thead>
            <tr className="border-b border-tinta text-left text-redam uppercase">
              <th className="py-1 font-semibold">Nomor SEP</th>
              <th className="font-semibold">RS</th>
              <th className="pr-4 text-right font-semibold">Selisih tarif</th>
              <th className="font-semibold">Status RME</th>
            </tr>
          </thead>
          <tbody>
            {d.lampiran.map(([sep, rs, delta, status]) => (
              <tr key={sep} className="border-b border-garis">
                <td className="py-1 font-mono whitespace-nowrap">{sep}</td>
                <td className="font-semibold whitespace-nowrap">{rs}</td>
                <td className="pr-4 text-right whitespace-nowrap">{rupiah(delta)}</td>
                <td>{status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <span className="flex-1" />
      <div className="text-xs text-tinta-2">
        <p className="font-semibold tracking-[0.6px] text-redam uppercase">Sumber dan versi</p>
        <p>{`${d.sumber}; sidik dokumen ${d.sidik_dokumen}`}</p>
        <OdblNote print className="mt-0.5" />
      </div>
      <footer className="flex items-start justify-between gap-6 border-t-2 border-tinta pt-2 text-xs">
        <p className="font-semibold">{d.kaki}</p>
        <p className="shrink-0 text-redam">Halaman 1 dari 1</p>
      </footer>
    </article>
  )
}
