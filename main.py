#!/usr/bin/env python3
"""
PetaniProxy v1.1.0
Pusat Amunisi Proxy Bersih, Segar & Berputar Otomatis (Local Rotating Gateway & WARP)
"""

import os
import sys
import time
import json
import argparse
import requests
from typing import Optional, List

# Force UTF-8 on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from colorama import init, Fore, Style
    init(autoreset=True)
except ImportError:
    class DummyColor:
        def __getattr__(self, name):
            return ""
    Fore = Style = DummyColor()

from core.fetcher import fetch_proxies_sync
from core.checker import check_proxies_pool, DEFAULT_TEST_URL
from core.exporter import export_all_formats
from core.server import start_proxy_server
from core.updater import (
    get_local_version_info,
    check_for_updates,
    render_update_banner,
    show_full_announcement,
    perform_update
)
from core.tui import (
    InteractiveMenu,
    build_header,
    build_metrics_card,
    build_info_card,
    build_table,
    render_badge,
    quick_confirm,
    quick_pause,
    read_key,
    clear_screen
)

BANNER = f"""{Fore.CYAN}{Style.BRIGHT}
  ██████╗ ███████╗████████╗ █████╗ ███╗   ██╗██╗██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗
  ██╔══██╗██╔════╝╚══██╔══╝██╔══██╗████╗  ██║██║██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝
  ██████╔╝█████╗     ██║   ███████║██╔██╗ ██║██║██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ 
  ██╔═══╝ ██╔══╝     ██║   ██╔══██║██║╚██╗██║██║██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  
  ██║     ███████╗   ██║   ██║  ██║██║ ╚████║██║██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   
  ╚═╝     ╚══════╝   ╚═╝   ╚═╝  ╚═╝╚═╝  ╚═══╝╚═╝╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   
{Fore.YELLOW}              🌾 PetaniProxy: Panen Proxy Cepat, Segar & Bergizi 🚜
{Fore.WHITE}          High-Speed Multi-Protocol Scraper, Validator & Local Gateway
{Fore.LIGHTBLACK_EX}                 Created & Maintained by {Fore.CYAN}@itzluthfi{Fore.LIGHTBLACK_EX} (github.com/itzluthfi)
{Style.RESET_ALL}"""

def get_settings_path() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "config", "settings.json")

