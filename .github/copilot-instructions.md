# Instruksi repository MFAR untuk GitHub Copilot

## Konteks sistem

Repository ini memuat kode, notebook, konfigurasi ilmiah, pengujian, dan dokumentasi untuk pipeline modular MFAR. Data AIS mentah, data kedatangan kendaraan, serta hasil simulasi besar disimpan di Google Drive dan tidak boleh dimasukkan ke Git.

Urutan eksekusi resmi adalah `notebooks/00_Run_All_Stages.ipynb` sebagai pengendali, kemudian Stage 01 sampai Stage 07. Modul Python utama berada di `src/`. Konfigurasi ilmiah berada di `config/` dan merupakan sumber tunggal bagi parameter pipeline, profil kapal, dermaga, membership fuzzy, aturan fuzzy, dan batas kelayakan tindakan.

## Aturan perubahan

1. Baca `README.md`, `AGENTS.md`, pengujian terkait, dan konfigurasi yang digunakan sebelum mengubah kode.
2. Pertahankan kontrak input-output Stage 01–07. Perubahan nama file, nama kolom, unit, zona waktu, atau urutan tahap harus didokumentasikan dan disertai migrasi yang jelas.
3. Jangan memindahkan parameter ilmiah ke nilai hard-coded apabila parameter tersebut semestinya berada di `config/*.csv`.
4. Jangan mengunggah data mentah, output simulasi, kredensial, folder ID Google Drive, atau informasi akses lokal.
5. Stage 07 adalah evaluasi skenario. Jangan menyatakan hasilnya sebagai validasi empiris dampak intervensi tanpa bukti lapangan yang sesuai.
6. Bedakan perubahan perangkat lunak, perubahan konfigurasi ilmiah, dan perubahan interpretasi metodologis dalam deskripsi pull request.
7. Jangan menghapus output interpretatif, metadata audit, atau pemeriksaan validasi tanpa pengganti yang setara dan alasan yang dapat diaudit.
8. Perubahan pada notebook harus tetap menghasilkan JSON notebook yang valid dan tidak boleh menambahkan data besar ke dalam output sel.

## Validasi wajib

Jalankan dari root repository:

```bash
python scripts/validate_repository.py
python -m unittest discover -s tests -v
```

Pull request harus menjelaskan tujuan, file yang berubah, dampak metodologis, hasil pengujian, dan keterbatasan yang tersisa. Gunakan branch terpisah dan jangan melakukan perubahan langsung pada `main`.
