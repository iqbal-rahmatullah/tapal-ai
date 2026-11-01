# TAPAL v2 — Target uji yang ditulis sebelum uji

> **Status: disetujui pengguna dan dikunci, 31 Oktober 2026.** Hash SHA-256 berkas ini tercatat di `TARGETS.lock` dan di papan Notion (tugas 100). Berkas ini tidak diubah lagi; perubahan yang tetap diperlukan sebelum segel TEST dibuka mengikuti bagian 10.

Ditulis 31 Oktober 2026, **sebelum generator dunia v2 dan mesin v2 dibuat**. Berkas ini menggantikan TARGETS v1 (berkas lokal di luar repo, `tapal-ai/TARGETS.md`, dibekukan 5 Oktober 2026). Isinya tidak boleh diubah setelah kunci jawaban TEST dibuka. Perubahan sebelum itu wajib dicatat di *Riwayat perubahan* beserta alasannya, dan hash barunya dicatat. Semua hasil dilaporkan apa adanya, termasuk target yang gagal.

Pelajaran dari uji buta v1 yang membentuk berkas ini:
- T1 recall modus diperpanjang gagal (3 dari 9 RS, 33%). Ambangnya **tidak** diturunkan.
- RS cerdik modus fiktif lolos semua (0 dari 5). Karena itu v2 membaca RME untuk seluruh populasi garis ventilator (bagian 6), termasuk klaim intubasi saja.
- Dunia sintetis v1 terlalu optimistis. Di Data Sampel, kode intubasi hanya ada di sekitar 1 dari 5 klaim ventilasi, sedangkan di dunia sintetis 4 dari 5. Dunia v2 dikalibrasi dari agregat Data Sampel.
- Dunia v1 hanya berisi pasien medis dengan 5 diagnosis. Di Data Sampel, hanya 21% klaim berventilasi yang berdiagnosis itu, dan ±24% klaim 96.71 adalah pasien operasi besar. Riset jalur tarif 31 Oktober 2026 (berkas lokal di luar repo, `tapal-percobaan/jalur-tarif-ventilasi/HASIL.md`) juga menemukan jalur trakeostomi (J-1-01) dan jalur intubasi saja (96.04 → J-1-20).

## 1. Lingkup
- **Garis:** ventilator. Tarif mengikuti Permenkes 3/2023.
  - Grup tujuannya tiga: J-1-20 (prosedur pernapasan non-kompleks), J-1-02 (ventilasi ≥96 jam tanpa trakeostomi), dan J-1-01 (ventilasi ≥96 jam dengan trakeostomi).
  - Kode pemicunya 96.71, 96.72, dan intubasi 96.04. Kode 96.04 saja sudah bisa membawa klaim ke J-1-20.
- **Klaim:** rawat inap bukan bayi, termasuk **pasien operasi besar**.
  - Pada pasien operasi, 96.71 tidak memindahkan grup; tarifnya ditentukan operasinya. Karena itu pasien operasi menjadi kontrol alami modus fiktif.
  - 96.72 tetap memindahkan klaim pasien operasi ke J-1-02, kecuali beberapa operasi jantung yang tarifnya lebih tinggi.
- **Bayi dikeluarkan.** Grup neonatal P-8 punya jalur tarif sendiri: di sana 96.72 menjadikan klaim "dengan prosedur mayor", dan besar lompatannya bergantung berat lahir. Garis ini digabung dengan garis berat lahir di masa finalis.
- **Modus:**
  - ventilasi fiktif, termasuk varian intubasi saja (kode 96.04 tanpa kode ventilasi);
  - ventilasi diperpanjang;
  - RME meragukan: catatan kloning antarpasien, atau ditulis massal setelah pasien pulang;
  - satu modus tersembunyi (bagian 3).
- **Tingkat pelaku:**
  - *biasa*: hanya kode atau jam yang dimanipulasi; bukti lain di klaim tidak ikut diubah;
  - *cerdik-1*: bukti pendukung di klaim ikut dipalsukan (kode intubasi, analisa gas darah, sewa alat), tetapi RME tetap jujur;
  - *cerdik-2 (RME karangan)*: teks RME juga menyebut ventilator, tetapi tanda vital, setelan alat, dan jejak waktu penulisan tidak ikut dipalsukan secara konsisten;
  - *cerdik-3*: semuanya dipalsukan secara konsisten. Ini di luar jangkauan uji berbasis dokumen (F1).
- **Mesin yang diuji:**
  - AI 1: peluang klaim didukung bukti;
  - AI 2: LLM pembaca RME, model asersi, pembaca fisiologi, kemiripan catatan, dan jejak waktu;
  - AI 3: agen audit yang belajar;
  - AI 4: penemu garis tarif;
  - Statistik: uji per RS dan uji asimetri garis.
- Garis lain hanya ditemukan dan diurutkan oleh AI 4, tidak dibedah tuntas. Garis berat lahir masuk masa finalis.

## 2. Sumber data
- **Dunia sintetis.**
  - Isinya 150 RS kelas A–D di regional 1–5, dengan klaim Januari–Desember 2025. Tarif diambil dari tabel Permenkes 3/2023.
  - Angka dasarnya dikalibrasi dari agregat Data Sampel Reguler. Baris data asli tidak pernah dicampur ke dunia sintetis.
- **Data Sampel BPJS 2025.**
  - Diolah lokal di laptop; yang keluar hanya agregat.
  - Dipakai untuk kalibrasi, uji kenyataan AI 1 (set Reguler), validasi luar AI 1 (set DM), dan pindai garis AI 4 (set Reguler, agregat nasional).
  - Data Sampel tidak memuat jam ventilasi, jadi garis jam hanya diuji di dunia sintetis.
- **Data ICU terbuka**, bersyarat izin unduh (tugas 205).
  - eICU-CRD Demo v2.0.1 untuk melatih pembaca fisiologi, dan MIMIC-IV Demo v2.2 untuk validasi luar.
  - Lisensinya ODbL v1.0. Isinya data pasien luar negeri yang sudah dianonimkan, bukan data JKN.