def load_settings() -> dict:
    spath = get_settings_path()
    if os.path.exists(spath):
        try:
            with open(spath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_settings(data: dict):
    spath = get_settings_path()
    os.makedirs(os.path.dirname(spath), exist_ok=True)
    with open(spath, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def open_in_explorer(target_path: str):
    """Buka folder atau sorot file di File Manager (Windows Explorer, macOS Finder, Linux)."""
    try:
        norm = os.path.normpath(target_path)
        if os.path.isfile(norm):
            if sys.platform == "win32":
                os.system(f'explorer /select,"{norm}"')
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", "-R", norm])
            else:
                import subprocess
                subprocess.run(["xdg-open", os.path.dirname(norm)])
        elif os.path.isdir(norm):
            if sys.platform == "win32":
                os.startfile(norm)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.run(["open", norm])
            else:
                import subprocess
                subprocess.run(["xdg-open", norm])
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka File Manager: {e}{Style.RESET_ALL}")

def open_in_text_editor(file_path: str):
    """Buka file text menggunakan default editor sistem (Notepad, TextEdit, atau default Linux)."""
    try:
        norm = os.path.normpath(file_path)
        if not os.path.exists(norm):
            return
        if sys.platform == "win32":
            os.system(f'start notepad "{norm}"')
        elif sys.platform == "darwin":
            import subprocess
            subprocess.run(["open", "-t", norm])
        else:
            import subprocess
            try:
                subprocess.run(["xdg-open", norm])
            except Exception:
                pass
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka Text Editor: {e}{Style.RESET_ALL}")

def open_url_in_browser(url: str):
    """Buka URL di browser default sistem."""
    try:
        import webbrowser
        webbrowser.open(url)
    except Exception as e:
        print(f"{Fore.RED}Gagal membuka browser: {e}{Style.RESET_ALL}")

def find_9router_db() -> Optional[str]:
    """Smart auto-detection for BansosRouter / 9Router SQLite database."""
    cfg_db = load_settings().get("9router_db_path")
    if cfg_db and os.path.exists(cfg_db):
        return cfg_db

    env_path = os.environ.get("BANSOS_ROUTER_DB") or os.environ.get("NINEROUTER_DB")
    if env_path and os.path.exists(env_path):
        return env_path

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.normpath(os.path.join(base_dir, "..", "eLrouter", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router-mibp-version", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "bansos-router", "data", "db", "data.sqlite")),
        "D:/FREELANCE/eLrouter/data/db/data.sqlite",
        "D:/FREELANCE/9router-mibp-version/data/db/data.sqlite",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def install_dependencies(quiet: bool = False) -> bool:
    """Auto-install or repair project dependencies using requirements.txt."""
    import subprocess
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}📦 MEMASANG DEPENDENSI PETANIPROXY...{Style.RESET_ALL}")
    print(f"{Fore.LIGHTBLACK_EX}Menjalankan: {sys.executable} -m pip install -r requirements.txt{Style.RESET_ALL}\n")
    req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
    cmd = [sys.executable, "-m", "pip", "install", "-r", req_file]
    if quiet:
        cmd.append("--quiet")
    res = subprocess.run(cmd)
    if res.returncode == 0:
        print(f"\n{Fore.GREEN}✓ Semua dependensi berhasil dipasang! Siap tempur! 🌾🚜{Style.RESET_ALL}")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
        return True
    else:
        print(f"\n{Fore.RED}⚠️ Pemasangan paket selesai dengan beberapa catatan/peringatan.{Style.RESET_ALL}")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")
        return False

def check_initial_dependencies() -> bool:
    """Smart check on first startup to ensure user has essential packages."""
    missing = []
    checks = [
        ("httpx", "httpx"),
        ("requests", "requests"),
        ("colorama", "colorama"),
        ("DrissionPage", "DrissionPage"),
        ("speech_recognition", "SpeechRecognition"),
        ("pydub", "pydub")
    ]
    for mod, pkg in checks:
        try:
            __import__(mod)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"\n{Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        print(f"  {Fore.WHITE}{Style.BRIGHT}📦 SETUP AWAL PETANIPROXY: Dependensi Belum Lengkap{Style.RESET_ALL}")
        print(f"  {Fore.LIGHTBLACK_EX}Terdeteksi beberapa paket yang belum terpasang di sistem Python kamu:{Style.RESET_ALL}")
        for m in missing:
            print(f"   {Fore.RED}•{Fore.WHITE} {m}{Style.RESET_ALL}")
        print(f"{Fore.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        ans = input(f"\n{Fore.CYAN}👉 Pasang semua dependensi otomatis sekarang (1-Klik via pip)? [Y/n]: {Style.RESET_ALL}").strip().lower()
        if ans in ("", "y", "yes"):
            return install_dependencies()
    return True

def find_grok_python() -> str:
    """Detect python executable for Grok Farm / Webshare Hunter."""
    candidates = [
        r"D:\FREELANCE\grok-register\venv\Scripts\python.exe",
        os.path.normpath(os.path.join(os.path.dirname(__file__), "..", "grok-register", "venv", "Scripts", "python.exe")),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return sys.executable

def run_webshare_hunter(accounts: int = 1, headless: bool = True) -> bool:
    """Run Webshare Hunter to harvest residential clean proxies that bypass Cloudflare."""
    import subprocess
    base_dir = os.path.dirname(os.path.abspath(__file__))
    ws_script = os.path.join(base_dir, "core", "webshare_hunter.py")
    cwd_run = base_dir

    if not os.path.exists(ws_script):
        grok_dir = r"D:\FREELANCE\grok-register"
        if not os.path.exists(grok_dir):
            grok_dir = os.path.normpath(os.path.join(base_dir, "..", "grok-register"))
        ws_script = os.path.join(grok_dir, "webshare_hunter_auto.py")
        cwd_run = grok_dir

    if not os.path.exists(ws_script):
        print(f"{Fore.RED}❌ Script Webshare Hunter tidak ditemukan di {ws_script}{Style.RESET_ALL}")
        return False

    py_exec = sys.executable or find_grok_python()
    print(f"\n{Fore.CYAN}{'🏢 Menjalankan Webshare Residential Hunter...' if CURRENT_LANG == 'ID' else '🏢 Launching Webshare Residential Hunter...'}{Style.RESET_ALL}")
    print(f"  • Target: {Fore.YELLOW}{accounts} Akun Webshare ({accounts * 10} IP Residensial AS/Eropa){Style.RESET_ALL}")
    print(f"  • Mode:   {Fore.WHITE}{'Background (Headless)' if headless else 'Tampak Layar'}{Style.RESET_ALL}")
    print(f"  • Hasil:  {Fore.GREEN}Otomatis lolos Cloudflare xAI Grok & disetor ke proxies.txt + BansosRouter{Style.RESET_ALL}\n")

    cmd = [py_exec, ws_script, str(accounts)]
    if headless:
        cmd.append("--headless")

    try:
        res = subprocess.run(cmd, cwd=cwd_run)
        return res.returncode == 0
    except Exception as e:
        print(f"{Fore.RED}❌ Gagal menjalankan Webshare Hunter: {e}{Style.RESET_ALL}")
        return False

def print_live_proxy(proxy_res: dict, current_count: int, target: int):
    proto = proxy_res.get("protocol", "http").upper()
    lat = proxy_res.get("latency_ms", 0)
    proxy = proxy_res.get("proxy", "")
    cc = proxy_res.get("country_code", "??")
    country = proxy_res.get("country", "Unknown")
    isp = proxy_res.get("isp", "-")
    anon = proxy_res.get("anonymity", "Elite")
    
    # Anonymity badge styling
    if anon == "Elite":
        anon_badge = f"{Fore.CYAN}{Style.BRIGHT}[ELITE]{Style.RESET_ALL}"
    elif anon == "Anonymous":
        anon_badge = f"{Fore.MAGENTA}[ANON]{Style.RESET_ALL} "
    else:
        anon_badge = f"{Fore.YELLOW}[TRAN]{Style.RESET_ALL} "

    # Color based on latency
    if lat < 1000:
        lat_color = Fore.GREEN
    elif lat < 2500:
        lat_color = Fore.YELLOW
    else:
        lat_color = Fore.RED

    print(
        f"  {Fore.GREEN}🟢 [LIVE {current_count}/{target}]{Style.RESET_ALL} "
        f"{Fore.CYAN}{proto:<6}{Style.RESET_ALL} "
        f"{Fore.WHITE}{proxy:<21}{Style.RESET_ALL} | "
        f"{anon_badge} | "
        f"{lat_color}{lat:>4}ms{Style.RESET_ALL} | "
        f"{Fore.BLUE}[{cc}] {country:<13}{Style.RESET_ALL} | "
        f"{Fore.LIGHTBLACK_EX}{isp[:22]}{Style.RESET_ALL}"
    )

def run_harvester(
    protocols: list, 
    max_check: int = 200, 
    target_alive: int = 20, 
    timeout: float = 3.0, 
    workers: int = 50, 
    country: str = None, 
    anonymity: str = None,
    target_url: str = None,
    output_dir: str = None, 
    sync_9router: str = None,
    serve_port: int = None
):
    t_start = time.perf_counter()
    check_url = target_url or DEFAULT_TEST_URL
    print(f"\n{Fore.YELLOW}⚡ [1/3] Scraping raw candidates from open-source feeds...{Style.RESET_ALL}")
    candidates = fetch_proxies_sync(protocols=protocols, country_filter=country)
    
    if not candidates:
        print(f"{Fore.RED}❌ Gagal mengambil kandidat proxy dari feed.{Style.RESET_ALL}")
        return []

    url_hint = f" | Target: {check_url[:35]}" if target_url else ""
    anon_hint = f" | Anonymity: {anonymity.upper()}" if anonymity and anonymity.lower() != 'all' else ""
    print(f"\n{Fore.YELLOW}🔍 [2/3] Validating up to {max_check} candidates (Target alive: {target_alive}, Timeout: {timeout}s{url_hint}{anon_hint})...{Style.RESET_ALL}")
    
    live_proxies = check_proxies_pool(
        candidates=candidates,
        max_check=max_check,
        target_alive=target_alive,
        timeout=timeout,
        max_workers=workers,
        country_filter=country,
        anonymity_filter=anonymity,
        test_url=check_url,
        on_live_callback=print_live_proxy
    )

    elapsed_total = round(time.perf_counter() - t_start, 2)
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(f"{Fore.GREEN}{Style.BRIGHT}🎉 Validation Complete! Found {len(live_proxies)} active proxies in {elapsed_total}s.{Style.RESET_ALL}")

    if not live_proxies:
        print(f"{Fore.YELLOW}⚠️ Tidak ada proxy yang lolos batas timeout {timeout}s. Coba perbesar --timeout atau perbanyak --max.{Style.RESET_ALL}")
        return []

    print(f"\n{Fore.YELLOW}💾 [3/3] Exporting verified proxies to disk...{Style.RESET_ALL}")
    files = export_all_formats(live_proxies, output_dir=output_dir, sync_9router_db=sync_9router)
    
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Plain Text:  {Fore.WHITE}{files.get('all_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} URLs Format: {Fore.WHITE}{files.get('urls_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Elite Only:  {Fore.WHITE}{files.get('elite_txt')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} Rich JSON:   {Fore.WHITE}{files.get('json')}{Style.RESET_ALL}")
    print(f"  {Fore.GREEN}✓{Style.RESET_ALL} CSV Sheet:   {Fore.WHITE}{files.get('csv')}{Style.RESET_ALL}")
    
    if "9router_db" in files:
        print(f"  {Fore.GREEN}✓{Style.RESET_ALL} BansosRouter DB: {Fore.WHITE}Synced to {files['9router_db']}{Style.RESET_ALL}")

    # Display Top 5 Fastest in clean Unicode Table
    table_headers = ["#", "PROTO", "IP : PORT", "ANON", "PING", "CC", "ISP / REGION"]
    table_rows = []
    for idx, p in enumerate(live_proxies[:5], 1):
        proto = p.get('protocol', 'http').upper()
        anon = f"{Fore.CYAN}[ELITE]{Style.RESET_ALL}" if p.get('anonymity') == 'Elite' else f"{Fore.LIGHTBLACK_EX}[ANON]{Style.RESET_ALL}"
        lat = p.get('latency_ms', 0)
        lat_str = f"{Fore.GREEN}{lat}ms{Style.RESET_ALL}" if lat < 500 else (f"{Fore.YELLOW}{lat}ms{Style.RESET_ALL}" if lat < 1500 else f"{Fore.RED}{lat}ms{Style.RESET_ALL}")
        table_rows.append([
            str(idx),
            proto,
            p.get('proxy', ''),
            anon,
            lat_str,
            p.get('country_code', '??'),
            (p.get('isp') or p.get('country') or '-')[:22]
        ])
    
    print(f"\n{build_table(table_headers, table_rows, title='AMUNISI PROXY TERCEPAT SIAP TEMBAK')}\n")

    if serve_port:
        card_items = [
            ("Forward Gateway", f"{Fore.CYAN}http://127.0.0.1:{serve_port}{Style.RESET_ALL} (Rotasi Otomatis)"),
            ("Web Dashboard", f"{Fore.GREEN}http://127.0.0.1:{serve_port}/dashboard{Style.RESET_ALL} (UI Mantau Live)"),
            ("PAC URL (HP)", f"{Fore.YELLOW}http://127.0.0.1:{serve_port}/proxy.pac{Style.RESET_ALL} (Auto-Config Wi-Fi)"),
            ("Sticky Session", f"{Fore.WHITE}Kirim header {Fore.YELLOW}X-Session-ID: <id>{Style.RESET_ALL} (Nahan IP 10m)"),
            ("Topeng Ninja", f"{Fore.GREEN}Aktif ●{Style.RESET_ALL} (Auto User-Agent Spoofing)")
        ]
        print(build_info_card(f"GATEWAY PRODUCTION AKTIF (PORT {serve_port})", card_items, border_color=Fore.GREEN))
        print(f"\n{Fore.LIGHTBLACK_EX}  Tekan Ctrl+C untuk menghentikan server gateway.{Style.RESET_ALL}\n")
        start_proxy_server(live_proxies, host="127.0.0.1", port=serve_port, background=False)

    return live_proxies

def view_saved_results(output_dir: str = None):
    """
    Fitur [S] Gudang & Daftar Hasil Panen Terminal:
    Menampilkan tabel proxy terverifikasi yang tersimpan di disk langsung di terminal.
    """
    if not output_dir:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(base_dir, "output")
    json_file = os.path.join(output_dir, "proxies.json")
    if not os.path.exists(json_file):
        print(f"\n{Fore.YELLOW}Belum ada riwayat hasil proxy tersimpan di {output_dir}. Jalankan harvest dulu!{Style.RESET_ALL}")
        return

    import json
    with open(json_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    proxies = data.get("proxies", [])
    if not proxies:
        print(f"\n{Fore.YELLOW}Gudang proxy lokal kosong. Silakan jalankan panen terlebih dahulu!{Style.RESET_ALL}")
        return

    limit = 15
    filter_cc = None

    while True:
        display_list = proxies
        if filter_cc:
            display_list = [p for p in proxies if (p.get("country_code") or "").upper() == filter_cc.upper()]

        t_headers = ["#", "PROTO", "IP : PORT", "ANON", "PING", "CC", "ISP / HOST REGION"]
        t_rows = []
        for idx, p in enumerate(display_list[:limit], 1):
            proto = p.get('protocol', 'http').upper()
            anon = f"{Fore.CYAN}[ELITE]{Style.RESET_ALL}" if (p.get('anonymity') or '').lower() == 'elite' else f"{Fore.LIGHTBLACK_EX}[ANON]{Style.RESET_ALL}"
            lat = p.get('latency_ms', 0)
            lat_str = f"{Fore.GREEN}{lat}ms{Style.RESET_ALL}" if lat < 500 else (f"{Fore.YELLOW}{lat}ms{Style.RESET_ALL}" if lat < 1500 else f"{Fore.RED}{lat}ms{Style.RESET_ALL}")
            t_rows.append([
                str(idx),
                proto,
                p.get('proxy', ''),
                anon,
                lat_str,
                p.get('country_code', '??'),
                (p.get('isp') or p.get('country') or '-')[:24]
            ])

        title_suffix = f" (Filter: {filter_cc})" if filter_cc else f" (Menampilkan {min(limit, len(display_list))} dari {len(proxies)} Total)"
        print(f"\n{build_table(t_headers, t_rows, title='DAFTAR HASIL PANEN PROXY TERVERIFIKASI' + title_suffix)}\n")

        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        print(f"{Fore.WHITE}{Style.BRIGHT}PILIH AKSI GUDANG HASIL PANEN:{Style.RESET_ALL}")
        if limit < len(display_list):
            print(f"  {Fore.CYAN}[A]{Fore.WHITE} 📜 Tampilkan Semua ({len(display_list)} Proxy)")
        print(f"  {Fore.GREEN}[1]{Fore.WHITE} 🚀 Nyalakan Gateway 8888 Menggunakan Stok Ini")
        print(f"  {Fore.YELLOW}[2]{Fore.WHITE} 🔍 Filter Berdasarkan Kode Negara (e.g. US, SG, ID)")
        print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📝 Buka File Daftar di Notepad (live_all.txt)")
        print(f"  {Fore.GREEN}[4]{Fore.WHITE} 📂 Buka Folder Output di File Explorer")
        print(f"  {Fore.CYAN}[6]{Fore.WHITE} 🌐 Buka Web Dashboard di Browser (Port 8888)")
        print(f"  {Fore.RED}[5]{Fore.WHITE} 🧹 Bersihkan / Hapus Stok Lama")
        print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
        print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
        sub = input(f"{Fore.YELLOW}Pilih aksi: {Style.RESET_ALL}").strip().lower()

        if sub == "a":
            limit = len(display_list)
        elif sub == "1":
            print(f"\n{Fore.GREEN}✓ Menyalakan Gateway 8888 dengan {len(proxies)} proxy... Tekan Ctrl+C untuk stop.{Style.RESET_ALL}\n")
            start_proxy_server(proxies, port=8888, background=False, enable_health_check=True)
            break
        elif sub == "2":
            cc_in = input(f"{Fore.CYAN}Masukkan kode 2 huruf negara (misal US, SG, ID, atau kosongkan untuk reset): {Style.RESET_ALL}").strip().upper()
            filter_cc = cc_in if cc_in else None
            limit = 15
        elif sub == "3":
            open_in_text_editor(os.path.join(output_dir, "live_all.txt"))
        elif sub == "4":
            open_in_explorer(output_dir)
        elif sub == "6":
            launch_web_dashboard(port=8888)
            break
        elif sub == "5":
            c_del = input(f"{Fore.RED}Yakin ingin menghapus seluruh file cache proxy di {output_dir}? [y/N]: {Style.RESET_ALL}").strip().lower()
            if c_del in ("y", "yes"):
                for fname in os.listdir(output_dir):
                    if fname.endswith((".txt", ".json", ".csv")):
                        try:
                            os.remove(os.path.join(output_dir, fname))
                        except Exception:
                            pass
                print(f"\n{Fore.GREEN}✓ Stok gudang amunisi berhasil dibersihkan!{Style.RESET_ALL}")
                break
        else:
            break

def launch_web_dashboard(port: int = 8888):
    """
    Fitur [D] Buka Web Dashboard:
    Menjalankan local gateway server dan langsung otomatis membuka browser ke Web UI Dashboard.
    """
    import webbrowser
    import json
    import threading

    dash_url = f"http://127.0.0.1:{port}/dashboard"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_file = os.path.join(base_dir, "output", "proxies.json")

    # 1. Cek apakah gateway port 8888 sudah berjalan di background
    server_alive = False
    try:
        import urllib.request
        req = urllib.request.Request(f"http://127.0.0.1:{port}/api/status", headers={"User-Agent": "PetaniTester/1.0"})
        with urllib.request.urlopen(req, timeout=1.2) as resp:
            if resp.status == 200:
                server_alive = True
    except Exception:
        server_alive = False

    if server_alive:
        print(f"\n{Fore.GREEN}✓ Gateway port {port} sudah berjalan aktif!{Style.RESET_ALL}")
        print(f"  {Fore.CYAN}👉 Membuka Web Dashboard di browser: {Fore.WHITE}{dash_url}{Style.RESET_ALL}\n")
        webbrowser.open(dash_url)
        try:
            input(f"{Fore.LIGHTBLACK_EX}[Tekan Enter untuk kembali ke menu...]{Style.RESET_ALL}")
        except (KeyboardInterrupt, EOFError):
            pass
        return

    # 2. Ambil proxy dari cache atau quick harvest
    proxies = []
    if os.path.exists(json_file):
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                proxies = data.get("proxies", [])
        except Exception:
            proxies = []

    if not proxies:
        print(f"\n{Fore.YELLOW}ℹ️ Gudang cache proxy belum ada. Melakukan quick-harvest 10 proxy kilat untuk Web Dashboard...{Style.RESET_ALL}")
        proxies = run_harvester(protocols=["http", "socks5"], max_check=180, target_alive=10, timeout=2.5, serve_port=None)
        if not proxies:
            print(f"{Fore.RED}❌ Gagal mendapatkan proxy untuk dashboard. Silakan periksa koneksi internet.{Style.RESET_ALL}")
            return

    # 3. Buka browser otomatis setelah delay singkat
    def _open_delayed():
        time.sleep(0.8)
        webbrowser.open(dash_url)

    threading.Thread(target=_open_delayed, daemon=True).start()

    card_items = [
        ("Web Dashboard", f"{Fore.GREEN}{dash_url}{Style.RESET_ALL} (Membuka di Browser...)"),
        ("Forward Gateway", f"{Fore.CYAN}http://127.0.0.1:{port}{Style.RESET_ALL} (Rotasi Aktif)"),
        ("PAC Script URL", f"{Fore.YELLOW}http://127.0.0.1:{port}/proxy.pac{Style.RESET_ALL}"),
        ("Active Proxies", f"{Fore.WHITE}{len(proxies)} Nodes Tersambung{Style.RESET_ALL}")
    ]
    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
    print(build_info_card(f"WEB DASHBOARD DESKTOP APP DILUNCURKAN (PORT {port})", card_items, border_color=Fore.GREEN))
    print(f"\n{Fore.LIGHTBLACK_EX}  Tekan Ctrl+C untuk menghentikan server dan kembali ke menu terminal.{Style.RESET_ALL}\n")

    start_proxy_server(proxies, host="127.0.0.1", port=port, background=False, enable_health_check=True)


CURRENT_LANG = "ID"

def test_live_masking(port: int = 8888):
    """
    Fitur Pembuktian Langsung [T]:
    Uji apakah IP asli tertutup sempurna lewat Gateway 8888.
    """
    print(f"\n{Fore.CYAN}🧪 MEMERIKSA STATUS ANONIMITAS (LIVE MASKING TEST)...{Style.RESET_ALL}")
    
    # 1. Mendeteksi IP Asli
    print(f"  {Fore.LIGHTBLACK_EX}[1/2] Mendeteksi IP Asli perangkat kamu (Direct Connection)...{Style.RESET_ALL}")
    real_ip = "Unknown"
    real_isp = "Unknown"
    try:
        r = requests.get("https://ipwho.is/", timeout=5.0)
        if r.status_code == 200:
            d = r.json()
            real_ip = d.get("ip", "Unknown")
            real_isp = f"{d.get('connection', {}).get('isp', d.get('isp', '-'))} - {d.get('city', '-')}, {d.get('country', '-')}"
    except Exception:
        try:
            r = requests.get("https://api.ipify.org?format=json", timeout=4.0)
            real_ip = r.json().get("ip", "Unknown")
        except Exception:
            pass

    # 2. Menguji Gateway 127.0.0.1:8888
    print(f"  {Fore.LIGHTBLACK_EX}[2/2] Menguji koneksi lewat Rotating Gateway (127.0.0.1:{port})...{Style.RESET_ALL}")
    proxies = {
        "http": f"http://127.0.0.1:{port}",
        "https": f"http://127.0.0.1:{port}"
    }
    gateway_ip = None
    gateway_info = None
    try:
        r = requests.get("https://ipwho.is/", proxies=proxies, timeout=8.0)
        if r.status_code == 200:
            d = r.json()
            gateway_ip = d.get("ip")
            gateway_info = f"{d.get('connection', {}).get('isp', d.get('isp', '-'))} - {d.get('city', '-')}, {d.get('country', '-')}"
    except Exception:
        try:
            r = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=6.0)
            if r.status_code == 200:
                gateway_ip = r.json().get("ip")
        except Exception:
            pass

    if gateway_ip:
        is_safe = (gateway_ip != real_ip)
        status_badge = f"{Fore.GREEN}● 100% AMAN & TERSAMARKAN (Zero Leak){Style.RESET_ALL}" if is_safe else f"{Fore.RED}○ BOCOR / SAMA DENGAN ASLI{Style.RESET_ALL}"
        card_data = [
            ("IP Asli Kamu", f"{Fore.YELLOW}{real_ip}{Style.RESET_ALL} ({real_isp})"),
            ("IP Masked Gateway", f"{Fore.GREEN}{gateway_ip}{Style.RESET_ALL} ({gateway_info or 'Masked Node'})"),
            ("Status Privasi", status_badge),
            ("Topeng Ninja", f"{Fore.CYAN}User-Agent Disanitasi Otomatis ✓{Style.RESET_ALL}")
        ]
        print(f"\n{build_info_card('HASIL AUDIT IDENTITAS & PRIVASI KONEKSI', card_data, border_color=Fore.GREEN if is_safe else Fore.RED)}\n")
    else:
        print(f"\n{Fore.YELLOW}▲ Gateway Petani (127.0.0.1:{port}) belum aktif di background.{Style.RESET_ALL}")
        ask = input(f"{Fore.CYAN}👉 Mau langsung nyalakan Gateway 8888 sekarang (1-Klik)? [Y/n]: {Style.RESET_ALL}").strip().lower()
        if ask in ("", "y", "yes"):
            print(f"\n{Fore.GREEN}🚀 Menyiapkan amunisi awal dan menyalakan Gateway {port}...{Style.RESET_ALL}")
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            initial = run_fast_harvester(max_latency_ms=1200, target_count=8, sync_db=bool(db_target))
            if initial:
                start_proxy_server(initial, port=port, background=True, enable_health_check=True)
                time.sleep(1.5)
                print(f"\n{Fore.GREEN}✓ Gateway berhasil aktif di background! Menguji kembali identitas...{Style.RESET_ALL}\n")
                return test_live_masking(port=port)
            else:
                print(f"{Fore.RED}❌ Gagal mendapatkan proxy hidup untuk mengisi gateway.{Style.RESET_ALL}")

    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}\n")



def show_settings_menu():
    """Pusat Pengaturan Cepat [K] - Interactive paste & persist config."""
    global CURRENT_LANG
    while True:
        cfg = load_settings()
        cs_key = cfg.get("capsolver_api_key", "").strip()
        custom_dom = cfg.get("custom_email_domain", "").strip()
        custom_db = cfg.get("9router_db_path", "").strip()
        
        from core.webshare_hunter import check_capsolver_balance
        cs_info = check_capsolver_balance()
        
        if cs_info.get("can_headless"):
            cs_status = f"{Fore.GREEN}Aktif (Saldo: ${cs_info['balance']:.3f}){Style.RESET_ALL}"
        elif cs_info.get("has_key"):
            cs_status = f"{Fore.YELLOW}Saldo Habis (${cs_info['balance']:.3f}){Style.RESET_ALL}"
        else:
            cs_status = f"{Fore.CYAN}Belum Diisi (Mode AI Audio Gratisan Aktif){Style.RESET_ALL}"

        dom_status = f"{Fore.GREEN}@{custom_dom}{Style.RESET_ALL}" if custom_dom else f"{Fore.CYAN}Otomatis / Fallback Pool (Bebas Domain Pribadi){Style.RESET_ALL}"
        db_detected = find_9router_db()
        db_status = f"{Fore.GREEN}{custom_db or db_detected}{Style.RESET_ALL}" if (custom_db or db_detected) else f"{Fore.LIGHTBLACK_EX}Tidak Terdeteksi (Mode Standalone){Style.RESET_ALL}"

        print(BANNER)
        print(f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}⚙️  PUSAT PENGATURAN CEPAT (INTERAKTIF — PASTE & GO)
  {Fore.LIGHTBLACK_EX}Tanpa perlu repot buka file JSON manual — tinggal paste di terminal!
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} 🔑 Setup API Key CapSolver
      {Fore.LIGHTBLACK_EX}Status : {cs_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Biar Webshare Hunter bisa jalan 100% di background (Headless).
               {Fore.YELLOW}*CATATAN: Tidak wajib! Versi gratisan audio bawaan tetap aktif tanpa saldo.{Fore.LIGHTBLACK_EX}

  {Fore.GREEN}[2]{Fore.WHITE} 📧 Setup Custom Domain Email Webshare
      {Fore.LIGHTBLACK_EX}Status : {dom_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Masukkan domain kamu (Cloudflare Email Routing) agar notifikasi akun
               masuk ke Gmail pribadi. Kosongkan jika ingin mode 0-modal otomatis.

  {Fore.GREEN}[3]{Fore.WHITE} 🔌 Setup Lokasi Database 9Router
      {Fore.LIGHTBLACK_EX}Status : {db_status}
      {Fore.LIGHTBLACK_EX}Fungsi : Tentukan path file data.sqlite jika tidak otomatis terdeteksi.

  {Fore.GREEN}[4]{Fore.WHITE} 🧹 Reset Pengaturan ke Default Pabrik (Bersihkan Config)
  {Fore.RED}[0]{Fore.WHITE} 🔙 Kembali ke Menu Utama

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}""")

        choice = input(f"{Fore.YELLOW}Pilih opsi pengaturan [1-4, 0=Kembali]: {Style.RESET_ALL}").strip()
        if choice in ("0", "b", "back", "q"):
            break
        elif choice == "1":
            print(f"\n{Fore.CYAN}🔑 PENGATURAN API KEY CAPSOLVER{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Tekan Enter tanpa ketik apa pun jika ingin menghapus key (kembali ke gratisan).{Style.RESET_ALL}")
            new_key = input(f"{Fore.YELLOW}Paste / Masukkan API Key CapSolver Anda: {Style.RESET_ALL}").strip()
            cfg["capsolver_api_key"] = new_key
            save_settings(cfg)
            if new_key:
                from core.webshare_hunter import check_capsolver_balance
                check_res = check_capsolver_balance(new_key)
                if check_res.get("can_headless"):
                    print(f"\n{Fore.GREEN}✅ API Key berhasil disimpan & diverifikasi! Saldo: ${check_res['balance']:.3f}. Mode Headless siap digunakan!{Style.RESET_ALL}")
                else:
                    print(f"\n{Fore.YELLOW}⚠️ API Key disimpan, tapi saldo kosong atau tidak valid (${check_res.get('balance', 0):.3f}). Audio solver gratisan tetap siap.{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.GREEN}✅ API Key dikosongkan. PetaniProxy kembali ke mode AI Audio Solver 100% gratisan bawaan.{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "2":
            print(f"\n{Fore.CYAN}📧 PENGATURAN CUSTOM DOMAIN WEBSHARE{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Contoh: mydomain.com (pastikan sudah disetup Catch-all di Cloudflare Email Routing).{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}Tekan Enter tanpa ketik apa pun untuk kembali ke domain pool otomatis (0-Modal).{Style.RESET_ALL}")
            new_dom = input(f"{Fore.YELLOW}Masukkan domain email Anda: {Style.RESET_ALL}").strip().lstrip("@")
            cfg["custom_email_domain"] = new_dom
            save_settings(cfg)
            if new_dom:
                print(f"\n{Fore.GREEN}✅ Domain disimpan: @{new_dom}. Registrasi Webshare berikutnya akan memakai domain ini!{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.GREEN}✅ Menggunakan domain pool otomatis bawaan PetaniProxy (0-Modal).{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "3":
            print(f"\n{Fore.CYAN}🔌 PENGATURAN DATABASE 9ROUTER{Style.RESET_ALL}")
            new_path = input(f"{Fore.YELLOW}Paste path lengkap ke data.sqlite 9Router: {Style.RESET_ALL}").strip()
            if new_path and os.path.exists(new_path):
                cfg["9router_db_path"] = new_path
                save_settings(cfg)
                print(f"\n{Fore.GREEN}✅ Database 9Router berhasil dihubungkan ke: {new_path}{Style.RESET_ALL}")
            elif not new_path:
                cfg.pop("9router_db_path", None)
                save_settings(cfg)
                print(f"\n{Fore.GREEN}✅ Menggunakan auto-detection bawaan.{Style.RESET_ALL}")
            else:
                print(f"\n{Fore.RED}❌ File tidak ditemukan di path tersebut: {new_path}{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")
        elif choice == "4":
            if os.path.exists(get_settings_path()):
                os.remove(get_settings_path())
            print(f"\n{Fore.GREEN}✅ Pengaturan berhasil di-reset ke default pabrik!{Style.RESET_ALL}")
            input(f"\n{Fore.LIGHTBLACK_EX}[Tekan Enter untuk lanjut...]{Style.RESET_ALL}")

def show_manual_menu():
    """Sub-menu [M] Bengkel Oprek Manual untuk power user."""

    global CURRENT_LANG
    while True:
        print(BANNER)
        if CURRENT_LANG == "ID":
            m_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🛠️  BENGKEL OPREK MANUAL (PETANIPROXY)
  {Fore.LIGHTBLACK_EX}Buat yang paham jeroan teknis — bebas atur protokol, filter & hook database
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} ⚡ Quick Harvest Standar   {Fore.LIGHTBLACK_EX}Ambil 15 proxy tercepat dari semua tipe
  {Fore.GREEN}[2]{Fore.WHITE} 🔒 Khusus SOCKS5          {Fore.LIGHTBLACK_EX}Protokol tercepat & stabil (HTTP diskip)
  {Fore.GREEN}[3]{Fore.WHITE} 🌐 Khusus HTTP / HTTPS    {Fore.LIGHTBLACK_EX}Proxy klasik untuk web traffic biasa
  {Fore.GREEN}[4]{Fore.WHITE} 🌍 Filter Negara Tertentu {Fore.LIGHTBLACK_EX}Bebas ketik kode ISO (ID, SG, US, JP, dll)
  {Fore.GREEN}[5]{Fore.WHITE} 🛡️ Khusus Elite Proxies   {Fore.LIGHTBLACK_EX}High Anonymity Only — anti bocor header
  {Fore.GREEN}[6]{Fore.WHITE} 🎯 Tembak Target URL      {Fore.LIGHTBLACK_EX}Uji tembus domain incaran (contoh: x.ai)
  {Fore.GREEN}[7]{Fore.WHITE} 🏠 Nyalakan Gateway 8888  {Fore.LIGHTBLACK_EX}Host forward proxy & REST API lokal
  {Fore.GREEN}[8]{Fore.WHITE} 🔌 Setor ke BansosRouter  {Fore.LIGHTBLACK_EX}Inject proxy langsung ke database SQLite
  {Fore.GREEN}[9]{Fore.WHITE} 📦 Perbaiki Dependensi   {Fore.LIGHTBLACK_EX}Self-healing pip install requirements.txt
  {Fore.RED}[0]{Fore.WHITE} 🔙 Balik ke Menu Racikan  {Fore.LIGHTBLACK_EX}Kembali ke beranda utama

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Pilih opsi Bengkel [1-9, 0=Kembali]: {Style.RESET_ALL}"
        else:
            m_box = f"""{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  {Fore.WHITE}{Style.BRIGHT}🛠️  MANUAL TUNING WORKSHOP (PETANIPROXY)
  {Fore.LIGHTBLACK_EX}For power users who need custom protocols, filters & database hooks
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  {Fore.GREEN}[1]{Fore.WHITE} ⚡ Standard Quick Sweep   {Fore.LIGHTBLACK_EX}Grab 15 fastest random live proxies
  {Fore.GREEN}[2]{Fore.WHITE} 🔒 Pure SOCKS5 Only       {Fore.LIGHTBLACK_EX}Ultra-fast SOCKS5 sockets only
  {Fore.GREEN}[3]{Fore.WHITE} 🌐 Classic HTTP / HTTPS   {Fore.LIGHTBLACK_EX}Standard HTTP browsing nodes
  {Fore.GREEN}[4]{Fore.WHITE} 🌍 Custom Country Filter  {Fore.LIGHTBLACK_EX}Filter by country ISO code (ID, SG, US...)
  {Fore.GREEN}[5]{Fore.WHITE} 🛡️ Elite Proxies Only     {Fore.LIGHTBLACK_EX}Strict ghost mode — zero header leaks
  {Fore.GREEN}[6]{Fore.WHITE} 🎯 Target-Specific Snipe  {Fore.LIGHTBLACK_EX}Probe directly against custom website/API
  {Fore.GREEN}[7]{Fore.WHITE} 🏠 Launch Local Gateway   {Fore.LIGHTBLACK_EX}Start rotating forward proxy on port 8888
  {Fore.GREEN}[8]{Fore.WHITE} 🔌 Sync BansosRouter DB   {Fore.LIGHTBLACK_EX}Feed live proxies into SQLite database pool
  {Fore.GREEN}[9]{Fore.WHITE} 📦 Repair Dependencies    {Fore.LIGHTBLACK_EX}Self-healing pip install requirements.txt
  {Fore.RED}[0]{Fore.WHITE} 🔙 Back to Presets Menu   {Fore.LIGHTBLACK_EX}Return to primary launcher

{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}"""
            prompt_str = f"{Fore.YELLOW}Select workshop option [1-9, 0=Back]: {Style.RESET_ALL}"

        print(m_box)
        try:
            choice = input(prompt_str).strip()
        except (KeyboardInterrupt, EOFError):
            break

        if choice in ("0", "b", "back", "q"):
            break
        elif choice == "1":
            q_str = f"{Fore.CYAN}{'Target proxy hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "2":
            q_str = f"{Fore.CYAN}{'Target SOCKS5 hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target SOCKS5 count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "3":
            q_str = f"{Fore.CYAN}{'Target HTTP hidup [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target HTTP count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
        elif choice == "4":
            cc_prompt = f"{Fore.CYAN}{'Kode negara ISO 2 huruf (contoh: ID, SG, US) [default: ID]: ' if CURRENT_LANG == 'ID' else 'Enter 2-letter Country Code [default: ID]: '}{Style.RESET_ALL}"
            cc = input(cc_prompt).strip() or "ID"
            t_prompt = f"{Fore.CYAN}{'Target proxy hidup [default: 5]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 5]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 5
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(350, target_val * 35), target_alive=target_val, country=cc, timeout=3.5)
        elif choice == "5":
            q_str = f"{Fore.CYAN}{'Target Elite proxy [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target Elite count [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(350, target_val * 20), target_alive=target_val, anonymity="elite", timeout=3.0)
        elif choice == "6":
            u_prompt = f"{Fore.CYAN}{'URL target uji [default: https://google.com]: ' if CURRENT_LANG == 'ID' else 'Target URL [default: https://google.com]: '}{Style.RESET_ALL}"
            t_url = input(u_prompt).strip() or "https://google.com"
            t_prompt = f"{Fore.CYAN}{'Target proxy lolos [default: 10]: ' if CURRENT_LANG == 'ID' else 'Target alive count [default: 10]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 10
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(400, target_val * 25), target_alive=target_val, target_url=t_url, timeout=3.5)
        elif choice == "7":
            port_prompt = f"{Fore.CYAN}{'Port gateway lokal [default: 8888]: ' if CURRENT_LANG == 'ID' else 'Local gateway port [default: 8888]: '}{Style.RESET_ALL}"
            port_input = input(port_prompt).strip()
            port_val = int(port_input) if port_input.isdigit() else 8888
            t_prompt = f"{Fore.CYAN}{'Jumlah proxy hidup di pool [default: 15]: ' if CURRENT_LANG == 'ID' else 'Target alive pool size [default: 15]: '}{Style.RESET_ALL}"
            t_input = input(t_prompt).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 15
            run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(300, target_val * 15), target_alive=target_val, timeout=3.0, serve_port=port_val)
        elif choice == "8":
            detected_db = find_9router_db()
            hint = f" [Terdeteksi: {detected_db}]" if detected_db else ""
            custom_path = input(f"{Fore.CYAN}{'Path ke data.sqlite BansosRouter' + hint + ' [Enter untuk default]: ' if CURRENT_LANG == 'ID' else 'Enter BansosRouter data.sqlite path' + hint + ' [Enter for default]: '}{Style.RESET_ALL}").strip()
            db_target = custom_path if custom_path else detected_db
            if db_target and os.path.exists(db_target):
                run_harvester(protocols=["http", "socks4", "socks5"], max_check=250, target_alive=15, sync_9router=db_target)
            else:
                print(f"{Fore.RED}{'Database tidak ditemukan. Pastikan path benar.' if CURRENT_LANG == 'ID' else 'Database not found. Please verify path.'}{Style.RESET_ALL}")
        elif choice == "9":
            install_dependencies()
        else:
            print(f"{Fore.RED}{'Pilihan tidak valid.' if CURRENT_LANG == 'ID' else 'Invalid option.'}{Style.RESET_ALL}")

        try:
            pause_msg = "[Tekan Enter untuk kembali ke menu bengkel...]" if CURRENT_LANG == "ID" else "[Press Enter to return to workshop...]"
            input(f"\n{Fore.LIGHTBLACK_EX}{pause_msg}{Style.RESET_ALL}")
        except (KeyboardInterrupt, EOFError):
            break

def get_features_readiness(lang: str = "ID") -> dict:
    """Check readiness status of features, CapSolver balance, and compute system readiness progress bar."""
    import importlib.util
    import socket
    from core.webshare_hunter import check_capsolver_balance

    status = {}
    score = 0

    # 1. Dependensi Inti
    pkgs = ["httpx", "requests", "colorama", "DrissionPage", "speech_recognition", "pydub"]
    missing = [p for p in pkgs if importlib.util.find_spec(p) is None]
    if not missing:
        status["deps_badge"] = f"{Fore.GREEN}[OK ✓]{Style.RESET_ALL}"
        status["deps_desc"] = "DrissionPage, httpx, pydub, speech_recognition"
        score += 25
    else:
        status["deps_badge"] = f"{Fore.YELLOW}[KURANG: {len(missing)}]{Style.RESET_ALL}"
        status["deps_desc"] = f"Missing: {', '.join(missing)}"

    # 2. Webshare Hunter Audio Solver
    dp_found = importlib.util.find_spec("DrissionPage") is not None
    sr_found = importlib.util.find_spec("speech_recognition") is not None
    if dp_found and sr_found:
        status["webshare"] = f"{Fore.GREEN}[SIAP TEMPUR ✓]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[READY ✓]{Style.RESET_ALL}"
        status["webshare_desc"] = "Free AI Audio Solver Aktif (Mode Jendela Tampak)" if lang == "ID" else "Free AI Audio Solver Active (Visible Window)"
        score += 25
    else:
        status["webshare"] = f"{Fore.YELLOW}[PERLU INSTALL]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.YELLOW}[SETUP NEEDED]{Style.RESET_ALL}"
        status["webshare_desc"] = "Paket DrissionPage / speech_rec belum lengkap" if lang == "ID" else "Packages missing"

    # 3. CapSolver Engine (Headless capability)
    cs_info = check_capsolver_balance()
    status["capsolver_info"] = cs_info
    if cs_info.get("can_headless"):
        status["capsolver_badge"] = f"{Fore.GREEN}[SIAP ✓]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[READY ✓]{Style.RESET_ALL}"
        status["capsolver_desc"] = f"Saldo: ${cs_info['balance']:.3f} (Headless Didukung Penuh)" if lang == "ID" else f"Balance: ${cs_info['balance']:.3f} (Headless Ready)"
        score += 20
    elif cs_info.get("has_key"):
        status["capsolver_badge"] = f"{Fore.YELLOW}[SALDO HABIS]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.YELLOW}[EMPTY BALANCE]{Style.RESET_ALL}"
        status["capsolver_desc"] = f"Saldo ${cs_info['balance']:.3f} (Headless Off, Gunakan Free Audio)" if lang == "ID" else f"Balance ${cs_info['balance']:.3f} (Use Free Audio)"
        score += 10
    else:
        status["capsolver_badge"] = f"{Fore.CYAN}[OPSIONAL / OFF]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.CYAN}[OPTIONAL / OFF]{Style.RESET_ALL}"
        status["capsolver_desc"] = "Mode AI Audio Gratisan 100% Aktif & Siap Tempur ✓" if lang == "ID" else "100% Free AI Audio Solver Active & Ready ✓"
        score += 20


    # 4. 9Router DB sync
    db_path = find_9router_db()
    if db_path:
        status["sync"] = f"{Fore.GREEN}[9ROUTER LINKED]{Style.RESET_ALL}"
        status["db_desc"] = f"Terhubung ({os.path.basename(db_path)})" if lang == "ID" else f"Connected ({os.path.basename(db_path)})"
        score += 20
    else:
        status["sync"] = f"{Fore.CYAN}[STANDALONE]{Style.RESET_ALL}"
        status["db_desc"] = "Mode Mandiri (Database 9Router tidak terdeteksi)" if lang == "ID" else "Standalone mode"
        score += 10

    # 5. Gateway 8888 live port status
    gw_active = False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.05)
            gw_active = (s.connect_ex(('127.0.0.1', 8888)) == 0)
    except Exception:
        gw_active = False

    if gw_active:
        status["gateway"] = f"{Fore.GREEN}[PORT 8888 AKTIF 🟢]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[PORT 8888 ONLINE 🟢]{Style.RESET_ALL}"
    else:
        status["gateway"] = f"{Fore.CYAN}[CEK LIVE]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.CYAN}[LIVE TEST]{Style.RESET_ALL}"


    # 6. Storage count
    base_dir = os.path.dirname(os.path.abspath(__file__))
    json_path = os.path.join(base_dir, "output", "proxies.json")
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                d = json.load(f)
                count = d.get("total_alive", 0)
                status["storage"] = f"{Fore.GREEN}[{count} PROXY TERSEDIA]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.GREEN}[{count} PROXIES READY]{Style.RESET_ALL}"
                status["storage_desc"] = f"{count} Proxy Aktif Tersimpan di Disk" if lang == "ID" else f"{count} Active Proxies Stored"
                score += 15
        except Exception:
            status["storage"] = f"{Fore.GREEN}[READY]{Style.RESET_ALL}"
            status["storage_desc"] = "File penyimpanan siap"
            score += 10
    else:
        status["storage"] = f"{Fore.LIGHTBLACK_EX}[KOSONG]{Style.RESET_ALL}" if lang == "ID" else f"{Fore.LIGHTBLACK_EX}[EMPTY]{Style.RESET_ALL}"
        status["storage_desc"] = "Belum ada riwayat panen tersimpan" if lang == "ID" else "No saved proxies yet"
        score += 5

    pct = min(100, score)
    bar_len = 10
    filled = int(bar_len * pct / 100)
    bar_str = "█" * filled + "░" * (bar_len - filled)
    status["percent"] = pct
    status["bar"] = bar_str

    if pct >= 85:
        bar_color = Fore.GREEN
        state_txt = "Amunisi Siap Tempur!" if lang == "ID" else "Battle-Ready!"
    elif pct >= 60:
        bar_color = Fore.YELLOW
        state_txt = "Sebagian Siap" if lang == "ID" else "Partially Ready"
    else:
        bar_color = Fore.RED
        state_txt = "Perlu Setup" if lang == "ID" else "Setup Needed"

    status["progress_line"] = f"{bar_color}[{bar_str}] {pct}%{Style.RESET_ALL} {Fore.LIGHTBLACK_EX}({state_txt}){Style.RESET_ALL}"
    return status

def show_interactive_menu():
    global CURRENT_LANG
    check_initial_dependencies()
    update_checked = False
    cached_update_info = None

    while True:
        # Check update once per app session (cached)
        if not update_checked:
            update_checked = True
            try:
                cached_update_info = check_for_updates(timeout=2.0)
            except Exception:
                cached_update_info = None

        local_info = get_local_version_info()
        local_ver = local_info.get("version", "1.2.0")
        st = get_features_readiness(lang=CURRENT_LANG)
        ready_label = f"{Fore.GREEN}● [SIAP]{Style.RESET_ALL}" if CURRENT_LANG == "ID" else f"{Fore.GREEN}● [READY]{Style.RESET_ALL}"

        update_msg = None
        if cached_update_info and cached_update_info.get("has_update"):
            update_msg = f"Update Tersedia: v{cached_update_info.get('remote_version')} (Pilih U)" if CURRENT_LANG == "ID" else f"Update Available: v{cached_update_info.get('remote_version')} (Select U)"

        menu = InteractiveMenu(
            title="PETANI PROXY",
            subtitle="Pusat Scraper, Validator Multi-Protokol dan Local Gateway" if CURRENT_LANG == "ID" else "High-Performance Multi-Protocol Scraper and Local Rotating Gateway",
            version=local_ver,
            metrics_title="STATUS DAN KESIAPAN SISTEM" if CURRENT_LANG == "ID" else "SYSTEM READINESS AND METRICS",
            metrics_data=[
                ("Dependensi Inti", st.get('deps_badge', ''), "BansosRouter DB", st.get('sync', '')),
                ("Webshare Hunter", st.get('webshare', ''), "Gateway (8888)", st.get('gateway', '')),
                ("CapSolver API", st.get('capsolver_badge', ''), "Gudang Cache", st.get('storage', ''))
            ],
            update_notice=update_msg
        )

        if CURRENT_LANG == "ID":
            menu.add_section("PIPELINES DAN RESIDENTIAL")
            menu.add_item("w", "Webshare Residential", "Ekstraksi otomatis IP Residential via audio solver", st.get('webshare', ''))
            menu.add_item("r", "Ternak Akun Grok xAI", "Panen akun Grok otomatis via DuckMail/Gmail", f"{Fore.GREEN}● [GROK]{Style.RESET_ALL}")
            menu.add_item("c", "Cloudflare WARP Local", "WireGuard Anycast tunnel bebas captcha, unlimited", f"{Fore.GREEN}● [ULTRA]{Style.RESET_ALL}")
            menu.add_item("f", "Fast Async Harvester", "Scrape massal filter latency rendah asinkron", f"{Fore.GREEN}● [FAST]{Style.RESET_ALL}")

            menu.add_section("LOCAL GATEWAY DAN PROFILES")
            menu.add_item("d", "Buka Web Dashboard", "Luncurkan Gateway & otomatis buka UI di browser", f"{Fore.CYAN}● [WEB UI]{Style.RESET_ALL}")
            menu.add_item("g", "Mode Petani 24/7", "Daemon rotasi otomatis port 8888 (auto-heal and refill)", ready_label)
            menu.add_item("1", "Profil Ternak Akun", "Khusus bot AI Grok/Qoder (Sync DB + Port 8888)", st.get('sync', ''))
            menu.add_item("2", "Profil Web Scraper", "Rotasi agresif pool 30+ IP tiap request", ready_label)
            menu.add_item("3", "Profil Low-Latency", "Node tercepat SG / ID / US (Ping rendah)", ready_label)

            menu.add_section("DIAGNOSTIK DAN EKSPOR")
            menu.add_item("e", "Ekspor File Proxy", "Simpan daftar proxy bersih ke TXT, JSON, CSV", f"{Fore.CYAN}● [EKSPOR]{Style.RESET_ALL}")
            menu.add_item("t", "Uji Kebocoran IP", "Audit live: bandingkan IP asli vs IP Gateway", st.get('gateway', ''))
            menu.add_item("s", "Gudang Proxy Lokal", "Lihat dan kelola file proxy tersimpan di disk", st.get('storage', ''))

            menu.add_section("PENGATURAN DAN SISTEM")
            menu.add_item("k", "Pengaturan Cepat", "Konfigurasi API key CapSolver dan path database", f"{Fore.LIGHTBLACK_EX}[CONFIG]{Style.RESET_ALL}")
            menu.add_item("u", "Cek Pembaruan", "Periksa dan update versi terbaru dari GitHub", f"{Fore.LIGHTBLACK_EX}[UPDATE]{Style.RESET_ALL}")
            menu.add_item("m", "Manual Filter Lab", "Kustomisasi protokol dan filter negara ISO", ready_label)
            menu.add_item("l", "Ganti Bahasa (EN/ID)", "Ubah bahasa antarmuka saat ini: ID", f"{Fore.LIGHTBLACK_EX}[LANG]{Style.RESET_ALL}")
            menu.add_item("0", "Keluar", "Tutup aplikasi PetaniProxy", f"{Fore.RED}[KELUAR]{Style.RESET_ALL}")
        else:
            menu.add_section("PIPELINES AND RESIDENTIAL")
            menu.add_item("w", "Webshare Residential", "Automated residential IP extraction via audio solver", st.get('webshare', ''))
            menu.add_item("r", "Grok xAI Account Farm", "Automated Grok registration via DuckMail/Gmail", f"{Fore.GREEN}● [GROK]{Style.RESET_ALL}")
            menu.add_item("c", "Cloudflare WARP Local", "WireGuard Anycast zero-captcha local tunnel", f"{Fore.GREEN}● [ULTRA]{Style.RESET_ALL}")
            menu.add_item("f", "Fast Async Harvester", "Mass concurrent scraper (low latency filter)", f"{Fore.GREEN}● [FAST]{Style.RESET_ALL}")

            menu.add_section("LOCAL GATEWAY AND PROFILES")
            menu.add_item("d", "Open Web Dashboard", "Launch Gateway & auto-open Web UI in browser", f"{Fore.CYAN}● [WEB UI]{Style.RESET_ALL}")
            menu.add_item("g", "24/7 Farmer Daemon", "Auto-rotating port 8888 gateway (auto-prune and refill)", ready_label)
            menu.add_item("1", "Bot Breeder Profile", "Tuned for Grok/Qoder bots (DB sync + Port 8888)", st.get('sync', ''))
            menu.add_item("2", "High-Concurrency Scraper", "Aggressive rotation, fresh IP every request", ready_label)
            menu.add_item("3", "Ultra-Low Latency Mode", "Low latency response nodes (SG / ID / US)", ready_label)

            menu.add_section("DIAGNOSTICS AND EXPORTS")
            menu.add_item("e", "Export Clean Pool", "Export live proxy pool into TXT, JSON, CSV", f"{Fore.CYAN}● [EXPORT]{Style.RESET_ALL}")
            menu.add_item("t", "Identity Leak Check", "Live audit: compare Direct IP vs Gateway IP", st.get('gateway', ''))
            menu.add_item("s", "Local Ammo Storage", "Inspect and manage cached proxies sitting on disk", st.get('storage', ''))

            menu.add_section("CONFIGURATION AND SYSTEM")
            menu.add_item("k", "Quick Settings", "Configure CapSolver API key and database path", f"{Fore.LIGHTBLACK_EX}[CONFIG]{Style.RESET_ALL}")
            menu.add_item("u", "Check for Updates", "Check and pull latest version from GitHub", f"{Fore.LIGHTBLACK_EX}[UPDATE]{Style.RESET_ALL}")
            menu.add_item("m", "Manual Filter Lab", "Custom protocols and ISO country filters", ready_label)
            menu.add_item("l", "Switch Language", "Toggle UI language (Currently: English)", f"{Fore.LIGHTBLACK_EX}[LANG]{Style.RESET_ALL}")
            menu.add_item("0", "Exit", "Close PetaniProxy session", f"{Fore.RED}[EXIT]{Style.RESET_ALL}")

        choice = menu.run()
        if not choice or choice in ("0", "q"):
            break

        if choice.lower() == "u":
            print(f"\n{Fore.CYAN}{'Memeriksa pembaruan ke GitHub...' if CURRENT_LANG == 'ID' else 'Checking GitHub for updates...'}{Style.RESET_ALL}")
            info = check_for_updates(timeout=3.5)
            if info.get("has_update"):
                print(render_update_banner(info, lang=CURRENT_LANG))
                show_full_announcement(info, lang=CURRENT_LANG)
                c_up = input(f"\n{Fore.YELLOW}{'Lakukan update sekarang? [Y/n]: ' if CURRENT_LANG == 'ID' else 'Perform update now? [Y/n]: '}{Style.RESET_ALL}").strip().lower()
                if c_up in ("", "y", "yes"):
                    perform_update(restart=True, lang=CURRENT_LANG)
            else:
                curr_ver = info.get("current_version", "1.0.0")
                print(f"\n{Fore.GREEN}✅ {'PetaniProxy sudah dalam versi paling baru' if CURRENT_LANG == 'ID' else 'PetaniProxy is up to date'} (v{curr_ver})!{Style.RESET_ALL}")
                show_full_announcement(info, lang=CURRENT_LANG)
            
            try:
                p_msg = "[Tekan Enter untuk kembali ke menu...]" if CURRENT_LANG == "ID" else "[Press Enter to return to main menu...]"
                input(f"\n{Fore.LIGHTBLACK_EX}{p_msg}{Style.RESET_ALL}")
            except (KeyboardInterrupt, EOFError):
                break
            continue

        if choice.lower() == "l":
            CURRENT_LANG = "EN" if CURRENT_LANG == "ID" else "ID"
            new_lang_name = "Bahasa Indonesia" if CURRENT_LANG == "ID" else "English"
            print(f"\n{Fore.GREEN}🌐 Bahasa antarmuka diubah ke: {new_lang_name}{Style.RESET_ALL}")
            continue

        if choice.lower() == "m":
            show_manual_menu()
            continue

        if choice.lower() == "k":
            show_settings_menu()
            continue

        if choice.lower() == "d":
            launch_web_dashboard(port=8888)
            continue

        if choice.lower() == "s":
            view_saved_results()
            continue

        if choice.lower() == "t":
            test_live_masking(port=8888)
        elif choice.lower() == "e":
            q_str = f"{Fore.CYAN}{'Target jumlah proxy hidup yang mau diekspor [default: 20]: ' if CURRENT_LANG == 'ID' else 'Target alive proxies to export [default: 20]: '}{Style.RESET_ALL}"
            t_input = input(q_str).strip()
            target_val = int(t_input) if t_input.isdigit() and int(t_input) > 0 else 20
            res = run_harvester(protocols=["http", "socks4", "socks5"], max_check=max(250, target_val * 15), target_alive=target_val, timeout=3.0)
            if res:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                out_dir = os.path.join(base_dir, "output")
                fm_name = "File Explorer" if sys.platform == "win32" else "Finder" if sys.platform == "darwin" else "File Manager"
                ed_name = "Notepad" if sys.platform == "win32" else "TextEdit" if sys.platform == "darwin" else "Text Editor"
                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}💾 FILE MENTAH SEGAR BERHASIL DIBUNGKUS!{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📂 Buka Folder Output ({fm_name})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📝 Buka File live_all.txt ({ed_name})")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-2, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_explorer(out_dir)
                    elif sub == "2":
                        open_in_text_editor(os.path.join(out_dir, "live_all.txt"))
                    else:
                        break
            continue
        elif choice == "" or choice == "1":
            print(f"\n{Fore.GREEN}{'🐔 Menjalankan Racikan Ternak Akun (Grok, Qoder & Bot AI)...' if CURRENT_LANG == 'ID' else '🐔 Launching Account Farming Preset (Grok, Qoder & AI)...'}{Style.RESET_ALL}")
            db_target = find_9router_db()
            if db_target:
                print(f"  {Fore.CYAN}✓ BansosRouter SQLite terdeteksi di: {Fore.WHITE}{db_target}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks5"], 
                max_check=350, 
                target_alive=20, 
                anonymity="elite", 
                timeout=2.5, 
                serve_port=8888, 
                sync_9router=db_target
            )
        elif choice == "2":
            print(f"\n{Fore.GREEN}{'🕷️ Menjalankan Racikan Scraper Brutal (Shopee, Tokopedia, Web Data)...' if CURRENT_LANG == 'ID' else '🕷️ Launching Mass Web Scraper Preset...'}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks4", "socks5"], 
                max_check=500, 
                target_alive=30, 
                anonymity="elite", 
                timeout=3.5, 
                serve_port=8888
            )
        elif choice == "3":
            print(f"\n{Fore.GREEN}{'⚡ Menjalankan Racikan Turbo Surfing (Ping Terendah, SG/ID/US)...' if CURRENT_LANG == 'ID' else '⚡ Launching Lightning Turbo Surfing Preset...'}{Style.RESET_ALL}")
            run_harvester(
                protocols=["http", "socks5"], 
                max_check=350, 
                target_alive=15, 
                timeout=2.0, 
                serve_port=8888
            )
        elif choice.lower() == "w":
            try:
                from core.webshare_hunter import run_webshare_hunter
            except ImportError as e:
                print(f"\n{Fore.RED}⚠️ Dependensi Webshare Hunter belum lengkap: {e}{Style.RESET_ALL}")
                ask_inst = input(f"{Fore.YELLOW}{'👉 Pasang otomatis sekarang (1-Klik via pip)? [Y/n]: ' if CURRENT_LANG == 'ID' else '👉 Auto-install dependencies now (1-Click via pip)? [Y/n]: '}{Style.RESET_ALL}").strip().lower()
                if ask_inst in ("", "y", "yes"):
                    if install_dependencies():
                        try:
                            from core.webshare_hunter import run_webshare_hunter
                        except ImportError:
                            print(f"{Fore.RED}{'Gagal memuat Webshare Hunter setelah instalasi.' if CURRENT_LANG == 'ID' else 'Failed to load Webshare Hunter after installation.'}{Style.RESET_ALL}")
                            continue
                    else:
                        continue
                else:
                    continue

            print(f"\n{Fore.YELLOW}{Style.BRIGHT}{'⭐ MEMBUKA WEBSHARE RESIDENTIAL HUNTER (FITUR MVP)...' if CURRENT_LANG == 'ID' else '⭐ LAUNCHING WEBSHARE RESIDENTIAL HUNTER (MVP FEATURE)...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: 1 Akun Webshare menghasilkan 10 IP Residential asli dengan username:password pribadi.' if CURRENT_LANG == 'ID' else '💡 Info: 1 Webshare account generates 10 genuine Residential IPs with private credentials.'}{Style.RESET_ALL}")
            acc_prompt = f"{Fore.CYAN}{'Berapa akun Webshare yang ingin dipanen? [Default: 1]: ' if CURRENT_LANG == 'ID' else 'How many Webshare accounts to hunt? [Default: 1]: '}{Style.RESET_ALL}"
            a_input = input(acc_prompt).strip()
            total_acc = int(a_input) if a_input.isdigit() and int(a_input) > 0 else 1

            from core.webshare_hunter import check_capsolver_balance
            cs_info = check_capsolver_balance()
            is_headless = False

            if cs_info.get("can_headless"):
                print(f"\n  {Fore.GREEN}✓ CapSolver API Aktif! Saldo: ${cs_info['balance']:.3f} (Mode Headless siap tempur){Style.RESET_ALL}")
                head_prompt = f"{Fore.CYAN}{'Jalankan di background tanpa jendela (Headless)? [Y/n]: ' if CURRENT_LANG == 'ID' else 'Run in background (Headless)? [Y/n]: '}{Style.RESET_ALL}"
                h_input = input(head_prompt).strip().lower()
                is_headless = h_input in ("", "y", "yes")
            else:
                print(f"\n{Fore.CYAN}ℹ️  STATUS ENGINE CAPTCHA & MODE TAMPILAN:{Style.RESET_ALL}")
                print(f"  • Solver Aktif   : {Fore.GREEN}Free AI Audio Solver (SpeechRecognition, Tanpa Saldo Token){Style.RESET_ALL}")
                print(f"  • Status Headless: {Fore.CYAN}Opsional / Dimatikan{Style.RESET_ALL} ({cs_info.get('message')})")
                print(f"  {Fore.LIGHTBLACK_EX}💡 Penjelasan: Audio Solver gratisan WAJIB menggunakan jendela tampak agar bot")
                print(f"     bergerak alami & tidak diblokir 'Automated queries' oleh Google reCAPTCHA.{Style.RESET_ALL}")
                print(f"  {Fore.GREEN}👉 Otomatis menggunakan Mode Jendela Tampak (Mode Paling Stabil & Gacor)...{Style.RESET_ALL}\n")
                is_headless = False

            db_target = find_9router_db()
            run_webshare_hunter(total=total_acc, headless=is_headless, sync_9router_db=db_target)
            
            base_dir = os.path.dirname(os.path.abspath(__file__))
            ws_file = os.path.join(base_dir, "output", "webshare_residential.txt")
            if os.path.exists(ws_file) and os.path.getsize(ws_file) > 0:
                fm_name = "File Explorer" if sys.platform == "win32" else "Finder" if sys.platform == "darwin" else "File Manager"
                ed_name = "Notepad" if sys.platform == "win32" else "TextEdit" if sys.platform == "darwin" else "Text Editor"
                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}🏢 AMUNISI RESIDENTIAL SIAP! PILIH AKSI:{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📝 Buka File Daftar IP di {ed_name} ({Fore.YELLOW}webshare_residential.txt{Fore.WHITE})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 📂 Buka Folder Output di {fm_name}")
                    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📋 Tampilkan Contoh Kode Python Requests Siap Pakai")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-3, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_text_editor(ws_file)
                    elif sub == "2":
                        open_in_explorer(os.path.dirname(ws_file))
                    elif sub == "3":
                        with open(ws_file, "r", encoding="utf-8") as f:
                            first_proxy = f.readline().strip()
                        print(f"\n{Fore.CYAN}📋 CONTOH KODE PYTHON REQUESTS:{Style.RESET_ALL}")
                        print(f"""{Fore.WHITE}import requests

proxies = {{
    "http": "{first_proxy or 'http://user:pass@ip:port'}",
    "https": "{first_proxy or 'http://user:pass@ip:port'}"
}}

resp = requests.get("https://api.ipify.org?format=json", proxies=proxies, timeout=10)
print("IP Aktif Residential:", resp.json()["ip"])
{Style.RESET_ALL}""")
                    else:
                        break
            continue
        elif choice.lower() == "r":
            print(f"\n{Fore.GREEN}{Style.BRIGHT}{'🤖 MEMBUKA MESIN TERNAK AKUN GROK xAI (STANDALONE)...' if CURRENT_LANG == 'ID' else '🤖 LAUNCHING GROK xAI ACCOUNT FARMER...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: Memanfaatkan pool residential proxy & auto-OTP via DuckMail/Gmail.' if CURRENT_LANG == 'ID' else '💡 Info: Utilizing residential proxies & auto-OTP via DuckMail/Gmail.'}{Style.RESET_ALL}\n")
            
            cnt_prompt = f"{Fore.CYAN}{'Berapa target akun Grok yang ingin dipanen? [Default: 1]: ' if CURRENT_LANG == 'ID' else 'How many Grok accounts to farm? [Default: 1]: '}{Style.RESET_ALL}"
            c_input = input(cnt_prompt).strip()
            total_grok = int(c_input) if c_input.isdigit() and int(c_input) > 0 else 1

            prov_prompt = f"{Fore.CYAN}Pilih Provider Email:\n  [1] DuckMail (Disposable instan, default)\n  [2] Gmail (Subaddress alias via IMAP)\nPilihan [1/2, default 1]: {Style.RESET_ALL}"
            p_input = input(prov_prompt).strip()
            mail_prov = "gmail" if p_input == "2" else "duckmail"

            head_prompt = f"{Fore.CYAN}Mode tampilan:\n  [1] Jendela Tampak / Semi-Manual (Bisa dipantau langsung, default)\n  [2] Background / Headless (Tanpa jendela)\nPilihan [1/2, default 1]: {Style.RESET_ALL}"
            h_input = input(head_prompt).strip()
            is_headless = (h_input == "2")

            try:
                from core.grok_farm import run_grok_farm
                run_grok_farm(total=total_grok, headless=is_headless, mail_provider=mail_prov)
            except Exception as e:
                print(f"{Fore.RED}❌ Gagal menjalankan Grok Farm: {e}{Style.RESET_ALL}")

            base_dir = os.path.dirname(os.path.abspath(__file__))
            acc_file = os.path.join(base_dir, "output", "grok_accounts.txt")
            if os.path.exists(acc_file) and os.path.getsize(acc_file) > 0:
                print(f"\n{Fore.GREEN}✓ Akun Grok tersimpan di: {Fore.YELLOW}{acc_file}{Style.RESET_ALL}")
                ans = input(f"{Fore.CYAN}Buka file akun di Notepad sekarang? [Y/n]: {Style.RESET_ALL}").strip().lower()
                if ans in ("", "y", "yes"):
                    open_in_text_editor(acc_file)
            continue
        elif choice.lower() == "c":
            print(f"\n{Fore.CYAN}{Style.BRIGHT}{'🚀 MEMBUAT PROFIL CLOUDFLARE WARP (WIREGUARD / SING-BOX)...' if CURRENT_LANG == 'ID' else '🚀 GENERATING CLOUDFLARE WARP PROFILE...'}{Style.RESET_ALL}")
            print(f"{Fore.LIGHTBLACK_EX}{'💡 Info: Registrasi resmi via Cloudflare REST API (100% legal, tanpa captcha, unlimited).' if CURRENT_LANG == 'ID' else '💡 Info: Official registration via Cloudflare REST API (zero captcha, unlimited).'}{Style.RESET_ALL}\n")
            from core.warp_generator import generate_and_save_warp
            db_target = find_9router_db()
            profile = generate_and_save_warp(sync_db=bool(db_target))
            if profile:
                base_dir = os.path.dirname(os.path.abspath(__file__))
                warp_conf = os.path.join(base_dir, "output", "warp", "warp.conf")
                warp_folder = os.path.join(base_dir, "output", "warp")
                is_win = sys.platform == "win32"
                is_mac = sys.platform == "darwin"
                is_linux = sys.platform.startswith("linux")
                fm_name = "File Explorer" if is_win else "Finder" if is_mac else "File Manager"

                if is_win:
                    platform_label = "Windows (.exe)"
                    download_url = "https://download.wireguard.com/windows-client/wireguard-installer.exe"
                elif is_mac:
                    platform_label = "macOS (Mac App Store)"
                    download_url = "https://apps.apple.com/us/app/wireguard/id1451685025"
                elif is_linux:
                    platform_label = "Linux (apt / pacman)"
                    download_url = "https://www.wireguard.com/install/"
                else:
                    platform_label = "Perangkat Anda"
                    download_url = "https://www.wireguard.com/install/"

                while True:
                    print(f"\n{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    print(f"{Fore.WHITE}{Style.BRIGHT}🎉 AMUNISI CLOUDFLARE WARP SIAP DIGUNAKAN! PILIH AKSI:{Style.RESET_ALL}")
                    print(f"  {Fore.GREEN}[1]{Fore.WHITE} 📂 Buka Folder File ({Fore.YELLOW}warp.conf{Fore.WHITE} di {fm_name})")
                    print(f"  {Fore.GREEN}[2]{Fore.WHITE} 🌐 Download / Install Resmi WireGuard untuk {Fore.YELLOW}{platform_label}{Fore.WHITE}")
                    print(f"  {Fore.GREEN}[3]{Fore.WHITE} 📋 Panduan Kilat Cara Pakai di WireGuard ({'Windows' if is_win else 'macOS' if is_mac else 'Linux'})")
                    print(f"  {Fore.RED}[0 / Enter]{Fore.WHITE} 🔙 Kembali ke Menu Utama")
                    print(f"{Fore.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{Style.RESET_ALL}")
                    sub = input(f"{Fore.YELLOW}Pilih aksi [1-3, 0=Kembali]: {Style.RESET_ALL}").strip()
                    if sub == "1":
                        open_in_explorer(warp_conf if os.path.exists(warp_conf) else warp_folder)
                    elif sub == "2":
                        if is_linux:
                            print(f"\n{Fore.CYAN}🐧 CARA INSTALL WIREGUARD DI LINUX:{Style.RESET_ALL}")
                            print(f"  • Ubuntu / Debian / Mint : {Fore.GREEN}sudo apt update && sudo apt install -y wireguard{Style.RESET_ALL}")
                            print(f"  • Arch Linux / Manjaro   : {Fore.GREEN}sudo pacman -S wireguard-tools{Style.RESET_ALL}")
                            print(f"  • Fedora / RHEL          : {Fore.GREEN}sudo dnf install wireguard-tools{Style.RESET_ALL}")
                            print(f"\n  🚀 Cara Konek Cepat via Terminal:")
                            print(f"    {Fore.YELLOW}sudo wg-quick up \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  🛑 Cara Matikan Tunnel:")
                            print(f"    {Fore.YELLOW}sudo wg-quick down \"{warp_conf}\"{Style.RESET_ALL}\n")
                            open_url_in_browser(download_url)
                        else:
                            print(f"  {Fore.GREEN}🌐 Membuka link download resmi WireGuard {platform_label}...{Style.RESET_ALL}")
                            open_url_in_browser(download_url)
                    elif sub == "3":
                        print(f"\n{Fore.CYAN}📖 PANDUAN KILAT CARA PAKAI (1 MENIT LANGSUNG KONEK):{Style.RESET_ALL}")
                        if is_win:
                            print(f"  1. Buka aplikasi WireGuard di Windows.")
                            print(f"  2. Klik tombol {Fore.YELLOW}'Add Tunnel'{Style.RESET_ALL} (atau tekan {Fore.YELLOW}Ctrl + O{Style.RESET_ALL}).")
                            print(f"  3. Pilih file: {Fore.GREEN}{warp_conf}{Style.RESET_ALL}")
                            print(f"  4. Klik tombol {Fore.YELLOW}'Activate'{Style.RESET_ALL}.")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh koneksi PC kamu otomatis berkecepatan monster via Cloudflare!{Style.RESET_ALL}")
                        elif is_mac:
                            print(f"  1. Buka aplikasi WireGuard dari Mac App Store / Applications.")
                            print(f"  2. Klik menu bar WireGuard -> {Fore.YELLOW}'Import tunnel(s) from file'{Style.RESET_ALL} (atau tekan {Fore.YELLOW}Cmd + O{Style.RESET_ALL}).")
                            print(f"  3. Pilih file: {Fore.GREEN}{warp_conf}{Style.RESET_ALL}")
                            print(f"  4. Klik tombol {Fore.YELLOW}'Activate'{Style.RESET_ALL}.")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh koneksi Mac kamu otomatis lewat Cloudflare WARP!{Style.RESET_ALL}")
                        else:
                            print(f"  1. Buka terminal Linux.")
                            print(f"  2. Jalankan perintah: {Fore.YELLOW}sudo wg-quick up \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  3. Cek IP aktif:      {Fore.GREEN}curl https://api.ipify.org{Style.RESET_ALL}")
                            print(f"  4. Matikan tunnel:    {Fore.YELLOW}sudo wg-quick down \"{warp_conf}\"{Style.RESET_ALL}")
                            print(f"  {Fore.GREEN}✓ Selesai! Seluruh network Linux kamu aman terlindungi Anycast Cloudflare!{Style.RESET_ALL}")
                    else:
                        break
            continue
        elif choice.lower() == "f":
            print(f"\n{Fore.CYAN}{Style.BRIGHT}{'⚡ MEMULAI AIOHTTP FAST PROXY HARVESTER...' if CURRENT_LANG == 'ID' else '⚡ LAUNCHING AIOHTTP FAST HARVESTER...'}{Style.RESET_ALL}")
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            run_fast_harvester(max_latency_ms=1200, target_count=15, sync_db=bool(db_target))
        elif choice.lower() == "g" or choice == "4":
            print(f"\n{Fore.GREEN}{Style.BRIGHT}{'🚜 MENJALANKAN MODE PETANI AFK 24/7 (RESILIENT GATEWAY + AUTO-HEALER)...' if CURRENT_LANG == 'ID' else '🚜 STARTING 24/7 AFK FARMER DAEMON (RESILIENT GATEWAY + AUTO-HEALER)...'}{Style.RESET_ALL}")
            from core.server import start_proxy_server
            from core.fast_validator import run_fast_harvester
            db_target = find_9router_db()
            print(f"  {Fore.LIGHTBLACK_EX}• Menyiapkan amunisi awal dari feed cepat...{Style.RESET_ALL}")
            initial = run_fast_harvester(max_latency_ms=1200, target_count=10, sync_db=bool(db_target))
            print(f"\n{Fore.GREEN}✓ Gateway aktif di http://127.0.0.1:8888 (Auto-prune & refill aktif non-stop). Tekan Ctrl+C untuk berhenti.{Style.RESET_ALL}\n")
            start_proxy_server(initial, port=8888, background=False, enable_health_check=True, health_check_interval=90, min_healthy_count=5)
        elif choice.lower() in ("s", "saved"):
            view_saved_results()
        elif choice == "0" or choice.lower() == "q":
            goodbye_msg = "Sesi PetaniProxy selesai." if CURRENT_LANG == "ID" else "PetaniProxy session ended."
            print(f"\n{Fore.LIGHTBLACK_EX}{goodbye_msg}{Style.RESET_ALL}\n")
            break
        else:
            invalid_msg = "Pilihan tidak valid." if CURRENT_LANG == "ID" else "Invalid option."
            print(f"{Fore.RED}{invalid_msg}{Style.RESET_ALL}")

        try:
            pause_msg = "Tekan tombol apa saja untuk kembali ke menu utama..." if CURRENT_LANG == "ID" else "Press any key to return to main menu..."
            quick_pause(pause_msg)
        except (KeyboardInterrupt, EOFError):
            break

def run_async_pipeline(accounts: int = 10, headless: bool = False, mail_provider: str = "duckmail"):
    """Menjalankan Webshare Residential Hunter dan Grok Farm secara simultan / asinkron (paralel)."""
    import threading
    from core.webshare_hunter import run_webshare_hunter
    from core.grok_farm import run_grok_farm

    print(f"\n{Fore.GREEN}{Style.BRIGHT}🚀 MEMULAI PIPELINE ASINKRON ALL-IN-ONE (PARALEL)...{Style.RESET_ALL}")
    print(f"  • Webshare Hunter : Panen proxy residential di background (Thread 1)")
    print(f"  • Grok Farm Engine: Panen {accounts} Akun Grok xAI serentak (Thread 2)")
    print(f"  • Provider Email  : {mail_provider.upper()}")
    print(f"  • Mode Browser    : {'Background (Headless)' if headless else 'Tampak Layar (Semi-Manual)'}\n")

    ws_target = max(1, (accounts + 9) // 10)
    db_target = find_9router_db()

    t_ws = threading.Thread(
        target=run_webshare_hunter,
        kwargs={"total": ws_target, "headless": headless, "sync_9router_db": db_target},
        name="Worker-WebshareHunter",
        daemon=True
    )
    t_grok = threading.Thread(
        target=run_grok_farm,
        kwargs={"total": accounts, "headless": headless, "mail_provider": mail_provider},
        name="Worker-GrokFarm"
    )

    t_ws.start()
    time.sleep(1)
    t_grok.start()

    t_grok.join()
    t_ws.join(timeout=10)

    print(f"\n{Fore.GREEN}✓ Pipeline Asinkron Selesai! Semua akun dan proxy berhasil dipanen.{Style.RESET_ALL}\n")

def main():
    if len(sys.argv) == 1:
        show_interactive_menu()
        return

    # Normalisasi CLI alias subcommands agar user-friendly
    if len(sys.argv) > 1:
        first_cmd = sys.argv[1].lower()
        if first_cmd in ("grok-farm", "farm-grok", "grok", "ternak-grok"):
            sys.argv[1] = "--grok-farm"
        elif first_cmd in ("webshare", "hunter", "webshare-hunter"):
            sys.argv[1] = "--webshare"
        elif first_cmd in ("pabrik", "pipeline", "async", "all-in-one"):
            sys.argv[1] = "--pipeline"

    parser = argparse.ArgumentParser(description="PetaniProxy v1.1.0 - High-Speed Multi-Protocol Proxy Harvester, Cloudflare WARP & Resilient Gateway")

    parser.add_argument("--protocol", "-p", choices=["all", "http", "socks4", "socks5"], default="all", help="Target proxy protocol (default: all)")
    parser.add_argument("--max", "-m", type=int, default=250, help="Maximum candidate proxies to validate (default: 250)")
    parser.add_argument("--target", "-t", type=int, default=15, help="Target number of alive proxies to collect (default: 15)")
    parser.add_argument("--timeout", type=float, default=3.0, help="Connection timeout in seconds (default: 3.0)")
    parser.add_argument("--workers", "-w", type=int, default=50, help="Concurrent testing workers (default: 50)")
    parser.add_argument("--country", "-c", type=str, default=None, help="Filter by country ISO code (e.g. US, SG, ID, DE)")
    parser.add_argument("--anonymity", choices=["all", "elite", "anonymous", "transparent"], default="all", help="Filter by anonymity level (default: all)")
    parser.add_argument("--target-url", type=str, default=None, help="Validate proxies against specific website (e.g. https://google.com)")
    parser.add_argument("--serve", nargs="?", const=8888, type=int, default=None, help="Start local rotating forward proxy & REST API on port (default: 8888)")
    parser.add_argument("--loop", "-l", type=int, default=0, help="Auto-refresh loop interval in minutes (0 = single run)")
    parser.add_argument("--output", "-o", type=str, default=None, help="Custom output directory")
    parser.add_argument("--sync-9router", type=str, default=None, help="Path to BansosRouter/9Router data.sqlite for direct database sync (or 'auto')")
    parser.add_argument("--warp", "-C", action="store_true", help="Generate Cloudflare WARP WireGuard & Sing-box profile (zero captcha, unlimited)")
    parser.add_argument("--fast-harvest", "-F", type=int, nargs="?", const=15, default=None, help="Run ultra-fast aiohttp proxy harvester for N targets")
    parser.add_argument("--max-latency", type=int, default=1200, help="Maximum latency in ms for fast harvester (default: 1200)")
    parser.add_argument("--daemon-gateway", "-G", action="store_true", help="Run 24/7 resilient local gateway on port 8888 with auto-healer")
    parser.add_argument("--webshare", "-W", type=int, nargs="?", const=1, default=None, help="Trigger Webshare Residential Hunter for N accounts (default: 1)")
    parser.add_argument("--grok-farm", "-K", type=int, nargs="?", const=1, default=None, help="Ternak Akun Grok xAI secara otomatis untuk N akun (default: 1)")
    parser.add_argument("--pipeline", "-P", type=int, nargs="?", const=10, default=None, help="Jalankan Pipeline Asinkron: Panen Webshare & Panen Akun Grok serentak (paralel)")
    parser.add_argument("--mail-provider", choices=["duckmail", "gmail"], default="duckmail", help="Provider email untuk Grok Farm: 'duckmail' atau 'gmail' (default: duckmail)")
    parser.add_argument("--headless", action="store_true", help="Run browser in headless mode (tanpa jendela)")
    parser.add_argument("--update", action="store_true", help="Perform 1-click update via git pull and exit")
    parser.add_argument("--check-update", action="store_true", help="Check for available updates on GitHub and display patch notes")
    parser.add_argument("--install-deps", action="store_true", help="Auto-install all dependencies from requirements.txt")
    parser.add_argument("--version", "-v", action="store_true", help="Show current version, announcement and exit")

    args = parser.parse_args()

    if args.version:
        v_info = get_local_version_info()
        print(BANNER)
        show_full_announcement(v_info)
        return

    if args.install_deps:
        print(BANNER)
        install_dependencies()
        return

    if args.check_update:
        print(BANNER)
        print(f"{Fore.CYAN}Memeriksa pembaruan ke GitHub...{Style.RESET_ALL}\n")
        info = check_for_updates(timeout=3.5)
        if info.get("has_update"):
            print(render_update_banner(info))
            show_full_announcement(info)
        else:
            print(f"{Fore.GREEN}✅ PetaniProxy sudah versi terbaru (v{info.get('current_version')})!{Style.RESET_ALL}")
            show_full_announcement(info)
        return

    if args.update:
        print(BANNER)
        perform_update(restart=False)
        return

    print(BANNER)

    router_db = args.sync_9router
    if router_db == "auto" or router_db is None:
        router_db = find_9router_db()

    if args.warp:
        from core.warp_generator import generate_and_save_warp
        generate_and_save_warp(output_dir=args.output, sync_db=bool(router_db))
        return

    if args.fast_harvest is not None:
        from core.fast_validator import run_fast_harvester
        run_fast_harvester(max_latency_ms=args.max_latency, target_count=args.fast_harvest, sync_db=bool(router_db))
        return

    if args.daemon_gateway:
        from core.server import start_proxy_server
        from core.fast_validator import run_fast_harvester
        print(f"\n{Fore.GREEN}🛡️ Menyiapkan amunisi awal untuk 24/7 Resilient Gateway...{Style.RESET_ALL}")
        initial = run_fast_harvester(max_latency_ms=args.max_latency, target_count=10, sync_db=bool(router_db))
        print(f"\n{Fore.GREEN}✓ Meluncurkan Gateway di http://127.0.0.1:8888 dengan auto-healer...{Style.RESET_ALL}\n")
        start_proxy_server(initial, port=8888, background=False, enable_health_check=True, health_check_interval=90, min_healthy_count=5)
        return

    if args.webshare is not None:
        try:
            from core.webshare_hunter import run_webshare_hunter, check_capsolver_balance
        except ImportError as e:
            print(f"{Fore.RED}⚠️ Dependensi Webshare Hunter belum lengkap: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Silakan jalankan: python main.py --install-deps{Style.RESET_ALL}\n")
            sys.exit(1)

        if args.headless:
            cs = check_capsolver_balance()
            if not cs.get("can_headless"):
                print(f"\n{Fore.YELLOW}⚠️ PERINGATAN HEADLESS:{Style.RESET_ALL} {cs.get('message')}")
                print(f"{Fore.LIGHTBLACK_EX}Menjalankan Audio Solver gratisan di mode headless berisiko tinggi memicu blokir 'Automated queries' dari Google.")
                print(f"Disarankan menjalankan tanpa flag --headless atau sediakan CAPSOLVER_API_KEY.{Style.RESET_ALL}\n")

        run_webshare_hunter(total=args.webshare, headless=args.headless, sync_9router_db=router_db, output_dir=args.output)
        return

    if args.grok_farm is not None:
        try:
            from core.grok_farm import run_grok_farm
        except ImportError as e:
            print(f"{Fore.RED}⚠️ Dependensi Grok Farm belum lengkap: {e}{Style.RESET_ALL}")
            print(f"{Fore.YELLOW}Silakan jalankan: python main.py --install-deps{Style.RESET_ALL}\n")
            sys.exit(1)

        print(f"\n{Fore.GREEN}{Style.BRIGHT}🤖 MENJALANKAN TERNAK AKUN GROK xAI (STANDALONE)...{Style.RESET_ALL}")
        print(f"  • Target Akun   : {Fore.YELLOW}{args.grok_farm}{Style.RESET_ALL}")
        print(f"  • Provider Email: {Fore.CYAN}{args.mail_provider.upper()}{Style.RESET_ALL}")
        print(f"  • Mode Browser  : {Fore.WHITE}{'Background (Headless)' if args.headless else 'Tampak Layar (Semi-Manual)'}{Style.RESET_ALL}\n")
        
        run_grok_farm(total=args.grok_farm, headless=args.headless, mail_provider=args.mail_provider)
        return

    if args.pipeline is not None:
        run_async_pipeline(accounts=args.pipeline, headless=args.headless, mail_provider=args.mail_provider)
        return

    proto_list = [args.protocol] if args.protocol != "all" else ["http", "socks4", "socks5"]

    if args.loop > 0:
        print(f"{Fore.MAGENTA}🔄 Auto-refresh loop active: Running every {args.loop} minutes... (Press Ctrl+C to stop){Style.RESET_ALL}")
        while True:
            try:
                run_harvester(
                    protocols=proto_list,
                    max_check=args.max,
                    target_alive=args.target,
                    timeout=args.timeout,
                    workers=args.workers,
                    country=args.country,
                    anonymity=args.anonymity,
                    target_url=args.target_url,
                    output_dir=args.output,
                    sync_9router=router_db,
                    serve_port=args.serve
                )
                print(f"{Fore.LIGHTBLACK_EX}Sleeping for {args.loop} minutes before next sweep...{Style.RESET_ALL}")
                time.sleep(args.loop * 60)
            except KeyboardInterrupt:
                print(f"\n{Fore.YELLOW}🛑 Harvester stopped by user.{Style.RESET_ALL}")
                break
    else:
        run_harvester(
            protocols=proto_list,
            max_check=args.max,
            target_alive=args.target,
            timeout=args.timeout,
            workers=args.workers,
            country=args.country,
            anonymity=args.anonymity,
            target_url=args.target_url,
            output_dir=args.output,
            sync_9router=router_db,
            serve_port=args.serve
        )

if __name__ == "__main__":
    main()
