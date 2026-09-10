# Checklist Release Ilmiah MFAR

Gunakan checklist ini untuk membekukan versi kode dan konfigurasi yang dipakai dalam artikel, laporan, validasi, atau demonstrasi.

## A. Kesiapan kode

- [ ] Semua perubahan terkait telah masuk melalui pull request.
- [ ] Branch `main` berada pada commit yang akan dirilis.
- [ ] Workflow `MFAR CI` berhasil.
- [ ] `python scripts/validate_repository.py` berhasil dari clean checkout.
- [ ] `python -m unittest discover -s tests -v` berhasil.
- [ ] Tidak ada data mentah, output besar, kredensial, folder ID, atau file lokal dalam Git.

## B. Kesiapan ilmiah

- [ ] Periode data dan kriteria inklusi dinyatakan.
- [ ] Konfigurasi aktif sudah ditinjau dan tersimpan di `config/`.
- [ ] Temporal calibration dan holdout dinyatakan.
- [ ] Perubahan definisi variabel, unit, membership, rule, dan batas tindakan telah ditinjau.
- [ ] Stage 07 dinyatakan sebagai evaluasi skenario.
- [ ] Analisis sensitivitas yang diwajibkan telah dijalankan.

## C. Full-run dan artefak

- [ ] `notebooks/00_Run_All_Stages.ipynb` dijalankan dari checkout commit release.
- [ ] Metadata eksekusi tersedia untuk Stage 01–07.
- [ ] Jumlah baris input dan output telah diperiksa.
- [ ] Dashboard, peta, workbook, dan tabel utama dapat dibuka.
- [ ] Anomali, nilai ekstrem, nilai negatif, dan output kosong telah diaudit.
- [ ] Paket audit menyimpan nama artefak dan checksum yang relevan.

## D. Manuskrip dan dokumentasi

- [ ] Setiap tabel dan gambar dipetakan ke notebook, file output, dan commit.
- [ ] README dan dokumentasi metode sesuai dengan perilaku kode.
- [ ] `CHANGELOG.md` dipindahkan dari `[Unreleased]` ke nomor versi.
- [ ] `CITATION.cff` diperiksa.
- [ ] Keterbatasan release ditulis dengan eksplisit.

## E. Tag dan GitHub Release

Format versi yang disarankan:

```text
v0.1.0  baseline awal
v0.2.0  penambahan fungsi atau perubahan metode yang kompatibel
v0.2.1  perbaikan bug tanpa perubahan interpretasi utama
v1.0.0  versi stabil yang dibekukan untuk keluaran utama
```

Langkah:

1. Buka **Releases → Draft a new release**.
2. Buat tag dari commit `main` yang telah diaudit.
3. Gunakan judul yang menjelaskan tujuan ilmiah release.
4. Cantumkan periode data, konfigurasi, perubahan, hasil pengujian, artefak, dan keterbatasan.
5. Lampirkan paket audit terpilih yang aman dipublikasikan.
6. Catat tag dan commit SHA pada manuskrip atau laporan terkait.

## F. Pemeriksaan pascarelease

- [ ] Release dapat di-clone dan divalidasi dari lingkungan bersih.
- [ ] Citation pada halaman repository tampil benar.
- [ ] Issue untuk perubahan berikutnya diarahkan ke release target baru.
- [ ] Manuskrip tidak mengambil artefak dari commit yang lebih baru tanpa deklarasi.
