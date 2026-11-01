export type Machine = "AI 1" | "AI 2" | "AI 3" | "AI 4" | "Statistik" | "Kode" | "LLM narasi" | "Manusia" | "Admin"
export type Mode = "fiktif" | "diperpanjang" | "rme_meragukan"
export type HandlingStatus = "baru" | "diklarifikasi" | "diaudit" | "selesai"
export type Confidence = "kuat" | "sedang" | "lemah" | "pola_kuat"

// bagian_contoh names the parts that are still design samples; the badge shows only when it is non-empty or the whole page is a sample.
export type DataSource = { sumber_data: "contoh_desain" | "mesin" | "mesin_dev"; bagian_contoh?: string[] }

export type FlaggedHospital = {
  kode_rs: string
  kelas: "A" | "B" | "C" | "D"
  kepemilikan: "Pemerintah" | "Swasta"
  regional: number
  mesin_penanda: "AI 1" | "AI 2"
  modus: Mode
  diakui: number | null
  wajar: number | null
  wajar_bawah: number | null
  wajar_atas: number | null
  q: number | null
  keyakinan: Confidence
  keterangan_keyakinan: string
  rupiah: number
  rupiah_bawah: number | null
  rupiah_atas: number | null
  n_klaim_dipertaruhkan: number | null
  status_penanganan: HandlingStatus
}

export type Queue = DataSource & {
  periode: { penilaian: string; klaim_diperiksa: string; diperbarui: string }
  ringkasan: {
    n_rs: number
    n_ditandai: number
    per_mesin: Record<string, number>
    total_rupiah: number
    total_bawah: number
    total_atas: number
    menunggu_rme: number
    klaim_desember?: number
    audit_kapasitas: number
    audit_terpakai: number
  }
  rs: FlaggedHospital[]
  urutan_keyakinan: string[]
  n_data_tidak_cukup: number
  data_tidak_cukup: { kode_rs: string; kelas: string; n_layak: number }[]
}

export type Step = { nama: string; mesin: string; waktu_ms: number | null }

export type ValidationIssue = { kolom: string; pesan: string; nilai_diterima: unknown }

export type RmeResult = {
  status: "diproses" | "selesai" | "dilewati"
  hasil?: string | null
  verdict?: "mendukung" | "tidak_mendukung" | "tidak_dapat_disimpulkan" | null
  sumber?: "llm_lokal" | "aturan" | null
  kutipan_terverifikasi?: number | null
}

export type CheckResponse = {
  nomor_sep: string
  status: "lolos_cepat" | "periksa_manual" | "didukung_rme"
  status_sebelumnya?: "lolos_cepat" | "periksa_manual" | "didukung_rme" | null
  peluang_didukung_bukti: number
  alasan: string[]
  alasan_rinci?: { teks: string; arah: "naik" | "turun" | null; mesin: string }[]
  peluang_panjang?: number | null
  selisih_tarif_dipertaruhkan: number
  rme: RmeResult
  versi_model: string
  waktu_proses_ms: number
  langkah: Step[]
}

export type ProfileClaim = {
  nomor_sep: string
  tanggal: string
  diagnosis: string
  prosedur: string
  jam: number
  peluang: number
  alasan: string[]
  selisih_tarif: number
  status_rme: "tidak_mendukung" | "tidak_dapat_disimpulkan" | "belum_dibaca" | "asal_meragukan" | "mendukung"
}

export type ProfileChart =
  | { jenis: "peluang"; judul: string; label: Machine[]; seri: string[]; temuan: string; rs: number[]; lain: number[] }
  | { jenis: "pembanding"; judul: string; label: Machine[]; temuan: string; rs: { kode: string; rasio: number }; lain: { rasio: number; y: number }[]; rentang_wajar: [number, number]; domain?: [number, number] }
  | { jenis: "jam"; judul: string; label: Machine[]; seri: string[]; temuan: string; awal: number; lebar: number; rs: number[]; lain: number[]; garis_tarif: number; plasebo: number[] }
  | { jenis: "waktu_tulis"; judul: string; label: Machine[]; seri: string[]; temuan: string; bulan: string[]; lain: { hari: number; y: number }[]; gelombang: { hari: number; tanggal: string; jam: string; n: number }[] }
  | { jenis: "kemiripan"; judul: string; label: Machine[]; temuan: string; n_pasien: number; n_kembar: number; median_kembar: number; keterangan: string }