- Tidak ada data peserta JKN riil di repo, aplikasi, maupun keluaran.

## 3. Aturan uji buta
1. **DEV** dipakai untuk mengembangkan dan menyetel. Seed-nya tetap, dan kunci jawabannya boleh dibuka.
2. **TEST** dibangkitkan dengan seed acak dan hanya dipakai **sekali**. Yang diacak:
   - RS pelaku, intensitas, dan tingkat pelaku, diambil dari rentang;
   - kebiasaan dokumentasi (termasuk jeda tulis RME) dan derau bukti, yang digeser dari DEV.
3. **Modus tersembunyi** dan **garis kedua yang dimanipulasi** (untuk AI 4) dipilih acak dari daftar kandidat di generator saat TEST dibangkitkan (pasangan yang mekanismenya sama, misalnya sama-sama diagnosis sekunder palsu, tidak diundi bersama), dan pilihannya hanya tercatat di kunci tersegel. Modus tersembunyi aktif sejak bulan pertama di RS pelakunya. Daftar kandidat ditetapkan di generator sebelum mesin mana pun dibuat. Mesin tidak boleh memuat aturan atau label khusus untuk kandidat mana pun.
4. **Gaya tulisan RME:** generator punya beberapa gaya tulisan. Satu gaya disisihkan dan hanya muncul di TEST. AI 2, termasuk prompt LLM dan daftar kata kuncinya, tidak boleh memuat kosakata atau aturan khusus gaya yang disisihkan; hal ini dicek otomatis oleh uji penjaga sebelum TEST dijalankan.
5. Kunci jawaban TEST disimpan di `data/sealed/`, yang tidak ikut repo. Hash SHA-256-nya dicatat di `TARGETS.lock` (bukan di berkas ini) sebelum mesin dibuat; lihat bagian 10.
6. Kunci tersegel hanya boleh dibuka di langkah evaluasi (tugas 720), dengan urutan ini:
   1. semua pengaturan dibekukan, lalu hash pembekuan mesin (kode, berkas model, konfigurasi) dicatat sebagai baris baru di `TARGETS.lock`;
   2. hash berkas ini dan hash kunci dicocokkan dengan `TARGETS.lock`;
   3. pengguna memberi aba-aba.
7. Kolom kebenaran selalu disimpan terpisah dari data klaim dan RME, juga untuk DEV.
8. Target dinilai pada kondisi **Dasar** (bagian 4). Kondisi lain dilaporkan, bukan target.
9. LLM terlalu lambat untuk membaca semua RME di laptop (±48 detik per RME). Karena itu:
   - ketepatan bacaan LLM (T7–T10) dinilai pada sampel `N_LLM`;
   - penandaan tingkat RS oleh AI 2 (T11–T13) memakai lapis cepat (asersi, fisiologi, kemiripan, jejak waktu, kata kunci) pada semua RME di populasi garis ventilator.

## 4. Kondisi uji
| Kondisi | Isi | Status |
|---|---|---|
| Dasar | 6–15% RS per modus menjadi pelaku, intensitas 8–30%, campuran tingkat biasa, cerdik-1, dan cerdik-2 | **target dinilai di sini** |
| Kasus sulit | derau bukti lebih besar, ekor keterlambatan catatan jujur lebih berat, "hari sibuk" di RS jujur yang menulis massal (seluruh catatan seorang pasien ditunda), dan porsi RS cerdik lebih tinggi | dilaporkan |
| Jarang | 0,5% klaim di populasi garis ventilator dimanipulasi | dilaporkan |
| Sering | 10% klaim di populasi garis ventilator dimanipulasi | dilaporkan |
| Terkonsentrasi | manipulasi hanya di ≤5 RS dengan intensitas tinggi | dilaporkan |
| iDRG tiruan | aturan grouper diubah: garis jam digeser dan ada satu kode pemicu baru | hanya untuk T21 |

Semua kondisi TEST memakai satu seed, sehingga klaim jujur dan RS pelaku identik antarkondisi dan yang berubah hanya dial kondisinya. Kasus sulit sengaja ikut mengubah klaim jujur (derau bukti dan ekor keterlambatan catatan).

## 5. Konstanta beku
| Nama | Nilai | Keterangan |
|---|---|---|
| `SEED_DEV` | 20261031 | seed generator DEV |
| `SEED_TEST` | acak saat dibangkitkan | hanya tersimpan di kunci tersegel |
| `N_RS` | 150 | RS kelas A–D, regional 1–5 |
| `PERIODE` | Januari–Desember 2025 | 12 bulan pembebanan |
| `N_FOLD` | 5 | GroupKFold per RS (*cross-fitting*) |
| `BH_Q` | 0,05 | batas *false discovery rate* Benjamini–Hochberg |
| `MIN_KLAIM` | 30 | minimal klaim layak per RS per modus agar RS dinilai |
| `TOP_K` | 50 | presisi pada 50 klaim teratas |
| `GARIS` | 96 jam | garis tarif J-1-20 → J-1-02 |
| `LEBAR` | 8 jam | setengah lebar jendela uji asimetri |
| `GARIS_PEMBANDING` | 120, 144, 168 jam | kelipatan 24 jam tanpa lompatan tarif |
| `GARIS_PLASEBO` | 120, 144 jam | diuji seolah-olah garis tarif |
| `JENDELA` | 72–119 jam | populasi model modus diperpanjang |
| `B_BOOT` | 1000 | ulangan bootstrap, dicuplik per RS |
| `LLM` | `gemma4:e4b-it-qat` lewat Ollama 0.40.13 | digest model `ee665637121887cf…`; pembaruan otomatis Ollama dimatikan sebelum TEST |
| `LLM_OPSI` | suhu 0, seed 42, `num_ctx` 8192, `think` false, keluaran dipaksa skema JSON | dikirim eksplisit di setiap panggilan |
| `LLM_BATAS` | 120 detik | lewat dari itu, aturan cadangan dipakai |
| `N_LLM` | 300 RME | sampel acak berlapis (modus × tingkat pelaku × gaya tulisan) dari TEST; ±4 jam komputasi di M1 |
| `KAPASITAS_AUDIT` | 60 klaim per bulan | 2 verifikator × 3 klaim/hari × 10 hari |
| `POPULASI_AUDIT` | populasi garis ventilator pada bulan itu | lihat definisi di bagian 6 |
| `PI_MIN` | 0,005 | batas bawah peluang terpilih setiap klaim di populasi audit |
| `BULAN_SIM` | 12 | lingkar bulanan agen audit |
| `N_ULANG` | 500 | ulangan simulasi untuk cakupan rentang |
| `LOMPATAN_MIN` | ×1,2 | lompatan tarif minimal agar sebuah ambang atau kode dianggap garis oleh AI 4 |

