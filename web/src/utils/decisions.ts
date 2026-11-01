import { useMutation, useQueryClient } from "@tanstack/react-query"
import { postJson } from "./api"
import { showToast } from "./toast"

export type DecisionKind =
  | "setujui"
  | "minta_klarifikasi"
  | "ajukan_audit"
  | "masukkan_rencana_audit"
  | "setujui_audit"
  | "susun_laporan"
  | "setujui_laporan"
  | "kirim_laporan"
  | "draf_surat"
  | "aktifkan_garis"
  | "tolak_garis"
  | "koreksi"

export type DecisionInput = {
  peran?: "verifikator" | "kepala_cabang" | "admin"
  objek_jenis: "klaim" | "rs" | "laporan" | "garis"
  objek_id: string
  keputusan: DecisionKind
  catatan: string
  dasar_ai?: Record<string, unknown>
  koreksi_untuk?: number | null
  bukti?: Record<string, unknown>
}

export type DecisionRow = Required<Omit<DecisionInput, "koreksi_untuk">> & {
  id: number
  waktu: string
  koreksi_untuk: number | null
  versi_model: string
  sidik_sebelum: string
  sidik: string
}

export const DECISION_LABEL: Record<DecisionKind, string> = {
  setujui: "Setujui",
  minta_klarifikasi: "Minta klarifikasi RS",
  ajukan_audit: "Ajukan audit",
  masukkan_rencana_audit: "Masukkan ke rencana audit",
  setujui_audit: "Setujui audit",
  susun_laporan: "Susun draf laporan",
  setujui_laporan: "Disetujui untuk klarifikasi",
  kirim_laporan: "Kirim ke kepala cabang",
  draf_surat: "Draf surat klarifikasi",
  aktifkan_garis: "Setujui jadi garis aktif",
  tolak_garis: "Tolak garis",
  koreksi: "Koreksi catatan",
}

export function useDecision(onDone?: (row: DecisionRow) => void) {
  const client = useQueryClient()
  return useMutation({
    mutationFn: (body: DecisionInput) => postJson<DecisionRow>("/keputusan", body),
    onSuccess: (row) => {
      client.invalidateQueries({ queryKey: ["/keputusan"] })
      showToast("Keputusan dicatat di Jejak keputusan")
      onDone?.(row)
    },
  })
}
