export function downloadCsv(filename: string, header: string[], rows: (string | number | null)[][]) {
  const cell = (v: string | number | null) => {
    const raw = v === null ? "" : String(v)
    // Security: a cell starting with = + - @ tab or CR would run as a spreadsheet formula, so it is prefixed with a quote.
    const s = /^[=+\-@\t\r]/.test(raw) ? `'${raw}` : raw
    return /[",\n;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
  }
  // The BOM lets spreadsheet apps read Indonesian text as UTF-8.
  const text = "﻿" + [header, ...rows].map((r) => r.map(cell).join(",")).join("\n")
  const url = URL.createObjectURL(new Blob([text], { type: "text/csv;charset=utf-8" }))
  const a = Object.assign(document.createElement("a"), { href: url, download: filename })
  a.click()
  URL.revokeObjectURL(url)
}