## 6. Definisi
- **Kode ventilasi** (arti sempit): 96.70, 96.71, dan 96.72. Arti sempit ini dipakai di skor poin, asimetri garis, dan klaim layak modus diperpanjang.
- **Kode pemicu garis ventilator:** kode ventilasi ditambah intubasi 96.04.
- **Populasi garis ventilator** (arti luas): klaim rawat inap bukan bayi yang dibayar di grup J-1-20, J-1-02, atau J-1-01, atau yang memuat kode pemicu. AI 1, AI 2, dan agen audit memakai populasi ini, termasuk klaim intubasi saja.
- **Label AI 1 (modus fiktif):** kode pemicu tercatat. Intubasi 96.04 adalah bagian label, bukan fitur (keputusan pengguna 31 Okt 2026, opsi A).
- **Fitur terlarang AI 1:** kolom yang ikut menentukan label atau grup bayar, yaitu kode pemicu, grup INA-CBG, severitas, tarif atau tagihan (jumlah yang ditagihkan ke BPJS, yaitu tarif INA-CBG; rincian tarif RS bukan tagihan dan boleh dipakai), jam ventilasi, ID RS, kolom kunci jawaban, dan turunan apa pun dari kolom itu (misalnya jumlah prosedur yang ikut menghitung kode pemicu). Versi utama AI 1 juga tidak memakai status pulang (keputusan pengguna 31 Okt 2026), karena status pulang adalah hasil perawatan, bukan bukti tindakan; versi dengan status pulang hanya dilaporkan sebagai pembanding.
- **Klaim layak (modus fiktif):** rawat ICU bukan bayi pada **pasien medis** dengan diagnosis sasaran. Klaim layak menjadi penyebut intensitas fiktif dan dasar `MIN_KLAIM`, T1, dan T11. Pasien operasi besar **tidak** termasuk klaim layak, karena 96.71 tidak menaikkan tarif mereka; mereka hanya ikut di populasi model AI 1 sebagai kontrol, dan alarm palsu pada mereka dilaporkan terpisah. Daftar diagnosis sasaran dan operasi besar ditetapkan di kontrak data (tugas 110) dari campuran Data Sampel, sebelum generator dijalankan.
- **Klaim layak (modus diperpanjang):** klaim berkode 96.71 atau 96.72 (arti sempit), pasien medis maupun operasi, **kecuali** pasien operasi jantung yang grupnya tidak pindah ke J-1-02 saat melewati 96 jam (misalnya bypass koroner dan katup jantung, yang tarifnya lebih tinggi dari J-1-02). Daftar grup yang dikecualikan ditetapkan di kontrak data (tugas 110) dari pola Data Sampel. Model dan uji O/E modus ini memakai klaim dengan jam tercatat di `JENDELA`.
- **Intensitas:**
  - fiktif: porsi klaim layak modus fiktif (pasien medis) tanpa ventilasi yang ditagih dengan kode pemicu (96.71, atau 96.04 saja);
  - diperpanjang: porsi ventilasi sebenarnya 72–95 jam yang dicatat 96–104 jam;
  - RME meragukan: porsi klaim populasi garis ventilator di RS itu yang catatannya kloning atau ditulis massal;
  - yang dipakai di target adalah **intensitas terwujud**, yaitu porsi klaim di kolam modus itu yang menurut kunci benar-benar dimanipulasi. RS pelaku yang intensitas terwujudnya 0 tidak dihitung sebagai pelaku di T1 dan T11–T13.
- **RS ditandai:** p satu sisi dari z robust lolos BH pada `BH_Q`, di lapis mana pun, **dan** jumlah tercatat melebihi harapan (O > E). z robust = (z − median) / max(MAD, 1) antar-RS: skala robust boleh melebar karena keragaman antar-RS, tetapi tidak boleh di bawah 1, karena z sudah berskala kebetulan. z setiap RS dihitung dari mid-p eksak jumlah Poisson-binomial, P(O > o) + ½·P(O = o), bukan dari pendekatan normal. Peluang per klaim AI 1 dikalibrasi isotonik, dipelajari silang dari RS lain. Aturan ini berlaku untuk semua lapis dan pembanding; untuk aturan tanpa AI, harapannya adalah laju gabungan semua RS.
- **Jalur cepat (`lolos_cepat`):** hanya berlaku bila AI 1 menilai risiko rendah **dan** lapis cepat AI 2 bersih. Ambangnya ditetapkan setelah AI 2 selesai, sebelum tugas 720.
- **Presisi pada k:** presisi harapan atas semua undian pemecah seri di batas k, yaitu (klaim positif di atas batas + (k − jumlah klaim di atas batas) × porsi positif di antara nilai kembar) / k. Berlaku untuk semua pihak (AI 1, model sederhana, skor poin) dan semua ukuran sejenis (T6, kapasitas audit, T22/T23); alasannya kestabilan.
- **Kode operasi besar di Data Sampel (T22, T23):** kode prosedur yang ≥50% dari ≥10 klaimnya jatuh di grup operasi besar, dihitung tanpa klaim 96.72 (hanya 96.72 yang memindahkan klaim bedah ke J-1-02), lalu dikurangi tindakan non-operasi hasil periksa akal sehat: 38.91 (kateterisasi arteri), 38.95 (kateter vena untuk dialisis), dan 90.06 (pemeriksaan sitologi). Hasilnya 60 kode, dibekukan di `engine/reality.py`.
- **Asimetri garis (log-rasio), sama dengan v1:**
  - LR(L) = ln[(n[L, L+8) + 0,5) / (n[L−8, L) + 0,5)], dari jam tercatat klaim berventilasi;
  - S(96) = LR(96) − rerata LR pada `GARIS_PEMBANDING`;
  - untuk garis plasebo L: S(L) = LR(L) − rerata LR pada `GARIS_PEMBANDING` selain L;
  - untuk garis L selain 96 jam (misalnya garis iDRG tiruan), garis pembandingnya L+24, L+48, dan L+72 jam selama bukan garis tarif; untuk L = 96 aturan ini menghasilkan `GARIS_PEMBANDING`;
  - rentang 95% dari bootstrap per RS.