export type Profile = DataSource & {
  kode_rs: string
  mesin_penanda?: "AI 1" | "AI 2"
  kelas: string
  kepemilikan: string
  regional: number
  modus: Mode
  keyakinan: Confidence
  keterangan_keyakinan: string
  status_penanganan: HandlingStatus
  ringkas_data: string
  kartu_diakui: { label: Machine[]; diakui: number; diakui_teks: string; wajar: number; wajar_bawah: number; wajar_atas: number; kelebihan_teks: string | null; catatan: string; catatan_jujur?: string }
  kartu_rupiah: { judul: string; nilai: number; bawah: number | null; atas: number | null; skala: number | null; subjudul?: string; rincian: string; catatan?: string }
  kartu_rme: { judul: string; hitungan: [string, number][]; status: [string, string][] }
  grafik_kiri: ProfileChart
  grafik_kanan: ProfileChart
  klaim_judul: string
  klaim_keterangan: string
  klaim_total: number
  klaim: ProfileClaim[]
}

export type ShortProfile = DataSource & FlaggedHospital & { hanya_ringkas: true }

export type Summary = {
  kode_rs: string
  sumber: "llm_lokal" | "aturan"
  durasi_ms: number
  segmen: { teks: string; token: string | null; asal: string | null }[]
  asal_angka: { angka: string; asal: string; label: Machine[] }[]
  catatan: string[]
  sumber_data: string
}

export type LlmState = { aktif: boolean; sakelar: boolean; tersedia: boolean; model: string }

export type RmeDoc = { id: string; label: string; judul: string; teks: string; sorot: string[] }
export type RmeQuote = { sebelum: string; sorot: string; sesudah: string; dokumen: string; cocok: boolean }

export type ClaimRme = {
  status: "selesai" | "diproses"
  tahap?: string
  jenis: "baca" | "aturan" | "asal_meragukan" | "tidak_dapat_disimpulkan" | "fisiologi"
  sumber: "llm_lokal" | "aturan"
  durasi_ms: number
  dokumen: RmeDoc[]
  dokumen_aktif?: string
  hasil: { alat?: string[]; baris?: [string, string][]; verdict: string; verdict_jenis: string; alasan?: string; aturan?: string }
  kutipan?: RmeQuote[]
  kutipan_ringkas?: string | null
  kutipan_semua_cocok?: boolean
  cek?: [string, string][]
  kata?: [string, [string, number][]][]
  jam?: string
  peringatan_aturan?: string
  kemiripan?: { judul: string; pasangan: { sep: string; pasien: string; teks: string; beda: string }[]; catatan: string }
  jejak?: { judul: string; layanan: string; tulis: string; catatan: string }
  asersi?: { ringkas: string; sama: boolean; sebutan: [string, string, string, string][]; kaki: string }
  fisiologi?: { ringkas: string; judul: string; per_jam: number[]; jam_tertulis: [number, number]; ambang: number; hari: [string, number][]; catatan: string; kaki: string; pita_teks?: string } | null
  verdict_akhir?: string
  catatan_sumber?: string
  tombol_utama: "minta_klarifikasi" | "ajukan_audit" | "setujui"
  sumber_data: string
}

export type ClaimReviewData = DataSource & {
  nomor_sep: string
  kode_rs: string
  rs_teks: string
  kelas_rawat: number
  periode: string
  eklaim: [string, string][]
  prosedur: { kode: string; keterangan: string }
  ventilator: { jam: number; rentang: string }
  tangga: { selisih: number; kali: string; kode: string; anak: { tarif: number; label: string; diklaim?: boolean }[] }
  biaya: [string, number, string][]
  ai1: { peluang: number; keterangan: string; ditandai: boolean; alasan: [string, string][]; tanpa_alasan?: string; catatan?: string }
  rme: { status: "diproses"; hasil: string }
  keputusan_terakhir: { id: number; waktu: string; peran: string; keputusan: string; catatan: string; sidik: string } | null
}

export type Story = { sumber: "llm_lokal" | "aturan"; durasi_ms: number; segmen: { teks: string; token: string | null; asal: string | null }[]; catatan: string[] }

export type ReportData = DataSource & {
  periode: string
  kepala: { wilayah: string; dianalisis: string; judul: string; sub: string }
  angka: { nilai: string; label: string; sub: string }[]
  rs: { kode_rs: string; modus: Mode; diakui: string; perkiraan: string; rentang: string; bukti: string; tindak: string }[]
  lampiran: [string, string, number, string][]
  ket_lampiran: string
  surat_rs?: string | null
  sumber: string
  kaki: string
  sidik_dokumen: string
}
