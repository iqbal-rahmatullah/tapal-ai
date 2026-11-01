
from typing import Any

SAMPLE = "contoh_desain"


def _rs(kode, kelas, milik, reg, mesin, modus, diakui, wajar, lo, hi, q, yakin, ket, rp, rp_lo, rp_hi, status, n_taruhan=None):
    return {"kode_rs": kode, "kelas": kelas, "kepemilikan": milik, "regional": reg, "mesin_penanda": mesin, "modus": modus, "diakui": diakui,
            "wajar": wajar, "wajar_bawah": lo, "wajar_atas": hi, "q": q, "keyakinan": yakin, "keterangan_keyakinan": ket, "rupiah": rp,
            "rupiah_bawah": rp_lo, "rupiah_atas": rp_hi, "n_klaim_dipertaruhkan": n_taruhan, "status_penanganan": status}


FLAGGED = [
    _rs("RS-031", "A", "Pemerintah", 2, "AI 1", "diperpanjang", 214, 178, 165, 191, 0.0004, "kuat", "q < 0,001", 1.37e9, 0.98e9, 1.79e9, "baru"),
    _rs("RS-117", "B", "Swasta", 1, "AI 1", "diperpanjang", 131, 90, 80, 101, 0.0004, "kuat", "q < 0,001", 1.23e9, 0.91e9, 1.58e9, "diklarifikasi"),
    _rs("RS-092", "C", "Swasta", 1, "AI 1", "fiktif", 141, 78, 69, 88, 0.0004, "kuat", "q < 0,001", 0.93e9, 0.78e9, 1.07e9, "baru"),
    _rs("RS-140", "B", "Swasta", 3, "AI 2", "rme_meragukan", None, None, None, None, None, "pola_kuat", "mirip 0,96", 0.72e9, None, None, "baru", 41),
    _rs("RS-019", "A", "Swasta", 1, "AI 1", "diperpanjang", 167, 151, 139, 163, 0.04, "lemah", "q = 0,04", 0.65e9, 0.21e9, 1.08e9, "baru"),
    _rs("RS-008", "B", "Pemerintah", 2, "AI 1", "fiktif", 203, 176, 162, 190, 0.02, "sedang", "q = 0,02", 0.47e9, 0.24e9, 0.71e9, "diaudit"),
    _rs("RS-064", "C", "Swasta", 3, "AI 1", "fiktif", 88, 61, 53, 70, 0.004, "sedang", "q = 0,004", 0.39e9, 0.27e9, 0.52e9, "baru"),
    _rs("RS-125", "C", "Pemerintah", 4, "AI 1", "diperpanjang", 39, 26, 21, 32, 0.03, "lemah", "q = 0,03", 0.18e9, 0.10e9, 0.27e9, "baru"),
    _rs("RS-077", "D", "Pemerintah", 5, "AI 1", "fiktif", 22, 11, 8, 15, 0.04, "lemah", "q = 0,04", 0.12e9, 0.08e9, 0.16e9, "baru"),
]

QUEUE: dict[str, Any] = {
    "sumber_data": SAMPLE,
    "periode": {"penilaian": "data 12 bulan, Jan–Des 2025", "klaim_diperiksa": "pembebanan Desember 2025", "diperbarui": "1 Jan 2026 pukul 02.00"},
    "ringkasan": {"n_rs": 150, "n_ditandai": 9, "per_mesin": {"AI 1": 8, "AI 2": 1}, "total_rupiah": 5.3e9, "total_bawah": 4.3e9,
                  "total_atas": 6.4e9, "menunggu_rme": 64, "audit_kapasitas": 60, "audit_terpakai": 38},
    "rs": FLAGGED,
    "urutan_keyakinan": ["RS-092", "RS-117", "RS-031", "RS-140", "RS-064", "RS-008", "RS-125", "RS-019", "RS-077"],
    "n_data_tidak_cukup": 23,
    "data_tidak_cukup": [],
}


def _claim(sep, tanggal, dx, px, jam, p, alasan, selisih, rme):
    return {"nomor_sep": sep, "tanggal": tanggal, "diagnosis": dx, "prosedur": px, "jam": jam, "peluang": p, "alasan": alasan,
            "selisih_tarif": selisih, "status_rme": rme}


_PEERS_C = [(1.044, 47.7), (1.018, 65.7), (0.945, 79.5), (1.046, 61.5), (0.94, 78.3), (1.12, 65.9), (0.921, 53.2), (1.014, 32.3), (1.006, 80.1),
            (0.972, 48.9), (0.958, 43.8), (1.012, 31.9), (1.026, 41.4), (0.937, 71.0), (0.973, 80.0), (1.024, 60.8), (0.959, 64.1), (0.976, 72.6),
            (1.073, 40.2), (0.977, 78.9), (1.078, 58.0), (1.084, 49.4), (0.903, 24.0), (0.977, 39.3), (1.036, 55.5), (1.008, 46.6), (1.014, 66.0),
            (0.993, 82.7), (1.027, 42.7), (1.028, 25.2), (0.964, 48.5), (0.936, 24.6), (0.96, 41.9), (0.961, 27.7), (0.923, 33.2), (0.939, 69.7),
            (1.014, 34.0), (1.006, 33.8), (0.933, 61.2), (1.005, 34.2), (1.013, 62.9), (1.089, 84.8), (1.144, 80.9), (0.931, 69.5), (1.01, 46.9),
            (0.905, 62.2), (1.085, 67.0), (0.937, 65.0), (0.952, 66.7), (1.101, 69.1), (1.003, 25.6), (1.018, 27.0), (0.963, 25.7), (0.998, 48.0),
            (0.971, 40.1), (0.986, 82.8), (1.085, 41.8), (1.064, 80.8), (1.063, 79.4), (0.994, 47.0), (0.964, 65.0), (1.012, 35.8), (0.957, 44.1),
            (0.982, 80.6), (1.044, 68.9), (0.908, 58.5), (1.029, 62.7), (0.964, 56.2), (0.915, 48.0), (0.874, 41.9), (1.018, 45.8), (0.972, 85.6),
            (1.092, 26.6), (1.022, 49.3), (0.998, 71.4), (1.44, 25.8), (1.5, 81.5)]
_PEERS_B = [(1.018, 45.0), (1.025, 83.6), (1.018, 74.0), (1.041, 48.2), (0.996, 56.3), (0.966, 74.4), (0.92, 78.9), (0.882, 60.6), (1.09, 30.0),
            (0.866, 34.4), (0.994, 62.9), (0.908, 69.3), (1.008, 66.5), (1.079, 32.8), (1.031, 47.2), (1.031, 85.5), (1.034, 41.7), (1.006, 67.8),
            (1.031, 33.8), (0.973, 36.5), (0.927, 58.5), (0.974, 42.0), (1.056, 34.3), (0.976, 55.9), (1.049, 59.1), (0.945, 35.6), (1.063, 32.6),
            (0.991, 73.7), (0.991, 83.4), (0.943, 48.3), (0.997, 77.9), (1.15, 25.2), (1.05, 46.6)]


def _peers(points, rs, ratio, text):
    return {"jenis": "pembanding", "judul": "Pembanding RS sekelas", "label": ["Statistik"], "temuan": text,
            "rs": {"kode": rs, "rasio": ratio}, "lain": [{"rasio": r, "y": round(y / 96, 3)} for r, y in points], "rentang_wajar": [0.85, 1.15]}


