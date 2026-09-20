# 🌾 PetaniProxy — Panduan Lengkap Penggunaan (Usage Guide)

Panduan praktis cara menggunakan **PetaniProxy (Panen Proxy Cepat, Segar & Bergizi)**, cara kustomisasi jumlah panen (> 15, misal 50 atau 100 proxy), filter negara, penggunaan Local Rotating Gateway, dan integrasi ke bot/scraper.

---

## Daftar Isi
1. [Untuk Apa Saja Tool Ini Digunakan? (Real-World Use Cases)](#1-untuk-apa-saja-tool-ini-digunakan-real-world-use-cases)
2. [Cara Menjalankan Menu Interaktif & Preset Khusus](#2-cara-menjalankan-menu-interaktif--preset-khusus)
3. [Cara Panen Lebih dari 15 Proxy (Kustom Jumlah)](#3-cara-panen-lebih-dari-15-proxy-kustom-jumlah)
4. [Cara Menjalankan Local Rotating Proxy & REST API (Port 8888)](#4-cara-menjalankan-local-rotating-proxy--rest-api-port-8888)
5. [Cara Panen Khusus Proxy Tertentu](#5-cara-panen-khusus-proxy-tertentu)
   - [Khusus Proxy Elite (High Anonymous)](#a-khusus-proxy-elite-high-anonymous)
   - [Khusus Negara Tertentu (ID, SG, US, dll)](#b-khusus-negara-tertentu-id-sg-us-dll)
   - [Khusus Tembus Website Tertentu (Google, Shopee, dll)](#c-khusus-tembus-website-tertentu-google-shopee-dll)
6. [Cara Integrasi ke Script Python / Scraper / Bot](#6-cara-integrasi-ke-script-python--scraper--bot)
7. [Tabel Semua Perintah CLI Lengkap](#7-tabel-semua-perintah-cli-lengkap)

---

## 1. Untuk Apa Saja Tool Ini Digunakan? (Real-World Use Cases)

Fungsi mendasar tool ini adalah menyediakan pasokan **IP proxy gratis tanpa batas** yang terus dirotasi. Berikut adalah skenario pemanfaatan terbesarnya:

1. **🕷️ Web Scraping Skala Besar**: Menghindari pemblokiran IP (*HTTP 429 Too Many Requests*) saat menyedot ribuan data marketplace (Shopee/Tokopedia), portal berita, atau media sosial.
2. **🤖 AI & LLM Load Balancing**: Membagi request bot AI (seperti bot WhatsApp Wakupi / Grok / ChatGPT / Gemini) ke puluhan IP agar tidak terkena limit rate API.
3. **👥 Otomasi Bot & Multi-Akun**: Mencegah bot kena banned atau deteksi checkpoint massal (Puppeteer, Playwright, Selenium) karena tiap instance browser memegang IP terisolasi.
4. **🌍 Audit SEO & Peringkat Google Regional**: Melihat hasil pencarian SERP dan tayangan iklan Google murni dari sudut pandang negara lain (misal: `--country US` atau `--country SG`).
5. **🛡️ Akses Bebas Sensor / Blokir ISP**: Membuka API publik atau forum developer global yang terblokir ISP lokal tanpa perlu bayar biaya VPN bulanan.
6. **🔒 Security Testing / Bug Bounty**: Mendistribusikan lalu lintas pengujian penetrasi endpoint agar tidak langsung memicu filter fail2ban server target.

---

## 2. Cara Menjalankan Menu Interaktif

Buka terminal di folder proyek:
```powershell
cd petani-proxy
python main.py
```
Akan muncul menu TUI bergaya kotak dengan watermark **`@itzluthfi`**. Anda cukup mengetik opsi yang diinginkan:
- `[W]` : 🏢 **Webshare Hunter Gacor (MVP)**: Panen 10-30 IP residential privat tembus Cloudflare Turnstile
- `[C]` : 🚀 **Cloudflare WARP Local**: Bikin profil WireGuard resmi via REST API (Zero Captcha, Unlimited)
- `[F]` : ⚡ **aiohttp Fast Harvester**: Saring ratusan proxy super cepat (<350ms dalam 1 detik)
- `[D]` : 🌐 **Buka Web Dashboard**: Luncurkan Local Gateway & langsung buka Web UI Desktop di Browser (`http://127.0.0.1:8888/dashboard`)
- `[G]` : 🚜 **Mode Petani AFK 24/7 [AUTO-HEALER]**: Daemon produksi non-stop di port 8888 (Auto-prune & refill)
- `[1]` : 🐔 **Racikan Ternak Akun**: Filter ketat Elite L1 buat Grok/Qoder, auto-sync 9Router
- `[2]` : 🕷️ **Racikan Scraper Barbar**: Pool 30+ IP, ganti IP tiap request, anti-block e-commerce
- `[3]` : ⚡ **Racikan Ngacir Anti-Lag**: Ping <350ms dari node SG, ID, dan US
- `[E]` : 📥 **Bungkus File Mentah**: Ekspor format TXT, JSON, CSV buat software bot lain
- `[T]` : 🧪 **Uji Kesaktian Topeng [CEK LIVE]**: Tes live adu IP asli vs IP Gateway (Zero Leak)
- `[K]` : ⚙️ **Quick Settings (Paste & Go)**: Setup CapSolver key, custom domain Webshare & DB 9Router
- `[U]` : 🔄 **Cek & Update Versi**: 1-Klik auto-update langsung dari repository GitHub resmi
- `[M]` : 🛠️ **Oprek Suka-Suka (Bengkel Manual)**: Racik protokol sendiri dan filter ISO negara
- `[S]` : 📂 **Gudang Amunisi**: Cek stok proxy aktif yang tersimpan di disk
- `[0]` : 💀 **Keluar**: Menutup aplikasi


---

## 2. Cara Panen Lebih dari 15 Proxy (Kustom Jumlah)

### Opsi A: Lewat Menu Interaktif
1. Jalankan `python main.py`.
2. Pilih opsi `[1]` (atau `[2]`, `[3]`, `[5]`).
3. Saat terminal bertanya:
   ```text
   Target alive proxies count [default: 15]:
   ```
   Ketik jumlah yang Anda mau, misalnya **`50`** atau **`100`**, lalu tekan Enter.
   *Sistem akan otomatis menyesuaikan batas pencarian calon IP agar target Anda tercapai!*

### Opsi B: Langsung Lewat Baris Perintah (CLI)
Gunakan flag `--target` (jumlah proxy hidup yang diinginkan) dan `--max` (maksimal calon yang dites):

* **Mau 50 Proxy Hidup:**
  ```powershell
  python main.py --target 50 --max 800
  ```
* **Mau 100 Proxy Hidup:**
  ```powershell
  python main.py --target 100 --max 1500
  ```
* **Mau 25 Proxy Khusus SOCKS5:**
  ```powershell
  python main.py --protocol socks5 --target 25 --max 500
  ```

---

## 3. Cara Menjalankan Local Rotating Proxy & REST API (Port 8888)

Fitur ini membuat komputer Anda menjadi **Proxy Gateway Lokal & Server API**. Anda tidak perlu repot gonta-ganti IP di bot Anda. Cukup arahkan bot ke `127.0.0.1:8888`, dan PetaniProxy yang akan merotasi request ke proxy-proxy hidup secara otomatis!

### A. Menjalankan Server:
```powershell
python main.py --serve 8888 --target 20
```
*Atau lewat menu interaktif `python main.py` lalu pilih opsi `[G]`.*

Saat dijalankan, terminal akan memanen 20 proxy hidup terlebih dahulu, lalu otomatis menampilkan pesan:
```text
🌐 STARTING LOCAL ROTATING GATEWAY & REST API...
  • Forward Proxy Endpoint: http://127.0.0.1:8888
  • Random Proxy REST API:  http://127.0.0.1:8888/api/random
  • All Proxies REST API:   http://127.0.0.1:8888/api/all
  • Health & Status API:    http://127.0.0.1:8888/api/status

Server running at 127.0.0.1:8888. Press Ctrl+C to stop.
```

### B. Penjelasan Tampilan Saat Dibuka di Browser (`http://127.0.0.1:8888`):
Jika Anda membuka link tersebut di browser (Chrome / Edge / Firefox), akan muncul data status server dalam format JSON:
```json
{
  "service": "PetaniProxy Gateway & REST API",
  "version": "1.1.0",
  "maintainer": "@itzluthfi (github.com/itzluthfi)",
  "stats": {
    "uptime_seconds": 24.5,
    "pool_size": 20,
    "total_routed_requests": 0,
    "successful_requests": 0,
    "failed_requests": 0,
    "current_index": 0
  },
  "endpoints": {
    "random": "/api/random",
    "all": "/api/all",
    "status": "/api/status"
  },
  "forward_proxy_usage": "Configure HTTP/HTTPS proxy to http://127.0.0.1:8888"
}
```
**Arti field di atas:**
* **`maintainer`** : Identitas pemilik/pembuat tool (`@itzluthfi`).
* **`pool_size`** : Jumlah proxy aktif yang tersimpan di dalam memori server dan siap dipakai bergiliran.
* **`total_routed_requests`** : Jumlah request yang sudah sukses diarahkan ke internet lewat proxy pool ini.
* **`uptime_seconds`** : Durasi berapa detik server ini sudah menyala di komputer Anda.

### C. Endpoint yang Bisa Anda Coba Langsung di Browser:
1. **`http://127.0.0.1:8888/api/random`**
   * Mengambil **1 IP proxy acak tercepat**. 
   * Setiap kali halaman browser di-refresh, URL ini akan berganti memberikan proxy hidup lainnya lengkap beserta negara, latensi (ms), dan level anonimitasnya (`Elite`).
2. **`http://127.0.0.1:8888/api/all`**
   * Mengambil **seluruh daftar proxy aktif** di dalam pool dalam format array JSON.
3. **`http://127.0.0.1:8888/api/status`**
   * Dashboard informasi kesehatan server, statistik routing, dan persentase sukses request.

### D. Menguji Forward Proxy lewat Terminal / cURL:
Buka terminal baru (biarkan terminal server tetap berjalan), lalu jalankan perintah ini:
```powershell
curl.exe -x http://127.0.0.1:8888 https://api.ipify.org
```
Setiap kali Anda menjalankan perintah di atas, IP keluar Anda akan otomatis berubah-ubah mengikuti proxy yang sedang digilir oleh server!

### E. Cara Mematikan Server:
Jika sudah selesai menggunakan server, cukup kembali ke jendela terminal tempat server berjalan, lalu tekan tombol **`Ctrl + C`** di keyboard untuk mematikan server dan kembali ke command prompt.

---

## 4. Cara Panen Khusus Proxy Tertentu

### A. Khusus Proxy Elite (High Anonymous)
Proxy tipe ini 100% menyembunyikan identitas Anda dan tidak meninggalkan header proxy apa pun:
```powershell
python main.py --anonymity elite --target 20
```
*Hasil otomatis tersimpan khusus di `output/live_elite.txt`.*

### B. Khusus Negara Tertentu (ID, SG, US, dll)
* **Khusus Indonesia (ID):**
  ```powershell
  python main.py --country ID --target 10
  ```
* **Khusus Singapura (SG):**
  ```powershell
  python main.py --country SG --target 15
  ```
* **Khusus Amerika Serikat (US):**
  ```powershell
  python main.py --country US --target 20
  ```

### C. Khusus Tembus Website Tertentu (Google, Shopee, dll)
Untuk memastikan proxy tidak diblokir atau kena CAPTCHA oleh website target:
* **Tes Tembus Google:**
  ```powershell
  python main.py --target-url https://google.com --target 10
  ```
* **Tes Tembus Marketplace:**
  ```powershell
  python main.py --target-url https://shopee.co.id --target 10
  ```

---

## 5. Cara Integrasi ke Script Python / Scraper / Bot

### Contoh 1: Menggunakan Local Rotating Gateway (Paling Direkomendasikan)
Setelah menjalankan `python main.py --serve 8888`, bot Python Anda cukup disetting seperti ini:

```python
import requests

# Cukup arahkan ke port lokal 8888
proxies = {
    "http": "http://127.0.0.1:8888",
    "https": "http://127.0.0.1:8888"
}

# Setiap request otomatis berganti IP dari pool yang hidup!
for i in range(5):
    resp = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
    print(f"Request #{i+1} menggunakan IP:", resp.json()["ip"])
```

### Contoh 2: Mengambil IP dari REST API secara Dinamis
```python
import requests

# Ambil 1 proxy acak dari PetaniProxy API
api_resp = requests.get("http://127.0.0.1:8888/api/random").json()
proxy_url = api_resp["url"]
print(f"Menggunakan proxy: {proxy_url} ({api_resp['country']} - {api_resp['anonymity']})")

# Gunakan proxy tersebut untuk scraping
data = requests.get("https://api.ipify.org", proxies={"http": proxy_url, "https": proxy_url})
print("IP Aktif:", data.text)
```

### Contoh 3: Membaca File Hasil Panen Langsung
File hasil panen selalu diperbarui di folder `output/`:
- `output/live_all.txt` : Format `IP:Port`
- `output/live_urls.txt` : Format `http://IP:Port` atau `socks5://IP:Port`
- `output/live_elite.txt` : Format URL khusus proxy Elite

```python
with open("output/live_all.txt", "r") as f:
    proxy_list = [line.strip() for line in f if line.strip()]

print(f"Ada {len(proxy_list)} proxy siap pakai!")
```

---

## 6. Tabel Semua Perintah CLI Lengkap

| Perintah | Fungsi |
| :--- | :--- |
| `python main.py` | Membuka TUI Menu Interaktif bergaya kotak |
| `python main.py --warp` | Generate profil Cloudflare WARP WireGuard & Sing-box |
| `python main.py --fast-harvest 15` | Saring 15 proxy ultra-cepat via aiohttp (<350ms) |
| `python main.py --daemon-gateway` | Jalankan 24/7 Resilient Gateway & Auto-Healer di port 8888 |
| `python main.py --webshare 1` | Panen akun Webshare (10 IP Residential Privat) |
| `python main.py --target 50` | Panen 50 proxy hidup tercepat |
| `python main.py --protocol socks5 --target 20` | Panen 20 proxy khusus SOCKS5 |
| `python main.py --country ID --target 10` | Panen 10 proxy khusus lokasi Indonesia |
| `python main.py --anonymity elite --target 15` | Panen 15 proxy tingkat Elite (Anti Bocor) |
| `python main.py --target-url https://google.com` | Validasi proxy langsung ke target web |
| `python main.py --serve 8888 --target 20` | Jalankan Rotating Forward Proxy & REST API di port 8888 |
| `python main.py --sync-9router auto` | Sinkronisasi proxy otomatis ke 9Router SQLite |
| `python main.py --check-update` | Cek info rilis, versi terbaru & patch notes |
| `python main.py --update` | 1-Klik auto-update repository ke versi terbaru |

---
*Created & maintained by **@itzluthfi** (https://github.com/itzluthfi)*

