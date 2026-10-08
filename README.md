# KeySound

Service lokal macOS: tombol keyboard memicu audio, dengan dashboard neobrutalism untuk konfigurasi. Satu berkas Python, satu HTML, tanpa framework web, database, akun, atau cloud.

## Jalankan

Dari direktori proyek ini:

```sh
# .venv sudah dipasang pada mesin pengembangan. Untuk instalasi baru:
uv venv .venv --python python3
uv pip install --python .venv/bin/python -r requirements.txt

# Uji logika tanpa mengakses keyboard atau memainkan audio:
python3 keysound.py --selftest

# Jalankan service:
.venv/bin/python keysound.py
```

Buka `http://127.0.0.1:8765`. Jangan membuka `dashboard.html` langsung dengan `file://`.
Jika `uv` tidak tersedia, gunakan Python yang menyediakan `venv`/`pip`: `python3 -m venv .venv`, lalu `.venv/bin/python -m pip install -r requirements.txt`.

Instalasi baru mulai dengan **suara dimatikan**, pack Gunshot, volume 25%, jeda 12 ms, dan maksimal 4 suara bersamaan. Pengaturan selanjutnya mengikuti JSON tersimpan; restart tidak mengembalikan pilihan Anda ke default.

- **Aktifkan/Matikan suara** membisukan atau mengaktifkan pemicu keyboard, bukan mematikan HTTP service. Preview tetap dapat digunakan saat suara keyboard dimatikan.
- **Ctrl+C** di terminal menghentikan seluruh service. Menutup tab browser tidak menghentikannya.
- Port dapat diganti: `.venv/bin/python keysound.py --port 8767`.
- Folder konfigurasi alternatif untuk pengujian: `.venv/bin/python keysound.py --port 8767 --config-dir /path/khusus-pengujian`.
- Service hanya bind ke `127.0.0.1`, tidak ada opsi untuk mengekspos ke LAN.

### Dependency

Dua dependency langsung, dikunci pada versi yang diuji dalam `requirements.txt`:

| Dependency | Alasan |
|---|---|
| `pyobjc-framework-Quartz` | Mengakses event tap keyboard macOS yang pasif, tanpa membaca karakter teks atau memblokir tombol. |
| `pyobjc-framework-AVFoundation` | Mendekode WAV/MP3 ke `AVAudioPCMBuffer` dan memutarnya lewat `AVAudioEngine`, tanpa membuat proses per ketukan. |

Paket transitif yang dibawa PyObjC: core, Cocoa, CoreAudio, dan CoreMedia. Jadi batas dua berlaku untuk **dependency langsung**, bukan jumlah wheel transitif. Tidak memerlukan NumPy, FFmpeg, browser automation, atau Node.js untuk menjalankan aplikasi.

Diuji pada macOS 15.8.1 Intel, Python 3.14.2, PyObjC 12.2.2. Arsitektur Apple Silicon belum diuji langsung. Self-check hanya memerlukan pustaka standar Python.

## Izin keyboard macOS

1. Buka **System Settings > Privacy & Security > Input Monitoring**.
2. Izinkan aplikasi yang meluncurkan service, misalnya Terminal, atau executable Python jika macOS menampilkannya sebagai aplikasi yang bertanggung jawab.
3. Periksa juga **Accessibility** bila listener belum siap. Identitas izin bisa berbeda ketika berpindah dari Terminal ke LaunchAgent.
4. Jika macOS meminta aplikasi peluncur ditutup, tutup dan buka kembali, kemudian jalankan ulang service.
5. Lihat **Keyboard: listener siap** di dashboard. Status ini berasal dari event tap aktual, bukan sekadar tanda centang permission.

Untuk listener *listen-only*, Input Monitoring adalah pengaturan yang relevan; jangan menganggap Accessibility selalu satu-satunya izin. Dashboard menampilkan instruksi ketika event tap gagal dibuat dan mencoba lagi setiap dua detik. Tidak ada upaya memberikan atau melewati izin secara otomatis.