_RS092 = {
    "kode_rs": "RS-092", "kelas": "C", "kepemilikan": "Swasta", "regional": 1, "modus": "fiktif", "keyakinan": "kuat",
    "keterangan_keyakinan": "q < 0,001", "status_penanganan": "baru",
    "ringkas_data": "1.146 rawat ICU, 141 klaim garis ventilator (96.71: 133, 96.72: 8, intubasi saja: 0), Jan–Des 2025",
    "kartu_diakui": {"label": ["AI 1", "Statistik"], "diakui": 141, "diakui_teks": "diakui (garis ventilator)", "wajar": 78, "wajar_bawah": 69,
                     "wajar_atas": 88, "kelebihan_teks": "kelebihan 63 klaim", "catatan": "Selisih diuji terhadap 149 RS lain: z robust 6,1; q < 0,001 setelah koreksi untuk 150 RS."},
    "kartu_rupiah": {"judul": "Perkiraan kelebihan bayar", "nilai": 0.93e9, "bawah": 0.78e9, "atas": 1.07e9, "skala": 1.5e9,
                     "rincian": "63 klaim × rata-rata selisih tarif Rp14,8 juta pada baris tarif RS ini (Kelas C Swasta, Regional 1)."},
    "kartu_rme": {"judul": "Dibaca 25 dari 63 klaim teratas", "hitungan": [["RME tidak mendukung", 21], ["Tidak dapat disimpulkan", 3], ["Mendukung", 1]],
                  "status": [["kemiripan", "Kemiripan catatan antarpasien: tidak ada pola"], ["jejak", "Jejak waktu: wajar, median ditulis 2 jam setelah layanan"]]},
    "grafik_kiri": {"jenis": "peluang", "judul": "Peluang didukung bukti", "label": ["AI 1"], "seri": ["RS-092", "77 RS kelas C lain"],
                    "temuan": "Klaim garis ventilator. 34% klaim RS-092 berpeluang di bawah 0,1; di RS kelas C lain hanya 4%.",
                    "rs": [34, 9, 4, 3, 3, 4, 6, 9, 12, 16], "lain": [4, 3, 3, 3, 4, 6, 9, 14, 21, 33]},
    "grafik_kanan": _peers(_PEERS_C, "RS-092", 1.81, "Rasio diakui ÷ wajar; 1,0 berarti sesuai bukti. RS-092 terjauh dari 77 RS kelas C lain."),
    "klaim_judul": "Klaim yang paling tidak didukung bukti", "klaim_keterangan": "4 dari 63 klaim kelebihan, urut menurut peluang terendah", "klaim_total": 63,
    "klaim": [
        _claim("SIN-092-25-00412", "03–08 Sep 2025", "J18.9", "96.71", 52, 0.04, ["sewa alat 0%", "tanpa gas darah"], 13497000, "tidak_mendukung"),
        _claim("SIN-092-25-00377", "21–25 Agu 2025", "J96.0", "96.71", 48, 0.05, ["sewa alat 0%", "ICU 2 hari"], 14120000, "tidak_mendukung"),
        _claim("SIN-092-25-00519", "02–06 Okt 2025", "J18.9", "96.71", 40, 0.06, ["tanpa gas darah", "obat 38%"], 13497000, "tidak_dapat_disimpulkan"),
        _claim("SIN-092-25-00288", "11–16 Jul 2025", "I63.9", "96.71", 60, 0.07, ["sewa alat 0%"], 15904000, "belum_dibaca"),
    ],
    "fakta_ringkasan": {"diakui": ["141 klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                        "wajar": ["78 klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                        "wajar_bawah": ["69", "rentang 95% wajar", ["AI 1", "Statistik"]], "wajar_atas": ["88", "rentang 95% wajar", ["AI 1", "Statistik"]],
                        "kelebihan": ["63 klaim", "diakui dikurangi wajar", ["Kode"]],
                        "rupiah": ["Rp0,93 miliar", "63 × selisih tarif Permenkes 3/2023", ["Kode"]],
                        "dibaca": ["25 RME", "bacaan RME berkutipan", ["AI 2"]], "tidak_mendukung": ["21 RME", "bacaan RME berkutipan", ["AI 2"]]},
}

_RS117 = {
    "kode_rs": "RS-117", "kelas": "B", "kepemilikan": "Swasta", "regional": 1, "modus": "diperpanjang", "keyakinan": "kuat",
    "keterangan_keyakinan": "q < 0,001", "status_penanganan": "diklarifikasi",
    "ringkas_data": "2.310 rawat ICU, 228 klaim ventilasi ≥72 jam (96.71: 97, 96.72: 131), data Jan–Des 2025",
    "kartu_diakui": {"label": ["AI 1", "Statistik"], "diakui": 131, "diakui_teks": "diakui ≥96 jam", "wajar": 90, "wajar_bawah": 80, "wajar_atas": 101,
                     "kelebihan_teks": "kelebihan 41", "catatan": "Selisih diuji terhadap 149 RS lain: z robust 5,2; q < 0,001 setelah koreksi untuk 150 RS."},
    "kartu_rupiah": {"judul": "Perkiraan kelebihan bayar", "nilai": 1.23e9, "bawah": 0.91e9, "atas": 1.58e9, "skala": 2.0e9,
                     "rincian": "41 klaim × rata-rata selisih J-1-20 → J-1-02 Rp30,0 juta pada baris tarif RS ini (Kelas B Swasta, Regional 1)."},
    "kartu_rme": {"judul": "Dibaca 18 dari 41 klaim teratas", "hitungan": [["Jam menurut RME < 96", 13], ["Tidak dapat disimpulkan", 3], ["Sesuai, ≥96 jam", 2]],
                  "status": [["jam", "Median jam menurut RME 88 jam, diklaim 99 jam"], ["kemiripan", "Kemiripan catatan antarpasien: tidak ada pola"]]},
    "grafik_kiri": {"jenis": "jam", "judul": "Jam ventilator tercatat, 72–120 jam", "label": ["Statistik"], "seri": ["RS-117", "RS kelas B lain"],
                    "temuan": "Asimetri di garis 96 jam +1,38 (+0,92 sampai +1,86); plasebo 120 jam +0,05 (−0,21 sampai +0,30).",
                    "awal": 72, "lebar": 4, "rs": [6, 5, 5, 3, 2, 1, 19, 11, 4, 3, 2, 2],
                    "lain": [7.6, 6.9, 6.3, 5.7, 5.1, 4.4, 8.9, 5.1, 3.8, 3.2, 3.2, 3.2], "garis_tarif": 96, "plasebo": [72, 120]},
    "grafik_kanan": _peers(_PEERS_B, "RS-117", 1.46, "Rasio klaim ≥96 jam diakui ÷ wajar; RS-117 1,46 dibanding 33 RS kelas B lain."),
    "klaim_judul": "Klaim ≥96 jam yang paling tidak didukung bukti", "klaim_keterangan": "4 dari 41 klaim kelebihan, urut menurut peluang terendah", "klaim_total": 41,
    "klaim": [
        _claim("SIN-117-25-00812", "12–19 Okt 2025", "J96.0", "96.72", 99, 0.09, ["lama ICU 4 hari", "jam RME 86"], 30593400, "tidak_mendukung"),
        _claim("SIN-117-25-00791", "03–09 Sep 2025", "J18.9", "96.72", 98, 0.11, ["ICU 4 hari", "ekstubasi hari ke-4"], 30593400, "tidak_mendukung"),
        _claim("SIN-117-25-00942", "21–28 Nov 2025", "I61.9", "96.72", 101, 0.13, ["jam RME 90"], 37320200, "tidak_dapat_disimpulkan"),
        _claim("SIN-117-25-00655", "07–13 Agu 2025", "J96.0", "96.72", 97, 0.14, ["lama ICU 4 hari"], 22413700, "belum_dibaca"),
    ],
    "fakta_ringkasan": {"diakui": ["131 klaim", "klaim ≥96 jam, uji per RS", ["AI 1", "Statistik"]],
                        "wajar": ["90 klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                        "wajar_bawah": ["80", "rentang 95% wajar", ["AI 1", "Statistik"]], "wajar_atas": ["101", "rentang 95% wajar", ["AI 1", "Statistik"]],
                        "kelebihan": ["41 klaim", "diakui dikurangi wajar", ["Kode"]],
                        "rupiah": ["Rp1,23 miliar", "41 × selisih J-1-20 → J-1-02, Permenkes 3/2023", ["Kode"]],
                        "dibaca": ["18 RME", "bacaan RME berkutipan", ["AI 2"]], "tidak_mendukung": ["13 RME", "jam menurut RME di bawah 96", ["AI 2"]]},
}

_LATER = [(420.2, 71.7), (85.6, 46.0), (230.3, 85.3), (380.4, 58.4), (153.5, 76.8), (257.1, 53.3), (65.4, 47.9), (89.1, 85.2), (211.4, 51.8),
          (253.2, 77.1), (212.8, 61.5), (376.4, 75.1), (37.4, 81.6), (305.3, 83.8), (507.4, 52.2), (378.7, 78.8), (307.4, 71.2), (360.7, 83.7),
          (203.7, 58.7), (319.9, 83.8), (65.8, 74.3), (509.1, 82.5), (482.8, 71.3), (351.5, 51.7), (473.1, 68.2), (390.8, 46.6), (222.7, 75.4),
          (134.5, 80.5), (337.1, 45.1), (181.2, 78.6), (479.7, 60.5), (26.2, 53.4), (296.5, 68.4), (279.1, 79.5), (380.9, 44.0), (254.5, 72.5),
          (9.2, 84.6), (14.0, 72.3), (478.0, 46.3), (162.7, 74.8), (432.9, 52.7), (119.6, 70.3), (336.8, 61.6), (448.1, 45.7), (279.4, 79.7),
          (181.5, 75.7), (236.1, 51.6), (487.3, 57.3), (146.2, 75.0), (140.5, 84.1), (509.1, 86.9), (201.1, 75.6), (108.8, 77.0), (260.3, 59.8),
          (189.3, 67.1)]

_RS140 = {
    "kode_rs": "RS-140", "kelas": "B", "kepemilikan": "Swasta", "regional": 3, "modus": "rme_meragukan", "keyakinan": "pola_kuat",
    "keterangan_keyakinan": "mirip 0,96", "status_penanganan": "baru",
    "ringkas_data": "1.480 rawat ICU, 96 klaim garis ventilator (96.71: 71, 96.72: 25, intubasi saja: 0), Jan–Des 2025",
    "kartu_diakui": {"label": ["AI 1", "Statistik"], "diakui": 96, "diakui_teks": "diakui (garis ventilator)", "wajar": 91, "wajar_bawah": 82, "wajar_atas": 101,
                     "kelebihan_teks": None, "catatan": "Selisih 5 klaim masih dalam rentang wajar (q = 0,71).",
                     "catatan_jujur": "Lolos pemeriksaan klaim; ditandai karena pola RME."},
    "kartu_rupiah": {"judul": "Nilai dipertaruhkan", "nilai": 0.72e9, "bawah": None, "atas": None, "skala": None,
                     "subjudul": "41 klaim dengan RME meragukan (96.71: 33, 96.72: 8)",
                     "rincian": "41 klaim × rata-rata selisih tarif Rp17,6 juta pada baris tarif RS ini (Kelas B Swasta, Regional 3).",
                     "catatan": "Ini bukan perkiraan kelebihan bayar: isinya baru bisa dipastikan lewat audit."},
    "kartu_rme": {"judul": "Dibaca 96 dari 96 klaim garis ventilator", "hitungan": [["Catatan nyaris identik", 41], ["Ditulis ≥72 jam kemudian", 84], ["Isi RME mendukung kode", 93]],
                  "status": [["kemiripan", "Kembar: 41 pasien, median kemiripan 0,96"], ["jejak", "3 gelombang tulis massal: 30 Sep, 31 Okt, 30 Nov"]]},
    "grafik_kiri": {"jenis": "waktu_tulis", "judul": "Kapan catatan ICU ditulis", "label": ["AI 2"], "seri": ["kelompok kembar", "pasien lain"],
                    "temuan": "Satu titik per pasien: tanggal catatan ICU-nya ditulis di server.",
                    "bulan": ["Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
                    "lain": [{"hari": round((x - 10) / 85.6 * 30.6, 1), "y": round(y / 96, 3)} for x, y in _LATER],
                    "gelombang": [{"hari": 91, "tanggal": "30 Sep", "jam": "22.14", "n": 14}, {"hari": 122, "tanggal": "31 Okt", "jam": "21.02", "n": 14},
                                  {"hari": 152, "tanggal": "30 Nov", "jam": "22.40", "n": 13}]},
    "grafik_kanan": {"jenis": "kemiripan", "judul": "Kemiripan catatan antarpasien", "label": ["AI 2", "Kode"],
                     "temuan": "Kemiripan teks setelah bagian templat baku dibuang; 96 × 96 pasien, diurutkan.",
                     "n_pasien": 96, "n_kembar": 41, "median_kembar": 0.96, "keterangan": "catatan nyaris identik, median kemiripan 0,96 (blok pekat kiri atas)"},
    "klaim_judul": "Klaim dengan catatan RME nyaris identik", "klaim_keterangan": "4 dari 41 klaim, urut menurut kemiripan tertinggi", "klaim_total": 41,
    "klaim": [
        _claim("SIN-140-25-01187", "05–08 Sep 2025", "J96.0", "96.71", 60, 0.71, ["mirip 0,97", "ditulis +22 hari"], 21572700, "asal_meragukan"),
        _claim("SIN-140-25-01203", "06–09 Sep 2025", "J96.0", "96.71", 58, 0.69, ["mirip 0,97", "ditulis +21 hari"], 18517400, "asal_meragukan"),
        _claim("SIN-140-25-01342", "03–07 Okt 2025", "J18.9", "96.71", 62, 0.74, ["mirip 0,96", "ditulis +24 hari"], 17892000, "asal_meragukan"),
        _claim("SIN-140-25-01455", "01–05 Nov 2025", "J96.0", "96.72", 104, 0.77, ["mirip 0,95", "ditulis +25 hari"], 49532200, "asal_meragukan"),
    ],
    "fakta_ringkasan": {"diakui": ["96 klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                        "wajar": ["91 klaim", "diakui vs wajar, uji per RS", ["AI 1", "Statistik"]],
                        "kembar": ["41 pasien", "kemiripan catatan antarpasien", ["AI 2", "Kode"]],
                        "kemiripan": ["0,96", "median kemiripan kelompok kembar", ["AI 2", "Kode"]],
                        "gelombang": ["3 gelombang", "jejak waktu tulis server", ["AI 2", "Kode"]],
                        "rupiah": ["Rp0,72 miliar", "41 × selisih tarif Permenkes 3/2023, nilai dipertaruhkan", ["Kode"]]},
}

PROFILES: dict[str, dict] = {p["kode_rs"]: {**p, "sumber_data": SAMPLE} for p in (_RS092, _RS117, _RS140)}

SUMMARY_TEMPLATES = {
    "fiktif": ["{rs} mengajukan {diakui} garis ventilator selama 12 bulan; bukti di klaim hanya mendukung {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
               "Kelebihan {kelebihan} setara perkiraan {rupiah}.", "Dari {dibaca} yang dibaca, {tidak_mendukung} tidak mendukung kode ventilasi."],
    "diperpanjang": ["{rs} mencatat {diakui} dengan ventilasi ≥96 jam; bukti di klaim hanya mendukung {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
                     "Kelebihan {kelebihan} setara perkiraan {rupiah}.", "Dari {dibaca} yang dibaca, {tidak_mendukung} mencatat jam di bawah garis 96 jam."],
    "rme_meragukan": ["{rs} lolos pemeriksaan klaim: diakui {diakui}, wajar {wajar}.",
                      "Catatan RME {kembar} nyaris identik (median kemiripan {kemiripan}) dan ditulis dalam {gelombang} tulis massal.",
                      "Nilai yang dipertaruhkan {rupiah}; isinya baru bisa dipastikan lewat audit."],
}


def _doc(id_, label, judul, teks, sorot=()):
    return {"id": id_, "label": label, "judul": judul, "teks": teks, "sorot": list(sorot)}


def _quote(before, mark, after, where, ok=True):
    return {"sebelum": before, "sorot": mark, "sesudah": after, "dokumen": where, "cocok": ok}


_DOCS_A = [
    _doc("a1", "CPPT 03-09", "CPPT, 03-09-2025 08.10, Dokter jaga",
         "S: sesak napas sejak 2 hari, batuk berdahak. O: SpO2 88% dengan NRM 10 lpm, RR 28x/mnt, ronki basah paru kanan. "
         "A: pneumonia komunitas. P: rawat ICU, antibiotik IV, observasi saturasi tiap jam.", ["NRM 10 lpm"]),
    _doc("a2", "Observasi ICU 03-09", "Observasi ICU, 03-09-2025 14.00, Perawat ICU",
         "Pasien terpasang nasal kanul 4 lpm, SpO2 96%, RR 22x/mnt. Tidak tampak tanda distres napas. Posisi semi-Fowler, mobilisasi bertahap. "
         "Balans cairan positif 300 ml. Lanjut terapi sesuai advis.", ["terpasang nasal kanul 4 lpm"]),
    _doc("a3", "CPPT 05-09", "CPPT, 05-09-2025 09.00, Dokter penanggung jawab",
         "S: sesak berkurang, batuk berkurang. O: O2 nasal kanul 2 lpm, SpO2 97%, RR 18x/mnt. A: pneumonia membaik. P: pindah ruang rawat biasa bila stabil.",
         ["nasal kanul 2 lpm"]),
    _doc("a4", "Resume 08-09", "Resume medis, 08-09-2025 10.15, Dokter penanggung jawab",
         "Diagnosis utama: pneumonia (J18.9). Terapi: antibiotik IV, oksigen nasal kanul. Kondisi pulang: sehat, kontrol poli paru satu minggu.",
         ["oksigen nasal kanul"]),
]

_KLAIM_A = {
    "nomor_sep": "SIN-092-25-00412", "kode_rs": "RS-092", "rs_teks": "RS-092, Kelas C, Swasta", "kelas_rawat": 3, "periode": "03-09-2025 → 08-09-2025",
    "eklaim": [["Pasien", "Laki-laki, 58 tahun"], ["Lama rawat", "6 hari, ICU 3 hari"], ["Diagnosis", "J18.9 Pneumonia"], ["Status pulang", "Sehat"],
               ["Sekunder", "I10, E11.9"], ["CBG", "J-1-20-II, sev. II"]],
    "prosedur": {"kode": "96.71", "keterangan": "tanpa kode intubasi 96.04 dan analisa gas darah 89.65"},
    "ventilator": {"jam": 52, "rentang": "03-09-2025 10.00 → 05-09-2025 14.00"},
    "tangga": {"selisih": 13497000, "kali": "3,7", "kode": "96.71",
               "anak": [{"tarif": 5078100, "label": "J-4-16-II, tanpa kode"}, {"tarif": 18575100, "label": "J-1-20-II, 96.71 (diklaim)", "diklaim": True},
                        {"tarif": 32340200, "label": "J-1-02-II, 96.72"}]},
    "biaya": [["Sewa alat", 0.0, "Rp0, tipikal Rp2,1 jt"], ["Rawat intensif", 0.52, "Rp3,6 jt, 52%"], ["Laboratorium", 0.35, "35% dari tipikal"], ["Obat", 0.41, "41% dari tipikal"]],
    "ai1": {"peluang": 0.04, "keterangan": "lebih rendah dari 98% klaim garis ventilator lain", "ditandai": True,
            "alasan": [["turun", "sewa alat Rp0"], ["turun", "tanpa analisa gas darah (89.65)"], ["turun", "ICU 3 hari, pulang sehat"], ["naik", "pneumonia dengan gagal napas"]]},
    "rme": {
        "jenis": "baca", "sumber": "llm_lokal", "durasi_ms": 47600, "dokumen": _DOCS_A, "dokumen_aktif": "a2",
        "hasil": {"alat": ["NRM 10 lpm", "nasal kanul 4 lpm", "nasal kanul 2 lpm"],
                  "baris": [["Ventilator invasif", "tidak ditemukan"], ["Intubasi", "tidak ditemukan"], ["Jam ventilator", "RME 0 jam, diklaim 52 jam"]],
                  "verdict": "RME tidak mendukung kode 96.71", "verdict_jenis": "tidak_mendukung"},
        "kutipan_ringkas": "terverifikasi 3 dari 3", "kutipan_semua_cocok": True,
        "kutipan": [_quote("SpO2 88% dengan ", "NRM 10 lpm", "", "CPPT, 03-09 08.10"),
                    _quote("Pasien terpasang ", "nasal kanul 4 lpm", ", SpO2 96%", "Observasi ICU, 03-09 14.00"),
                    _quote("Terapi: antibiotik IV, ", "oksigen nasal kanul", "", "Resume medis, 08-09 10.15")],
        "cek": [["jejak", "Jejak waktu: wajar, ditulis 0–3 jam setelah layanan"], ["kemiripan", "Kemiripan: tidak ada (maks 0,41)"]],
        "tombol_utama": "minta_klarifikasi",
    },
    "rme_aturan": {
        "jenis": "aturan", "sumber": "aturan", "durasi_ms": 140, "dokumen": _DOCS_A, "dokumen_aktif": "a2",
        "kata": [["Kata napas ringan", [["nasal kanul", 3], ["NRM", 1]]], ["Kata ventilator", [["ventilator", 0], ["SIMV", 0], ["ETT", 0], ["intubasi", 0]]]],
        "jam": "tidak dihitung aturan, diklaim 52 jam",
        "hasil": {"verdict": "Tidak mendukung 96.71, aturan cadangan, keyakinan lebih rendah", "verdict_jenis": "tidak_mendukung"},
        "peringatan_aturan": "Aturan tidak membaca konteks (misalnya “ventilator dilepas”); periksa dokumen langsung.",
        "kutipan": [_quote("…SpO2 88% dengan ", "NRM", " 10 lpm", "CPPT, 03-09 08.10"), _quote("…Pasien terpasang ", "nasal kanul", " 4 lpm…", "Observasi ICU, 03-09 14.00"),
                    _quote("…O2 ", "nasal kanul", " 2 lpm, SpO2 97%", "CPPT, 05-09 09.00"), _quote("…antibiotik IV, oksigen ", "nasal kanul", "", "Resume medis, 08-09 10.15")],
        "cek": [["jejak", "Jejak waktu: wajar, ditulis 0–3 jam setelah layanan"], ["kemiripan", "Kemiripan: tidak ada (maks 0,41)"]],
        "tombol_utama": "minta_klarifikasi",
    },
}

_DOCS_B = [
    _doc("b1", "Lap. tindakan 05-09", "Laporan tindakan, 05-09-2025 09.05, Dokter anestesi",
         "Dilakukan intubasi dengan ETT nomor 7,5 tanpa penyulit. Pasien dihubungkan ke ventilator mode SIMV, FiO2 60%, PEEP 6.", ["intubasi", "ventilator mode SIMV"]),
    _doc("b2", "Observasi ICU 05-09", "Observasi ICU, 05-09-2025 14.00, Perawat ICU",
         "Pasien terpasang ventilator mode SIMV, FiO2 50%, PEEP 6, RR set 14x/mnt. SpO2 97%. Suction ETT 2x.", ["terpasang ventilator mode SIMV"]),
    _doc("b3", "CPPT 06-09", "CPPT, 06-09-2025 08.30, Dokter penanggung jawab",
         "O: ventilator SIMV, FiO2 40%, PEEP 5, SpO2 98%. A: gagal napas akut membaik. P: rencana penyapihan bertahap.", ["ventilator SIMV"]),
    _doc("b4", "Resume 08-09", "Resume medis, 08-09-2025 10.00, Dokter penanggung jawab",
         "Diagnosis utama: gagal napas akut (J96.0). Ekstubasi 07-09-2025 21.00. Kondisi pulang: sehat.", ["Ekstubasi 07-09-2025 21.00"]),
]

_KLAIM_B = {
    "nomor_sep": "SIN-140-25-01187", "kode_rs": "RS-140", "rs_teks": "RS-140, Kelas B, Swasta", "kelas_rawat": 2, "periode": "05-09-2025 → 08-09-2025",
    "eklaim": [["Pasien", "Perempuan, 63 tahun"], ["Lama rawat", "4 hari, ICU 3 hari"], ["Diagnosis", "J96.0 Gagal napas akut"], ["Status pulang", "Sehat"],
               ["Sekunder", "J18.9, I10"], ["CBG", "J-1-20-II, sev. II"]],
    "prosedur": {"kode": "96.71", "keterangan": "dengan kode intubasi 96.04 dan analisa gas darah 89.65"},
    "ventilator": {"jam": 60, "rentang": "05-09-2025 09.00 → 07-09-2025 21.00"},
    "tangga": {"selisih": 21572700, "kali": "4,9", "kode": "96.71",
               "anak": [{"tarif": 5583900, "label": "J-4-11-II, tanpa kode"}, {"tarif": 27156600, "label": "J-1-20-II, 96.71 (diklaim)", "diklaim": True},
                        {"tarif": 63288800, "label": "J-1-02-II, 96.72"}]},
    "biaya": [["Sewa alat", 1.04, "Rp2,2 jt, 104%"], ["Rawat intensif", 0.98, "Rp6,8 jt, 98%"], ["Laboratorium", 0.91, "91% dari tipikal"], ["Obat", 0.87, "87% dari tipikal"]],
    "ai1": {"peluang": 0.71, "keterangan": "sejalan dengan klaim garis ventilator lain, AI 1 tidak menandai", "ditandai": False,
            "alasan": [["naik", "biaya rawat intensif sesuai tipikal"], ["naik", "ada analisa gas darah"], ["naik", "sewa alat sesuai tipikal"], ["turun", "pulang sehat setelah ICU 3 hari"]]},
    "rme": {
        "jenis": "asal_meragukan", "sumber": "llm_lokal", "durasi_ms": 48300, "dokumen": _DOCS_B, "dokumen_aktif": "b2",
        "hasil": {"alat": ["ventilator invasif SIMV", "ekstubasi 07-09 21.00"],
                  "baris": [["Intubasi", "ditemukan, 05-09 09.05 (laporan tindakan)"], ["Jam ventilator", "RME 60 jam, diklaim 60 jam"]],
                  "verdict": "Isi RME mendukung kode 96.71, kutipan terverifikasi 3 dari 3", "verdict_jenis": "mendukung"},
        "kemiripan": {"judul": "Catatan ini 97% sama dengan catatan 12 pasien lain di RS ini",
                      "pasangan": [{"sep": "SIN-140-25-01187", "pasien": "Perempuan, 63 th", "teks": "ventilator SIMV, FiO2 50%, PEEP 6, RR set 14, SpO2 ", "beda": "97%"},
                                   {"sep": "SIN-140-25-01203", "pasien": "Perempuan, 58 th", "teks": "ventilator SIMV, FiO2 50%, PEEP 6, RR set 14, SpO2 ", "beda": "95%"}],
                      "catatan": "Hanya umur, tanggal, dan SpO2 (tebal) yang berbeda; sisa teks sama persis."},
        "jejak": {"judul": "Ditulis 22 hari setelah pasien pulang, sekaligus dengan 40 pasien lain", "layanan": "05–08 Sep", "tulis": "30 Sep 22.14–22.19",
                  "catatan": "Jam server rekam medis (meta.lastUpdated), bukan diisi RS."},
        "verdict_akhir": "Isi mendukung, asal-usul catatan meragukan, disarankan ajukan audit",
        "tombol_utama": "ajukan_audit",
    },
}

_DOCS_E = [
    _doc("e1", "CPPT 02-10", "CPPT, 02-10-2025 16.30, Dokter jaga",
         "S: sesak dan demam. O: SpO2 91% dengan masker sederhana 6 lpm, RR 26x/mnt. A: pneumonia. P: rawat ICU, antibiotik IV.", ["masker sederhana 6 lpm"]),
    _doc("e2", "Observasi ICU 03-10", "Observasi ICU, 03-10-2025 20.00, Perawat ICU",
         "Pasien terpasang nasal kanul 3 lpm, SpO2 95%, RR 20x/mnt, kesadaran compos mentis. Duduk di tempat tidur, makan per oral setengah porsi.",
         ["terpasang nasal kanul 3 lpm"]),
    _doc("e3", "CPPT 04-10", "CPPT, 04-10-2025 09.00, Dokter penanggung jawab", "O: O2 nasal kanul 2 lpm, SpO2 97%. A: pneumonia membaik. P: pindah ruang rawat biasa."),
    _doc("e4", "Resume 06-10", "Resume medis, 06-10-2025 11.00, Dokter penanggung jawab", "Diagnosis utama: pneumonia (J18.9). Terapi: antibiotik IV, oksigen. Kondisi pulang: sehat."),
]

_KLAIM_E = {
    "nomor_sep": "SIN-092-25-00519", "kode_rs": "RS-092", "rs_teks": "RS-092, Kelas C, Swasta", "kelas_rawat": 3, "periode": "02-10-2025 → 06-10-2025",
    "eklaim": [["Pasien", "Perempuan, 66 tahun"], ["Lama rawat", "5 hari, ICU 2 hari"], ["Diagnosis", "J18.9 Pneumonia"], ["Status pulang", "Sehat"],
               ["Sekunder", "I10"], ["CBG", "J-1-20-II, sev. II"]],
    "prosedur": {"kode": "96.71", "keterangan": "tanpa analisa gas darah 89.65"},
    "ventilator": {"jam": 40, "rentang": "02-10-2025 18.00 → 04-10-2025 10.00"},
    "tangga": {"selisih": 13497000, "kali": "3,7", "kode": "96.71",
               "anak": [{"tarif": 5078100, "label": "J-4-16-II, tanpa kode"}, {"tarif": 18575100, "label": "J-1-20-II, 96.71 (diklaim)", "diklaim": True},
                        {"tarif": 32340200, "label": "J-1-02-II, 96.72"}]},
    "biaya": [["Sewa alat", 0.24, "Rp0,5 jt, 24%"], ["Rawat intensif", 0.61, "Rp4,2 jt, 61%"], ["Laboratorium", 0.44, "44% dari tipikal"], ["Obat", 0.38, "38% dari tipikal"]],
    "ai1": {"peluang": 0.06, "keterangan": "lebih rendah dari 96% klaim garis ventilator lain", "ditandai": True,
            "alasan": [["turun", "tanpa analisa gas darah (89.65)"], ["turun", "obat 38% dari tipikal"], ["turun", "ICU 2 hari, pulang sehat"], ["naik", "pneumonia"]]},
    "rme": {
        "jenis": "tidak_dapat_disimpulkan", "sumber": "llm_lokal", "durasi_ms": 49000, "dokumen": _DOCS_E, "dokumen_aktif": "e2",
        "hasil": {"verdict": "Tidak dapat disimpulkan", "verdict_jenis": "tidak_dapat_disimpulkan",
                  "alasan": "Kutipan yang diajukan LLM tidak ditemukan di dokumen (1 dari 3 gagal dicocokkan). Hasil ditolak; baca dokumen langsung.",
                  "aturan": "Tiap kutipan dicocokkan huruf demi huruf dengan dokumen sebelum hasil LLM boleh tampil."},
        "kutipan_ringkas": "1 dari 3 gagal dicocokkan", "kutipan_semua_cocok": False,
        "kutipan": [_quote("SpO2 91% dengan ", "masker sederhana 6 lpm", "", "CPPT, 02-10 16.30"),
                    _quote("Pasien terpasang ", "nasal kanul 3 lpm", ", SpO2 95%", "Observasi ICU, 03-10 20.00"),
                    _quote("Pasien ", "terintubasi, ventilator mode SIMV", "", "diajukan dari Observasi ICU, 03-10 20.00", ok=False)],
        "cek": [["jejak", "Jejak waktu: wajar, ditulis 0–2 jam setelah layanan"], ["kemiripan", "Kemiripan: tidak ada (maks 0,38)"]],
        "tombol_utama": "minta_klarifikasi",
    },
}

_HOURLY_G = [0.124, 0.124, 0.124, 0.099, 0.099, 0.124, 0.124, 0.124, 0.124, 0.154, 0.154, 0.124, 0.124, 0.124, 0.124, 0.124, 0.124, 0.124,
             0.124, 0.124, 0.124, 0.124, 0.118, 0.118, 0.118, 0.124, 0.124, 0.099, 0.124, 0.124, 0.124, 0.124, 0.124, 0.124, 0.134, 0.134,
             0.134, 0.124, 0.101, 0.124, 0.124, 0.124, 0.131, 0.124, 0.124, 0.124, 0.124, 0.118, 0.124, 0.124, 0.124, 0.154, 0.118, 0.124]

_KLAIM_G = {
    "nomor_sep": "SIN-063-25-00731", "kode_rs": "RS-063", "rs_teks": "RS-063, Kelas C, Swasta", "kelas_rawat": 3, "periode": "16-10-2025 → 21-10-2025",
    "sumber_mesin": "SEP-3495164986",
    "eklaim": [["Pasien", "Perempuan, 48 tahun"], ["Lama rawat", "6 hari, ICU 3 hari"], ["Diagnosis", "I63.9 Infark serebral"], ["Status pulang", "Sehat"],
               ["Sekunder", "E78.5"], ["CBG", "J-1-20-I, sev. I"]],
    "prosedur": {"kode": "96.71", "keterangan": "dengan kode intubasi 96.04 dan analisa gas darah 89.65"},
    "ventilator": {"jam": 50, "rentang": "17-10-2025 21.19 → 19-10-2025 23.19"},
    "tangga": {"selisih": 11964200, "kali": "4,0", "kode": "96.71",
               "anak": [{"tarif": 4036200, "label": "G-4-14-I, tanpa kode"}, {"tarif": 16000400, "label": "J-1-20-I, 96.71 (diklaim)", "diklaim": True},
                        {"tarif": 23700600, "label": "J-1-02-I, 96.72"}]},
    "biaya": [["Sewa alat", 2.1, "Rp3,0 jt, 210%"], ["Rawat intensif", 0.99, "Rp8,5 jt, 99%"], ["Laboratorium", 0.46, "46% dari tipikal"], ["Obat", 0.72, "72% dari tipikal"]],
    "ai1": {"peluang": 1.0, "keterangan": "setara dengan sebagian besar klaim garis ventilator, AI 1 tidak menandai", "ditandai": False, "alasan": [],
            "tanpa_alasan": "Tidak ada bukti di klaim yang mengubah peluang lebih dari 0,01: kode intubasi 96.04, analisa gas darah 89.65, dan sewa alat ikut tercatat.",
            "catatan": "AI 1 hanya membaca kolom klaim; kolom lengkap belum tentu sesuai kejadian."},
    "rme": {
        "jenis": "fisiologi", "sumber": "llm_lokal", "durasi_ms": 49900, "dokumen": [],
        "hasil": {"alat": ["ventilator invasif PC", "ekstubasi 19-10 23.19"], "baris": [["Jam ventilator", "RME 50 jam, diklaim 50 jam"]],
                  "verdict": "Isi RME mendukung kode 96.71, kutipan terverifikasi 6 dari 6", "verdict_jenis": "mendukung"},
        "asersi": {"ringkas": "ventilasi invasif: ya", "sama": True,
                   "sebutan": [["17-10 21.19", "…dihubungkan ke ventilator mekanik mode PC.", "ventilator", "terpasang"],
                               ["18-10 21.00", "Pasien terpasang ventilator mekanik mode PC…", "ventilator", "terpasang"],
                               ["19-10 09.23", "Rencana penyapihan dan pelepasan ventilator…", "ventilator", "rencana"],
                               ["19-10 23.19", "…spontan dengan sungkup non-rebreathing 13 lpm.", "NRM", "terpasang"]],
                   "kaki": "Pembaca kedua tanpa LLM: 10 sebutan dari 9 catatan; terpasang 9, rencana 1, lainnya 0."},
        "fisiologi": {"ringkas": "0 dari 50 jam berventilasi", "judul": "Peluang ventilasi invasif per jam menurut angka lembar, 17-10 20.00 sampai 20-10 01.00",
                      "per_jam": _HOURLY_G, "jam_tertulis": [1, 51], "ambang": 0.5, "hari": [["18-10", 4], ["19-10", 28], ["20-10", 52]],
                      "catatan": "Kolom alat di lembar menulis ventilator, tetapi FiO2, PEEP, dan RR setelan kosong selama 50 jam itu; RR total 16–32/menit.",
                      "kaki": "Membaca angka, bukan kolom alat. AUC 0,94 (eICU, RS disisihkan); AUC 0,97 (MIMIC-IV)."},
        "cek": [["jejak", "Jejak waktu: ditulis 15–66 jam sesudah pulang"], ["kemiripan", "Kemiripan: tidak ada (maks 0,70)"]],
        "verdict_akhir": "Teks mendukung, angka lembar tanda vital tidak, jadi tidak dapat disimpulkan",
        "tombol_utama": "ajukan_audit",
    },
}

CLAIMS: dict[str, dict] = {c["nomor_sep"]: {**c, "sumber_data": SAMPLE} for c in (_KLAIM_A, _KLAIM_B, _KLAIM_E, _KLAIM_G)}


AUDIT_LIST = [
    ('SIN-009-25-54303', 'RS-009', 'nilai', 1.0, 37430200, 1),
    ('SIN-042-25-10632', 'RS-042', 'nilai', 1.0, 39470200, 0),
    ('SIN-077-25-88038', 'RS-077', 'nilai', 1.0, 40277400, 1),
    ('SIN-077-25-97260', 'RS-077', 'nilai', 0.9691, 30562900, 1),
    ('SIN-038-25-95555', 'RS-038', 'nilai', 0.5907, 24786200, 0),
    ('SIN-054-25-94781', 'RS-054', 'nilai', 0.4926, 15455900, 1),
    ('SIN-072-25-62612', 'RS-072', 'nilai', 0.4522, 17916600, 0),
    ('SIN-119-25-04119', 'RS-119', 'nilai', 0.437, 18145300, 1),
    ('SIN-139-25-72348', 'RS-139', 'nilai', 0.384, 23217400, 0),
    ('SIN-038-25-99372', 'RS-038', 'nilai', 0.3482, 14639200, 1),
    ('SIN-042-25-49216', 'RS-042', 'eksplorasi', 0.3348, 27922800, 0),
    ('SIN-114-25-45202', 'RS-114', 'nilai', 0.3327, 12386800, 1),
    ('SIN-027-25-83412', 'RS-027', 'nilai', 0.2129, 82931400, 0),
    ('SIN-078-25-57170', 'RS-078', 'nilai', 0.2048, 12955300, 0),
    ('SIN-067-25-42735', 'RS-067', 'eksplorasi', 0.1673, 45098200, 0),
    ('SIN-058-25-94165', 'RS-058', 'nilai', 0.1662, 40854800, 0),
    ('SIN-027-25-85976', 'RS-027', 'eksplorasi', 0.1382, 33592700, 0),
    ('SIN-064-25-41182', 'RS-064', 'eksplorasi', 0.1182, 57715400, 0),
    ('SIN-014-25-25152', 'RS-014', 'nilai', 0.1147, 104981800, 0),
    ('SIN-120-25-43242', 'RS-120', 'nilai', 0.1115, 24268500, 0),
    ('SIN-145-25-03503', 'RS-145', 'nilai', 0.1061, 23046400, 0),
    ('SIN-009-25-84090', 'RS-009', 'nilai', 0.1017, 53320400, 0),
    ('SIN-139-25-61155', 'RS-139', 'nilai', 0.0971, 15972900, 0),
    ('SIN-085-25-25054', 'RS-085', 'nilai', 0.0954, 14783600, 0),
    ('SIN-065-25-73415', 'RS-065', 'nilai', 0.092, 64730500, 0),
    ('SIN-130-25-80949', 'RS-130', 'nilai', 0.0903, 65877800, 0),
    ('SIN-052-25-17023', 'RS-052', 'nilai', 0.0866, 62211700, 0),
    ('SIN-058-25-01158', 'RS-058', 'nilai', 0.0856, 142791000, 0),
    ('SIN-027-25-78063', 'RS-027', 'nilai', 0.0832, 145917200, 0),
    ('SIN-043-25-90231', 'RS-043', 'nilai', 0.0812, 45167800, 0),
    ('SIN-081-25-36586', 'RS-081', 'nilai', 0.0641, 70725600, 0),
    ('SIN-108-25-47926', 'RS-108', 'nilai', 0.0607, 84722500, 0),
    ('SIN-104-25-19755', 'RS-104', 'nilai', 0.0571, 89008000, 0),
    ('SIN-081-25-18169', 'RS-081', 'eksplorasi', 0.0532, 41274900, 0),
    ('SIN-144-25-07259', 'RS-144', 'nilai', 0.0516, 24997400, 0),
    ('SIN-111-25-66349', 'RS-111', 'nilai', 0.0507, 42264200, 0),
    ('SIN-118-25-24083', 'RS-118', 'eksplorasi', 0.0489, 33277400, 0),
    ('SIN-118-25-04989', 'RS-118', 'nilai', 0.0461, 62854800, 0),
    ('SIN-081-25-86146', 'RS-081', 'eksplorasi', 0.0438, 37906200, 0),
    ('SIN-125-25-21646', 'RS-125', 'nilai', 0.0414, 48342900, 0),
    ('SIN-116-25-15605', 'RS-116', 'eksplorasi', 0.0401, 17999900, 0),
    ('SIN-086-25-56248', 'RS-086', 'nilai', 0.0378, 23669900, 0),
    ('SIN-042-25-64521', 'RS-042', 'nilai', 0.0336, 58129300, 0),
    ('SIN-090-25-06070', 'RS-090', 'nilai', 0.0289, 21441200, 0),
    ('SIN-094-25-89964', 'RS-094', 'nilai', 0.0288, 38943500, 0),
    ('SIN-054-25-82415', 'RS-054', 'nilai', 0.0286, 48737000, 0),
    ('SIN-118-25-44272', 'RS-118', 'nilai', 0.0256, 26062600, 0),
    ('SIN-092-25-63785', 'RS-092', 'nilai', 0.0252, 18196100, 0),
    ('SIN-016-25-49133', 'RS-016', 'nilai', 0.0246, 26468000, 0),
    ('SIN-135-25-76294', 'RS-135', 'nilai', 0.0225, 35866600, 0),
    ('SIN-027-25-81366', 'RS-027', 'nilai', 0.0224, 34231000, 0),
    ('SIN-147-25-11204', 'RS-147', 'nilai', 0.0196, 31238200, 0),
    ('SIN-006-25-54748', 'RS-006', 'nilai', 0.0191, 19147400, 0),
    ('SIN-095-25-32288', 'RS-095', 'nilai', 0.0186, 18540000, 0),
    ('SIN-062-25-16223', 'RS-062', 'nilai', 0.0183, 18093500, 0),
    ('SIN-098-25-11027', 'RS-098', 'nilai', 0.0181, 19874700, 0),
    ('SIN-101-25-64829', 'RS-101', 'nilai', 0.0177, 17278500, 0),
    ('SIN-125-25-01977', 'RS-125', 'nilai', 0.0149, 13510500, 0),
    ('SIN-149-25-33728', 'RS-149', 'nilai', 0.0148, 19048300, 0),
    ('SIN-085-25-20415', 'RS-085', 'eksplorasi', 0.005, 0, 0),
]

AUDIT = {
    "sumber_data": SAMPLE,
    "bulan": "Pembebanan Des 2025, bulan ke-12",
    "pengaturan": {"anggaran": 60, "asal_anggaran": "2 verifikator × 3 klaim/hari × 10 hari (asumsi, bisa diubah)", "kebijakan": "agen",
                   "batas_pi": "Batas bawah π 0,005 memakai ±8 dari 60 audit per bulan untuk eksplorasi",
                   "catatan_urutan": "Peluang: rupiah yang ditemukan hampir sama, tetapi rentang takaran sekitar 30% lebih lebar."},
    "daftar": [{"nomor_sep": s, "kode_rs": rs, "alasan": why, "pi": pi, "dipertaruhkan": stake, "temuan": hit} for s, rs, why, pi, stake, hit in AUDIT_LIST],
    "takaran": {"total": 6875483454, "rentang_resmi": [2.90e9, 10.85e9], "rentang_varians_desain": [4.33e9, 9.42e9], "cakupan_varians_desain": 0.84,
                "ht": 6921605860, "nilai_sebenarnya": 6459675000, "rupiah_ditemukan": 3.1e9, "porsi_ditemukan": 0.47, "skala": 14e9,
                "kaki": "500 simulasi: rentang resmi kena 96% kali; lebar rentang sekitar 1,2 kali total kebocoran."},
    "kurva": {"bulan": ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"],
              "agen": [143, 328, 266, 227, 214, 280, 180, 292, 269, 378, 290, 311], "statis": [106, 139, 70, 57, 70, 163, 74, 126, 85, 148, 102, 90],
              "kaki": "Januari: skor statis sama, tetapi klaim dipilih lewat undian berbobot π, bukan 60 teratas. Pola yang belum diajarkan ke AI 1 dan AI 2 ditemukan median bulan ke-4."},
    "perbandingan": [{"kebijakan": "Agen belajar", "rupiah_per_100": 441e6, "audit_rs_jujur_per_100": 36, "takaran": "kena 96%"},
                     {"kebijakan": "Skor statis", "rupiah_per_100": 171e6, "audit_rs_jujur_per_100": 59, "takaran": "tidak bisa"},
                     {"kebijakan": "Acak saja", "rupiah_per_100": 43e6, "audit_rs_jujur_per_100": 56, "takaran": "kena 95%"}],
    "kaki_perbandingan": "500 simulasi, RS beradaptasi; agen menyentuh 69 dari 83 RS jujur.",
}

LINES = {
    "sumber_data": SAMPLE,
    "subjudul": "AI 4 membaca sendiri kode dan ambang tempat tarif INA-CBG melompat; setiap garis diuji dulu, lalu disetujui admin sebelum dipakai.",
    "cakupan": "Wilayah Uji, 150 RS, Jan–Des 2025",
    "ubin": [{"nilai": "32", "satuan": "garis", "keterangan": "ditemukan AI 4: 1 ambang, 31 kode", "label": ["AI 4"], "asal": "pohon 99,7% + pindai langsung"},
             {"nilai": "6", "satuan": "garis", "keterangan": "menyala: 3 aktif, 3 temuan", "label": ["Statistik", "AI 1"], "asal": "asimetri dan uji per RS"},
             {"nilai": "28", "satuan": "garis", "keterangan": "garis temuan menunggu admin", "label": ["AI 4"], "asal": "belum memengaruhi penandaan"},
             {"nilai": "72 jam", "satuan": "", "keterangan": "garis jam baru di dunia iDRG tiruan", "label": ["AI 4"], "asal": "ditemukan ulang tanpa ubah kode"}],
    "garis": [
        {"id": "96.71", "nama": "96.71, ventilasi <96 jam", "jenis": "kode prosedur", "grup": "grup medis → J-1-20", "kali": "×4,7", "menyala": True, "uji": "6 RS ditandai", "rupiah": "Rp1,5 M", "rentang": "rentang 0,8–2,4 M", "status": "aktif"},
        {"id": "96.04", "nama": "96.04, intubasi", "jenis": "kode prosedur", "grup": "grup medis → J-1-20", "kali": "×4,5", "menyala": True, "uji": "5 RS ditandai", "rupiah": "Rp0,5 M", "rentang": "rentang 0,2–1,0 M", "status": "aktif"},
        {"id": "38.95", "nama": "38.95, kateter dialisis", "jenis": "kode prosedur, temuan baru", "grup": "N-4-10 → N-1-12", "kali": "×1,8", "menyala": True, "uji": "10 RS ditandai", "rupiah": "Rp0,5 M", "rentang": "rentang 0,2–0,9 M", "status": "temuan",
         "fakta": ["AI 4: kode ini memindahkan klaim N-4-10 → N-1-12, tarif ×1,8, pada 792 dari 1.132 klaim berkode.",
                   "Uji diakui vs wajar per RS: menyala di 10 RS, perkiraan Rp0,5 M (rentang 0,2–0,9 M).",
                   "Sebelum disetujui, garis ini tidak memengaruhi penandaan maupun antrean kerja."], "judul": "38.95, Kateter vena untuk dialisis"},
        {"id": "E87", "nama": "E87, elektrolit", "jenis": "diagnosis sekunder", "grup": "keparahan I → II", "kali": "×1,4", "menyala": True, "uji": "1 RS ditandai", "rupiah": "Rp37 jt", "rentang": "rentang 14–66 jt", "status": "temuan",
         "fakta": ["AI 4: diagnosis sekunder E87 menaikkan keparahan I → II, tarif ×1,4.", "Uji per RS: menyala di 1 RS, perkiraan Rp37 jt (rentang 14–66 jt).",
                   "Garis ini termasuk dua garis yang menyala di DEV padahal tidak dimanipulasi (T20 gagal)."], "judul": "E87, Gangguan elektrolit (diagnosis sekunder)"},
        {"id": "39.95", "nama": "39.95, hemodialisis", "jenis": "kode, pindai langsung", "grup": "beragam", "kali": "×3,9", "menyala": True, "uji": "5 RS ditandai", "rupiah": "Rp24 jt", "rentang": "rentang 0–82 jt", "status": "temuan",
         "fakta": ["AI 4: kode 39.95 ditemukan lewat pindai kode langsung, kenaikan tarif ×3,9 di beberapa grup.", "Uji per RS: menyala di 5 RS, perkiraan Rp24 jt (rentang 0–82 jt).",
                   "Garis ini termasuk dua garis yang menyala di DEV padahal tidak dimanipulasi (T20 gagal)."], "judul": "39.95, Hemodialisis"},
        {"id": "jam96", "nama": "Jam ventilasi ≥96", "jenis": "ambang, lewat kode 96.72", "grup": "J-1-20 → J-1-02", "kali": "×2,2", "menyala": True, "uji": "S(96) +0,20", "rupiah": "Rp0–5,7 M", "rentang": "belum terukur", "status": "aktif", "rincian": True},
        {"id": "31.1", "nama": "31.1, trakeostomi", "jenis": "kode prosedur", "grup": "J-1-02 → J-1-01", "kali": "×1,5", "menyala": False, "uji": "0 RS", "rupiah": None, "rentang": None, "status": "aktif"},
        {"id": "lain", "nama": "25 garis lain", "jenis": "34.04, 31.29, 88.72, …", "grup": "beragam", "kali": "×1,4–9,4", "menyala": False, "uji": "0 RS", "rupiah": None, "rentang": None, "status": "temuan"},
    ],
    "kaki_tabel": "Menampilkan 8 baris dari 32 garis; garis yang tidak menyala diringkas.",
    "terpilih": "38.95",
    "t24": {"judul": "Uji kenyataan T24, 168.988 klaim: 4 dari 4 jalur yang sudah diketahui ditemukan ulang tanpa diberi tahu.",
            "jalur": ["96.71 → J-1-20", "96.72 → J-1-02", "Trakeostomi → J-1-01", "96.04 → J-1-20"],
            "catatan": "96.04 dan trakeostomi ditemukan lewat pindai kode langsung. Dihitung di laptop; hanya agregat nasional, tanpa menilai fasilitas tertentu."},
    "rincian_jam": {"fakta": ["Ambang lewat kode 96.72: J-1-20 → J-1-02, tarif ×2,2.", "Uji asimetri: S(96) +0,20 (rentang +0,01 sampai +0,39). Plasebo 120 dan 144 jam bersih.",
                              "Rupiah belum terukur: rentang Rp0–5,7 M. Di DEV nilai tertanamnya Rp0,62 M."],
                    "titik": [[24, -0.235, -0.352, -0.126], [48, -0.034, -0.172, 0.111], [72, -0.236, -0.412, -0.057], [96, 0.196, 0.010, 0.385],
                              [120, 0.029, -0.182, 0.251], [144, 0.048, -0.168, 0.280], [168, -0.041, -0.309, 0.255]],
                    "keterangan": "Sumbu X: garis jam ventilasi. S(L): penumpukan klaim tepat di atas garis dibanding di bawahnya, dikoreksi pola 24 jam. Garis tegak = rentang 95%.",
                    "catatan": "Uji ini lemah: di dunia kembar tanpa kecurangan pun S(96) = +0,14, dan kelebihan 20 klaim tidak bisa dibedakan dari variasi alami (±50 klaim). Bukti per klaim datang dari AI 2, yang menghitung jam dari RME."},
    "catatan_jujur": "Garis temuan adalah pola pembayaran yang dibaca model pengganti, bukan aturan grouper resmi, dan belum memengaruhi penandaan sebelum disetujui admin. Uji DEV T20 gagal: 2 garis yang tidak dimanipulasi ikut menyala (E87 dan 39.95).",
}

REPORT = {
    "sumber_data": SAMPLE,
    "periode": "Desember 2025",
    "kepala": {"wilayah": "Wilayah Uji (data sintetis)", "dianalisis": "Dianalisis 1 Jan 2026 02.00, model tapal-1.0", "judul": "Ringkasan pemeriksaan garis tarif, Desember 2025",
               "sub": "Penilaian RS memakai data 12 bulan (Jan–Des 2025); klaim yang diperiksa: pembebanan Desember 2025."},
    "angka": [{"nilai": "9 dari 150", "label": "RS ditandai", "sub": "8 oleh AI 1, 1 oleh AI 2"},
              {"nilai": "Rp5,3 miliar", "label": "perkiraan kelebihan bayar 12 bulan", "sub": "rentang Rp4,3–6,4 miliar"},
              {"nilai": "1 RS", "label": "dengan RME meragukan", "sub": "RS-140, lolos pemeriksaan klaim"}],
    "rs": [{"kode_rs": "RS-031", "modus": "diperpanjang", "diakui": "214 vs 178", "perkiraan": "Rp1,37 miliar", "rentang": "0,98–1,79", "bukti": "Jam ventilator menumpuk di 96–104; RME belum dibaca", "tindak": "Audit"},
           {"kode_rs": "RS-117", "modus": "diperpanjang", "diakui": "131 vs 90", "perkiraan": "Rp1,23 miliar", "rentang": "0,91–1,58", "bukti": "RME: jam < 96 pada 13 dari 18 klaim yang dibaca", "tindak": "Klarifikasi (berjalan)"},
           {"kode_rs": "RS-092", "modus": "fiktif", "diakui": "141 vs 78", "perkiraan": "Rp0,93 miliar", "rentang": "0,78–1,07", "bukti": "RME hanya menyebut nasal kanul pada 21 dari 25 klaim", "tindak": "Klarifikasi"},
           {"kode_rs": "RS-140", "modus": "rme_meragukan", "diakui": "lolos AI 1", "perkiraan": "Rp0,72 miliar", "rentang": "dipertaruhkan, 41 klaim", "bukti": "Catatan ICU mirip (median 0,96) dan ditulis massal", "tindak": "Audit"},
           {"kode_rs": "RS-019", "modus": "diperpanjang", "diakui": "167 vs 151", "perkiraan": "Rp0,65 miliar", "rentang": "0,21–1,08", "bukti": "Keyakinan lemah (q = 0,04)", "tindak": "Klarifikasi"}],
    "lampiran": [["SIN-031-25-00211", "RS-031", 41770900, "belum dibaca"], ["SIN-117-25-00903", "RS-117", 30593400, "RME 88 jam vs diklaim 99 jam"],
                 ["SIN-092-25-00412", "RS-092", 13497000, "tidak mendukung: nasal kanul, kutipan cocok 3 dari 3"],
                 ["SIN-140-25-01455", "RS-140", 49532200, "isi mendukung; asal-usul catatan meragukan"], ["SIN-019-25-00098", "RS-019", 42584900, "belum dibaca"]],
    "ket_lampiran": "Daftar lengkap: 63 klaim RS-092, 41 klaim RS-140, dan klaim teratas RS lain ada di berkas CSV terlampir.",
    "sumber": "Data E-Klaim pembebanan Desember 2025 dan penilaian RS Jan–Des 2025 (sintetis); tarif INA-CBG Permenkes 3/2023; model tapal-1.0; dianalisis 1 Jan 2026 02.00",
    "kaki": "Sinyal untuk diperiksa, bukan tuduhan. Keputusan ada di verifikator. Jangan diedarkan sebelum klarifikasi RS.",
    "fakta_narasi": {"tiga_rs": ["Rp3,53 miliar", "jumlah perkiraan tiga RS teratas (Kode)"], "total": ["Rp5,3 miliar", "perkiraan kelebihan bayar 12 bulan (AI 1, Kode)"],
                     "klaim_nasal": ["21", "RME RS-092 yang hanya menyebut nasal kanul (AI 2)"], "klaim_dibaca": ["25", "RME RS-092 yang dibaca (AI 2)"],
                     "catatan_kembar": ["41", "catatan ICU RS-140 yang nyaris identik (AI 2, Kode)"], "median_mirip": ["0,96", "median kemiripan catatan RS-140 (AI 2, Kode)"]},
    "templat_narasi": ["Tiga RS menyumbang {tiga_rs} dari {total} perkiraan kelebihan bayar selama 12 bulan.",
                       "Rupiah terbesar ada pada klaim ventilasi diperpanjang di RS-031 (kelas A) dan RS-117 (kelas B).",
                       "Di RS-092, {klaim_nasal} dari {klaim_dibaca} RME yang dibaca hanya menyebut nasal kanul atau masker oksigen.",
                       "RS-140 lolos pemeriksaan berbasis klaim, tetapi {catatan_kembar} catatan ICU-nya mirip satu sama lain (median {median_mirip}) dan ditulis massal.",
                       "Usulan: audit RS-031 dan RS-140; klarifikasi RS-117, RS-092, dan RS-019."],
}

LETTER = {
    "RS-092": {"kepada": "Direktur RS-092", "perihal": "Permintaan klarifikasi klaim ventilasi mekanik", "tanggal": "31 Desember 2025",
               "fakta": {"diakui": ["141 klaim", "diakui (AI 1, Statistik)"], "wajar": ["78 klaim", "wajar menurut bukti (AI 1, Statistik)"],
                         "wajar_bawah": ["69", "rentang 95% wajar"], "wajar_atas": ["88", "rentang 95% wajar"], "kelebihan": ["63 klaim", "diakui dikurangi wajar (Kode)"]},
               "templat": ["Berdasarkan pemeriksaan pasca-klaim Januari–Desember 2025, RS-092 mengajukan {diakui} garis ventilator (ventilasi mekanik atau intubasi), sedangkan bukti pada klaim hanya mendukung sekitar {wajar} (rentang {wajar_bawah}–{wajar_atas}).",
                           "Untuk {kelebihan} terlampir, kami mohon RS mengirimkan dokumen pendukung pemakaian ventilator: laporan tindakan intubasi, lembar observasi ventilator per jam, dan catatan penyapihan."],
               "penutup": "Surat ini adalah permintaan klarifikasi, bukan kesimpulan pemeriksaan. Mohon dokumen dikirim sesuai jangka waktu klarifikasi yang berlaku.",
               "lampiran": "Lampiran: daftar 63 klaim (nomor SEP, tanggal layanan, selisih tarif) dari Profil RS-092."},
}
