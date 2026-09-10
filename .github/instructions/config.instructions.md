---
applyTo: "config/**/*.csv"
---

- Perlakukan file konfigurasi sebagai parameter ilmiah yang diberi versi dan dapat diaudit.
- Jangan mengubah nama kolom, unit, domain membership, prioritas rule, cooldown, atau fase kelayakan tindakan tanpa memperbarui pengujian serta dokumentasi.
- Periksa keterkaitan `membership_parameters.csv`, `fuzzy_rules.csv`, dan `action_constraints.csv` sebelum commit.
- Hindari duplikasi kode, rule, membership, kapal, terminal, atau baris parameter.
- Jelaskan alasan ilmiah, nilai lama, nilai baru, sumber bukti, dan analisis sensitivitas yang diperlukan pada pull request.
