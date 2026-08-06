---
applyTo: "notebooks/**/*.ipynb"
---

- Pertahankan urutan Stage 00–07 dan kontrak file antartahap.
- Notebook harus tetap berupa JSON notebook format 4 yang valid.
- Jangan menyimpan data mentah, output besar, token, kredensial, atau path lokal absolut di dalam notebook.
- Logika yang digunakan lintas notebook harus ditempatkan di `src/`, bukan diduplikasi dalam banyak sel.
- Gunakan resolver pada `src/mfar_paths.py` untuk akses kode dan Google Drive.
- Ketika mengubah output, pertahankan metadata eksekusi dan artefak interpretatif yang diperlukan untuk audit.
- Jelaskan dampak metodologis perubahan notebook di pull request dan jalankan validasi repository serta unit test.