**Secure Input** dapat membuat event keyboard tidak terlihat, terutama di kolom kata sandi/aplikasi tertentu. Ini batas platform, bukan alasan untuk menonaktifkan perlindungan. Sebuah tap yang siap juga tidak menjamin event tersedia saat Secure Input aktif.

## Menggunakan dashboard

1. Aktifkan suara, pilih pack, lalu atur volume.
2. Mode **satu suara** memakai suara fallback untuk semua tombol.
3. Mode **per tombol** memakai urutan: override dashboard → mapping `pack.json` → suara fallback.
4. Klik tombol pada keyboard visual atau pilih lewat dropdown. Pilih audio, kemudian **Simpan mapping**.
5. **Reset tombol** menghapus override dashboard; jika pack memiliki mapping bawaan, mapping itu berlaku lagi.
6. **Test tombol** memainkan mapping yang sudah tersimpan menurut mode aktif, bukan perubahan dropdown yang belum disimpan.
7. Pilih atau seret WAV/MP3, klik **Unggah audio**, kemudian pilih pack **Custom**. Upload tidak diam-diam mengganti pack aktif.
8. Pilih **Suara default / fallback** untuk mengubah suara utama pack. Semua perubahan tersimpan dan berlaku tanpa restart service.

Keyboard visual tidak menjadi monitor ketikan. Tombol yang disorot adalah tombol yang dipilih untuk konfigurasi, bukan tombol terakhir yang Anda ketik.

Label keyboard mengikuti posisi fisik ANSI/macOS, bukan layout bahasa aktif. Dropdown mencakup tombol tambahan seperti numpad. Tombol Fn/media yang tidak dikirim macOS sebagai event keyboard biasa dapat tidak berbunyi. Pada layar maksimal 820 px, keyboard visual digantikan dropdown agar target klik tidak terlalu kecil; semua mapping tetap tersedia.

### Batas audio dan unggahan

- WAV atau MP3, maksimal 10 MiB per berkas, maksimal 10 detik, 1–2 kanal, sample rate 8–192 kHz.
- Maksimal 16 berkas per pack, total buffer decoded maksimal 64 MiB saat pack diterima.
- Nama: huruf Latin, angka, spasi, titik, tanda hubung, garis bawah; harus dimulai huruf/angka. Path traversal, symlink, nama terlalu panjang, berkas kosong, dan audio palsu ditolak.
- Isi file diperiksa, lalu benar-benar didekode sebelum dipublikasikan. Ekstensi saja tidak dianggap validasi.
- File upload mendapat akhiran acak agar tidak menimpa file sebelumnya. Tidak ada penimpaan berdasarkan nama pengguna.
- Jeda 0–200 ms berlaku **global**, bukan per tombol. Jeda 0 mengizinkan ketukan yang sangat berdekatan. Auto-repeat tetap diabaikan.
- Batas 1–8 suara bersamaan bersifat global lintas klip, termasuk preview. Saat penuh, suara baru dilewati, bukan diantrikan tanpa batas.
- Volume mixer dibagi batas suara bersamaan sebagai headroom konservatif. Jika jumlah voice dinaikkan, satu suara akan terdengar lebih pelan.
- Antrian dibatasi dan event berumur lebih dari 100 ms dibuang agar tidak muncul rentetan suara terlambat.

### Latensi

**Di bawah 30 ms adalah target, bukan hasil pengukuran akustik yang sudah dibuktikan.**

Semua audio pack aktif didekode ke memori sebelum dipakai. Jalur keydown hanya menentukan nama buffer, memasukkannya ke antrian kecil, kemudian menjadwalkan node audio yang sudah dibuat. Tidak ada pembacaan file, decoding, HTTP request, atau `afplay`/subprocess per tombol.

