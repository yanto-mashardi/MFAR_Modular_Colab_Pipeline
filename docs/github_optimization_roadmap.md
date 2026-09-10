# Roadmap Optimalisasi GitHub untuk MFAR

Roadmap ini menerjemahkan sepuluh prioritas optimalisasi ke tindakan repository, pengaturan GitHub, dan keluaran audit.

| Prioritas | Tindakan | Status setelah PR tata kelola | Bukti atau langkah lanjutan |
|---:|---|---|---|
| 1 | Perkuat `.gitignore` dan bersihkan file lokal | Diterapkan | `.gitignore`; penghapusan seluruh `desktop.ini`; audit otomatis |
| 2 | Bangun GitHub Project lintas pekerjaan MFAR | Memerlukan pengaturan UI | Buat Project `MFAR Research & Development Control` dan tambahkan Issues roadmap |
| 3 | Jadikan Issues sebagai sumber tugas resmi | Diterapkan sebagian | Issue forms bug dan perubahan ilmiah; Issues backlog dibuat terpisah |
| 4 | Lindungi branch `main` | Memerlukan pengaturan UI | Wajibkan pull request, CI, penyelesaian percakapan, serta larang force push |
| 5 | Tambahkan GitHub Actions ringan | Diterapkan | `.github/workflows/ci.yml`, audit repository, unit test, artifact log |
| 6 | Terapkan versioning dan release ilmiah | Infrastruktur diterapkan | `CHANGELOG.md`, `CITATION.cff`, release checklist; tag pertama dibuat setelah full-run |
| 7 | Perkuat dokumentasi dan keterlacakan | Diterapkan sebagian | `CONTRIBUTING.md`, `AGENTS.md`, reproducibility protocol; data dictionary dan manuscript mapping dilanjutkan |
| 8 | Aktifkan keamanan dan pembaruan dependency | Diterapkan sebagian | Dependabot dan `SECURITY.md`; secret scanning serta private vulnerability reporting diaktifkan melalui UI |
| 9 | Publikasikan dokumentasi melalui GitHub Pages | Direncanakan | Pilih MkDocs atau static documentation setelah struktur docs stabil |
| 10 | Aktifkan agen dan instruksi repository | Infrastruktur diterapkan | Copilot instructions, path-specific instructions, AGENTS.md, custom agent MFAR; kebijakan akun diaktifkan melalui UI |

## GitHub Project yang disarankan

Nama:

```text
MFAR Research & Development Control
```

Status:

```text
Backlog → Ready → In Progress → Validation → Review → Revision → Done
```

Field:

- `Work type`: Bug, Feature, Methodology, Data, Validation, Documentation, Governance;
- `Stage`: 00 sampai 07, Cross-stage, Repository;
- `Priority`: Critical, High, Medium, Low;
- `Evidence required`: Yes atau No;
- `Release target`;
- `Manuscript section`;
- `Due date`.

## Ruleset untuk `main`

Atur melalui **Settings → Rules → Rulesets → New branch ruleset**:

- target branch: `main`;
- require a pull request before merging;
- required approvals: minimal 1 ketika kolaborator tersedia;
- require status checks: `Repository and scientific-contract validation`;
- require conversation resolution;
- block force pushes;
- restrict deletions;
- gunakan squash merge untuk PR kecil atau merge commit untuk perubahan besar yang memerlukan histori cabang.

## Pemanfaatan agen

Gunakan agen untuk tugas dengan acceptance criteria yang terukur, misalnya:

- menambah pengujian kontrak Stage;
- mengaudit nilai negatif dan rentang variabel;
- membuat data dictionary dari kode dan konfigurasi;
- memperbaiki dokumentasi reproduksibilitas;
- memeriksa dependency dan kegagalan CI.

Perubahan definisi ilmiah, pemilihan metode, interpretasi hasil, dan klaim validasi tetap memerlukan keputusan peneliti manusia setelah memeriksa bukti.