- **Skor poin tanpa AI:** jumlah bendera aturan per klaim. Empat aturan pertama sama dengan v1; aturan kelima ditambahkan di v2 untuk varian intubasi saja:
  - kode ventilasi tanpa kode intubasi 96.04;
  - kode ventilasi dengan `sewa_alat` = 0;
  - jam tercatat 96–100;
  - `icu_los` × 24 < jam tercatat;
  - klaim J-1-20 tanpa kode ventilasi (intubasi saja).
- **Bacaan RME diterima:** semua kutipan LLM cocok kata per kata dengan dokumen, dan model asersi tidak berbeda pendapat. Selain itu, hasilnya "tidak dapat disimpulkan".
- **Diterima tetapi salah:** bacaan diterima yang status ventilasi invasifnya berbeda dari kunci, atau jam ventilasinya meleset lebih dari 2 jam.
- **Rupiah ditemukan (AI 3):** jumlah selisih tarif pada klaim yang diaudit dan menurut kunci memang dimanipulasi.
- **Skor gabungan statis:** pembanding AI 3. Klaim diurutkan menurut nilai harapan dari AI 1 dan AI 2, tanpa belajar dari hasil audit dan tanpa eksplorasi.
- **Cakupan:** porsi ulangan simulasi yang rentang 95% takarannya memuat nilai sebenarnya.
- **Garis ditemukan (AI 4):** ambang atau kode yang lompatan tarifnya ≥`LOMPATAN_MIN` muncul di daftar kandidat AI 4. Kandidat datang dari dua jalan:
  - pohon pengganti;
  - pindai kode langsung: klaim berkode dibandingkan dengan klaim tanpa kode itu di daun pohon yang sama. Kode menjadi kandidat bila kelebihan klaim yang dibayar ≥`LOMPATAN_MIN` di atas tebakan pohon tanpa kode itu mencapai ≥10 klaim dan bermakna (mid-p Poisson, BH pada `BH_Q`).
- **Garis menyala (AI 4):** garis yang lolos uji pada `BH_Q`. Ambang diuji dengan uji asimetri, kode pemicu diuji dengan diakui vs wajar per RS.

## 7. Target
### AI 1 dan statistik (dibawa dari v1)
| # | Target | Ukuran | Ambang |
|---|---|---|---|
| T1 | Recall RS pelaku biasa | porsi RS pelaku tingkat biasa (intensitas ≥10%, ≥`MIN_KLAIM` klaim layak) yang ditandai pada modusnya | ≥80% per modus (fiktif, diperpanjang) |
| T2 | Alarm palsu | porsi RS jujur yang ditandai oleh lapis mana pun; termasuk jebakan puncak 24 jam kuat, pasien lebih berat yang terlihat di kolom, dan RS jujur yang menulis resume serta sebagian catatan secara massal setelah pasien pulang | ≤5% |
| T3 | Garis plasebo | rentang 95% S(120) dan S(144) pada data gabungan semua RS memuat 0 | keduanya lolos |
| T4 | Konfirmasi penumpukan | S(96) pada RS yang ditandai di modus diperpanjang dikurangi S(96) pada RS lain; rentang 95% bootstrap per RS | batas bawah > 0 |
| T5 | Rupiah | median \|perkiraan − sebenarnya\| / sebenarnya, pada RS pelaku yang ditandai benar | ≤25% |
| T6 | AI vs tanpa AI | presisi pada `TOP_K` klaim teratas: AI 1 dibanding skor poin; positifnya hanya klaim modus itu, dan klaim modus lain dikeluarkan dari kumpulan, bukan dihitung salah | ≥2× per modus |

### AI 2 — pembaca RME
| # | Target | Ukuran | Ambang |
|---|---|---|---|
| T7 | Ketepatan bacaan LLM | pada `N_LLM` RME: akurasi status ventilasi invasif di antara bacaan yang diterima | ≥95% |
| T8 | Diterima tetapi salah | porsi bacaan diterima yang salah, dengan semua lapis aktif | ≤2% |
| T9 | Tidak dapat disimpulkan | porsi RME di sampel `N_LLM` yang berakhir "tidak dapat disimpulkan" | ≤15% |
| T10 | Galat jam | median galat absolut jam ventilasi pada bacaan diterima yang invasif | ≤2 jam |
| T11 | RS cerdik-1 | porsi RS cerdik-1 (intensitas ≥10%, ≥`MIN_KLAIM` klaim layak) yang ditandai pada modusnya | ≥80% (v1: 0 dari 5) |
| T12 | RS dengan RME karangan | porsi RS cerdik-2 yang ditandai pada modusnya lewat fisiologi atau jejak waktu | ≥70% |
| T13 | RS dengan RME meragukan | porsi RS pelaku modus RME meragukan yang ditandai | ≥80% |
| T14 | Model asersi | akurasi rata-rata per kelas pada gaya tulisan yang disisihkan | ≥90% |
| T15 | Pembaca fisiologi (bersyarat tugas 205) | AUC peluang ventilasi invasif per jam pada RS eICU yang disisihkan (GroupKFold per RS) | ≥0,85 |