Waktu keydown sampai suara benar-benar terdengar juga dipengaruhi output device, buffer sistem, beban mesin, dan Bluetooth. Uji fisik dengan mikrofon/loopback atau rekaman berkecepatan tinggi diperlukan untuk membuktikan target. Keberhasilan `play()` atau waktu HTTP bukan ukuran latensi akustik. Setelah perangkat audio berubah atau mesin audio berhenti, pilih output yang benar di macOS, lalu klik **Muat ulang audio & pack**.

## Berkas dan konfigurasi

```text
keysound/
  keysound.py
  dashboard.html
  requirements.txt
  README.md
  .gitignore
  packs/gunshot/
    pack.json
    gunshot.wav

~/.config/keysound/
  config.json
  packs/custom/
    pack.json
    ...file unggahan...
```

Konfigurasi hanya satu `config.json`. `pack.json` adalah metadata aset, bukan konfigurasi service tambahan. Penyimpanan konfigurasi menggunakan temporary file di direktori yang sama, flush, lalu atomic replace. Konfigurasi tidak sah tidak ditimpa diam-diam; service melaporkan galat saat startup.

Contoh konfigurasi:

```json
{
  "enabled": false,
  "pack": "gunshot",
  "mode": "per-key",
  "volume": 0.25,
  "debounce_ms": 12,
  "max_voices": 4,
  "overrides": {"gunshot": {"36": "gunshot.wav"}},
  "default_sound": {}
}
```

Gunakan dashboard untuk perubahan saat service hidup. Jika mengedit JSON langsung, hentikan service terlebih dahulu, simpan salinan konfigurasi lama, lalu jalankan kembali. Menghapus audio yang masih dipakai mapping/default akan ditolak saat pemuatan; perbarui referensinya sebelum menghapus berkas. Tidak ada fitur hapus aset atau marketplace.

## Membuat sound pack

Buat direktori di `packs/nama-pack/` pada proyek, atau `~/.config/keysound/packs/nama-pack/`. Gunakan ID direktori unik berisi huruf, angka, `-`, atau `_`. Jangan menduplikasi `gunshot`/`custom` di dua lokasi.

Masukkan audio dan `pack.json`:

```json
{
  "name": "Suara Saya",
  "default": "default.wav",
  "mapping": {
    "36": "enter.wav",
    "49": "space.mp3",
    "51": "backspace.wav"
  },
  "source": "Cantumkan pembuat, sumber, dan izin penggunaan audio Anda."
}
```

Semua file yang dirujuk harus benar-benar ada dalam folder yang sama. Mapping memakai kode tombol virtual macOS dalam string, bukan karakter hasil ketikan. Contoh: `36` Enter, `49` Space, `51` Backspace, `0` posisi A. Daftar kode tersedia dalam `KEYS` di `keysound.py` dan dropdown dashboard. Klik **Muat ulang audio & pack** untuk memuat pack baru tanpa restart.

### Sumber Gunshot bawaan

`gunshot.wav` adalah **efek tembakan sintetis buatan proyek ini**, bukan rekaman senjata dan bukan sampel yang diunduh dari situs lain. Dibuat deterministik dari derau pseudoacak seed 27, gelombang sinus berfrekuensi menurun, dan envelope eksponensial. Durasi 0,24 detik, mono PCM 16-bit, 48 kHz. Ada fade-in singkat dan ekor yang meredup. Ini suara nyata yang dapat diputar, bukan placeholder kosong.

Aset sintetis `packs/gunshot/gunshot.wav` didedikasikan sebagai CC0-1.0. Tidak ada klaim lisensi tersebut untuk audio yang Anda unggah sendiri. Metadata sumber ikut tersimpan di `pack.json` dan ditampilkan di dashboard.

## Autostart lewat LaunchAgent (opsional)

**Belum dipasang otomatis.** Ikuti bagian ini hanya jika ingin service berjalan ketika login. Hentikan instance terminal terlebih dahulu supaya tidak berebut port. Izin macOS perlu diperiksa kembali setelah berpindah metode peluncuran.

