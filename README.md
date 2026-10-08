# KeySound

Suara keyboard global dengan dashboard neobrutalism lokal. Mendukung **macOS dan Windows**, tanpa akun, database, cloud, atau framework web. Pack bawaan berisi efek tembakan sintetis yang benar-benar dapat diputar.

## Windows: mulai di sini

Gunakan Python **3.13 atau 3.14, 64-bit**. Dari PowerShell di folder proyek:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe keysound.py --selftest
.\.venv\Scripts\python.exe keysound.py
```

Buka `http://127.0.0.1:8765`, lalu klik **Aktifkan suara**. Tidak perlu mengaktifkan venv dengan `Activate.ps1`. Jangan menyalin `.venv` dari Mac; buat venv baru di Windows.

**Ctrl+C** menghentikan proses terminal. Menutup tab dashboard tidak menghentikan aplikasi. Tombol **Matikan suara** hanya membisukan pemicu keyboard, bukan menutup service.

### Autostart, start, stop Windows

Jalankan di sesi pengguna Windows yang akan memakai KeySound. Hentikan instance terminal terlebih dahulu supaya port tidak bentrok.

```powershell
# Pasang task dan mulai sekarang; berikutnya otomatis setelah login.
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 Install

# Periksa task dan endpoint dashboard.
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 Status

# Hentikan proses task DAN nonaktifkan autostart.
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 Stop

# Mulai lagi DAN aktifkan autostart kembali.
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 Start

# Hapus task tanpa menghapus konfigurasi atau audio Anda.
powershell -NoProfile -ExecutionPolicy Bypass -File .\windows.ps1 Uninstall
```

`-ExecutionPolicy Bypass` di sini berlaku hanya untuk proses PowerShell tersebut, tidak mengubah kebijakan global. Baca `windows.ps1` sebelum menjalankannya. Jika kebijakan organisasi menolak registrasi task, gunakan mode terminal atau minta persetujuan administrator; jangan melewati kebijakan tersebut.

Task `KeySound` memakai `pythonw.exe`, akun pengguna yang login, hak **Limited**, dan tidak meminta kata sandi. Log startup/galat: `%LOCALAPPDATA%\KeySound\service.log`. Tidak ada log ketikan. Skrip menolak menimpa task dengan jalur berbeda dan menolak instalasi ketika port 8765 sedang dipakai. Jika proyek dipindahkan, uninstall task dari lokasi lama sebelum memasang di lokasi baru.

Ini **background app dalam sesi desktop**, bukan Windows Service/Session 0. Task dimulai setelah login, bukan sebelum login. Layar login, UAC/secure desktop, Fn/media tertentu, dan aplikasi yang membatasi input tidak dijamin tertangkap. Tidak ada upaya melewati batas tersebut. Jangan menjalankan sebagai administrator hanya untuk memperluas cakupan listener.

## macOS

Backend macOS tetap memakai Quartz + AVAudioEngine, bukan diganti dengan backend Windows.

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python keysound.py --selftest
.venv/bin/python keysound.py
```

Jika Python lokal tidak menyediakan pip, `uv venv .venv --python python3` lalu `uv pip install --python .venv/bin/python -r requirements.txt` adalah alternatif.

### Izin macOS

Buka **System Settings > Privacy & Security > Input Monitoring** dan izinkan aplikasi peluncur/Python yang ditampilkan macOS. Periksa juga **Accessibility** bila listener belum siap. Identitas izin bisa berbeda antara Terminal dan LaunchAgent; jangan mengasumsikan sebuah symlink venv selalu menjadi identitas yang dinilai macOS.

**Restart proses setelah menambah/mengubah izin.** Percobaan ulang pembuatan tap tidak selalu memperbarui izin proses yang sudah berjalan. Secure Input dapat membatasi event keyboard; KeySound tidak melewatinya.

### Autostart macOS (opsional)

Hentikan instance terminal terlebih dahulu. Dari folder proyek:

```sh
python3 - <<'PY'
import plistlib
from pathlib import Path
project = Path.cwd().resolve()
assert (project / 'keysound.py').is_file()
assert (project / '.venv/bin/python').exists()
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

`open('xb')` menolak menimpa plist lama. Setelah izin diperbarui, restart agent:

```sh
launchctl kickstart -k "gui/$(id -u)/local.keysound"
```

Stop/unload:

```sh
launchctl bootout "gui/$(id -u)" "$HOME/Library/LaunchAgents/local.keysound.plist"
```

