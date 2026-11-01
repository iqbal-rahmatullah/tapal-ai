const id = (digits: number) => new Intl.NumberFormat("id-ID", { minimumFractionDigits: digits, maximumFractionDigits: digits })

export function num(x: number, digits = 0): string {
  return id(digits).format(x)
}

export function rupiah(x: number): string {
  return (x < 0 ? "−Rp" : "Rp") + id(0).format(Math.abs(Math.round(x)))
}

export function signedRupiah(x: number): string {
  return (x >= 0 ? "+" : "") + rupiah(x)
}

export function miliar(x: number, digits = 2): string {
  return `Rp${num(x / 1e9, digits)} miliar`
}

export function juta(x: number, digits = 0): string {
  return `Rp${num(x / 1e6, digits)} juta`
}

export function range(lo: number, hi: number, digits = 2, scale = 1e9): string {
  return `${num(lo / scale, digits)}–${num(hi / scale, digits)}`
}

export function prob(p: number): string {
  return num(p, 2)
}

export function seconds(ms: number): string {
  return `${num(ms / 1000, 1)} dtk`
}

export function dateTime(iso: string): string {
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, "0")
  return `${pad(d.getDate())}-${pad(d.getMonth() + 1)}-${d.getFullYear()} ${pad(d.getHours())}.${pad(d.getMinutes())}`
}

export function qText(q: number): string {
  return q < 0.001 ? "q < 0,001" : `q = ${num(q, q < 0.01 ? 3 : 2)}`
}
