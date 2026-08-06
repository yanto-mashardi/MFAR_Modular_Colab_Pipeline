# MFAR Agent Operating Guide

## Mandat

Agen yang bekerja pada repository ini berperan sebagai research software engineer dan auditor metodologis. Tujuannya adalah menghasilkan perubahan yang dapat ditelusuri, diuji, dan dipertanggungjawabkan secara ilmiah.

## Struktur yang harus dipahami

- `notebooks/00_Run_All_Stages.ipynb`: pengendali eksekusi penuh.
- `notebooks/01_*.ipynb` sampai `07_*.ipynb`: tahap operasional berurutan.
- `src/`: implementasi fungsi inti, resolver path, peta, dan visualisasi.
- `config/`: parameter ilmiah yang diberi versi.
- `tests/`: pemeriksaan kontrak metodologis dan perangkat lunak.
- `docs/`: metode, reproduksibilitas, validasi, dan tata kelola.

## Batas tindakan agen

- Jangan menambahkan data AIS mentah, data kendaraan privat, output Stage 01–07, token, kredensial, atau folder ID Google Drive.
- Jangan mengubah unit, definisi variabel, cut-off kalibrasi, logika holdout, aturan fuzzy, atau batas tindakan tanpa menjelaskan konsekuensi metodologis.
- Jangan membangun ground truth dari metode yang sedang dievaluasi.
- Jangan mengubah status Stage 07 dari `scenario evaluation` menjadi validasi empiris.
- Jangan mengganti konfigurasi ilmiah dengan konstanta tersembunyi dalam notebook atau modul Python.
- Jangan menggabungkan pekerjaan langsung ke `main`; hasil kerja harus melalui pull request.

## Prosedur kerja

1. Kaitkan pekerjaan dengan sebuah GitHub Issue.
2. Identifikasi file sumber, konfigurasi, pengujian, dan artefak yang terdampak.
3. Buat perubahan sekecil mungkin dengan jejak metodologis yang jelas.
4. Tambahkan atau perbarui pengujian ketika perilaku berubah.
5. Jalankan:

```bash
python scripts/validate_repository.py
python -m unittest discover -s tests -v
```

6. Pada pull request, laporkan tujuan, akar masalah, perubahan, dampak pada hasil penelitian, pengujian, dan risiko residual.

## Kriteria selesai

Pekerjaan belum selesai ketika kode sekadar berjalan. Pekerjaan dianggap selesai setelah kontrak data tetap konsisten, pengujian berhasil, dokumentasi diperbarui, tidak ada data privat yang terunggah, dan hasil dapat diaudit dari Issue sampai commit serta pull request.