### AI 3 — agen audit yang belajar
| # | Target | Ukuran | Ambang |
|---|---|---|---|
| T16 | Nilai belajar | rupiah ditemukan selama `BULAN_SIM` bulan: agen dibanding skor gabungan statis, pada kapasitas yang sama | ≥1,1× |
| T17 | Modus tersembunyi | bulan saat agen sudah menemukan ≥3 klaim modus tersembunyi (kumulatif) | paling lambat bulan ke-6 |
| T18 | Takaran tak bias | cakupan rentang 95% dari `N_ULANG` ulangan | 92–98% |

### AI 4 — penemu garis tarif
| # | Target | Ukuran | Ambang |
|---|---|---|---|
| T19 | Garis ditemukan | semua garis di grouper sintetis muncul di daftar kandidat tanpa diberi tahu: garis 96 jam, kode pemicu 96.71 dan 96.04, trakeostomi → J-1-01, dan garis kedua yang tertanam | 5 dari 5 |
| T20 | Garis menyala | garis yang dimanipulasi menyala; garis tidak dimanipulasi yang ikut menyala dihitung | semua yang dimanipulasi menyala, salah menyala ≤1 |
| T21 | Siap iDRG | di kondisi iDRG tiruan, garis yang berubah ditemukan ulang tanpa mengubah kode | semua |

### Data nyata (Data Sampel, agregat)
| # | Target | Ukuran | Ambang |
|---|---|---|---|
| T22 | Uji kenyataan AI 1 | di set Reguler. **Populasi:** versi Data Sampel dari klaim layak modus fiktif, dihitung dari kolom yang ada di Data Sampel: rawat inap bukan bayi (umur lebih dari 28 hari saat masuk, dari tanggal lahir peserta), diagnosis primer sasaran, tanpa kode operasi besar; syarat rawat ICU tidak dipakai karena kolomnya tidak ada. **Label pengganti:** kode pemicu tercatat (bukan label kecurangan). **Fitur:** tanpa fitur terlarang AI 1 (bagian 6). Diukur AUC dan kalibrasi total (tercatat dibagi diperkirakan) dari prediksi di luar lipatan (validasi silang dikelompokkan per kab/kota, `N_FOLD` lipatan) | AUC ≥0,80; kalibrasi 0,9–1,1 |
| T23 | Validasi luar AI 1 | AUC di set DM, dengan populasi, label, dan fitur yang sama dengan T22, dibanding AUC T22 | turun ≤0,05 |
| T24 | Uji kenyataan AI 4 | di set Reguler, AI 4 menemukan ulang jalur 96.71 → J-1-20, 96.72 → J-1-02, trakeostomi → J-1-01, dan 96.04 → J-1-20 tanpa diberi tahu. Jawabannya sudah diketahui dari riset 31 Okt 2026, jadi ini uji kenyataan, bukan uji buta | 4 dari 4 |

## 8. Dilaporkan, bukan target
- Hasil per kelas RS (A–D) untuk T1 dan T11–T13.
- Porsi rupiah tertanam yang berada di RS yang ditandai.
- Jejak modus fiktif, seperti di v1.
- AUC dan kalibrasi AI 1 pada klaim RS jujur.
- AI 1 juga dalam versi tanpa rincian tarif RS (`tarif_rs`), karena rincian itu dikarang dan tidak ada di Data Sampel; selisihnya menunjukkan seberapa besar kinerja AI 1 bergantung pada data karangan.
- AI 1 juga dalam versi dengan status pulang, di DEV dan di T22/T23, sebagai pembanding versi utama. Status pulang (terutama meninggal) adalah fitur tunggal terkuat di Data Sampel (AUC 0,867).
- Model sederhana (regresi logistik dengan umur, lama rawat, status pulang, dan diagnosis primer) dijalankan di jalur yang sama dengan AI 1 (kalibrasi, uji per RS, putaran ulang): T1, T2, dan plasebo DEV, serta presisi pada `TOP_K` dan pada kapasitas audit untuk kedua model, di DEV dan di Data Sampel. Model sederhana juga dilaporkan tanpa status pulang, agar setara dengan AI 1 versi utama.
- T6 juga dengan klaim RME meragukan dihitung positif. Bila klaim positif lebih sedikit dari k, presisi maksimumnya ditulis dan perbandingannya disebut tidak bermakna.
- Sumbangan tiap lapis AI 2: LLM saja, ditambah asersi, ditambah fisiologi (T8 per lapis).
- Hasil kondisi Kasus sulit, Jarang, Sering, dan Terkonsentrasi.
- **Agen audit:**
  - kurva belajar per bulan;
  - RS jujur yang ikut diaudit;
  - pembanding acak, aturan, dan skor AI 1 statis.
- Pembaca fisiologi di MIMIC-IV Demo (validasi luar).
- Untuk T22 dan T23: average precision beserta prevalensi label; AUC model sederhana (regresi logistik dengan umur, lama rawat, status pulang, dan diagnosis primer); dan AUC pada semua rawat inap bukan bayi sebagai pembanding angka v1 (0,976).
- Daftar garis temuan AI 4 di Data Sampel (agregat nasional), setelah ditinjau pengguna.
- Waktu proses per langkah di laptop demo, termasuk AI 2 per RME.
- Keluaran kit hkeval (tugas 700), bila tersedia.
- Mengikuti Workshop #3 (Henry Lucky, 23 Okt 2026), di samping target:
  - presisi pada k = kapasitas audit (60 klaim per bulan, 720 setahun), di samping presisi pada `TOP_K`;
  - lift terhadap pemilihan acak dan rupiah recall pada k;
  - porsi RS jujur yang ditandai atau diaudit per kelas RS, regional, ukuran, dan tingkat dokumentasi;
  - fraud rate di samping setiap angka presisi, dan jumlah RS di set uji;
  - uji berpasangan (bootstrap per RS) untuk selisih AI 1 dan skor poin pada T6;
  - recall pada k per modus, termasuk modus tersembunyi, dibanding k/N;
  - uji placebo pada kembaran bebas fraud dari dunia yang sama (setiap bendera di sana adalah alarm palsu); plasebo DEV sudah terpakai untuk penyetelan AI 1 (31 Okt 2026), jadi yang independen hanya plasebo TEST;
  - pindai kebocoran: AUC satu fitur untuk setiap kolom publik, ambang 0,80.

