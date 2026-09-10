# Changelog

Semua perubahan penting pada MFAR Modular Google Colab Pipeline dicatat dalam dokumen ini. Format mengikuti prinsip Keep a Changelog dan versioning akan menggunakan Semantic Versioning setelah release pertama diterbitkan.

## [Unreleased]

### Added

- GitHub Actions workflow untuk audit repository dan unit test.
- Pemeriksaan otomatis notebook, konfigurasi, kontrak fuzzy, dan kebersihan repository.
- Dependabot untuk dependency Python dan GitHub Actions.
- Issue forms untuk bug pipeline dan perubahan metode atau konfigurasi ilmiah.
- Pull request template dengan pemeriksaan dampak metodologis.
- Instruksi repository, instruksi path-specific, `AGENTS.md`, dan custom agent `MFAR Research Engineer`.
- Pedoman kontribusi, kebijakan keamanan, reproduksibilitas, dan roadmap tata kelola GitHub.
- Citation metadata untuk perangkat lunak penelitian.

### Changed

- `.gitignore` diperluas untuk mencegah data mentah, output simulasi, kredensial, file temporer, dan metadata sistem operasi masuk ke Git.
- Dokumentasi penyimpanan Google Drive diubah agar tidak mengekspos folder ID.

### Removed

- File `desktop.ini` dari root, `config/`, dan `notebooks/`.

## Riwayat sebelum versioning

Pengembangan awal repository mencakup pipeline Stage 01–07, resolver Google Drive, dashboard interpretatif, peta validasi, konfigurasi fuzzy, evaluasi skenario, dan unit test. Riwayat rinci tersedia melalui commit dan pull request sebelum release pertama.
