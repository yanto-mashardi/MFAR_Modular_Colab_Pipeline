# MFAR Modular Google Colab Pipeline

Pipeline modular AIS → interpolasi lima menit → monitoring dermaga → forecast
tanpa intervensi → fuzzification → rule evaluation → validasi candidate action.

Kode notebook dan konfigurasi model berada di repository ini. Data besar dan
hasil simulasi disimpan terpisah pada folder Google Drive:

```text
In_Out_MFAR_Modular_Colab_Pipeline/
├── data_raw/
│   ├── ais_raw.csv
│   └── vehicle_arrival_rate_30min.csv
└── stage_output/
    ├── stage_01/
    ├── stage_02/
    ├── stage_03/
    ├── stage_04/
    ├── stage_05/
    ├── stage_06/
    └── stage_07/
```

Folder ID: `1CrvswSCmR0_Tr7mWYufrOXYgCMdRQpgq`. Folder ID dan URL hanya
merupakan identitas; keduanya tidak boleh diberikan langsung kepada
`pandas.read_csv()`.

## Menyiapkan path

Semua notebook memakai `src/mfar_paths.py`. Di Google Colab, modul tersebut
memasang Drive pada `/content/drive` dan mencari folder
`In_Out_MFAR_Modular_Colab_Pipeline`. Notebook harus dijalankan dari checkout
repository atau `MFAR_CODE_ROOT` harus menunjuk ke checkout tersebut.

Untuk lokasi Drive nonstandar, termasuk Google Drive for Desktop di Windows:

```python
import os
os.environ["MFAR_GDRIVE_ROOT"] = r"G:\My Drive\Post Doctor\In_Out_MFAR_Modular_Colab_Pipeline"
os.environ["MFAR_CODE_ROOT"] = r"C:\path\to\MFAR_Modular_Colab_Pipeline"
```

Tetapkan environment variable sebelum mengimpor `src.mfar_paths` atau
menjalankan cell setup notebook. Resolver berhenti dengan daftar path yang
diperiksa bila folder tidak ditemukan.

## Urutan eksekusi dan kontrak utama

| Urutan | Notebook | Input utama | Output untuk tahap berikutnya |
|---|---|---|---|
| 01 | `01_AIS_Input_and_Cleaning.ipynb` | `data_raw/ais_raw.csv` | `stage_01/01_ais_clean.csv` |
| 02 | `02_Time_Grid_and_State_Preparation.ipynb` | `stage_01/01_ais_clean.csv` | `stage_02/02_vessel_interpolated_grid.csv` |
| 03 | `03_Monitoring_State.ipynb` | `stage_02/02_vessel_interpolated_grid.csv` | `stage_03/03_input_state_enhanced.csv` |
| 04 | `04_No_Intervention_Forecast.ipynb` | Stage 3 dan `data_raw/vehicle_arrival_rate_30min.csv` | `stage_04/04_fuzzy_input.csv` |
| 05 | `05_Fuzzification.ipynb` | `stage_04/04_fuzzy_input.csv` | `stage_05/05_fuzzy_memberships.csv` |
| 06 | `06_Rule_Evaluation.ipynb` | `stage_05/05_fuzzy_memberships.csv` | `stage_06/06_rule_evaluation.csv` |
| 07 | `07_Candidate_Action.ipynb` | Stage 4 queue/event log dan Stage 6 rule evaluation | laporan Stage 7 |

Jalankan notebook 01–07 secara berurutan. Setiap tahap memeriksa keberadaan,
keterbacaan, isi, dan kolom wajib input sebelum melanjutkan. Rerun mengganti
artefak dengan nama yang sama hanya di folder tahapnya; file lain tidak
dihapus.

Setiap tahap juga membuat `NN_execution_metadata.json` berisi waktu eksekusi,
sumber input, jumlah baris input/output, direktori output, dan daftar artefak.

## Input dan konfigurasi

File `*_TEMPLATE.csv` di root repository hanya contoh dan bukan input aktif.
Konfigurasi ilmiah tetap berada pada `config/`, termasuk profil kapal, dermaga,
parameter membership, fuzzy rules, dan action constraints. Perubahan migrasi
path tidak mengubah nilai parameter atau formula model.

Dependensi Python utama: `pandas`, `numpy`, `folium`, `matplotlib`,
`ipywidgets`, dan—khusus Colab—`google.colab`.


## Keluaran interpretatif

Notebook tetap menulis CSV/JSON sebagai kontrak data antartahap. Setiap `Run all`
sekarang juga menghasilkan artefak yang dapat dibaca langsung:

| Tahap | Artefak interpretatif |
|---|---|
| 01 | `01_ais_full_validation_map.html`, `01_data_quality_dashboard.html`, `01_readable_summary.xlsx` |
| 02 | `02_validation_map_<MMSI>_<tanggal>.html`, `02_interpolated_full_validation_map.html`, `02_interpolation_dashboard.html`, `02_readable_summary.xlsx` |
| 03 | `03_berth_monitoring_story.html`, `03_readable_summary.xlsx` |
| 04 | `04_operational_forecast_dashboard.html`, `04_readable_results.xlsx` |
| 05 | `05_fuzzy_case_explorer.html`, `05_readable_summary.xlsx` |
| 06 | `06_rule_action_flow.html`, `06_readable_results.xlsx` |
| 07 | `07_intervention_validation_dashboard.html`, `07_readable_results.xlsx` |

Peta dipakai untuk validasi spasial. Timeline, Sankey, dashboard waktu, matriks
membership, kartu indikator, dan workbook Excel dipakai sesuai karakter hasil
pada tahap lain. Peta Stage 02 per kapal-hari merupakan validasi lintasan utama;
peta seluruh periode hanya menunjukkan cakupan data.

Artefak HTML bersifat interaktif: pengguna dapat melakukan zoom, hover, memilih
legend, serta menyembunyikan atau menampilkan seri. Workbook Excel hanya memuat
ringkasan dan hasil yang relevan bagi pembaca; tabel besar tetap berada di CSV.

Untuk menjalankan seluruh tahap dalam satu kali perintah, buka
[`notebooks/00_Run_All_Stages.ipynb`](notebooks/00_Run_All_Stages.ipynb) di
Google Colab lalu pilih **Runtime → Run all**. Notebook pengendali memperbarui
branch `test-colab-pipeline`, memasang dependensi, mengeksekusi 01–07, dan
menimpa artefak bernama sama pada Google Drive.

Instal dependensi sebelum eksekusi penuh:

```bash
pip install -r requirements.txt
```