## 9. Kegagalan yang diperkirakan, diumumkan sebelum uji
- **F1. RS cerdik-3 lolos.** RS yang memalsukan klaim, teks RME, fisiologi, dan jejak waktu secara konsisten diperkirakan lolos dari semua lapis berbasis dokumen. Hanya audit lapangan yang bisa menangkapnya; eksplorasi agen audit mungkin menemukan sebagian.
- **F2. Alarm palsu dari pasien yang lebih berat.** RS jujur dengan pasien lebih berat yang tidak terlihat di kolom klaim dapat memicu alarm palsu. Hasilnya dilaporkan terpisah dan tidak dimasukkan ke T2.
- **F3. RS kecil sulit dinilai.** RS kecil (terutama kelas D) sering tidak memenuhi `MIN_KLAIM`, atau lolos karena daya ujinya rendah. Di v1, modus diperpanjang kelas C 0/3 dan kelas D 0/3. Periode v2 hanya 12 bulan (v1: 24 bulan), jadi masalah ini bisa lebih berat.
- **F4. Penilaian fisiologi di dunia sintetis optimistis.** Fisiologi sintetis dikalibrasi dari sumber yang sama dengan data latih. Ukuran yang jujur hanya T15 (RS eICU yang disisihkan) dan validasi luar MIMIC-IV.
- **F5. Data ICU dari luar negeri.** Data ICU terbuka berasal dari RS Amerika Serikat; pola tanda vital dan setelan alat di RS Indonesia bisa berbeda.
- **F6. AI 4 di Data Sampel terbatas.** Di sana AI 4 hanya bisa menemukan garis berbasis kode dan lama rawat; garis jam tidak terlihat karena jam ventilasi tidak tercatat.
- **F7. Keluaran LLM belum terbukti identik antar-run.** Pada suhu 0 dan seed tetap pun, kesamaan antar-run atau antar-versi Ollama belum terbukti. Karena itu versinya dikunci (`LLM`) dan setiap jawaban mentah disimpan.
- **F8. Agen audit hanya diuji dalam simulasi.** Hasil auditnya diambil dari kunci dunia uji, bukan dari audit sungguhan.
- **F9. Urutan prioritas grouper disimpulkan dari data.** Aturan mana yang mengalahkan mana (operasi besar, ventilasi panjang, bypass koroner) di dunia sintetis ditiru dari pola pembayaran Data Sampel, bukan dari pedoman INA-CBG. Bila tiruannya keliru, hasil pada pasien operasi bisa bias.

## 10. Hash dan `TARGETS.lock`
- TARGETS v1, dibekukan 5 Oktober 2026: `27db0f7a843230c0e03bf3b909554094fc6c4813b6e0142415d2a682acaa3905` (berkas lokal di luar repo, `tapal-ai/TARGETS.md`).
- `TARGETS.lock` adalah buku catatan tambah-saja di repo. Satu baris berisi hash SHA-256, nama berkas, waktu (WIB), dan keterangan. Urutan barisnya:
  1. hash berkas ini saat disetujui pengguna;
  2. hash kunci TEST di `data/sealed/`, setelah tugas 260 dan sebelum mesin dibuat;
  3. hash pembekuan mesin (kode, berkas model, konfigurasi), di tugas 720, sebelum kunci dibuka.
- Setiap baris baru masuk sebagai commit tersendiri (satu commit per baris) dan disalin ke tugas Notion 100, sehingga waktunya tercatat di dua tempat.
- Hash tidak pernah ditulis di dalam berkas ini, jadi berkas ini tidak perlu disentuh lagi setelah dikunci. Perubahan yang tetap diperlukan sebelum segel dibuka dicatat di *Riwayat perubahan*, dan hash barunya ditambahkan ke `TARGETS.lock` beserta alasannya.
- **Sejak riwayat baris kedelapan, aturan statistik dibekukan.** Sebelum pembekuan mesin, yang masih boleh hanya perbaikan bug, yaitu kode yang tidak melakukan apa yang tertulis di berkas ini. Setiap perbaikan dicatat beserta angka sebelum dan sesudahnya. Hasil yang buruk dilaporkan sebagai target gagal, tidak diperbaiki dengan menyetel ulang aturan.
- **Sejak riwayat baris kesembilan, metode AI 4 juga dibekukan,** dengan aturan yang sama.
- **Sejak riwayat baris kesepuluh, metode AI 2 juga dibekukan,** dengan aturan yang sama.