`bootout` menghentikan agent dalam sesi saat ini. Untuk meniadakan autostart pada login berikutnya, hapus plist melalui Finder setelah `bootout`. Konfigurasi/audio tidak perlu dihapus. `KeepAlive` bisa memulai kembali proses yang hanya dihentikan dengan `kill`, jadi gunakan `bootout` untuk stop terkontrol. Tidak perlu `sudo`.

## Dashboard dan mapping

- Instalasi baru: suara OFF, Gunshot, volume 25%, jeda global 12 ms, maksimal 4 suara bersamaan.
- Pengaturan tersimpan dan berlaku langsung. Restart memakai pengaturan terakhir, bukan selalu default.
- Mode **single**: semua tombol memakai suara fallback.
- Mode **per-key**: override dashboard → mapping pack → fallback.
- Pilih tombol pada keyboard visual/dropdown, pilih audio, lalu **Simpan mapping**.
- **Reset tombol** menghapus override; mapping pack dapat berlaku kembali.
- **Test tombol** memakai mapping tersimpan menurut mode aktif, bukan dropdown yang belum disimpan.
- **Unggah audio** menambahkan ke pack Custom. Pilih Custom untuk memakainya; upload tidak mengganti pack aktif diam-diam.
- Tombol **Muat ulang audio & pack** memuat pack baru atau perangkat output baru tanpa restart service.
- Layar sempit memakai dropdown, bukan keycap yang diperkecil di bawah target klik 44 px.

Nomor mapping adalah ID internal yang dipertahankan dari versi macOS awal. Windows menerjemahkan **scan code posisi fisik**, bukan langsung memakai `vkCode`. Jadi `36` tetap Enter, `49` Space, `51` Backspace, `0` posisi A pada kedua platform. Enter numpad berbeda dari Enter utama. Win menggantikan label Cmd; Alt menggantikan Option. Label mengikuti layout fisik ANSI, bukan karakter hasil layout bahasa aktif. Tombol tidak dikenal memakai fallback dan mungkin tidak memiliki pilihan mapping tersendiri.

Keyboard visual bukan monitor ketikan. Sorotan menunjukkan tombol yang dipilih untuk konfigurasi, bukan tombol terakhir yang diketik.

## Audio, privasi, dan batas

- WAV/MP3, maksimal 10 MiB/file, 10 detik, mono/stereo, 8–192 kHz, maksimal 16 file per pack.
- Decoder memeriksa isi audio, bukan hanya ekstensi. Upload traversal/symlink/berkas palsu ditolak; nama akhir diberi akhiran unik agar tidak menimpa aset lama.
- Audio dipreload. Tidak ada decoding, HTTP, atau proses `afplay` per ketukan.
- Windows memakai satu output stream dan mixer maksimal 8 voice. Konversi sample rate dilakukan saat preload dengan interpolasi linear, cukup untuk efek pendek tetapi bukan konverter musik berfidelitas tinggi. Buffer sumber dan output dibatasi total 64 MiB.
- macOS memakai PCM buffer dan AVAudioPlayerNode, dengan batas buffer decoded 64 MiB. Kedua backend membatasi voice secara global dan melewati suara baru jika penuh.
- Volume dibagi batas voice untuk headroom konservatif. Batas voice yang lebih tinggi membuat satu ketukan lebih pelan.
- Auto-repeat ditolak. Windows menyimpan set tombol yang **sedang ditahan** untuk tujuan itu dan menghapusnya saat dilepas; tidak menyimpan riwayat/karakter ketikan.
- Debounce 0–200 ms berlaku global. Antrian terbatas; pemicu berumur lebih dari 100 ms dibuang.
- Jika output berhenti, playback mencoba memulihkannya. Windows membatasi percobaan gagal agar tidak berulang pada setiap ketukan. Jika perangkat berubah tetapi stream lama masih aktif, pilih output OS yang benar dan klik **Muat ulang audio & pack**.
- **Latensi akustik <30 ms belum dibuktikan.** `play()` sukses, CI hijau, atau HTTP 200 bukan bukti suara terdengar/latensi fisik. Bluetooth, driver, dan buffer perangkat memengaruhi hasil.
- Tidak menggunakan mikrofon, telemetry, CDN, atau pengiriman audio/ketikan ke internet.
- Dashboard hanya `127.0.0.1`, tanpa login, dengan validasi Host/Origin, header khusus pada mutasi, dan CSP. Ini bukan perlindungan terhadap proses lokal yang sudah mengakses akun Anda. Jangan mengekspos lewat proxy/tunnel.

## Konfigurasi dan pack

- macOS: `~/.config/keysound/config.json`.
- Windows: `%LOCALAPPDATA%\KeySound\config.json`.
- Audio custom berada di `packs/custom/` dalam direktori konfigurasi masing-masing.
- `--config-dir PATH` dan `--port 8767` tersedia untuk instance uji terpisah.
- `--log-file PATH` tersedia untuk log startup/galat ketika dijalankan tanpa terminal.