Dari direktori proyek, buat plist dengan jalur absolut. Cuplikan berikut menolak menimpa plist yang sudah ada:

```sh
python3 - <<'PY'
import plistlib
from pathlib import Path
project = Path.cwd().resolve()
assert (project / 'keysound.py').is_file(), 'Jalankan dari direktori keysound'
assert (project / '.venv/bin/python').exists(), 'Pasang .venv terlebih dahulu'
root = Path.home() / '.config/keysound'
root.mkdir(parents=True, exist_ok=True)
target = Path.home() / 'Library/LaunchAgents/local.keysound.plist'
target.parent.mkdir(parents=True, exist_ok=True)
config = {
    'Label': 'local.keysound',
    'ProgramArguments': [str(project / '.venv/bin/python'), '-u', str(project / 'keysound.py')],
    'WorkingDirectory': str(project),
    'RunAtLoad': True,
    'KeepAlive': True,
    'ThrottleInterval': 15,
    'ProcessType': 'Interactive',
    'StandardOutPath': str(root / 'service.log'),
    'StandardErrorPath': str(root / 'service-error.log'),
}
with target.open('xb') as stream:
    plistlib.dump(config, stream)
print(target)
PY
plutil -lint "$HOME/Library/LaunchAgents/local.keysound.plist"
launchctl bootstrap "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.keysound.plist"
launchctl print "gui/$(id -u)/local.keysound"
```

