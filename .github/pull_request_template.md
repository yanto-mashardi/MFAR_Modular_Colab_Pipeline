## Tujuan

Jelaskan masalah atau pertanyaan penelitian yang diselesaikan dan tautkan Issue terkait.

Closes #

## Akar masalah

Jelaskan penyebab teknis, data, konfigurasi, atau metodologis.

## Perubahan

- 

## Dampak metodologis

Jelaskan pengaruh terhadap definisi variabel, unit, urutan Stage 01–07, temporal holdout, forecast, membership, rule, inferensi Mamdani, kelayakan tindakan, evaluasi skenario, dan interpretasi hasil. Tulis `Tidak ada` apabila benar-benar tidak ada dampak.

## Kontrak data dan konfigurasi

- [ ] Nama file dan kolom antartahap tetap kompatibel atau migrasinya didokumentasikan.
- [ ] Parameter ilmiah tetap berada di `config/*.csv`.
- [ ] Data mentah, output besar, kredensial, token, path lokal, dan folder ID tidak dimasukkan ke Git.

## Validasi

- [ ] `python scripts/validate_repository.py`
- [ ] `python -m unittest discover -s tests -v`
- [ ] Pengujian tambahan atau audit notebook telah dilakukan bila relevan.

Ringkasan hasil pengujian:

```text

```

## Artefak bukti

Sebutkan tabel, grafik, workbook, HTML, metadata eksekusi, atau log yang digunakan untuk memeriksa hasil. Simpan data besar di Google Drive dan tulis nama artefaknya tanpa mengekspos akses privat.

## Risiko residual dan keterbatasan

- 

## Kesiapan review

- [ ] Dokumentasi terkait telah diperbarui.
- [ ] Perubahan telah diperiksa terhadap Issue dan acceptance criteria.
- [ ] Stage 07 tetap dinyatakan sebagai evaluasi skenario kecuali tersedia bukti empiris.
