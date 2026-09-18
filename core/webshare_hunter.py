"""
WEBSHARE PROXY HUNTER (AUTO-CAPTCHA SOLVER VERSION)
---------------------------------------------------
Dilengkapi Human Mouse Movement (Bezier Curve),
Typing Simulation, dan SpeechRecognition Audio Solver.

Jalankan:
  .\venv\Scripts\python.exe webshare_hunter_auto.py 1
"""

import datetime
import json
import math
import os
import random
import re
import sqlite3
import string
import sys
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", line_buffering=True)
    except Exception:
        pass
import tempfile
import time
import urllib.request
import uuid
import requests
import speech_recognition as sr
from pydub import AudioSegment
from DrissionPage import Chromium, ChromiumOptions
from colorama import Fore, Style

def find_default_db():
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(os.path.dirname(current_dir), "eLrouter", "data", "db", "data.sqlite"),
        os.path.join(os.path.dirname(current_dir), "9router-mibp-version", "data", "db", "data.sqlite"),
        os.path.join(current_dir, "..", "eLrouter", "data", "db", "data.sqlite"),
        os.path.join(current_dir, "..", "9router-mibp-version", "data", "db", "data.sqlite"),
        r"d:\FREELANCE\eLrouter\data\db\data.sqlite",
        r"d:\FREELANCE\9router-mibp-version\data\db\data.sqlite"
    ]
    for c in candidates:
        norm = os.path.abspath(c)
        if os.path.exists(norm):
            return norm
    return None

def find_grok_proxies_txt():
    current_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(os.path.dirname(current_dir), "grok-register", "proxies.txt"),
        os.path.join(current_dir, "..", "grok-register", "proxies.txt"),
        r"d:\FREELANCE\grok-register\proxies.txt"
    ]
    for c in candidates:
        norm = os.path.abspath(c)
        if os.path.exists(norm):
            return norm
    return None

def sync_to_9router(proxy_list, db_path=None):
    target_db = db_path or find_default_db()
    if not target_db or not os.path.exists(target_db):
        return 0
    try:
        conn = sqlite3.connect(target_db)
        cur = conn.cursor()
        now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
        cur.execute('SELECT data FROM proxyPools')
        existing_urls = set()
        for r in cur.fetchall():
            try:
                d = json.loads(r[0])
                existing_urls.add(d.get('proxyUrl'))
            except:
                pass

        added = 0
        for p in proxy_list:
            if p in existing_urls:
                continue
            m = re.match(r'http://([^:]+):([^@]+)@([^:]+):(\d+)', p)
            if m:
                u, pw, host, port = m.groups()
                p_id = str(uuid.uuid4())
                data_json = json.dumps({
                    'name': f'Webshare Resi ({host}:{port})',
                    'proxyUrl': p,
                    'noProxy': '',
                    'type': 'http',
                    'strictProxy': False,
                    'lastTestedAt': None,
                    'lastError': None
                })
                cur.execute('INSERT INTO proxyPools (id, isActive, testStatus, data, createdAt, updatedAt) VALUES (?, 1, "unknown", ?, ?, ?)',
                            (p_id, data_json, now, now))
                existing_urls.add(p)
                added += 1
        conn.commit()
        conn.close()
        print(f'{Fore.GREEN}[+] {added} Residential Proxy berhasil disinkronkan ke BansosRouter ({target_db})!{Style.RESET_ALL}')
        return added
    except Exception as e:
        print(f'{Fore.RED}[!] Gagal sinkron ke BansosRouter: {e}{Style.RESET_ALL}')
        return 0

