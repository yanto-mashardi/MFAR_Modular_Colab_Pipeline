Stage 4 — Daily No-Intervention Forecast

Input aktif:
- <DRIVE_ROOT>/stage_output/stage_03/03_input_state_enhanced.csv
- <DRIVE_ROOT>/data_raw/vehicle_arrival_rate_30min.csv
- config/vessel_profiles.csv
- config/terminal_berths.csv

Output disimpan di <DRIVE_ROOT>/stage_output/stage_04/.
Output utama Stage 5 adalah 04_fuzzy_input.csv.

Karakteristik model yang dipertahankan:
- simulasi 07:00–23:55 pada grid 5 menit;
- baseline stateful dan tidak menambah kapal;
- arrival kendaraan berasal dari laju 30 menit;
- antrean dikurangi hanya pada event keberangkatan AIS;
- occupancy dievaluasi pada estimasi waktu tiba;
- metadata eksekusi disimpan sebagai 04_execution_metadata.json.

Path diselesaikan oleh src/mfar_paths.py. Gunakan MFAR_GDRIVE_ROOT untuk
lokasi Google Drive yang tidak standar. File template di root repository bukan
input aktif.
