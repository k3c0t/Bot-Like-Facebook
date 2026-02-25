# Facebook Auto like

GUI desktop tool untuk melakukan auto-like postingan di Facebook feed menggunakan Selenium + PyQt5.

**⚠️ Penting**: Penggunaan bot semacam ini melanggar [Facebook Terms of Service](https://www.facebook.com/terms). Akun Anda berisiko tinggi untuk di **banned** atau **checkpoint** permanen. Gunakan dengan risiko sendiri.

## Fitur

- Login menggunakan cookies (cookies.json)
- Menampilkan identitas akun (nama, ID, foto profil dengan efek glow)
- Auto-like postingan yang muncul di feed
- Batas waktu berjalan (default 20 menit)
- Delay acak (anti-pattern detection)
- Tabel log aktivitas real-time
- Progress bar & tombol Start/Stop
- Headless mode (bisa dimatikan di config)

## Requirements

Python 3.8 – 3.12 direkomendasikan


## pengaturan 

COOKIE_FILE = "cookies.json"
MAX_RUNTIME_MINUTES = 20
DELAY_MIN = 5
DELAY_MAX = 10
HEADLESS = True           # Ubah ke False jika ingin melihat browser
SCROLL_PAUSE_MIN = 3
SCROLL_PAUSE_MAX = 6