def append_to_proxies_txt(new_proxies, filepath=None):
    target_file = filepath or find_grok_proxies_txt()
    if not target_file:
        return 0
    existing = set()
    try:
        with open(target_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    existing.add(line.strip())
    except:
        pass
    
    added = 0
    os.makedirs(os.path.dirname(os.path.abspath(target_file)), exist_ok=True)
    with open(target_file, 'a', encoding='utf-8') as f:
        for p in new_proxies:
            if p not in existing:
                f.write(p + '\n')
                existing.add(p)
                added += 1
    print(f'{Fore.GREEN}[+] {added} Proxy baru ditambahkan ke {target_file} (Total: {len(existing) + added}){Style.RESET_ALL}')
    return added

def simulate_human_mouse(page, target_x, target_y, steps=25):
    try:
        start_x = random.randint(100, 400)
        start_y = random.randint(100, 400)
        ctrl_x = (start_x + target_x) / 2 + random.randint(-80, 80)
        ctrl_y = (start_y + target_y) / 2 + random.randint(-80, 80)

        for i in range(steps + 1):
            t = i / float(steps)
            curr_x = (1 - t)**2 * start_x + 2 * (1 - t) * t * ctrl_x + t**2 * target_x
            curr_y = (1 - t)**2 * start_y + 2 * (1 - t) * t * ctrl_y + t**2 * target_y

            page.run_cdp('Input.dispatchMouseEvent', {
                'type': 'mouseMoved',
                'x': int(curr_x),
                'y': int(curr_y)
            })
            time.sleep(random.uniform(0.008, 0.022))

        time.sleep(random.uniform(0.1, 0.25))
    except Exception:
        pass

def human_click_element(page, element):
    try:
        rect = element.rect
        if rect:
            cx = rect.location[0] + rect.size[0] / 2 + random.uniform(-4, 4)
            cy = rect.location[1] + rect.size[1] / 2 + random.uniform(-4, 4)
            simulate_human_mouse(page, cx, cy)
        element.click()
    except Exception:
        try:
            element.click()
        except:
            pass


def check_capsolver_balance(api_key: str = None) -> dict:
    """
    Cek ketersediaan CapSolver API Key dan saldo USD terkini secara real-time.
    Mengembalikan status kesiapan dan apakah mode headless layak dijalankan.
    """
    key = api_key or os.environ.get("CAPSOLVER_API_KEY", "").strip()
    if not key:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        for fname in [os.path.join("config", "settings.json"), "config.json", "local_config.json", ".env"]:
            fpath = os.path.join(base_dir, fname)
            if os.path.exists(fpath):
                try:
                    if fname.endswith(".json"):
                        with open(fpath, "r", encoding="utf-8") as f:
                            c = json.load(f)
                            key = c.get("CAPSOLVER_API_KEY", "") or c.get("capsolver_api_key", "")
                    elif fname == ".env":
                        with open(fpath, "r", encoding="utf-8") as f:
                            for line in f:
                                if line.startswith("CAPSOLVER_API_KEY="):
                                    key = line.split("=", 1)[1].strip().strip('"').strip("'")
                except Exception:
                    pass
            if key:
                break

    if not key:
        return {
            "has_key": False,
            "balance": 0.0,
            "status": "NOT_CONFIGURED",
            "can_headless": False,

            "message": "Key Kosong (Free Audio Solver Aktif)"
        }

    try:
        r = requests.post("https://api.capsolver.com/getBalance", json={"clientKey": key}, timeout=3.0)
        data = r.json()
        if data.get("errorId") == 0:
            bal = float(data.get("balance", 0.0))
            if bal >= 0.003:
                return {
                    "has_key": True,
                    "balance": bal,
                    "status": "READY",
                    "can_headless": True,
                    "message": f"Saldo Aktif: ${bal:.3f} (Headless Ready)"
                }
            else:
                return {
                    "has_key": True,
                    "balance": bal,
                    "status": "EMPTY",
                    "can_headless": False,
                    "message": f"Saldo Habis: ${bal:.3f} (Headless Dimatikan)"
                }
        else:
            return {
                "has_key": True,
                "balance": 0.0,
                "status": "INVALID",
                "can_headless": False,
                "message": f"Key Tidak Valid ({data.get('errorCode', 'Error')})"
            }
    except Exception:
        return {
            "has_key": True,
            "balance": 0.0,
            "status": "TIMEOUT",
            "can_headless": False,
            "message": "Key Ada (Network Timeout)"
        }

def try_solve_capsolver(page, capsolver_key):
    """Optional paid solver: solves reCAPTCHA via CapSolver API if key is configured."""
    try:
        sitekey = page.run_js("""
            const el = document.querySelector('[data-sitekey]');
            if (el) return el.getAttribute('data-sitekey');
            const iframe = document.querySelector('iframe[src*="recaptcha"]');
            if (iframe) {
                const match = iframe.src.match(/[?&]k=([^&]+)/);
                if (match) return match[1];
            }
            return '';
        """)
        if not sitekey:
            return False

        print(f"[*] [CapSolver] Terdeteksi sitekey: {sitekey}. Mengirim task ke CapSolver...")
        task_res = requests.post("https://api.capsolver.com/createTask", json={
            "clientKey": capsolver_key,
            "task": {
                "type": "ReCaptchaV2TaskProxyLess",
                "websiteURL": page.url,
                "websiteKey": sitekey
            }
        }, timeout=10).json()

        task_id = task_res.get("taskId")
        if not task_id:
            print(f"[!] [CapSolver] Gagal membuat task: {task_res.get('errorDescription')}")
            return False

        for _ in range(30):
            time.sleep(2)
            result = requests.post("https://api.capsolver.com/getTaskResult", json={
                "clientKey": capsolver_key,
                "taskId": task_id
            }, timeout=10).json()
            if result.get("status") == "ready":
                token = result.get("solution", {}).get("gRecaptchaResponse")
                if token:
                    print("[+] [CapSolver] Token reCAPTCHA berhasil didapatkan!")
                    page.run_js(f"""
                        const el = document.getElementById('g-recaptcha-response');
                        if (el) el.value = "{token}";
                    """)
                    return True
            elif result.get("status") == "failed":
                return False
        return False
    except Exception as e:
        print(f"[Debug] CapSolver error: {e}")
        return False


def try_solve_audio(page):

    try:
        frames = page.get_frames()
        for f in frames:
            # 1. Cek apakah ada input response audio di frame ini
            has_input = f.run_js('return !!document.getElementById("audio-response");')

            # 2. Jika input belum ada, cek dan klik tombol headphone
            if not has_input:
                clicked_audio = f.run_js('''
                    const btn = document.getElementById('recaptcha-audio-button') || 
                                document.querySelector('.rc-button-audio');
                    if (btn && btn.offsetParent !== null) {
                        btn.click();
                        return true;
                    }
                    return false;
                ''')
                if clicked_audio:
                    print('[*] Tombol Headphone reCAPTCHA diklik, menunggu audio siap...')
                    time.sleep(4)
                    f.run_js('''
                        const playBtn = Array.from(document.querySelectorAll('button')).find(b => b.innerText.includes('PLAY'));
                        if (playBtn) playBtn.click();
                    ''')
                    time.sleep(2)
                    has_input = f.run_js('return !!document.getElementById("audio-response");')

            if not has_input:
                continue

            # Cek jika ada batas automated queries
            is_limited = f.run_js('''
                const el = document.querySelector('.rc-doscaptcha-header-text') || 
                           Array.from(document.querySelectorAll('div, p')).find(e => e.innerText && e.innerText.includes('automated queries'));
                return el ? el.innerText : '';
            ''')
            if is_limited and 'automated queries' in is_limited:
                print(f'[!] Google mendeteksi limit audio: "{is_limited.strip()}".')
                return False

            # Ambil link audio
            mp3_url = f.run_js('''
                const src = document.getElementById('audio-source');
                if (src && src.src) return src.src;
                const a = document.querySelector('a.rc-audiochallenge-tdownload-link') || 
                          document.querySelector('a[href*=".mp3"]');
                return a ? a.href : '';
            ''')

            if not mp3_url:
                # Cek teks tantangan apa yang muncul di frame
                frame_text = f.run_js('return document.body ? document.body.innerText.replace(/\\n+/g, " ") : "";')
                print(f'[*] Status kotak audio: {frame_text[:100]}...')
                time.sleep(2)
                continue

            if mp3_url:
                print('[*] Mengunduh rekaman audio captcha...')
                with tempfile.TemporaryDirectory() as tmpdir:
                    mp3_path = os.path.join(tmpdir, 'audio.mp3')
                    wav_path = os.path.join(tmpdir, 'audio.wav')
                    urllib.request.urlretrieve(mp3_url, mp3_path)
                    
                    sound = AudioSegment.from_file(mp3_path)
                    duration_sec = sound.duration_seconds
                    sound.export(wav_path, format='wav')

                    rec = sr.Recognizer()
                    with sr.AudioFile(wav_path) as source:
                        audio = rec.record(source)
                        text = rec.recognize_google(audio)
                        print(f'[+] Durasi audio: {duration_sec:.1f} detik. Transkripsi: "{text}"')

                    listen_wait = max(4.0, duration_sec + 1.5)
                    print(f'[*] Jeda mendengarkan audio ({listen_wait:.1f} detik)...')
                    time.sleep(listen_wait)

                    f.run_js('''
                        const inp = document.getElementById('audio-response');
                        if (inp) { inp.focus(); inp.value = ""; }
                    ''')
                    time.sleep(0.5)

                    print('[*] Mengetik teks per karakter perlahan layaknya manusia...')
                    for char in text:
                        escaped_char = char.replace('\\', '\\\\').replace('"', '\\"')
                        f.run_js(f'''
                            const inp = document.getElementById('audio-response');
                            if (inp) {{
                                inp.value += "{escaped_char}";
                                inp.dispatchEvent(new KeyboardEvent('keydown', {{ key: "{escaped_char}", bubbles: true }}));
                                inp.dispatchEvent(new KeyboardEvent('keypress', {{ key: "{escaped_char}", bubbles: true }}));
                                inp.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                inp.dispatchEvent(new KeyboardEvent('keyup', {{ key: "{escaped_char}", bubbles: true }}));
                            }}
                        ''')
                        time.sleep(random.uniform(0.12, 0.28))

                    time.sleep(random.uniform(1.5, 2.5))

                    verified = f.run_js('''
                        const vbtn = document.getElementById('recaptcha-verify-button');
                        if (vbtn) {
                            vbtn.click();
                            return true;
                        }
                        return false;
                    ''')
                    if verified:
                        print('[+] Tombol Verify captcha berhasil ditekan!')
                        time.sleep(6)
                        return True
            else:
                # Di mode headless, jika audio-source lambat ter-load, beri jeda
                time.sleep(2)
                return False
    except Exception as e:
        print(f'[Debug Audio] {e}')
    return False

def get_webshare_email_domain(custom_domain: str = None) -> str:
    """
    Mengambil domain email valid untuk registrasi Webshare.
    Prioritas:
    1. custom_domain argumen (dari UI / modal)
    2. Environment variable WEBSHARE_EMAIL_DOMAIN / WEBSHARE_DOMAIN
    3. config/settings.json -> custom_email_domain
    4. Live API Mail.tm (mengambil domain aktif dengan DNS MX valid)
    5. Fallback pool domain publik terverifikasi
    """
    if custom_domain and custom_domain.strip():
        return custom_domain.strip().lstrip("@")

    # 1. Environment variable
    env_dom = os.environ.get("WEBSHARE_EMAIL_DOMAIN") or os.environ.get("WEBSHARE_DOMAIN")
    if env_dom and env_dom.strip():
        return env_dom.strip().lstrip("@")

    # 2. Config files
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_paths = [
        os.path.join(base_dir, "config", "settings.json"),
        os.path.join(base_dir, "config.json"),
        os.path.join(base_dir, "local_config.json")
    ]
    for cpath in config_paths:
        if os.path.exists(cpath):
            try:
                with open(cpath, "r", encoding="utf-8") as f:
                    c = json.load(f)
                    dom = c.get("custom_email_domain") or c.get("webshare_email_domain") or c.get("email_domain")
                    if dom and dom.strip():
                        return dom.strip().lstrip("@")
            except Exception:
                pass

    # 3. Dynamic Live DuckMail Domain Fetcher (api.duckmail.sbs)
    try:
        r = requests.get("https://api.duckmail.sbs/domains", timeout=3.5)
        if r.status_code == 200:
            members = r.json().get("hydra:member", [])
            live_domains = [m.get("domain") for m in members if m.get("domain") and m.get("isVerified", True)]
            if live_domains:
                return random.choice(live_domains)
    except Exception:
        pass

    # 4. Dynamic Live Mail.tm Domain Fetcher (api.mail.tm)
    try:
        r = requests.get("https://api.mail.tm/domains", timeout=3.5)
        if r.status_code == 200:
            members = r.json().get("hydra:member", [])
            live_domains = [m.get("domain") for m in members if m.get("domain") and m.get("isActive", True)]
            if live_domains:
                return random.choice(live_domains)
    except Exception:
        pass

    # 5. Fallback verified DuckMail domain pool (Terbukti aktif dengan MX DNS valid)
    fallback_pool = [
        "niceground.shop",
        "stoneground.shop",
        "lakeground.shop",
        "canvaspace.shop",
        "vercelspace.shop",
        "bananaspace.shop",
        "sunstarmoon.shop",
        "makesomestone.shop",
        "hubaiclass.org",
        "markaihub.shop",
        "uberip.com"
    ]
    return random.choice(fallback_pool)

def hunt_single_auto(index, total, headless=False, custom_domain=None):
    random_str = ''.join(random.choices(string.ascii_lowercase + string.digits, k=10))
    domain = get_webshare_email_domain(custom_domain=custom_domain)
    email = f'ws{random_str}@{domain}'
    special = random.choice('!@#$%')
    rand_mid = ''.join(random.choices(string.ascii_letters + string.digits, k=6))
    password = f'Passw0rd{special}{rand_mid}@#'

    print('\n' + '='*60)
    print(f'     WEBSHARE AUTO-HUNTER — AKUN [{index}/{total}]' + (' [HEADLESS]' if headless else ''))
    print('='*60)
    print(f'[*] Email yang disiapkan   : {email}')
    print(f'[*] Password yang disiapkan: {password}')


    co = ChromiumOptions()
    co.auto_port()
    if headless:
        co.headless(True)
        co.set_argument('--window-size=1920,1080')
        # Di mode headless wajib set user-agent nyata agar reCAPTCHA tidak membatasi audio challenge
        co.set_user_agent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36')
    else:
        co.set_argument('--start-maximized')
    co.set_argument('--disable-blink-features=AutomationControlled')
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-dev-shm-usage')

    browser = Chromium(co)
    try:
        page = browser.latest_tab
        print('[*] Meluncurkan browser Chrome...')
        page.get('https://proxy.webshare.io/register')
        time.sleep(3)

        # 1. Isi Form Email & Password & Checkbox ToS
        try:
            email_box = page.ele('@name=email') or page.ele('@type=email')
            if email_box:
                human_click_element(page, email_box)
                email_box.clear()
                for ch in email:
                    email_box.input(ch)
                    time.sleep(random.uniform(0.02, 0.07))
                time.sleep(0.4)

            pass_box = page.ele('@name=password') or page.ele('@type=password')
            if pass_box:
                human_click_element(page, pass_box)
                pass_box.clear()
                for ch in password:
                    pass_box.input(ch)
                    time.sleep(random.uniform(0.02, 0.07))
                time.sleep(0.4)

            chk_ele = page.ele('tag:input@type=checkbox') or page.ele('.PrivateSwitchBase-input')
            if chk_ele:
                human_click_element(page, chk_ele)
            else:
                page.run_js('''
                    const chk = document.querySelector("input[type='checkbox'], input.PrivateSwitchBase-input");
                    if (chk && !chk.checked) { chk.click(); }
                ''')
            print('[*] Form dan Terms of Service terisi dengan simulasi kursor alami.')
        except Exception as e:
            print(f'[Debug] Form: {e}')

        # 2. Klik tombol "Sign Up With Email"
        time.sleep(1)
        try:
            btn_signup = page.ele('text:Sign Up With Email') or page.ele('text:Sign Up')
            if btn_signup:
                human_click_element(page, btn_signup)
                print('[*] Tombol "Sign Up With Email" berhasil diklik secara manusiawi!')
        except Exception as e:
            print(f'[Debug] Klik Sign Up: {e}')

        # 3. Pantau reCAPTCHA & tunggu login
        print('[*] Memantau reCAPTCHA / menunggu masuk ke Dashboard...')
        logged_in = False
        start_time = time.time()
        last_attempt_time = 0

        while time.time() - start_time < 180:
            url = page.url or ''
            if 'register' not in url and 'dashboard.webshare.io' in url:
                logged_in = True
                print('\n[+] Konfirmasi: Berhasil masuk ke dalam Dashboard!')
                break

            has_error = page.run_js('''
                const alert = Array.from(document.querySelectorAll('div, p, span')).find(el => el.innerText && el.innerText.includes('Too many attempts'));
                return !!alert;
            ''')
            if has_error:
                print('[!] Webshare mendeteksi "Too many attempts". Cooldown 30 detik...')
                time.sleep(30)
                try:
                    retry_signup = page.ele('text:Sign Up With Email')
                    if retry_signup:
                        human_click_element(page, retry_signup)
                except:
                    pass

            # Update last_attempt_time setiap kali memanggil solver agar tidak spam
            if time.time() - last_attempt_time > 15:
                last_attempt_time = time.time()
                capsolver_key = os.environ.get("CAPSOLVER_API_KEY", "").strip()
                solved = False
                if capsolver_key:
                    solved = try_solve_capsolver(page, capsolver_key)
                if not solved:
                    try_solve_audio(page)

            time.sleep(3)

        if not logged_in:
            print(f'[!] Akun {index} waktu tunggu habis / belum masuk dashboard.')
            return []

        # ============================================================
        # 4. ACTIVE POLLING & SMART DASHBOARD / PROXY LIST HARVESTER
        # ============================================================
        print('[*] Masuk ke mode Smart Polling di Dashboard/Proxy List...')
        proxies = []
        poll_start = time.time()

        while time.time() - poll_start < 60 and not proxies:
            url = page.url or ''

            # A. Tangani Modal Onboarding QuickStart jika masih terbuka
            page.run_js('''
                const buttons = Array.from(document.querySelectorAll('button'));
                const btnGo = buttons.find(b => b.innerText.includes('Go To Proxy List'));
                if (btnGo) btnGo.click();
                const closeBtn = document.querySelector('button[aria-label="Close"], svg[data-testid="CloseIcon"]');
                if (closeBtn) closeBtn.click();
            ''')

            # B. Jika ada Download Link input (modal download sudah terbuka), ambil langsung!
            dl_url = page.run_js(r'''
                const input = document.querySelector('input[value*="proxy/list/download"]');
                if (input) return input.value;
                const anyInput = Array.from(document.querySelectorAll('input')).find(i => i.value && i.value.includes('/download/'));
                return anyInput ? anyInput.value : '';
            ''')
            if dl_url:
                print(f'[*] Menemukan Download Link API: {dl_url}')
                try:
                    r = requests.get(dl_url, timeout=15)
                    if r.status_code == 200 and r.text.strip():
                        for line in r.text.strip().splitlines():
                            parts = line.strip().split(':')
                            if len(parts) == 4:
                                ip, port, u, pw = parts
                                proxies.append(f'http://{u}:{pw}@{ip}:{port}')
                        if proxies:
                            print(f'[+] SUKSES! Berhasil mengunduh {len(proxies)} proxy dari Download Link!')
                            break
                except Exception as e:
                    print(f'[Debug] Error API: {e}')

            # C. Ekstrak langsung dari baris tabel DOM jika sudah terlihat
            extracted = page.run_js(r'''
                const out = [];
                const rows = Array.from(document.querySelectorAll('tr'));
                for (const r of rows) {
                    const cells = Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim());
                    if (cells.length >= 5) {
                        const ip = cells[1];
                        const port = cells[2];
                        const user = cells[3];
                        const pass = cells[4];
                        if (ip && port && user && pass && ip.match(/^\d+\.\d+\.\d+\.\d+$/) && port.match(/^\d+$/)) {
                            out.push(`http://${user}:${pass}@${ip}:${port}`);
                        }
                    }
                }
                return out;
            ''')
            if extracted and isinstance(extracted, list) and len(extracted) > 0:
                proxies = extracted
                print(f'[+] SUKSES! Berhasil mengambil {len(proxies)} proxy langsung dari tabel layar!')
                break

            # D. Jika tombol Download terlihat, klik tombol Download
            btn_download = page.ele('text:Download') or page.ele('tag:button@@text():Download')
            if btn_download and not dl_url:
                print('[*] Tombol Download ditemukan, mengklik...')
                human_click_element(page, btn_download)
                time.sleep(1.5)
                continue

            # E. Jika masih di halaman utama Dashboard, navigasi ke Proxy List
            if 'proxy/list' not in url:
                btn_view = page.ele('text:Go To Proxy List') or page.ele('text:View My Proxy List') or page.ele('tag:p@@text():Proxy List')
                if btn_view:
                    print(f'[*] Navigasi: mengklik {btn_view.text}...')
                    human_click_element(page, btn_view)
                    time.sleep(2)
                    continue

            time.sleep(1.5)

        if not proxies:
            print('[!] Proxy belum terambil, menahan browser 15 detik...')
            time.sleep(15)

        return proxies

    finally:
        try:
            browser.quit()
        except:
            pass

def run_webshare_hunter(total: int = 1, headless: bool = False, sync_9router_db: str = None, output_dir: str = None, custom_domain: str = None):
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = output_dir or os.path.join(base_dir, "output")
    os.makedirs(out_dir, exist_ok=True)

    db_path = sync_9router_db or find_default_db()
    grok_txt = find_grok_proxies_txt()
    output_webshare_txt = os.path.join(out_dir, "webshare_residential.txt")
    output_elite_txt = os.path.join(out_dir, "live_elite.txt")

    mode_str = f"{Fore.YELLOW}[Mode: Background/Headless]{Style.RESET_ALL}" if headless else f"{Fore.GREEN}[Mode: Jendela Tampak]{Style.RESET_ALL}"
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🌾 PETANIPROXY x WEBSHARE RESIDENTIAL HUNTER (AUTO-SOLVER){Style.RESET_ALL}")
    print(f"  • Target Akun       : {Fore.YELLOW}{total}{Style.RESET_ALL} Akun (Potensi {total * 10} Residential IP)")
    print(f"  • Mode Tampilan     : {mode_str}")
    if custom_domain:
        print(f"  • Custom Domain     : {Fore.MAGENTA}@{custom_domain}{Style.RESET_ALL}")
    print(f"  • BansosRouter SQLite: {Fore.WHITE}{db_path or 'Tidak Terdeteksi (Skip)'}{Style.RESET_ALL}")
    print(f"  • Grok Farm Proxies : {Fore.WHITE}{grok_txt or 'Tidak Terdeteksi (Skip)'}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")

    all_gathered = []
    for i in range(1, total + 1):
        proxies = hunt_single_auto(i, total, headless=headless, custom_domain=custom_domain)
        if proxies:
            print(f"  {Fore.GREEN}✓ Akun [{i}/{total}] menghasilkan {len(proxies)} residential proxy baru.{Style.RESET_ALL}")
            # 1. Simpan ke output PetaniProxy
            append_to_proxies_txt(proxies, output_webshare_txt)
            append_to_proxies_txt(proxies, output_elite_txt)
            # 2. Sinkron ke Grok Farm
            if grok_txt:
                append_to_proxies_txt(proxies, grok_txt)
            # 3. Sinkron ke BansosRouter DB
            if db_path:
                sync_to_9router(proxies, db_path)
            all_gathered.extend(proxies)
        else:
            print(f"  {Fore.YELLOW}⚠️ Akun [{i}/{total}] belum menghasilkan proxy.{Style.RESET_ALL}")

        if i < total:
            print(f"  {Fore.LIGHTBLACK_EX}Istirahat 3 detik sebelum akun berikutnya...{Style.RESET_ALL}")
            time.sleep(3)

    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🎉 PANEN RESIDENTIAL SELESAI! Total {len(all_gathered)} proxy baru terkumpul.{Style.RESET_ALL}")
    print(f"  • File PetaniProxy   : {Fore.WHITE}{output_webshare_txt}{Style.RESET_ALL}")
    if grok_txt:
        print(f"  • Feed Grok Farm     : {Fore.WHITE}{grok_txt}{Style.RESET_ALL}")
    if db_path:
        print(f"  • DB BansosRouter    : {Fore.WHITE}{db_path}{Style.RESET_ALL}")
    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
    return all_gathered

def main():
    total = 1
    headless = '--headless' in sys.argv or '-h' in sys.argv or 'headless' in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith('-') and a != 'headless']

    if args and args[0].isdigit():
        total = int(args[0])
    else:
        print('='*60)
        print('   WEBSHARE PROXY HUNTER — AUTO SOLVER VERSION (FREE)')
        print('='*60)
        try:
            inp = input('Berapa akun Webshare yang ingin dibuat? (Default: 1): ').strip()
            if inp.isdigit() and int(inp) > 0:
                total = int(inp)
            ans = input('Jalankan di background tanpa jendela (Headless)? [y/N]: ').strip().lower()
            if ans in ('y', 'yes'):
                headless = True
        except (KeyboardInterrupt, EOFError):
            print('\n[!] Dibatalkan.')
            return

    run_webshare_hunter(total=total, headless=headless)

if __name__ == '__main__':
    main()

