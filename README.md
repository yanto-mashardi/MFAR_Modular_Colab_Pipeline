# MFAR Modular Google Colab Pipeline

Pipeline modular dari AIS mentah sampai Candidate Action. Setiap notebook membaca CSV tahap sebelumnya dan menyimpan CSV baru.

## Cara menjalankan
1. Ekstrak folder ke `MyDrive/MFAR_Modular_Colab_Pipeline`
2. Ganti `data_raw/ais_raw.csv` bila menggunakan AIS lain
3. Isi `data_raw/daily_vehicle_distribution.csv`
4. Jalankan notebook 01 sampai 07 secara berurutan
5. Periksa setiap CSV output sebelum lanjut

## Catatan
Parameter membership dan bobot rule masih provisional dan sengaja dipisahkan ke CSV agar mudah dikalibrasi tanpa mengubah kode.
