# Protokol Reproduksibilitas MFAR

## 1. Pembagian sumber resmi

| Komponen | Sumber resmi | Diberi versi di Git |
|---|---|---|
| Modul Python | `src/` | Ya |
| Notebook Stage 00–07 | `notebooks/` | Ya |
| Parameter ilmiah | `config/` | Ya |
| Pengujian dan audit | `tests/`, `scripts/` | Ya |
| Dokumentasi | `README.md`, `docs/` | Ya |
| Data AIS mentah | Google Drive terbatas | Tidak |
| Data kedatangan kendaraan | Google Drive terbatas | Tidak |
| Output Stage dan dashboard | Google Drive terbatas atau artifact release terpilih | Tidak secara default |

Kode dan konfigurasi pada commit tertentu harus cukup untuk menjelaskan bagaimana hasil dibentuk. Data privat disimpan terpisah dan diidentifikasi melalui manifest lokal, bukan melalui folder ID publik.

## 2. Validasi dari clean checkout

```bash
git clone https://github.com/yanto-mashardi/MFAR_Modular_Colab_Pipeline.git
cd MFAR_Modular_Colab_Pipeline
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python scripts/validate_repository.py
python -m unittest discover -s tests -v
```

Validasi ini memeriksa struktur repository, notebook format 4, keberadaan konfigurasi, kontrak membership-rule-action, file lokal terlarang, serta unit test pipeline yang tidak memerlukan data privat.

## 3. Eksekusi data penuh

1. Checkout tag atau commit yang akan digunakan.
2. Siapkan folder Google Drive `In_Out_MFAR_Modular_Colab_Pipeline` pada lokasi privat.
3. Tempatkan input aktif pada `data_raw/` di Google Drive.
4. Buka `notebooks/00_Run_All_Stages.ipynb` di Google Colab.
5. Pastikan checkout menggunakan branch, tag, atau commit yang dimaksud.
6. Jalankan **Runtime → Run all**.
7. Periksa metadata eksekusi dan artefak interpretatif pada setiap `stage_output/stage_NN/`.

## 4. Manifest run penelitian

Setiap run yang dipakai untuk artikel, laporan, atau keputusan perlu mencatat:

- commit SHA dan tag;
- tanggal serta waktu eksekusi;
- versi Python dan dependency;
- periode data;
- checksum atau identitas internal input tanpa mengekspos data;
- salinan konfigurasi aktif;
- jumlah baris input dan output setiap tahap;
- status unit test dan audit repository;
- daftar artefak tabel, gambar, workbook, HTML, dan metadata;
- keterbatasan atau anomali run.

Metadata `NN_execution_metadata.json` pada setiap tahap menjadi komponen minimum. Untuk release ilmiah, gabungkan metadata tersebut dalam satu paket audit.

## 5. Pembekuan versi untuk manuskrip

Sebelum submission atau revisi jurnal:

1. Selesaikan pull request terkait metode dan hasil.
2. Jalankan CI serta full-run Colab.
3. Periksa tabel dan gambar terhadap manuskrip.
4. Perbarui `CHANGELOG.md` dan pemetaan manuskrip.
5. Buat tag dan GitHub Release.
6. Catat tag, commit SHA, periode data, dan konfigurasi pada dokumen penelitian.

Perubahan setelah pembekuan versi harus masuk release baru. Manuskrip tidak boleh menggabungkan tabel atau gambar dari commit dan konfigurasi yang berbeda tanpa penjelasan eksplisit.

## 6. Batas interpretasi

Stage 07 merupakan evaluasi skenario tindakan. Hasilnya menggambarkan konsekuensi model pada kondisi dan asumsi yang ditetapkan. Klaim dampak empiris memerlukan validasi lapangan atau desain evaluasi kausal yang terpisah.
