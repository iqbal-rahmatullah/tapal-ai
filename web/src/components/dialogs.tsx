import { useEffect, useRef, useState, type ReactNode } from "react"
import { errorText } from "../utils/api"
import { Button, Icon, MachineLabel } from "./ui"

export function Modal({ title, onClose, children, width = 560 }: { title: ReactNode; onClose: () => void; children: ReactNode; width?: number }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-40 grid place-items-center bg-tinta/40 p-6" onMouseDown={onClose}>
      <section
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        className="flex max-h-full flex-col gap-4 overflow-y-auto rounded-lg bg-kartu p-6 shadow-[0_8px_24px_rgba(11,11,11,0.15)]"
        style={{ width }}
      >
        <header className="flex items-center justify-between gap-3">
          <h2 className="font-display text-lg font-bold text-tinta">{title}</h2>
          <button onClick={onClose} aria-label="Tutup" className="rounded-md p-1 text-tinta-2 hover:bg-latar">
            <Icon name="x" size={18} />
          </button>
        </header>
        {children}
      </section>
    </div>
  )
}

export function NoteDialog({ title, subject, confirm, pending, error, onSubmit, onClose }: { title: string; subject: string; confirm: string; pending: boolean; error: unknown; onSubmit: (note: string) => void; onClose: () => void }) {
  const [note, setNote] = useState("")
  const ref = useRef<HTMLTextAreaElement>(null)
  useEffect(() => ref.current?.focus(), [])
  return (
    <Modal title={title} onClose={onClose} width={520}>
      <p className="flex items-center gap-2 text-sm text-tinta-2">
        <MachineLabel kind="Manusia" />
        Keputusan atas <span className="font-mono font-semibold text-tinta">{subject}</span> dicatat di Jejak keputusan bersama dasar AI dan sidiknya.
      </p>
      <label className="flex flex-col gap-1.5 text-[13px] font-semibold text-tinta">
        Catatan (wajib)
        <textarea
          ref={ref}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          rows={3}
          placeholder="Alasan keputusan"
          className="rounded-md border border-garis px-3 py-2 text-sm font-normal outline-hidden focus:border-biru"
        />
      </label>
      {error !== null && error !== undefined && (
        <p role="alert" className="flex items-center gap-2 text-sm text-merah">
          <Icon name="circle-x" size={16} />
          Keputusan belum tercatat. {errorText(error)}
        </p>
      )}
      <footer className="flex justify-end gap-2">
        <Button onClick={onClose}>Batal</Button>
        <Button variant="primer" icon="check" disabled={!note.trim() || pending} onClick={() => onSubmit(note.trim())}>
          {pending ? "Mencatat…" : confirm}
        </Button>
      </footer>
    </Modal>
  )
}

export function Drawer({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose()
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [onClose])
  return (
    <div className="fixed inset-0 z-40 bg-tinta/30" onMouseDown={onClose}>
      <aside
        role="dialog"
        aria-modal="true"
        onMouseDown={(e) => e.stopPropagation()}
        className="absolute top-0 right-0 flex h-full w-[480px] flex-col gap-4 overflow-y-auto bg-kartu px-6 py-[22px] shadow-[-8px_0_24px_rgba(11,11,11,0.15)]"
      >
        {children}
      </aside>
    </div>
  )
}
