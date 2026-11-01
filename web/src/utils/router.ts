import { useSyncExternalStore } from "react"

export type Route =
  | { page: "antrean" }
  | { page: "rs"; kode: string }
  | { page: "klaim"; sep: string }
  | { page: "cek" }
  | { page: "pemindai" }
  | { page: "audit" }
  | { page: "laporan" }
  | { page: "jejak" }
  | { page: "cetak" }
  | { page: "tidak_ada"; path: string }

export function parse(hash: string): Route {
  const [first = "", second = ""] = hash.replace(/^#\/?/, "").split("/").map(decodeURIComponent)
  switch (first) {
    case "":
    case "antrean":
      return { page: "antrean" }
    case "rs":
      return second ? { page: "rs", kode: second } : { page: "antrean" }
    case "klaim":
      return second ? { page: "klaim", sep: second } : { page: "antrean" }
    case "cek":
    case "pemindai":
    case "audit":
    case "laporan":
    case "jejak":
    case "cetak":
      return { page: first }
    default:
      return { page: "tidak_ada", path: hash }
  }
}

function subscribe(notify: () => void) {
  window.addEventListener("hashchange", notify)
  return () => window.removeEventListener("hashchange", notify)
}

export function useRoute(): Route {
  return parse(useSyncExternalStore(subscribe, () => window.location.hash))
}

export function href(...parts: string[]): string {
  return "#/" + parts.map(encodeURIComponent).join("/")
}

export function go(...parts: string[]) {
  window.location.hash = href(...parts)
}
