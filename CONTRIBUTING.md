# Kontribusi pada MFAR Modular Google Colab Pipeline

## Alur kerja

1. Buat atau pilih GitHub Issue yang menjelaskan masalah, bukti, dan acceptance criteria.
2. Buat branch dari `main` dengan salah satu pola berikut:

```text
feat/issue-<nomor>-<ringkasan>
fix/issue-<nomor>-<ringkasan>
research/issue-<nomor>-<ringkasan>
docs/issue-<nomor>-<ringkasan>
chore/issue-<nomor>-<ringkasan>
```

3. Lakukan perubahan dengan ruang lingkup terbatas dan commit yang menjelaskan maksud perubahan.
4. Jalankan validasi lokal.
5. Buka pull request dan isi seluruh bagian template.
6. Gabungkan ke `main` setelah pemeriksaan metodologis dan status GitHub Actions berhasil.

## Validasi lokal

```bash
python -m pip install -r requirements.txt
python scripts/validate_repository.py
python -m unittest discover -s tests -v
```

Eksekusi Stage 01–07 dengan data penuh tetap dilakukan di Google Colab dan Google Drive. Validasi GitHub menggunakan pemeriksaan struktur, konfigurasi, notebook, dan unit test yang tidak memerlukan data privat.

## Perubahan konfigurasi ilmiah

Perubahan pada `config/*.csv` harus mencantumkan:

- nilai atau definisi sebelumnya;
- nilai atau definisi baru;
- alasan ilmiah atau operasional;
- sumber bukti;
- dampak pada Stage terkait;
- rencana validasi atau sensitivitas;
- perubahan pengujian dan dokumentasi.

Parameter yang digunakan algoritma harus tetap berasal dari file konfigurasi. Hindari konstanta tersembunyi dalam notebook atau modul Python.

## Data dan keamanan

Jangan commit:

- data AIS mentah;
- data kedatangan kendaraan privat;
- output Stage 01–07;
- file `.env`, token, API key, service account, atau kredensial;
- path lokal absolut;
- Google Drive folder ID atau tautan akses privat;
- dokumen yang memuat data personal atau institusional terbatas.

## Standar pull request

Pull request harus dapat menjawab:

1. Masalah apa yang diselesaikan?
2. Mengapa kondisi sebelumnya tidak memadai?
3. File dan kontrak apa yang berubah?
4. Apakah interpretasi ilmiah berubah?
5. Pengujian dan artefak apa yang membuktikan hasil?
6. Keterbatasan apa yang masih tersisa?

Perubahan yang mengubah definisi variabel, unit, temporal holdout, membership, fuzzy rule, inferensi, atau kelayakan tindakan memerlukan review metodologis sebelum merge.