Konfigurasi UTF-8 disimpan dengan atomic replace. Jika mengedit JSON langsung, hentikan aplikasi lebih dahulu. Konfigurasi rusak tidak ditimpa diam-diam. Jangan menghapus audio yang masih direferensikan mapping/default.

Untuk pack baru, buat direktori `packs/nama-pack/` di proyek atau direktori konfigurasi. ID direktori harus unik, berisi huruf, angka, `-`, atau `_`. Tambahkan audio dan `pack.json`:

```json
{
  "name": "Suara Saya",
  "default": "default.wav",
  "mapping": {"36": "enter.wav", "49": "space.mp3"},
  "source": "Cantumkan pembuat, sumber, dan izin penggunaan audio."
}
```

Semua file yang dirujuk harus ada. Klik **Muat ulang audio & pack** setelah menambah pack. Tidak ada marketplace atau penghapusan aset otomatis.

`packs/gunshot/gunshot.wav` adalah efek sintetis dari derau pseudoacak seed 27, sinus menurun, dan envelope eksponensial; bukan rekaman senjata atau sampel pihak ketiga. Durasi 0,24 detik, PCM16 mono 48 kHz. Aset tersebut didedikasikan sebagai CC0-1.0; pernyataan ini tidak berlaku untuk unggahan pengguna.

## Dependency dan struktur

`requirements.txt` menggunakan platform markers. Windows tidak memasang PyObjC, macOS tidak memerlukan paket Windows untuk menjalankan aplikasi.

| Platform | Dependency langsung | Fungsi |
|---|---|---|
| macOS | Quartz, AVFoundation melalui PyObjC | Global event tap dan audio native |
| Windows | pynput, sounddevice, soundfile, NumPy | Hook tanpa pembacaan karakter, output stream, decoding, dan mixing/resampling |

Ada dependency transitif seperti CFFI, six, dan framework PyObjC. Tidak memerlukan FFmpeg, Node, atau paket GUI. `windows_backend.py` mengisolasi API Windows; `keysound.py` tetap menangani konfigurasi, pack, HTTP, worker, dan backend macOS. Dashboard tetap satu file HTML/CSS/JS.

## Pengujian

```sh
python keysound.py --selftest
python -m unittest test_backends -v
```

Self-check pertama hanya memakai stdlib. `test_backends.py` menguji decoder macOS (khusus Mac), scan code Windows, auto-repeat, WAV/MP3, konversi sample rate, hasil PCM mixer, batas voice, dan API dengan **perangkat audio palsu yang diberi label jelas di tes**. Tes hook Windows benar-benar mencoba memasang/melepas hook bila dijalankan di Windows; tidak memasukkan ketikan atau merekam teks.

Untuk menjalankan seluruh tes Windows-backend di Mac, diperlukan sounddevice/soundfile/NumPy tambahan. Itu bukan dependency runtime macOS. CI memisahkan instalasi per platform dan memeriksa sintaks `windows.ps1` dengan parser PowerShell.

CI tidak membuktikan suara terdengar di laptop Windows pengguna, akses semua aplikasi, latensi <30 ms, atau autostart setelah reboot fisik. Setelah instalasi di Windows, periksa **Keyboard: listener siap**, tekan Test, uji ketikan di Notepad, lalu uji Install/Stop/Start dan login ulang. Jangan menyimpulkan hasil hardware hanya dari respons `played: true`.

### Pemeriksaan dashboard

Desain tetap neobrutalism, ENERGY 3 / RHYTHM 2 / MOTION 1. Perubahan lintas platform terbatas pada teks, bantuan sistem operasi, dan label Alt/Win. Tidak menambah komponen dekoratif atau framework. Pengujian awal meliputi kontrol, empty/loading/error state, target klik, fokus keyboard, kontras, dan viewport 320–1280 px; pengujian hardware Windows tetap diperlukan.

### Referensi primer

```text
https://developer.apple.com/documentation/avfaudio/avaudioplayernode
https://support.apple.com/guide/mac-help/control-access-to-input-monitoring-on-mac-mchl4cedafb6/mac
https://pynput.readthedocs.io/en/latest/faq.html
https://python-sounddevice.readthedocs.io/en/latest/api/streams.html
https://python-soundfile.readthedocs.io/en/latest/
https://learn.microsoft.com/en-us/windows/win32/services/interactive-services
https://learn.microsoft.com/en-us/powershell/module/scheduledtasks/new-scheduledtaskprincipal
```