## 11. Riwayat perubahan
| Tanggal | Perubahan | Alasan |
|---|---|---|
| 31 Okt 2026 | draf dibuat | — |
| 31 Okt 2026 | draf direvisi sebelum dikunci: pasien operasi masuk lingkup; J-1-01 dan 96.04 disebut sebagai bagian garis; populasi garis ventilator didefinisikan; varian intubasi saja masuk modus fiktif; skor poin ditambah satu aturan; T19 diperluas menjadi 5 garis; T24 dan F9 ditambah | riset jalur tarif di Data Sampel (berkas lokal di luar repo, `tapal-percobaan/jalur-tarif-ventilasi/HASIL.md`); empat usulan disetujui pengguna |
| 31 Okt 2026 | draf direvisi lagi sebelum dikunci, dan **sebelum T22 diukur** pada populasi barunya: hash kunci TEST dan hash pembekuan dicatat di `TARGETS.lock`, tidak di berkas ini; istilah "kode ventilasi" (sempit) dan "populasi garis ventilator" (luas) dipisahkan per kemunculan; 96.04 menjadi bagian label AI 1, bukan fitur (opsi A), dan fitur terlarang AI 1 ditulis; klaim layak modus fiktif hanya pasien medis; operasi jantung yang tidak pindah ke J-1-02 dikeluarkan dari modus diperpanjang; T11–T12 ditambah "pada modusnya"; T22 memakai populasi klaim layak modus fiktif versi Data Sampel dengan ambang AUC ≥0,80 (sebelumnya ≥0,90 pada semua rawat inap) dan diukur dari prediksi di luar lipatan per kab/kota, T23 mengikuti; pelaporan AP, prevalensi, dan model sederhana ditambah | tinjauan pengguna atas draf |
| 31 Okt 2026 | disetujui pengguna dan dikunci; hash dicatat di `TARGETS.lock` | — |
| 31 Okt 2026 | direvisi sesudah dikunci, sebelum hash kunci TEST dicatat: intensitas di target ditetapkan sebagai intensitas terwujud; "tagihan" di fitur terlarang AI 1 diperjelas (tarif INA-CBG, bukan rincian tarif RS) dan AI 1 tanpa rincian tarif RS ditambahkan ke pelaporan; garis pembanding diperluas menjadi L+24, L+48, L+72 untuk garis selain 96 jam; jeda tulis RME disebut di kebiasaan yang digeser di TEST; larangan kosakata dan aturan gaya yang disisihkan di AI 2 ditambahkan, dijaga `tests/test_blind_rules.py`; pengundian modus tersembunyi dan garis kedua dibatasi pada pasangan yang mekanismenya berbeda; semua kondisi TEST memakai satu seed; Kasus sulit memakai ekor keterlambatan catatan jujur yang lebih berat dan skenario hari sibuk; jebakan RS jujur yang menulis secara massal ditambahkan ke T2; pelaporan Workshop #3 ditambahkan ke bagian 8 | tinjauan pengguna atas laporan fase 1 (data sintetis). Pemicu aturan gaya: contoh gaya yang disisihkan sempat terlihat oleh pengguna dan pengembang (`contoh-rme.md` no. 7, dibuat dari dunia buangan seed 999, bukan dari TEST). Tambahan dari Workshop #3 dan tinjauan kedua pengguna |
| 31 Okt 2026 | direvisi sesudah hash kunci TEST dicatat, sebelum mesin dibekukan; kunci TEST tidak dibuka maupun dibaca. Isinya: z setiap RS dihitung dari mid-p eksak Poisson-binomial untuk semua lapis dan pembanding; peluang AI 1 dikalibrasi isotonik silang per RS; positif T6 hanya klaim modus itu, dan klaim modus lain dikeluarkan dari kumpulan; jalur cepat hanya bila AI 1 menilai risiko rendah dan lapis cepat AI 2 bersih; kode operasi besar di Data Sampel didefinisikan (60 kode); pelaporan ditambah AI 1 tanpa status pulang dan model sederhana di jalur yang sama dengan AI 1. **Plasebo DEV sudah terpakai untuk penyetelan**, jadi yang independen hanya plasebo TEST | hasil AI 1 di DEV dan pindai T22. Kembaran DEV tanpa fraud menandai 17 RS jujur (peluang terlalu yakin di ujung), lalu 4 RS setelah kalibrasi isotonik (dua sampai tiga klaim ventilasi singkat berkode 96.04 per RS; pendekatan normal gagal), dan 0 RS dengan p eksak di eksperimen. T6 menghukum AI 1 untuk klaim modus lain. Pelaku cerdik lolos AI 1 sepenuhnya, sehingga jalur cepat tanpa AI 2 mengulang kegagalan v1. Di T22, status pulang sendirian mencapai AUC 0,867 dan model sederhana AUC 0,950. Definisi operasi besar berbasis klaim tanpa kode pemicu membuang 15 kode bedah hanya karena jumlah klaimnya di bawah 10. T22 sudah diukur dengan definisi 63 dan 46 kode sebelum keputusan ini (AUC 0,971 pada keduanya). Keputusan pengguna 31 Okt 2026 |
| 31 Okt 2026 | direvisi sebelum mesin dibekukan; kunci TEST tidak dibuka maupun dibaca. Isinya: versi utama AI 1 tidak memakai status pulang (kode di commit `1987cf3`), dan versi dengan status pulang hanya pembanding; presisi pada k memakai presisi harapan atas nilai kembar untuk semua pihak dan semua ukuran sejenis (T6, kapasitas audit, T22/T23); model sederhana juga dilaporkan tanpa status pulang; porsi RS jujur yang ditandai juga dilaporkan per tingkat dokumentasi | status pulang adalah hasil perawatan, bukan bukti tindakan, mudah dimainkan, dan bisa merugikan RS yang berhasil menyelamatkan pasien. Sendirian ia mencapai AUC 0,867 di Data Sampel, dan dengan status pulang plasebo DEV menandai 2 RS jujur. Harganya: T22 turun dari 0,971 ke 0,946, dan semua target yang lolos tetap lolos. Presisi skor poin berubah 0,14–0,20 antarvarian di run yang sama hanya karena undian pemecah seri; alasan perbaikannya kestabilan, bukan hasil, karena presisi harapan hanya mengambil nilai tengah dari angka yang naik turun. Keputusan pengguna 31 Okt 2026 |
| 31 Okt 2026 | direvisi sebelum mesin dibekukan; kunci TEST tidak dibuka maupun dibaca. Isinya: z robust = (z − median) / max(MAD, 1), dan RS hanya ditandai bila O > E, untuk semua lapis dan pembanding (kode di commit `1481b3c`). **Aturan statistik dibekukan sejak baris ini; sesudahnya hanya perbaikan bug** (bagian 10) | **Diputuskan setelah T20 gagal di DEV**; TEST tetap tersegel. Dasarnya prinsip: z sudah berskala kebetulan (mid-p eksak), jadi skala robust boleh melebar karena keragaman antar-RS tetapi tidak boleh di bawah 1; dan RS yang tidak mencatat lebih banyak dari harapan tidak bisa disebut mencatat berlebihan. Penyebab langsungnya: untuk kode yang jarang, MAD menyusut sampai 0,006, sehingga RS kelas D yang tidak pernah mencatat kode operasi ikut ditandai. Angka DEV sebelum → sesudah: garis tidak dimanipulasi yang ikut menyala (T20) 8 → 1 (E87); AI 1 utama T1 fiktif 4/4 → 4/4, T2 1/81 → 0/81 (RS-135 tidak lagi ditandai), RS-008 (pelaku tingkat cerdik) tidak lagi ditandai, plasebo 0 → 0 RS, galat T5 10,4% → 8,2%, T6 tetap 6,1×; versi dengan status pulang plasebo 2 → 0 RS; aturan "ICU lebih pendek" T1 4/4 → 2/4 dan alarm palsu 16% → 0%. Ini perubahan aturan statistik kelima setelah melihat hasil DEV (sesudah kalibrasi isotonik, z eksak, mid-p, dan presisi harapan); makin sering aturan diubah setelah melihat hasil, makin besar risiko hanya bagus di soal latihan, maka aturan dibekukan. Keputusan pengguna 31 Okt 2026 |
| 31 Okt 2026 | direvisi sebelum mesin dibekukan; kunci TEST tidak dibuka maupun dibaca. Isinya: AI 4 ditambah **pindai kode langsung** di samping pohon pengganti (bagian 6, "Garis ditemukan"). Ikut masuk perbaikan bug AI 4: selisih rupiah, kelipatan, dan grup asal ambang lewat kode kini dihitung terhadap grup tepat di bawah garis (sebelumnya terhadap kode yang dicolek ke grup medis), dan rentang rupiah garis jam memuat sebaran alami antar-garis 24 jam. Kode di `engine/ai4.py` (sha256 `3d767efa…7d669`, belum di-commit). **Metode AI 4 dibekukan sejak baris ini; sesudahnya hanya perbaikan bug** (bagian 10) | **Diputuskan setelah melihat T24 gagal** (2 dari 4 jalur); TEST tetap tersegel. Penyebabnya: pohon pengganti di Data Sampel hanya cocok 88,6% dan memakai minimal 50 klaim per daun, sehingga jalur yang jarang (96.04 saja: 26 klaim; trakeostomi: 92 klaim) tidak terpelajari. Angka sebelum → sesudah: T24 Reguler 2/4 → 4/4 (96.04 → J-1-20 dan trakeostomi → J-1-01 kini ditemukan); T24 set DM, diuji sekali dengan semua jalur ≥10 klaim, 2/4 → 4/4; T19 5/5 → 5/5; T21 lolos → lolos; kandidat kode baru dari pindai langsung: DEV 3, iDRG 0, Reguler 243 (di samping 171 dari pohon), DM 100 (di samping 81); garis tidak dimanipulasi yang ikut menyala di DEV 1 → 2 (39.95 dan E87), sehingga **T20 berubah dari lolos menjadi gagal**. Di Reguler, 29 kandidat baru menunjuk ke grup ventilasi; hanya 96.04 dan 31.1 yang jalur dikenal, sisanya kemungkinan tindakan ICU yang menyertai ventilasi. Keputusan pengguna 31 Okt 2026 |
| 1 Nov 2026 | direvisi sebelum mesin dibekukan; kunci TEST tidak dibuka maupun dibaca. Isinya: AI 2 menahan putusan ("tidak dapat disimpulkan") bila dokumen kunci selama masa ventilasi yang diklaim, yaitu laporan tindakan dan catatan perawat, ditulis lebih lambat dari persentil 99 klaim jujur DEV untuk jenis dokumen itu (median keterlambatan per klaim; batas 17,68 jam dan 330,97 jam, dihitung dan disimpan 1 Nov 2026 11.45 WIB sebelum run ulang di `tapal-percobaan/ai2-dev/jejak_waktu_ambang.json`); klaim tanpa jam mulai dan selesai ventilator memakai seluruh masa rawat. LLM juga dibaca ulang sekali bila ada kutipan yang tidak ditemukan persis di RME, dengan kutipan itu disebutkan. Kode: `engine/ai2.py` sha256 `f3574cb7…b9de9d3`, `engine/ai2_fast.py` sha256 `3701263c…2825940` (belum di-commit). **Metode AI 2 dibekukan sejak baris ini; sesudahnya hanya perbaikan bug** (bagian 10) | **Diputuskan setelah melihat T8 gagal** (6,7%); TEST tetap tersegel. Batas ditentukan dari sebaran klaim jujur, bukan disetel pada kasus RME karangan (TARGETS bagian 1: cerdik-2 tidak memalsukan jejak waktu secara konsisten). Angka sebelum → sesudah, 314 klaim sampel DEV, semua lapis, lipatan per RS: T8 6,7% (13 dari 193) → 2,7% (5 dari 187), **tetap gagal**; T9 38,5% → 40,4%, tetap gagal, definisinya tidak diubah; T7 100% → 100%; T10 0 → 0 jam; klaim jujur tak tersimpulkan di sampel 19 → 18 dari 120. Klaim jujur di seluruh populasi DEV yang ikut tertahan aturan baru: 348 dari 19.118 (1,8%), terpusat di RS jujur yang menulis massal (222 dari 713, 31%). Ulang kutipan: 6 bacaan diulang, 5 menjadi cocok. Keputusan pengguna 1 Nov 2026 |
