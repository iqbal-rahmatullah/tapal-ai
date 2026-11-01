import { json, jsonParseLinter } from "@codemirror/lang-json"
import { linter } from "@codemirror/lint"
import { Annotation, Compartment, EditorState, RangeSetBuilder, StateEffect, StateField } from "@codemirror/state"
import { Decoration, EditorView, type DecorationSet } from "@codemirror/view"
import { basicSetup } from "codemirror"
import { useEffect, useRef } from "react"

const setBaseline = StateEffect.define<string[]>()
// Marks updates that come from the value prop, so only the user's own typing reaches onChange.
const external = Annotation.define<boolean>()

const changedLines = StateField.define<{ base: string[]; deco: DecorationSet }>({
  create: () => ({ base: [], deco: Decoration.none }),
  update(value, tr) {
    let base = value.base
    for (const e of tr.effects) if (e.is(setBaseline)) base = e.value
    if (!tr.docChanged && base === value.base) return value
    const b = new RangeSetBuilder<Decoration>()
    const doc = tr.state.doc
    for (let i = 1; i <= doc.lines; i++) {
      const line = doc.line(i)
      if (base.length && line.text !== base[i - 1]) b.add(line.from, line.from, Decoration.line({ class: "cm-diubah" }))
    }
    return { base, deco: b.finish() }
  },
  provide: (f) => EditorView.decorations.from(f, (v) => v.deco),
})

const theme = EditorView.theme({
  "&": { fontSize: "13px", backgroundColor: "#FCFCFB", height: "100%" },
  ".cm-content": { fontFamily: "JetBrains Mono, monospace" },
  ".cm-gutters": { backgroundColor: "#FCFCFB", color: "#898781", border: "none" },
  ".cm-diubah": { backgroundColor: "rgba(205, 226, 251, 0.45)", boxShadow: "inset 3px 0 0 #2A78D6" },
  "&.cm-focused": { outline: "none" },
})

export function JsonEditor({ value, baseline, readOnly, onChange, height = 248 }: { value: string; baseline?: string; readOnly: boolean; onChange?: (text: string) => void; height?: number }) {
  const host = useRef<HTMLDivElement>(null)
  const view = useRef<EditorView | null>(null)
  const editable = useRef(new Compartment())
  const latest = useRef(onChange)
  useEffect(() => {
    latest.current = onChange
  })

  useEffect(() => {
    if (!host.current) return
    const v = new EditorView({
      parent: host.current,
      state: EditorState.create({
        doc: value,
        extensions: [
          basicSetup,
          json(),
          linter(jsonParseLinter()),
          theme,
          changedLines,
          editable.current.of([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]),
          EditorView.updateListener.of((u) => {
            if (u.docChanged && !u.transactions.some((t) => t.annotation(external))) latest.current?.(u.state.doc.toString())
          }),
        ],
      }),
    })
    view.current = v
    return () => {
      v.destroy()
      view.current = null
    }
  }, [])

  useEffect(() => {
    const v = view.current
    if (v && v.state.doc.toString() !== value) v.dispatch({ changes: { from: 0, to: v.state.doc.length, insert: value }, annotations: external.of(true) })
  }, [value])

  useEffect(() => {
    view.current?.dispatch({ effects: setBaseline.of(baseline ? baseline.split("\n") : []) })
  }, [baseline])

  useEffect(() => {
    view.current?.dispatch({ effects: editable.current.reconfigure([EditorState.readOnly.of(readOnly), EditorView.editable.of(!readOnly)]) })
  }, [readOnly])

  return <div ref={host} style={{ height }} className="overflow-hidden rounded-md border border-garis" aria-label="JSON permintaan" />
}
