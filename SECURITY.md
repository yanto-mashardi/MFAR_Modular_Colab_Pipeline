# Kebijakan Keamanan MFAR

## Ruang lingkup

Kebijakan ini mencakup kode Python, notebook, konfigurasi, GitHub Actions, dependency, dan dokumentasi pada repository MFAR.

## Melaporkan kerentanan

Jangan mempublikasikan token, kredensial, data privat, atau rincian eksploitasi pada GitHub Issue publik. Gunakan menu **Security → Report a vulnerability** pada repository apabila private vulnerability reporting telah diaktifkan. Apabila menu tersebut belum tersedia, hubungi maintainer melalui kanal institusional yang tercantum pada profil atau publikasi resmi tanpa menyertakan secret di ruang publik.

Sertakan informasi berikut:

- file atau komponen terdampak;
- langkah reproduksi yang aman;
- dampak potensial;
- versi, branch, atau commit;
- usulan mitigasi bila tersedia.

## Data yang dilarang masuk repository

- data AIS mentah dan data kendaraan privat;
- output simulasi yang memuat data operasional sensitif;
- file `.env`, API key, token, service account, SSH key, atau kredensial;
- Google Drive folder ID dan tautan akses privat;
- data personal, database dump, atau dokumen institusi terbatas.

## Dependency dan workflow

Dependency Python dan GitHub Actions diperiksa melalui Dependabot. Pull request dependency harus melewati workflow `MFAR CI` dan diperiksa terhadap kemungkinan perubahan numerik, visual, atau reproduksibilitas.

## Versi yang didukung

Sebelum release stabil pertama, hanya branch `main` terbaru yang memperoleh perbaikan keamanan. Setelah versioning diterapkan, kebijakan versi yang didukung dicatat pada release notes.
