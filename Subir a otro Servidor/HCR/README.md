# HCR Server

[Bahasa Indonesia](#bahasa-indonesia) | [English](#english)

## Bahasa Indonesia

Installer untuk Linux dengan systemd. Simpan `install.sh` dan binary `hcr-server`
yang sesuai arsitektur server dalam satu folder, misalnya `/root/hcr`.
Folder tempat installer berada otomatis menjadi direktori kerja service.

### Persiapan

Pilih arsip sesuai arsitektur Linux: `386` untuk x86 dengan SSE2, `amd64` untuk x86-64,
`arm` untuk ARMv7, atau `arm64` untuk ARM 64-bit. Ekstrak ke folder baru, lalu periksa
versi binary dari folder tersebut:

```bash
./hcr-server --version
```

Ambil paket dari sumber tepercaya.
Sertifikat dan private key disiapkan sendiri dan tidak disertakan dalam arsip.

```bash
cd /root/hcr
sudo chown -R root:root /root/hcr
sudo chmod 755 /root/hcr install.sh hcr-server
```

Folder dan berkas harus milik root serta tidak bisa ditulis pengguna lain.
Pastikan port yang dipilih tersedia dan diizinkan firewall.

### Instalasi

Untuk HCR Plain tanpa TLS, cukup siapkan script dan binary:

```bash
sudo ./install.sh --transport plain --port 8080 --target 127.0.0.1:22
```

Untuk menerima TLS dan non-TLS pada port yang sama, tambahkan `fullchain.pem`
dan `privkey.pem` milik server Anda ke folder tersebut, lalu jalankan:

```bash
sudo chmod 600 privkey.pem
sudo ./install.sh
```

Default: port `8080`, transport `auto` (TLS dan non-TLS), target SSH
`127.0.0.1:22`. Gunakan `--port` untuk memilih port pada semua alamat jaringan server,
atau `--transport tls` untuk menerima TLS saja.

### Mengubah pengaturan

Parameter lain ada di `./install.sh --help`. Jalankan ulang dengan seluruh
parameter yang ingin dipakai untuk mengubah pengaturan; service akan restart
dan koneksi aktif terputus. Parameter yang tidak disebut kembali ke default.
Nilai Frame diperiksa sebelum file service ditulis atau service di-restart.
Parameter lain diteruskan ke HCR Server. Jika service gagal berjalan, lihat pesan
error melalui `journalctl -u hcr-server`.
Installer mengelola nama service `hcr-server` tanpa memeriksa folder asalnya.
Service berjalan sebagai root dengan pengaturan bawaan systemd, tanpa batas resource
atau isolasi tambahan.

### Frame dan diagnostik

Ukuran frame download diatur lewat `--max-download-frame`, default `16384` byte.
Rentang `1` sampai `262140` byte juga ditampilkan di bantuan installer. Untuk nilai
di atas `16384`, installer memeriksa batas yang didukung binary di folder yang sama.
Jika nilainya tidak valid atau dukungan tersebut belum tersedia, installer berhenti
tanpa mengubah service yang ada. Nilai di atas `16384` memerlukan
HC terbaru di seluruh client yang memakai listener tersebut. Frame lebih besar
bukan jaminan lebih cepat dan menggunakan buffer lebih besar.

Untuk pemeriksaan jalur, tambahkan `--diagnostics-interval 10s` bersama parameter
lain. Interval aktif dapat dipilih dari 10 detik sampai 5 menit; `0` mematikannya.
Log berisi ringkasan teknis tanpa payload atau credential. Sertakan kembali opsi
ini ketika menjalankan ulang installer jika diagnostik ingin tetap aktif.

### Status dan uninstall

```bash
./install.sh --version
systemctl status hcr-server
journalctl -u hcr-server -n 50
```

Untuk melepas service:

```bash
sudo ./install.sh --uninstall
```

Uninstall menghentikan service dan melepas tautan systemd. Script, binary,
sertifikat, dan file unit tetap tersimpan di folder ini.

## English

Installer for Linux with systemd. Keep `install.sh` and the `hcr-server` binary
for your server's architecture in the same folder, such as `/root/hcr`.
The installer folder automatically becomes the service's working directory.

### Preparation

Choose the archive for your Linux architecture: `386` for x86 with SSE2, `amd64`
for x86-64, `arm` for ARMv7, or `arm64` for 64-bit ARM. Extract it into a new folder,
then check the binary version from that folder:

```bash
./hcr-server --version
```

Obtain the package from a trusted source.
Certificates and private keys are supplied by you and are not included in the archive.

```bash
cd /root/hcr
sudo chown -R root:root /root/hcr
sudo chmod 755 /root/hcr install.sh hcr-server
```

The folder and files must be owned by root and not writable by other users.
Make sure the chosen port is available and allowed by your firewall.

### Installation

For HCR Plain without TLS, only the script and binary are needed:

```bash
sudo ./install.sh --transport plain --port 8080 --target 127.0.0.1:22
```

To accept TLS and non-TLS connections on the same port, add your server's
`fullchain.pem` and `privkey.pem` to that folder, then run:

```bash
sudo chmod 600 privkey.pem
sudo ./install.sh
```

Defaults: port `8080`, transport `auto` (TLS and non-TLS), SSH target
`127.0.0.1:22`. Use `--port` to select the port on all server network addresses,
or `--transport tls` to accept TLS only.

### Changing settings

Other options are listed in `./install.sh --help`. To change settings, run the installer
again with every option you want to keep. This restarts the service and disconnects
active sessions. Omitted options return to their defaults.
The Frame value is checked before writing the service file or restarting the service.
Other parameters are passed to HCR Server. If the service fails to start, check the
error messages with `journalctl -u hcr-server`.
The installer manages the service named `hcr-server` without checking its original folder.
The service runs as root with systemd defaults, without additional resource limits
or isolation.

### Frames and diagnostics

Set the maximum download frame size with `--max-download-frame`; the default is
`16384` bytes. The range of `1` through `262140` bytes is also shown in the installer
help. For values above `16384`, the installer checks the limit supported by the binary
in the same folder. If the value is invalid or that support is unavailable, it stops
without changing the existing service. Values above `16384` require updated HC
on every client using that listener. Larger frames do not guarantee higher speeds
and use larger buffers.

For connection diagnostics, add `--diagnostics-interval 10s` alongside your other
options. Active intervals can range from 10 seconds to 5 minutes; `0` turns diagnostics
off. Logs contain technical summaries without payloads or credentials. Include this
option again when rerunning the installer to keep diagnostics enabled.

### Status and uninstall

```bash
./install.sh --version
systemctl status hcr-server
journalctl -u hcr-server -n 50
```

To remove the service:

```bash
sudo ./install.sh --uninstall
```

Uninstall stops the service and removes the systemd link. The script, binary,
certificates, and unit file remain in this folder.