Menonaktifkan autostart dan menghentikan instance LaunchAgent:

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.keysound.plist"
```

Setelah `bootout`, hapus `local.keysound.plist` melalui Finder bila tidak ingin aktif lagi pada login berikutnya. Jangan memakai `sudo`. Log di atas hanya keluaran startup/galat, tidak ada log tombol. Jika folder proyek atau interpreter dipindahkan, plist perlu diperbarui. Template plist sudah diperiksa sintaksnya; bootstrap dan permission dalam konteks LaunchAgent belum diuji karena autostart tidak dipasang.

## Privasi dan keamanan localhost

- Event tap bersifat pasif; KeySound tidak memblokir atau memodifikasi input.
- Kode tombol dipakai sementara untuk resolusi suara, lalu dibuang. Antrian hanya memuat nama suara, generation, dan timestamp; tidak ada riwayat tombol atau teks.
- Tidak ada akses mikrofon, upload ke internet, telemetry, font/CDN eksternal, atau endpoint berisi ketikan.
- Tanpa autentikasi sesuai ruang lingkup aplikasi lokal. Pemeriksaan Host, Origin, header khusus untuk operasi tulis, pembatasan ukuran, dan CSP tetap diterapkan untuk mengurangi risiko situs lain mengendalikan service.
- Ini bukan batas keamanan terhadap proses lokal lain atau orang yang memiliki akses ke akun macOS Anda. Jangan memasang reverse proxy/tunnel ke aplikasi ini.
- HTTP server satu proses dan satu request pada satu waktu, timeout koneksi 5 detik. Cukup untuk dashboard pribadi; bukan server publik atau multi-user.

## Verifikasi dan batas klaim

Self-check yang dapat dijalankan ulang:

```sh
python3 keysound.py --selftest
```

Memeriksa default/config persistence, penolakan tipe/nilai tidak sah, single/per-key/override/fallback, serta validasi nama, traversal, signature, file kosong, dan batas upload. Tidak meminta permission dan tidak memainkan suara. Pengujian integrasi native dan dashboard dilakukan terpisah pada mesin pengembangan, dengan konfigurasi sementara; self-check bukan bukti akustik.

Hasil pengujian nyata pada 8 Oktober 2026:

- PASS: decode WAV, engine berjalan, buffer audio diputar, batas voice berlaku, node dipakai ulang.
- PASS: event uji F18 diposting melalui Quartz, diterima event tap global, diteruskan ke worker, lalu ke playback native. Tidak ada teks dimasukkan ke aplikasi.
- PASS: HTTP config, penyimpanan JSON, mapping, auto-repeat, debounce, upload, fallback, pergantian pack, dan penolakan input tidak sah.
- PASS: Origin asing, Host asing, dan operasi tulis tanpa header khusus ditolak.
- PASS: simulasi penolakan pembuatan event tap menampilkan instruksi izin; listener pulih saat event tap kembali tersedia. Permission OS yang sudah ada tidak dicabut untuk tes ini.
- PASS: WAV dan MP3 stereo 44,1 kHz diunggah lewat dashboard dan diputar melalui backend native. Berkas dengan header WAV palsu ditolak oleh decoder.
- Belum diverifikasi: latensi akustik <30 ms, penggunaan hardware Apple Silicon, bootstrap LaunchAgent, dan seluruh variasi tombol Fn/media.

### Delivery gate dashboard

- **Hard gate PASS:** kontrol punya aksi nyata; empty/loading/error state tersedia; tidak ada metrik pemasaran, tautan kosong, atau aset orang/logo rekaan. Kontrol HTML native, fokus 3 px, dan urutan Tab diuji.
- **Purpose gate PASS:** kuning menandai aktivasi/pilihan pack, cyan menandai mapping, coral menandai galat/matikan. Border tebal mengikuti bentuk keycap; hard shadow terbatas pada kontrol, pack aktif, dan feedback. Tidak ada gradient, blur, atau animasi dekoratif.
- **Liveliness PASS:** ENERGY 3 / RHYTHM 2 / MOTION 1. Panel kontrol adalah titik perhatian, keyboard visual adalah motif fungsional, dan layout mengikuti alur pilih pack → mapping → upload, bukan dashboard statistik generik.
- **Craftsmanship PASS:** font sistem tebal mengikuti identitas neobrutalism tanpa unduhan; ruang memisahkan pengaturan global, mapping, dan unggahan. Pengujian lebar 320, 390, 640, 768, 820, 821, 1024, 1100, 1140, 1141, dan 1280 px tidak menemukan overflow horizontal. Keyboard yang terlihat memiliki target minimal 44×44 px; layar sempit memakai dropdown.
- **Kontras PASS:** teks gelap terhadap kuning 11,25:1, cyan 12,51:1, coral 7,16:1, putih hangat 17,30:1, latar 15,46:1. Teks kontrol nonaktif 6,99:1. Rasio dihitung, bukan ditebak dari tampilan.
- **Click-through PASS:** toggle on/off; volume; mode; kedua kartu pack; 76 tombol keyboard visual; dropdown tombol; simpan/reset mapping; Test tombol; fallback/Test; simpan batas; muat ulang; pilih berkas; drag-and-drop; upload WAV/MP3; empty upload; penolakan fake WAV; disclosure pengaturan/izin. Tidak ada JavaScript exception atau unhandled rejection yang tertangkap selama pengujian kontrol.

### Referensi implementasi

Dokumentasi primer yang diperiksa:

```text
https://developer.apple.com/documentation/avfaudio/avaudioplayernode
https://support.apple.com/guide/mac-help/control-access-to-input-monitoring-on-mac-mchl4cedafb6/mac
```

### Yang perlu kamu lakukan (sekali saja):

1. Buka System Settings → Privacy & Security → Input Monitoring
2. Klik tombol + dan tambahkan:

   /Users/ascaliko/Ascaliko/Programming/Projects/me/orca/keysound/.venv/bin/python

3. Pastikan toggle-nya ON
4. Cek juga Accessibility — tambahkan path yang sama jika belum ada

Setelah izin diberikan, listener akan otomatis siap dalam beberapa detik (service retry setiap 2 detik). Cek status di dashboard http://127.0.0.1:8765 —harusnya "Keyboard: listener siap".