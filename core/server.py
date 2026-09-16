"""
core/server.py - Local Rotating Gateway, Sticky Session, Header Sanitizer & Web Dashboard
Provides a local forward-proxy endpoint (HTTP/HTTPS CONNECT) that automatically rotates
requests across verified alive proxies, plus a modern Desktop Command Center Web UI and REST API.
Zero external server dependencies (uses standard library socket, http.server, threading).
"""
import os
import sys
import json
import time
import socket
import select
import random
import threading
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import List, Dict, Any, Optional, Tuple

COMMON_USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1"
]

FAVICON_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="#d4ff32"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>"""

# Webshare Task Manager State
webshare_hunter_state = {
    "status": "idle",
    "progress": 0,
    "current_account": 0,
    "total_accounts": 0,
    "gathered_count": 0,
    "logs": [],
    "last_error": None
}
webshare_lock = threading.Lock()

class ProxyPoolManager:
    """Manages in-memory verified proxies, sticky sessions, and stats."""
    def __init__(self, initial_proxies: Optional[List[Dict[str, Any]]] = None):
        self.lock = threading.Lock()
        self.proxies: List[Dict[str, Any]] = initial_proxies or []
        self.index = 0
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.start_time = time.time()
        self.health_checker = None
        self.sessions: Dict[str, Dict[str, Any]] = {}
        self.session_ttl_sec = 600

    def update_pool(self, new_proxies: List[Dict[str, Any]]):
        with self.lock:
            self.proxies = new_proxies
            self.index = 0

    def get_all(self) -> List[Dict[str, Any]]:
        with self.lock:
            return list(self.proxies)

    def get_random(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.proxies:
                return None
            return random.choice(self.proxies)

    def force_rotate(self) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.proxies:
                return None
            self.index += 1
            return self.proxies[self.index % len(self.proxies)]

    def get_next(self, session_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        with self.lock:
            if not self.proxies:
                return None

            now = time.time()
            expired = [k for k, v in self.sessions.items() if v.get("expires_at", 0) < now]
            for k in expired:
                del self.sessions[k]

            if session_id:
                sess_info = self.sessions.get(session_id)
                if sess_info and sess_info.get("proxy") in self.proxies:
                    sess_info["expires_at"] = now + self.session_ttl_sec
                    self.total_requests += 1
                    return sess_info["proxy"]

                proxy = self.proxies[self.index % len(self.proxies)]
                self.index += 1
                self.sessions[session_id] = {
                    "proxy": proxy,
                    "expires_at": now + self.session_ttl_sec
                }
                self.total_requests += 1
                return proxy

            proxy = self.proxies[self.index % len(self.proxies)]
            self.index += 1
            self.total_requests += 1
            return proxy

    def mark_result(self, success: bool):
        with self.lock:
            if success:
                self.successful_requests += 1
            else:
                self.failed_requests += 1

    def get_stats(self) -> Dict[str, Any]:
        with self.lock:
            uptime = round(time.time() - self.start_time, 1)
            total = self.total_requests
            success_pct = round((self.successful_requests / max(1, total)) * 100, 1) if total > 0 else 100.0
            current_proxy = self.proxies[self.index % len(self.proxies)] if self.proxies else None
            
            stats = {
                "uptime_seconds": uptime,
                "pool_size": len(self.proxies),
                "total_routed_requests": self.total_requests,
                "successful_requests": self.successful_requests,
                "failed_requests": self.failed_requests,
                "success_rate_percent": success_pct,
                "active_sticky_sessions": len(self.sessions),
                "current_index": self.index,
                "active_proxy": current_proxy.get("proxy") if current_proxy else None,
                "active_country": current_proxy.get("country") if current_proxy else None,
                "active_cc": current_proxy.get("country_code") if current_proxy else None
            }
            if self.health_checker:
                stats["health_checker"] = {
                    "status": "active" if getattr(self.health_checker, "is_running", False) else "stopped",
                    "interval_sec": getattr(self.health_checker, "check_interval_sec", 90),
                    "total_evicted": getattr(self.health_checker, "total_evicted", 0),
                    "total_refilled": getattr(self.health_checker, "total_refilled", 0),
                    "last_check_time": getattr(self.health_checker, "last_check_time", None)
                }
            return stats


DASHBOARD_HTML = r"""<!DOCTYPE html>
<html lang="id">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>PetaniProxy Desktop Command Center</title>
  <link rel="icon" type="image/svg+xml" href="/favicon.ico">
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #0b0c0f; }
    code, pre, .font-mono { font-family: 'JetBrains Mono', monospace; }
    .pulse-dot { animation: pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite; }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: .4; } }
    .lime-btn { background-color: #d4ff32; color: #0b0c0f; font-weight: 700; }
    .lime-btn:hover { background-color: #c0ee20; }
    .app-card { background-color: #14161c; border: 1px solid rgba(255, 255, 255, 0.06); }
    .app-card:hover { border-color: rgba(255, 255, 255, 0.12); }
    .custom-scroll::-webkit-scrollbar { width: 5px; height: 5px; }
    .custom-scroll::-webkit-scrollbar-thumb { background: #262933; border-radius: 4px; }
    .kbd-badge { background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12); border-radius: 4px; font-family: 'JetBrains Mono', monospace; font-size: 10px; padding: 2px 6px; }
    .modal-backdrop { background-color: rgba(7, 8, 11, 0.85); backdrop-filter: blur(8px); }
    
    /* Interactive Tooltip Engine */
    .has-tooltip { position: relative; display: inline-flex; align-items: center; cursor: pointer; }
    .tooltip-content {
      visibility: hidden; opacity: 0; position: absolute; z-index: 60;
      bottom: 125%; left: 50%; transform: translateX(-50%) translateY(4px);
      width: 270px; padding: 10px 12px; background: #1c1f2b;
      border: 1px solid rgba(212, 255, 50, 0.3); border-radius: 12px;
      color: #e2e8f0; font-size: 11px; line-height: 1.4;
      box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.7);
      transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
      pointer-events: none;
    }
    .tooltip-content::after {
      content: ""; position: absolute; top: 100%; left: 50%;
      margin-left: -6px; border-width: 6px; border-style: solid;
      border-color: #1c1f2b transparent transparent transparent;
    }
    .has-tooltip:hover .tooltip-content, .has-tooltip:focus .tooltip-content {
      visibility: visible; opacity: 1; transform: translateX(-50%) translateY(0);
    }
  </style>
</head>
<body class="text-slate-100 min-h-screen flex items-center justify-center p-2 sm:p-4 md:p-6 select-none selection:bg-[#d4ff32] selection:text-black">

  <!-- Desktop App Container Frame -->
  <div class="w-full max-w-7xl bg-[#0f1015] border border-white/[0.08] rounded-[28px] p-4 sm:p-6 lg:p-7 shadow-2xl flex flex-col md:flex-row gap-6 overflow-hidden relative min-h-[760px]">

    <!-- Left Floating Dock Sidebar -->
    <aside class="w-full md:w-16 bg-[#161820] border border-white/[0.06] rounded-2xl md:rounded-full py-3 md:py-6 px-4 md:px-2 flex flex-row md:flex-col justify-between items-center shrink-0 z-20 shadow-xl">
      <!-- Top Brand Glyph -->
      <div class="flex flex-row md:flex-col items-center gap-4">
        <div class="w-10 h-10 rounded-full bg-white text-slate-950 flex items-center justify-center shadow-lg transition hover:scale-105" title="PetaniProxy Core">
          <svg class="w-5 h-5 text-black" viewBox="0 0 24 24" fill="currentColor">
            <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/>
          </svg>
        </div>

        <!-- Navigation Tab Buttons -->
        <nav class="flex flex-row md:flex-col items-center gap-3">
          <button onclick="switchTab('dashboard')" id="nav-dash" class="w-10 h-10 rounded-full lime-btn flex items-center justify-center shadow-md transition transform active:scale-95" title="Dashboard Utama (1)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"/></svg>
          </button>
          <button onclick="switchTab('table')" id="nav-table" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition" title="Daftar & Multi-Filter Proxy (2)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M3 10h18M3 14h18m-9-4v8m-7 0h14a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
          </button>
          <button onclick="switchTab('radar')" id="nav-radar" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition" title="Uji Kebocoran IP Radar (3)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
          </button>
          <button onclick="switchTab('snippets')" id="nav-snippets" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition" title="Scraping & Bot Live Playground (4)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M10 20l4-16m4 4l4 4-4 4M6 16l-4-4 4-4"/></svg>
          </button>
          <button onclick="openGrokModal()" id="nav-grok" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-purple-600/30 text-purple-400 hover:text-purple-300 border border-purple-500/20 flex items-center justify-center transition" title="Ternak Akun Grok xAI (G)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
          </button>
          <button onclick="openHunterModal()" id="nav-hunter" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-emerald-600/30 text-emerald-400 hover:text-emerald-300 border border-emerald-500/20 flex items-center justify-center transition" title="Panen Residential Webshare (W)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
          </button>
          <button onclick="forceRotate()" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition" title="Force Rotate IP Instan (R)">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          </button>
        </nav>
      </div>

      <!-- Bottom Utilities -->
      <div class="flex flex-row md:flex-col items-center gap-3">
        <button onclick="openShortcutsModal()" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition" title="Pusat Bantuan & Kamus (?)">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
        </button>
        <a href="/proxy.pac" target="_blank" class="w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition text-xs font-bold font-mono" title="PAC Script Auto-Config">
          PAC
        </a>
        <div class="w-10 h-10 rounded-full bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 flex items-center justify-center text-xs font-bold relative" title="Gateway Live di Port 8888">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
          <span class="w-2.5 h-2.5 bg-emerald-400 rounded-full absolute -top-0.5 -right-0.5 border-2 border-[#161820] pulse-dot"></span>
        </div>
      </div>
    </aside>

    <!-- Main View Canvas -->
    <main class="flex-1 flex flex-col gap-5 overflow-hidden">

      <!-- Top Header Bar with Preset Profiles -->
      <header class="flex flex-col gap-3.5 pb-2 border-b border-white/[0.06]">
        <div class="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <div>
            <h1 class="text-xl sm:text-2xl font-extrabold text-white tracking-tight flex items-center gap-2.5">
              PetaniProxy <span class="text-[11px] px-2.5 py-0.5 rounded-full bg-white/10 text-slate-300 font-mono font-semibold">Core v1.2.0</span>
            </h1>
            <p class="text-xs sm:text-sm text-[#8b8f9a]">Pusat Kendali Rotating Gateway, Stealth Sanitizer & Auto-Healer</p>
          </div>

          <div class="flex items-center gap-2.5 w-full sm:w-auto justify-between sm:justify-end">
            <!-- Global Search Pill -->
            <div class="relative w-full sm:w-60">
              <input type="text" id="filter-input" onkeyup="handleGlobalSearch(event)" placeholder="Cari IP, CC, ISP... (/)" class="w-full bg-[#161820] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white placeholder-[#8b8f9a] rounded-full pl-9 pr-9 py-2 outline-none transition font-mono">
              <svg class="w-4 h-4 text-[#8b8f9a] absolute left-3 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
              <span class="absolute right-3 top-2 kbd-badge text-slate-400">/</span>
            </div>

            <!-- Grok Breeder Modal Button -->
            <button onclick="openGrokModal()" class="px-3.5 py-2 rounded-full bg-purple-600/20 hover:bg-purple-600/30 text-purple-300 font-bold text-xs transition border border-purple-500/30 shrink-0 flex items-center gap-1.5 active:scale-95" title="Buka Mesin Ternak Grok xAI">
              <svg class="w-3.5 h-3.5 text-purple-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
              <span class="hidden lg:inline">Ternak Grok xAI</span>
            </button>

            <!-- Force Rotate Button -->
            <button onclick="forceRotate()" class="px-4 py-2 rounded-full bg-[#2563eb] hover:bg-blue-600 text-white font-bold text-xs transition shadow-lg shadow-blue-600/30 shrink-0 flex items-center gap-1.5 active:scale-95">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              <span>Rotate IP</span>
            </button>
          </div>
        </div>

        <!-- Mode Presets Bar -->
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <span class="text-[#8b8f9a] font-medium flex items-center gap-1">
            <span>Mode Operasi:</span>
            <span class="has-tooltip text-slate-400 hover:text-white">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span class="tooltip-content">
                <strong>Preset Profil Pintar</strong><br>
                Racikan konfigurasi otomatis: Scraper barbar, ternak akun Grok AI xAI, atau stealth anti-doxing.
              </span>
            </span>
          </span>

          <button onclick="applyPreset('barbar')" id="preset-barbar" class="px-3 py-1 rounded-full bg-[#1b1e27] hover:bg-white/10 text-slate-300 font-semibold transition border border-white/[0.05] flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-amber-400"></span>
            <span>Scraper Barbar</span>
          </button>
          
          <button onclick="applyPreset('grok')" id="preset-grok" class="px-3 py-1 rounded-full bg-[#1b1e27] hover:bg-white/10 text-slate-300 font-semibold transition border border-white/[0.05] flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-purple-400"></span>
            <span>Ternak Akun Grok xAI</span>
          </button>

          <button onclick="applyPreset('stealth')" id="preset-stealth" class="px-3 py-1 rounded-full bg-[#1b1e27] hover:bg-white/10 text-slate-300 font-semibold transition border border-white/[0.05] flex items-center gap-1.5">
            <span class="w-2 h-2 rounded-full bg-emerald-400"></span>
            <span>Anti-Doxing Stealth</span>
          </button>
        </div>
      </header>

      <!-- View Section: Dashboard -->
      <div id="view-dashboard" class="space-y-5 overflow-y-auto custom-scroll flex-1 pr-1">

        <!-- Bento Grid: Top Section -->
        <div class="grid grid-cols-12 gap-5">

          <!-- Left Big Card: Gateway Health & Latency Wave -->
          <div class="col-span-12 lg:col-span-8 app-card rounded-3xl p-6 flex flex-col justify-between space-y-6">
            <div class="flex items-center justify-between">
              <div class="flex items-center gap-2">
                <span class="text-sm font-bold text-white tracking-wide">Gateway Activity & Health</span>
                <span class="w-2 h-2 rounded-full bg-emerald-400 pulse-dot"></span>
                <span class="has-tooltip text-slate-500 hover:text-white">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span class="tooltip-content">
                    <strong>Denyut Nadi Gateway 127.0.0.1:8888</strong><br>
                    Live request routing, success rate counter, dan auto-refill proxy pool secara otomatis jika node menipis.
                  </span>
                </span>
              </div>
              <div class="flex items-center gap-2">
                <button onclick="triggerRefill()" id="btn-refill-trigger" class="text-xs px-3 py-1 rounded-full bg-[#262933] hover:bg-slate-700 text-slate-300 hover:text-white font-medium transition flex items-center gap-1">
                  <svg class="w-3 h-3 text-[#d4ff32]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 4v16m8-8H4"/></svg>
                  <span>Refill Pool</span>
                </button>
              </div>
            </div>

            <!-- Wave Graph Visual -->
            <div class="w-full h-24 relative flex items-center">
              <svg class="w-full h-full" viewBox="0 0 500 100" preserveAspectRatio="none">
                <path d="M0,50 Q60,20 120,60 T240,40 T360,70 T500,30" fill="none" stroke="#262933" stroke-width="3" stroke-linecap="round"/>
                <path d="M0,65 Q70,90 140,40 T280,75 T400,25 T500,60" fill="none" stroke="#3b82f6" stroke-width="2.5" stroke-linecap="round"/>
                <path d="M0,45 Q80,10 160,55 T300,20 T420,65 T500,40" fill="none" stroke="#d4ff32" stroke-width="3" stroke-linecap="round"/>
              </svg>
              <div class="absolute left-[32%] top-2 flex flex-col items-center">
                <div class="px-2 py-0.5 rounded-full bg-[#d4ff32] text-black text-[10px] font-extrabold shadow-lg">
                  LIVE ROTATION
                </div>
                <div class="w-0.5 h-10 border-l border-dashed border-[#d4ff32]/60"></div>
                <div class="w-2.5 h-2.5 rounded-full bg-[#d4ff32] ring-4 ring-[#d4ff32]/20"></div>
              </div>
            </div>

            <!-- 3 Big Numbers Row -->
            <div class="grid grid-cols-3 gap-4 pt-2 border-t border-white/[0.05]">
              <div>
                <div class="text-xs text-[#8b8f9a] font-medium flex items-center gap-1">
                  <span>Active Pool</span>
                  <span class="has-tooltip text-slate-500 hover:text-white">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="tooltip-content">
                      <strong>Lumbung Amunisi Proxy</strong><br>
                      Jumlah node proxy valid siap pakai di memory. Jika berkurang di bawah 5, Auto-Healer langsung nyendok proxy baru.
                    </span>
                  </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold text-white mt-0.5 font-mono" id="stat-pool">-</div>
                <div class="text-[11px] text-[#8b8f9a] mt-1">Target Pool: 20+</div>
              </div>
              <div>
                <div class="text-xs text-[#8b8f9a] font-medium flex items-center gap-1">
                  <span>Requests Routed</span>
                  <span class="has-tooltip text-slate-500 hover:text-white">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="tooltip-content">
                      <strong>Total Tembakan Bot</strong><br>
                      Berapa kali bot / scraper kamu meminta data lewat gateway lokal ini.
                    </span>
                  </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold text-white mt-0.5 font-mono" id="stat-req">-</div>
                <div class="text-[11px] text-[#8b8f9a] mt-1">Success: <span id="stat-success" class="text-[#d4ff32]">100%</span></div>
              </div>
              <div>
                <div class="text-xs text-[#8b8f9a] font-medium flex items-center gap-1">
                  <span>Avg Latency</span>
                  <span class="has-tooltip text-slate-500 hover:text-white">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="tooltip-content">
                      <strong>Dukun Ping / Rata-rata Latensi</strong><br>
                      Rata-rata waktu respon proxy di pool. Semakin kecil, bot semakin kencang menyedot data.
                    </span>
                  </span>
                </div>
                <div class="text-2xl sm:text-3xl font-extrabold text-[#d4ff32] mt-0.5 font-mono" id="stat-ping">-</div>
                <div class="text-[11px] text-[#8b8f9a] mt-1">Low Latency Node</div>
              </div>
            </div>
          </div>

          <!-- Right Card: Active Gateway & Geolocation Matrix -->
          <div class="col-span-12 lg:col-span-4 bg-[#2563eb] rounded-3xl p-6 text-white flex flex-col justify-between shadow-xl shadow-blue-600/20">
            <div class="flex items-center justify-between">
              <span class="text-sm font-bold tracking-wide flex items-center gap-1.5">
                <span>Gateway Live</span>
                <span class="has-tooltip text-blue-200 hover:text-white">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span class="tooltip-content text-slate-900 bg-white border-blue-300">
                    <strong>Local Forward Proxy 8888</strong><br>
                    Tinggal arahkan bot Python, Node.js, cURL, atau browser ke http://127.0.0.1:8888. Semua otomatis ter-rotasi!
                  </span>
                </span>
              </span>
              <span class="text-xs font-semibold bg-white/20 px-2.5 py-0.5 rounded-full font-mono">127.0.0.1:8888</span>
            </div>

            <div class="my-4">
              <div class="text-[11px] text-blue-100 font-medium mb-2 flex items-center justify-between">
                <span>Active Geolocation Pool:</span>
                <span class="font-mono text-xs font-bold" id="stat-cc-count">0 Countries</span>
              </div>
              <div class="grid grid-cols-4 gap-2 text-center text-xs font-mono" id="cc-matrix-grid">
                <div class="p-2 rounded-xl bg-white/10 font-bold">US</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">SG</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">ID</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">DE</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">JP</div>
                <div class="p-2 rounded-xl bg-[#d4ff32] text-black font-extrabold shadow-lg">ROT</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">NL</div>
                <div class="p-2 rounded-xl bg-white/10 font-bold">FR</div>
              </div>
            </div>

            <div class="pt-3 border-t border-white/20 flex items-center justify-between text-xs">
              <span class="text-blue-100 flex items-center gap-1">
                <span>Sticky Session Lock:</span>
                <span class="has-tooltip text-blue-200 hover:text-white">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span class="tooltip-content text-slate-900 bg-white border-blue-300">
                    <strong>Kuncian Jodoh IP (10 Menit)</strong><br>
                    Pakai header <code>X-Session-ID: bot1</code> untuk mengunci IP yang sama selama 10 menit. Wajib buat login & checkout!
                  </span>
                </span>
              </span>
              <span class="font-bold font-mono bg-black/20 px-2.5 py-0.5 rounded-full" id="stat-sess">0 Active</span>
            </div>
          </div>

        </div>

        <!-- Bento Grid: Middle & Bottom Section -->
        <div class="grid grid-cols-12 gap-5">

          <!-- Left Column Widgets -->
          <div class="col-span-12 lg:col-span-4 space-y-4">
            
            <!-- Topeng Ninja Stealth Sanitizer Card -->
            <div class="app-card rounded-3xl p-5 flex items-center justify-between">
              <div class="space-y-1">
                <div class="text-[11px] text-[#8b8f9a] font-bold uppercase tracking-wider flex items-center gap-1">
                  <span>Topeng Ninja</span>
                  <span class="has-tooltip text-slate-500 hover:text-white">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="tooltip-content">
                      <strong>Anti-Cloudflare WAF</strong><br>
                      Otomatis membuang header cepu (X-Forwarded-For, Via, Client-IP) & mengganti User-Agent python jadi Chrome asli biar gak diblokir.
                    </span>
                  </span>
                </div>
                <div class="text-sm font-bold text-white">Stealth Sanitizer</div>
                <div class="text-xs text-[#8b8f9a]">Zero DNS Leak • Genuine Chrome UA</div>
              </div>
              <div class="w-14 h-14 rounded-full border-4 border-[#262933] border-t-[#d4ff32] border-r-[#d4ff32] flex items-center justify-center font-extrabold text-xs text-[#d4ff32] font-mono">
                100%
              </div>
            </div>

            <!-- Health Bar Card -->
            <div class="app-card rounded-3xl p-5 space-y-3">
              <div class="flex items-center justify-between text-xs font-semibold">
                <span class="text-white flex items-center gap-1">
                  <span>Auto-Healer Daemon</span>
                  <span class="has-tooltip text-slate-500 hover:text-white">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                    <span class="tooltip-content">
                      <strong>Dokter Jaga Anti-Boncos</strong><br>
                      Background thread yang membuang IP mati tiap 90 detik & otomatis memanen ulang proxy segar dari 12 provider publik.
                    </span>
                  </span>
                </span>
                <span class="text-[#d4ff32] font-mono">24/7 Active</span>
              </div>
              <div class="w-full h-2.5 rounded-full bg-[#262933] overflow-hidden">
                <div class="h-full bg-[#d4ff32] rounded-full" style="width: 90%"></div>
              </div>
              <div class="flex items-center justify-between text-[11px] text-[#8b8f9a]">
                <span>Prune node mati otomatis</span>
                <span>Auto-Refill pool</span>
              </div>
            </div>

            <!-- Double Trigger VIP: Grok Farm & Webshare -->
            <div class="grid grid-cols-2 gap-3">
              <button onclick="openGrokModal()" class="p-4 rounded-2xl bg-purple-900/20 hover:bg-purple-900/30 border border-purple-500/30 text-left transition flex flex-col justify-between space-y-2">
                <div class="w-8 h-8 rounded-xl bg-purple-600/30 flex items-center justify-center text-purple-300">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
                </div>
                <div>
                  <div class="text-xs font-bold text-white">Ternak Grok xAI</div>
                  <div class="text-[10px] text-[#8b8f9a]">Auto-Breeder Akun</div>
                </div>
              </button>

              <button onclick="openHunterModal()" class="p-4 rounded-2xl bg-emerald-900/20 hover:bg-emerald-900/30 border border-emerald-500/30 text-left transition flex flex-col justify-between space-y-2">
                <div class="w-8 h-8 rounded-xl bg-emerald-600/30 flex items-center justify-center text-emerald-300">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
                </div>
                <div>
                  <div class="text-xs font-bold text-white">Panen Webshare</div>
                  <div class="text-[10px] text-[#8b8f9a]">10 Residential IP/Akun</div>
                </div>
              </button>
            </div>

          </div>

          <!-- Right Column Widget: Verified Proxy Cards Stream -->
          <div class="col-span-12 lg:col-span-8 app-card rounded-3xl p-6 flex flex-col justify-between space-y-5">
            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h3 class="text-sm font-bold text-white tracking-wide">Amunisi Proxy Terverifikasi</h3>
                <p class="text-xs text-[#8b8f9a]" id="proxy-count-hint">Memuat data proxy aktif...</p>
              </div>

              <div class="flex items-center gap-1.5 p-1 bg-[#111216] border border-white/[0.05] rounded-full text-xs">
                <button onclick="setCardFilter('all')" id="pill-all" class="px-3 py-1 rounded-full lime-btn text-xs transition">All</button>
                <button onclick="setCardFilter('http')" id="pill-http" class="px-3 py-1 rounded-full text-[#8b8f9a] hover:text-white transition">HTTP</button>
                <button onclick="setCardFilter('socks5')" id="pill-socks5" class="px-3 py-1 rounded-full text-[#8b8f9a] hover:text-white transition">SOCKS5</button>
                <button onclick="setCardFilter('elite')" id="pill-elite" class="px-3 py-1 rounded-full text-[#8b8f9a] hover:text-white transition">Elite</button>
              </div>
            </div>

            <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3" id="proxy-cards-grid">
              <!-- Dynamically populated -->
            </div>
          </div>

        </div>

      </div>

      <!-- View Section: Full Proxy Table -->
      <div id="view-table" class="space-y-4 hidden flex-1 flex flex-col overflow-hidden">
        <div class="app-card rounded-3xl p-6 flex-1 flex flex-col space-y-4 overflow-hidden">
          
          <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-4 pb-2 border-b border-white/[0.06]">
            <div>
              <h3 class="text-base font-bold text-white flex items-center gap-2">
                <span>Daftar Seluruh Pool Proxy</span>
                <span class="text-xs font-mono px-2.5 py-0.5 rounded-full bg-white/10 text-emerald-400 font-bold" id="table-total-badge">0 Live</span>
              </h3>
              <p class="text-xs text-[#8b8f9a]">Tabel amunisi proxy aktif dengan multi-filter dan ekspor format instan</p>
            </div>

            <div class="flex flex-wrap items-center gap-2">
              <button onclick="copyAllProxies()" class="px-3 py-1.5 rounded-xl bg-[#1e212b] hover:bg-slate-700 text-xs font-medium text-slate-200 transition border border-white/[0.06] flex items-center gap-1.5">
                <svg class="w-3.5 h-3.5 text-[#d4ff32]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>
                <span>Copy All</span>
              </button>

              <div class="relative inline-block text-left">
                <button onclick="toggleExportMenu()" id="btn-export" class="px-3.5 py-1.5 rounded-xl bg-[#2563eb] hover:bg-blue-600 text-xs font-bold text-white transition flex items-center gap-1.5 shadow-md">
                  <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/></svg>
                  <span>Export</span>
                  <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M19 9l-7 7-7-7"/></svg>
                </button>
                <div id="export-dropdown" class="hidden absolute right-0 mt-2 w-44 rounded-2xl bg-[#1c1f28] border border-white/[0.1] shadow-2xl z-30 py-1.5">
                  <a href="/api/export?format=txt" download class="block px-4 py-2 text-xs text-slate-200 hover:bg-white/10 hover:text-white transition">TXT (Plain IP:Port)</a>
                  <a href="/api/export?format=urls" download class="block px-4 py-2 text-xs text-slate-200 hover:bg-white/10 hover:text-white transition">URLs (http://ip:port)</a>
                  <a href="/api/export?format=csv" download class="block px-4 py-2 text-xs text-slate-200 hover:bg-white/10 hover:text-white transition">CSV Spreadsheet</a>
                  <a href="/api/export?format=json" download class="block px-4 py-2 text-xs text-slate-200 hover:bg-white/10 hover:text-white transition">Rich JSON File</a>
                </div>
              </div>

              <button onclick="refreshData()" class="p-2 rounded-xl bg-[#1e212b] hover:bg-slate-700 text-slate-300 hover:text-white transition border border-white/[0.06]" title="Refresh Data">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
              </button>
            </div>
          </div>

          <!-- Multi-Filter Bar -->
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-5 gap-2.5">
            <div class="md:col-span-2 relative">
              <input type="text" id="table-search-input" onkeyup="onFilterChange()" placeholder="Cari IP, Port, ISP, Region..." class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white placeholder-[#8b8f9a] rounded-xl pl-8 pr-3 py-2 outline-none transition font-mono">
              <svg class="w-3.5 h-3.5 text-[#8b8f9a] absolute left-3 top-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"/></svg>
            </div>

            <div>
              <select id="filter-protocol" onchange="onFilterChange()" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white rounded-xl px-3 py-2 outline-none transition font-mono">
                <option value="all">Protocol: All</option>
                <option value="http">HTTP</option>
                <option value="socks4">SOCKS4</option>
                <option value="socks5">SOCKS5</option>
              </select>
            </div>

            <div>
              <select id="filter-country" onchange="onFilterChange()" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white rounded-xl px-3 py-2 outline-none transition font-mono">
                <option value="all">Country: All</option>
              </select>
            </div>

            <div>
              <select id="filter-sort" onchange="onFilterChange()" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white rounded-xl px-3 py-2 outline-none transition font-mono">
                <option value="latency-asc">Sort: Ping Terendah</option>
                <option value="latency-desc">Sort: Ping Tertinggi</option>
                <option value="country-asc">Sort: Negara (A-Z)</option>
                <option value="protocol">Sort: Protokol</option>
              </select>
            </div>
          </div>

          <!-- Proxy Data Table -->
          <div class="overflow-x-auto custom-scroll flex-1 rounded-2xl border border-white/[0.05] bg-[#111216]">
            <table class="w-full text-left text-xs font-mono">
              <thead class="text-[#8b8f9a] border-b border-white/[0.06] bg-[#161820] uppercase tracking-wider text-[11px] sticky top-0 z-10">
                <tr>
                  <th class="py-3 px-4 w-12 text-center">#</th>
                  <th class="py-3 px-4">Protokol</th>
                  <th class="py-3 px-4">IP : Port</th>
                  <th class="py-3 px-4">Anonimitas</th>
                  <th class="py-3 px-4">Latency</th>
                  <th class="py-3 px-4">Region</th>
                  <th class="py-3 px-4">ISP / Host Organization</th>
                  <th class="py-3 px-4 text-center">Aksi</th>
                </tr>
              </thead>
              <tbody id="proxy-table-rows" class="divide-y divide-white/[0.03] text-slate-300">
                <tr><td colspan="8" class="py-12 text-center text-[#8b8f9a]">Memuat data amunisi proxy...</td></tr>
              </tbody>
            </table>
          </div>

          <!-- Pagination Footer -->
          <div class="flex flex-col sm:flex-row items-center justify-between gap-4 pt-2 text-xs">
            <div class="flex items-center gap-3 text-[#8b8f9a]">
              <span id="pagination-info">Menampilkan 0 - 0 dari 0 proxy</span>
              <span class="text-white/20">|</span>
              <div class="flex items-center gap-1.5">
                <span>Per Halaman:</span>
                <select id="items-per-page" onchange="changePageSize()" class="bg-[#111216] border border-white/[0.08] text-white rounded-lg px-2 py-1 outline-none font-mono">
                  <option value="10">10</option>
                  <option value="25" selected>25</option>
                  <option value="50">50</option>
                  <option value="100">100</option>
                  <option value="all">Semua</option>
                </select>
              </div>
            </div>

            <div class="flex items-center gap-1" id="pagination-buttons">
              <!-- Dynamically populated -->
            </div>
          </div>

        </div>
      </div>

      <!-- View Section: Identity Leak Test Radar -->
      <div id="view-radar" class="space-y-4 hidden flex-1 flex flex-col overflow-y-auto custom-scroll pr-1">
        <div class="app-card rounded-3xl p-6 flex-1 flex flex-col space-y-6">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-white/[0.06]">
            <div>
              <h3 class="text-base font-bold text-white flex items-center gap-2">
                <svg class="w-5 h-5 text-[#d4ff32]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z"/></svg>
                <span>Identity Leak Radar (Audit Anonimitas Live)</span>
              </h3>
              <p class="text-xs text-[#8b8f9a]">Membandingkan identitas asli perangkat dengan identitas terselubung via Local Gateway</p>
            </div>
            <button onclick="runLeakTest()" id="btn-leak-run" class="px-4 py-2 rounded-xl bg-[#2563eb] hover:bg-blue-600 text-white font-bold text-xs transition flex items-center gap-2 shadow-md active:scale-95">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              <span>Jalankan Audit Sekarang</span>
            </button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
            <!-- Direct IP Card -->
            <div class="p-6 rounded-3xl bg-[#111216] border border-rose-500/20 space-y-4">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold uppercase tracking-wider text-rose-400 font-mono">1. DIRECT CONNECTION (IP ASLI)</span>
                <span class="px-2 py-0.5 rounded-full bg-rose-500/10 text-rose-400 text-[10px] font-bold">UNPROTECTED</span>
              </div>
              <div class="space-y-2">
                <div class="text-xs text-[#8b8f9a]">Alamat IP Asli Terdeteksi:</div>
                <div class="text-xl font-bold font-mono text-white" id="leak-direct-ip">Klik 'Jalankan Audit'</div>
              </div>
              <div class="pt-3 border-t border-white/[0.06] space-y-1 text-xs text-[#8b8f9a]">
                <div>ISP: <span class="text-slate-200 font-medium font-mono" id="leak-direct-isp">-</span></div>
                <div>Lokasi: <span class="text-slate-200 font-medium font-mono" id="leak-direct-loc">-</span></div>
              </div>
            </div>

            <!-- Masked Gateway IP Card -->
            <div class="p-6 rounded-3xl bg-[#111216] border border-emerald-500/20 space-y-4">
              <div class="flex items-center justify-between">
                <span class="text-xs font-bold uppercase tracking-wider text-emerald-400 font-mono">2. GATEWAY 127.0.0.1:8888 (TOPENG NINJA)</span>
                <span class="px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 text-[10px] font-bold">100% PROTECTED</span>
              </div>
              <div class="space-y-2">
                <div class="text-xs text-[#8b8f9a]">Alamat IP Masking yang Dilihat Target:</div>
                <div class="text-xl font-bold font-mono text-[#d4ff32]" id="leak-gw-ip">Menunggu Uji...</div>
              </div>
              <div class="pt-3 border-t border-white/[0.06] space-y-1 text-xs text-[#8b8f9a]">
                <div>ISP Upstream: <span class="text-slate-200 font-medium font-mono" id="leak-gw-isp">-</span></div>
                <div>Lokasi Node: <span class="text-slate-200 font-medium font-mono" id="leak-gw-loc">-</span></div>
              </div>
            </div>
          </div>

          <div id="leak-verdict-card" class="p-5 rounded-2xl bg-[#161820] border border-white/[0.06] flex items-center justify-between">
            <div class="flex items-center gap-3">
              <div class="w-10 h-10 rounded-full bg-white/10 flex items-center justify-center text-[#d4ff32]">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
              </div>
              <div>
                <div class="text-xs font-bold text-white" id="leak-verdict-title">Status Proteksi Belum Diuji</div>
                <div class="text-[11px] text-[#8b8f9a]" id="leak-verdict-desc">Tekan tombol di atas untuk menguji apakah identitas aslimu tertutup sempurna tanpa DNS leak.</div>
              </div>
            </div>
            <div class="font-mono text-sm font-bold text-[#d4ff32]" id="leak-score">-</div>
          </div>
        </div>
      </div>

      <!-- View Section: Scraping & Bot Live Playground -->
      <div id="view-snippets" class="space-y-5 hidden flex-1 flex flex-col custom-scroll overflow-y-auto pr-1">
        
        <div class="app-card rounded-3xl p-6 space-y-5 border border-[#d4ff32]/20 shadow-xl shadow-black/40">
          <div class="flex flex-col lg:flex-row lg:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-bold text-white flex items-center gap-2">
                <svg class="w-5 h-5 text-[#d4ff32]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                <span>Scraping & Bot Live Playground</span>
              </h3>
              <p class="text-xs text-[#8b8f9a]">6 Target scraping berguna siap tembak via gateway 127.0.0.1:8888 dengan anti-bot header simulasi</p>
            </div>

            <!-- 6 High-Value Useful Scraping Presets -->
            <div class="flex flex-wrap items-center gap-1.5 text-xs">
              <span class="text-[#8b8f9a] font-medium">Target Berguna:</span>
              <button onclick="setUsefulPreset('ecommerce')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Harga & Produk Tokopedia/Shopee Mock">🛒 E-Commerce</button>
              <button onclick="setUsefulPreset('crypto')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Live Harga Bitcoin, ETH, SOL">📈 Crypto Market</button>
              <button onclick="setUsefulPreset('jobs')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Lowongan Remote Developer USD">💼 Remote Jobs</button>
              <button onclick="setUsefulPreset('hackernews')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Trending AI News & HackerNews">📰 AI Trends</button>
              <button onclick="setUsefulPreset('finance')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Saham Nvidia / Apple Realtime">📊 Yahoo Finance</button>
              <button onclick="setUsefulPreset('geo')" class="px-2.5 py-1 rounded-lg bg-white/5 hover:bg-[#d4ff32] hover:text-black text-slate-300 font-mono text-[11px] transition" title="Scrape Fraud Risk & Geolocation ISP">🛡️ IP Intel</button>
            </div>
          </div>

          <!-- Interactive Request Form -->
          <div class="space-y-3">
            <div class="grid grid-cols-1 md:grid-cols-12 gap-3">
              <div class="md:col-span-2">
                <select id="live-test-method" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white rounded-xl px-3 py-2.5 outline-none transition font-mono font-bold">
                  <option value="GET">GET</option>
                  <option value="POST">POST</option>
                </select>
              </div>

              <div class="md:col-span-6 relative">
                <input type="text" id="live-test-url" value="https://dummyjson.com/products/search?q=phone" placeholder="https://dummyjson.com/products/search?q=phone" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white placeholder-[#8b8f9a] rounded-xl pl-3 pr-3 py-2.5 outline-none transition font-mono">
              </div>
              
              <div class="md:col-span-4">
                <input type="text" id="live-test-session" placeholder="Session ID (Misal: scraper_worker_01)" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-white placeholder-[#8b8f9a] rounded-xl px-3 py-2.5 outline-none transition font-mono">
              </div>
            </div>

            <div class="grid grid-cols-1 md:grid-cols-12 gap-3">
              <div class="md:col-span-8 flex flex-col sm:flex-row items-start sm:items-center gap-2">
                <span class="text-xs text-[#8b8f9a] whitespace-nowrap">Anti-Bot User-Agent:</span>
                <select id="live-test-ua" class="w-full bg-[#111216] border border-white/[0.08] focus:border-[#d4ff32] text-xs text-slate-300 rounded-xl px-3 py-2 outline-none font-mono">
                  <option value="chrome-win">Chrome 125 (Windows 11) - Highest Trust</option>
                  <option value="chrome-mac">Chrome 125 (macOS Sonoma) - Clean Headers</option>
                  <option value="safari-ios">Mobile Safari (iPhone 15 Pro) - Anti-Cloudflare</option>
                  <option value="edge-win">Microsoft Edge (Windows 10) - Corporate Profile</option>
                </select>
              </div>

              <div class="md:col-span-4">
                <button onclick="executeLiveTest()" id="btn-live-test" class="w-full py-2.5 px-4 rounded-xl lime-btn text-xs font-bold transition flex items-center justify-center gap-2 shadow-lg shadow-[#d4ff32]/10 active:scale-95">
                  <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
                  <span>Jalankan Request</span>
                </button>
              </div>
            </div>
          </div>

          <!-- Response Output Viewer -->
          <div id="live-test-output-box" class="p-4 rounded-2xl bg-[#0c0d11] border border-white/[0.05] space-y-2.5">
            <div class="flex items-center justify-between text-xs">
              <div class="flex items-center gap-2">
                <span class="font-bold text-slate-300">Hasil Response Live:</span>
                <span id="live-test-status" class="px-2 py-0.5 rounded-full bg-white/10 text-slate-400 font-mono text-[10px] font-bold">READY</span>
              </div>
              <div class="flex items-center gap-3 text-[#8b8f9a] font-mono text-[11px]">
                <span>Latency: <strong id="live-test-latency" class="text-white">-</strong></span>
                <span>Routed IP: <strong id="live-test-ip" class="text-[#d4ff32]">-</strong></span>
              </div>
            </div>
            <pre id="live-test-json" class="text-[11px] text-emerald-300 font-mono overflow-x-auto p-3 bg-black/40 rounded-xl max-h-52 custom-scroll">// Klik tombol 'Jalankan Request' di atas untuk melihat respon langsung dari target scraping</pre>
          </div>
        </div>

        <!-- Integration Snippets Grid -->
        <div class="app-card rounded-3xl p-6 space-y-4">
          <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h3 class="text-base font-bold text-white">Kode Snippet Integrasi Siap Salin</h3>
              <p class="text-xs text-[#8b8f9a]">Salin konfigurasi ini langsung ke bot scraper, framework Python, cURL, atau browser Anda</p>
            </div>
            <button onclick="generateWarpProfile()" id="btn-warp-gen" class="px-3.5 py-1.5 rounded-xl bg-[#1e212b] hover:bg-slate-700 text-xs font-bold text-[#d4ff32] transition border border-[#d4ff32]/30 flex items-center gap-1.5">
              <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
              <span>+ Generate WARP WireGuard</span>
            </button>
          </div>

          <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
            <!-- Python Requests -->
            <div class="p-4 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-2">
              <div class="flex items-center justify-between text-xs text-[#8b8f9a] font-semibold">
                <span class="text-white">Python Requests (Rotasi + Sticky)</span>
                <div class="flex items-center gap-2">
                  <button onclick="executeLiveTest()" class="text-xs px-2.5 py-0.5 rounded bg-white/10 hover:bg-[#d4ff32] hover:text-black font-bold text-slate-200 transition">▶ Test Live</button>
                  <button onclick="copySnippet('code-py')" class="text-[#d4ff32] hover:underline cursor-pointer">Copy</button>
                </div>
              </div>
              <pre id="code-py" class="text-[11px] text-emerald-300 font-mono overflow-x-auto p-2.5 bg-black/40 rounded-xl">import requests

# Mode Rotasi Bebas (Tiap Request Ganti IP):
proxies = {"http": "http://127.0.0.1:8888", "https": "http://127.0.0.1:8888"}
r = requests.get("https://dummyjson.com/products/search?q=phone", proxies=proxies)
print("Data Produk:", r.json()["products"][0]["title"])

# Mode Sticky Session (Nahan 1 IP selama 10 Menit):
headers = {"X-Session-ID": "scraper_session_01"}
r2 = requests.get("https://example.com", proxies=proxies, headers=headers)</pre>
            </div>

            <!-- Python HTTPX Async -->
            <div class="p-4 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-2">
              <div class="flex items-center justify-between text-xs text-[#8b8f9a] font-semibold">
                <span class="text-white">Python HTTPX (Asinkron)</span>
                <div class="flex items-center gap-2">
                  <button onclick="executeLiveTest()" class="text-xs px-2.5 py-0.5 rounded bg-white/10 hover:bg-[#d4ff32] hover:text-black font-bold text-slate-200 transition">▶ Test Live</button>
                  <button onclick="copySnippet('code-httpx')" class="text-[#d4ff32] hover:underline cursor-pointer">Copy</button>
                </div>
              </div>
              <pre id="code-httpx" class="text-[11px] text-cyan-300 font-mono overflow-x-auto p-2.5 bg-black/40 rounded-xl">import httpx
import asyncio

async def fetch():
    async with httpx.AsyncClient(proxy="http://127.0.0.1:8888") as client:
        res = await client.get("https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd")
        print("Bitcoin USD:", res.json())

asyncio.run(fetch())</pre>
            </div>

            <!-- cURL CLI -->
            <div class="p-4 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-2">
              <div class="flex items-center justify-between text-xs text-[#8b8f9a] font-semibold">
                <span class="text-white">cURL Command Line</span>
                <div class="flex items-center gap-2">
                  <button onclick="executeLiveTest()" class="text-xs px-2.5 py-0.5 rounded bg-white/10 hover:bg-[#d4ff32] hover:text-black font-bold text-slate-200 transition">▶ Test Live</button>
                  <button onclick="copySnippet('code-curl')" class="text-[#d4ff32] hover:underline cursor-pointer">Copy</button>
                </div>
              </div>
              <pre id="code-curl" class="text-[11px] text-amber-300 font-mono overflow-x-auto p-2.5 bg-black/40 rounded-xl"># Uji rotasi request scraping:
curl -x http://127.0.0.1:8888 https://remoteok.com/api

# Uji sticky session:
curl -x http://127.0.0.1:8888 -H "X-Session-ID: task_1" https://api.ipify.org</pre>
            </div>

            <!-- Browser & Mobile Auto-PAC -->
            <div class="p-4 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-2">
              <div class="flex items-center justify-between text-xs text-[#8b8f9a] font-semibold">
                <span class="text-white">Browser / iPhone / Android (Auto-PAC)</span>
                <button onclick="copySnippet('code-pac')" class="text-[#d4ff32] hover:underline cursor-pointer">Copy</button>
              </div>
              <pre id="code-pac" class="text-[11px] text-indigo-300 font-mono overflow-x-auto p-2.5 bg-black/40 rounded-xl"># Di Pengaturan Wi-Fi HP / Proxy Browser:
Pilih: Auto Proxy Configuration (PAC)
URL:   http://127.0.0.1:8888/proxy.pac

# Otomatis route semua traffic browser lewat proxy rotasi!</pre>
            </div>
          </div>
        </div>
      </div>

    </main>
  </div>

  <!-- Mesin Ternak Akun Grok xAI Modal -->
  <div id="grok-modal" class="fixed inset-0 modal-backdrop hidden z-50 flex items-center justify-center p-4">
    <div class="w-full max-w-lg bg-[#161820] border border-purple-500/40 rounded-3xl p-6 space-y-5 shadow-2xl max-h-[90vh] overflow-y-auto custom-scroll">
      <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-xl bg-purple-600/20 border border-purple-500/30 flex items-center justify-center text-purple-300">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M9.75 17L9 20l-1 1h8l-1-1-.75-3M3 13h18M5 17h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z"/></svg>
          </div>
          <div>
            <h4 class="text-base font-bold text-white">Mesin Ternak Akun Grok xAI</h4>
            <p class="text-[11px] text-[#8b8f9a]">Auto-Breeder Akun Grok xAI dengan Mail.tm OTP Polling</p>
          </div>
        </div>
        <button onclick="closeGrokModal()" class="text-[#8b8f9a] hover:text-white p-1 rounded-lg">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>

      <div class="space-y-4 text-xs">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[#8b8f9a] mb-1 font-medium">Target Jumlah Akun:</label>
            <input type="number" id="grok-target-count" value="1" min="1" max="20" class="w-full bg-[#111216] border border-white/[0.08] focus:border-purple-400 text-white rounded-xl px-3 py-2 font-mono font-bold outline-none">
          </div>

          <div>
            <label class="block text-[#8b8f9a] mb-1 font-medium">Mode Browser:</label>
            <select id="grok-headless" class="w-full bg-[#111216] border border-white/[0.08] focus:border-purple-400 text-white rounded-xl px-3 py-2 font-mono outline-none">
              <option value="true">Background (Headless)</option>
              <option value="false">Jendela Tampak (Visible)</option>
            </select>
          </div>
        </div>

        <div class="p-3.5 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-1.5">
          <div class="text-[11px] font-bold text-purple-300">Alur Kerja Ternak Otomatis:</div>
          <div class="text-[11px] text-slate-300">1. Generate mailbox via Mail.tm API dengan DNS MX terverifikasi.</div>
          <div class="text-[11px] text-slate-300">2. Submit form registrasi xAI dengan proxy rotasi PetaniProxy.</div>
          <div class="text-[11px] text-slate-300">3. Polling OTP 6 digit dan auto-submit.</div>
          <div class="text-[11px] text-slate-300">4. Ekstrak SSO Cookie & simpan ke <code>output/grok_accounts.txt</code>.</div>
        </div>

        <!-- Progress Box -->
        <div id="grok-progress-box" class="hidden p-3.5 rounded-2xl bg-black/60 border border-purple-500/30 space-y-2.5">
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-purple-300 font-bold flex items-center gap-1.5" id="grok-status-text">
              <span class="w-2 h-2 rounded-full bg-purple-400 animate-ping"></span>
              <span>Menyiapkan Browser...</span>
            </span>
            <span class="text-purple-400 font-mono font-bold" id="grok-progress-pct">0%</span>
          </div>
          <div class="w-full h-2 rounded-full bg-[#262933] overflow-hidden">
            <div id="grok-progress-bar" class="h-full bg-purple-500 rounded-full transition-all duration-300" style="width: 0%"></div>
          </div>
          <!-- Live Terminal Window -->
          <div class="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
            <span class="font-bold text-slate-300">Live Terminal Logs:</span>
            <span id="grok-step-badge" class="px-2 py-0.5 rounded bg-purple-950/80 text-purple-300 font-mono text-[9px] border border-purple-800/50 uppercase">STARTING</span>
          </div>
          <div id="grok-terminal-logs" class="bg-[#0b0c0f] border border-white/[0.08] rounded-xl p-2.5 font-mono text-[10px] h-36 overflow-y-auto custom-scroll text-slate-300 flex flex-col gap-1 select-text">
            <div class="text-slate-500">// Menunggu log sinkronisasi dari terminal...</div>
          </div>
        </div>

        <button onclick="startGrokJob()" id="btn-start-grok" class="w-full py-2.5 px-4 rounded-xl bg-purple-600 hover:bg-purple-500 text-white font-bold text-xs transition flex items-center justify-center gap-2 shadow-lg shadow-purple-600/30 active:scale-95">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          <span>Mulai Ternak Akun Grok Sekarang</span>
        </button>
      </div>
    </div>
  </div>

  <!-- Mesin Panen Webshare Residential Modal -->
  <div id="hunter-modal" class="fixed inset-0 modal-backdrop hidden z-50 flex items-center justify-center p-4">
    <div class="w-full max-w-lg bg-[#161820] border border-emerald-500/30 rounded-3xl p-6 space-y-5 shadow-2xl max-h-[90vh] overflow-y-auto custom-scroll">
      <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
        <div class="flex items-center gap-2.5">
          <div class="w-9 h-9 rounded-xl bg-emerald-600/20 border border-emerald-500/30 flex items-center justify-center text-emerald-300">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10"/></svg>
          </div>
          <div>
            <h4 class="text-base font-bold text-white">Mesin Panen Residential Webshare</h4>
            <p class="text-[11px] text-[#8b8f9a]">Auto-Hunter Webshare dengan Live MX Email Resolver</p>
          </div>
        </div>
        <button onclick="closeHunterModal()" class="text-[#8b8f9a] hover:text-white p-1 rounded-lg">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
      </div>

      <div class="space-y-4 text-xs">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block text-[#8b8f9a] mb-1 font-medium">Target Akun Webshare:</label>
            <input type="number" id="hunter-target-count" value="1" min="1" max="20" class="w-full bg-[#111216] border border-white/[0.08] focus:border-emerald-400 text-white rounded-xl px-3 py-2 font-mono font-bold outline-none">
            <span class="text-[10px] text-[#8b8f9a] mt-0.5 block">1 Akun = 10 Residential IP Gratis</span>
          </div>

          <div>
            <label class="block text-[#8b8f9a] mb-1 font-medium">Mode Browser:</label>
            <select id="hunter-headless" class="w-full bg-[#111216] border border-white/[0.08] focus:border-emerald-400 text-white rounded-xl px-3 py-2 font-mono outline-none">
              <option value="true">Background (Headless)</option>
              <option value="false">Jendela Tampak (Visible)</option>
            </select>
          </div>
        </div>

        <!-- Custom Catch-All Domain Option -->
        <div>
          <label class="block text-[#8b8f9a] mb-1 font-medium">Domain Email Resolver (Opsional):</label>
          <input type="text" id="hunter-custom-domain" placeholder="Kosongkan untuk Auto-Fetch Live MX (Mail.tm)" class="w-full bg-[#111216] border border-white/[0.08] focus:border-emerald-400 text-white rounded-xl px-3 py-2 font-mono outline-none">
          <span class="text-[10px] text-[#8b8f9a] mt-0.5 block">Webshare menolak domain dummy tanpa DNS MX. Gunakan domain aktif atau catch-all pribadi.</span>
        </div>

        <!-- Sync Targets Info -->
        <div class="p-3.5 rounded-2xl bg-[#111216] border border-white/[0.05] space-y-1.5">
          <div class="text-[11px] font-bold text-emerald-300">Otomatis Terintegrasi ke:</div>
          <div class="text-[11px] text-slate-300 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
            <span><code>output/webshare_residential.txt</code> & PetaniProxy Memory Pool</span>
          </div>
          <div class="text-[11px] text-slate-300 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
            <span><code>grok-register/proxies.txt</code> (Feed Mesin Ternak Grok)</span>
          </div>
          <div class="text-[11px] text-slate-300 flex items-center gap-1.5">
            <svg class="w-3.5 h-3.5 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg>
            <span>BansosRouter SQLite Database</span>
          </div>
        </div>

        <!-- Progress Box -->
        <div id="hunter-progress-box" class="hidden p-3.5 rounded-2xl bg-black/60 border border-emerald-500/30 space-y-2.5">
          <div class="flex items-center justify-between text-[11px]">
            <span class="text-emerald-300 font-bold flex items-center gap-1.5" id="hunter-status-text">
              <span class="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
              <span>Menyiapkan Browser...</span>
            </span>
            <span class="text-emerald-400 font-mono font-bold" id="hunter-progress-pct">0%</span>
          </div>
          <div class="w-full h-2 rounded-full bg-[#262933] overflow-hidden">
            <div id="hunter-progress-bar" class="h-full bg-emerald-500 rounded-full transition-all duration-300" style="width: 0%"></div>
          </div>
          <!-- Live Terminal Window -->
          <div class="mt-2 text-[10px] text-slate-400 flex items-center justify-between">
            <span class="font-bold text-slate-300">Live Terminal Logs:</span>
            <span id="hunter-step-badge" class="px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-300 font-mono text-[9px] border border-emerald-800/50 uppercase">HARVESTING</span>
          </div>
          <div id="hunter-terminal-logs" class="bg-[#0b0c0f] border border-white/[0.08] rounded-xl p-2.5 font-mono text-[10px] h-36 overflow-y-auto custom-scroll text-slate-300 flex flex-col gap-1 select-text">
            <div class="text-slate-500">// Menunggu log panen...</div>
          </div>
        </div>

        <button onclick="startHunterJob()" id="btn-start-hunter" class="w-full py-2.5 px-4 rounded-xl bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs transition flex items-center justify-center gap-2 shadow-lg shadow-emerald-600/30 active:scale-95">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          <span>Mulai Panen Sekarang</span>
        </button>
      </div>
    </div>
  </div>

  <!-- Keyboard Shortcuts & Pusat Bantuan Modal -->
  <div id="shortcuts-modal" class="fixed inset-0 modal-backdrop hidden z-50 flex items-center justify-center p-4">
    <div class="w-full max-w-lg bg-[#161820] border border-white/[0.1] rounded-3xl p-6 space-y-5 shadow-2xl max-h-[85vh] overflow-y-auto custom-scroll">
      <div class="flex items-center justify-between pb-3 border-b border-white/[0.06]">
        <h4 class="text-base font-bold text-white flex items-center gap-2">
          <svg class="w-5 h-5 text-[#d4ff32]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4"/></svg>
          <span>Pusat Bantuan & Kamus Petani</span>
        </h4>
        <button onclick="closeShortcutsModal()" class="text-[#8b8f9a] hover:text-white text-xs font-bold font-mono px-2 py-1 rounded bg-white/5">Esc</button>
      </div>

      <div class="space-y-3 text-xs">
        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Kamus Singkat Petani</div>
        
        <div class="p-3 rounded-2xl bg-[#111216] space-y-1">
          <div class="text-[#d4ff32] font-bold">Topeng Ninja (Stealth Sanitizer)</div>
          <div class="text-slate-300 text-[11px]">Membuang semua header cepu (<code>X-Forwarded-For</code>, <code>Via</code>, <code>CF-Connecting-IP</code>) dan menyamarkan bot menjadi Chrome asli. Biar target website mikir kamu orang kantoran biasa.</div>
        </div>

        <div class="p-3 rounded-2xl bg-[#111216] space-y-1">
          <div class="text-purple-400 font-bold">Ternak Akun Grok xAI</div>
          <div class="text-slate-300 text-[11px]">Modul mandiri internal PetaniProxy untuk memproduksi akun Grok xAI lengkap dengan SSO tokens dan cookies.</div>
        </div>

        <div class="p-3 rounded-2xl bg-[#111216] space-y-1">
          <div class="text-emerald-400 font-bold">Live MX Email Resolver (Webshare Hunter)</div>
          <div class="text-slate-300 text-[11px]">Webshare menolak domain asal-asalan. PetaniProxy otomatis mengambil domain aktif yang memiliki record DNS MX valid dari Mail.tm.</div>
        </div>

        <div class="p-3 rounded-2xl bg-[#111216] space-y-1">
          <div class="text-blue-400 font-bold">Auto-PAC Browser Proxy</div>
          <div class="text-slate-300 text-[11px]">Alamat script proxy otomatis (<code>/proxy.pac</code>) untuk ditempel di pengaturan Wi-Fi HP atau browser tanpa butuh aplikasi VPN tambahan.</div>
        </div>
      </div>

      <div class="space-y-2 text-xs pt-2 border-t border-white/[0.06]">
        <div class="text-[11px] font-bold text-slate-400 uppercase tracking-wider">Pintasan Tombol Keyboard</div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Tab Dashboard Utama</span>
          <span class="kbd-badge text-white">1</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Tab Daftar & Multi-Filter Proxy</span>
          <span class="kbd-badge text-white">2</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Tab Identity Leak Radar</span>
          <span class="kbd-badge text-white">3</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Tab Scraping & Bot Live Playground</span>
          <span class="kbd-badge text-white">4</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Buka Modal Ternak Grok xAI</span>
          <span class="kbd-badge text-purple-400">G</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Buka Modal Panen Webshare</span>
          <span class="kbd-badge text-emerald-400">W</span>
        </div>
        <div class="flex items-center justify-between p-2 rounded-xl bg-[#111216]">
          <span class="text-slate-300">Force Rotate IP Instan</span>
          <span class="kbd-badge text-[#d4ff32]">R</span>
        </div>
      </div>
    </div>
  </div>

  <!-- Toast Notification Container -->
  <div id="toast-container" class="fixed top-5 right-5 z-50 flex flex-col gap-2 pointer-events-none"></div>

  <script>
    let allProxies = [];
    let currentCardFilter = 'all';
    let currentPage = 1;
    let pageSize = 25;
    let filteredTableProxies = [];
    let hunterPollTimer = null;
    let grokPollTimer = null;

    // Switch View Tabs
    function switchTab(tab) {
      ['dashboard', 'table', 'radar', 'snippets'].forEach(function(t) {
        var viewEl = document.getElementById('view-' + t);
        if (viewEl) viewEl.classList.add('hidden');
        var navBtn = document.getElementById('nav-' + (t === 'dashboard' ? 'dash' : t));
        if (navBtn) {
          navBtn.className = 'w-10 h-10 rounded-full bg-slate-800/60 hover:bg-slate-700/80 text-slate-400 hover:text-white flex items-center justify-center transition';
        }
      });

      var activeView = document.getElementById('view-' + tab);
      if (activeView) activeView.classList.remove('hidden');

      var activeNav = document.getElementById('nav-' + (tab === 'dashboard' ? 'dash' : tab));
      if (activeNav) {
        activeNav.className = 'w-10 h-10 rounded-full lime-btn flex items-center justify-center shadow-md transition';
      }

      if (tab === 'table') {
        onFilterChange();
      }
    }

    // Preset Profiles
    function applyPreset(preset) {
      ['barbar', 'grok', 'stealth'].forEach(function(p) {
        var btn = document.getElementById('preset-' + p);
        if (btn) btn.className = 'px-3 py-1 rounded-full bg-[#1b1e27] hover:bg-white/10 text-slate-300 font-semibold transition border border-white/[0.05] flex items-center gap-1.5';
      });

      var activeBtn = document.getElementById('preset-' + preset);
      if (activeBtn) {
        activeBtn.className = 'px-3 py-1 rounded-full bg-white/20 text-white font-bold transition border border-[#d4ff32] flex items-center gap-1.5';
      }

      if (preset === 'barbar') {
        showToast('Mode Scraper Barbar Aktif', 'Rotasi IP tiap request, delay minimal siap gasak!', 'info');
        switchTab('snippets');
        document.getElementById('live-test-session').value = '';
      } else if (preset === 'grok') {
        showToast('Mode Ternak Grok Aktif', 'Sticky session 10m siap dipakai untuk registrasi Grok!', 'info');
        openGrokModal();
      } else if (preset === 'stealth') {
        showToast('Mode Stealth Aktif', 'Header sanitizer 100% ketat, zero DNS leak terpasang!', 'info');
        switchTab('radar');
      }
    }

    // Card Filters
    function setCardFilter(filter) {
      currentCardFilter = filter;
      ['all', 'http', 'socks5', 'elite'].forEach(function(f) {
        var btn = document.getElementById('pill-' + f);
        if (btn) {
          btn.className = (f === filter) ? 'px-3 py-1 rounded-full lime-btn text-xs transition' : 'px-3 py-1 rounded-full text-[#8b8f9a] hover:text-white transition';
        }
      });
      renderCards();
    }

    function renderCards() {
      var grid = document.getElementById('proxy-cards-grid');
      var filtered = allProxies;
      if (currentCardFilter === 'http') filtered = allProxies.filter(function(p) { return (p.protocol || '').toLowerCase() === 'http'; });
      if (currentCardFilter === 'socks5') filtered = allProxies.filter(function(p) { return (p.protocol || '').toLowerCase() === 'socks5'; });
      if (currentCardFilter === 'elite') filtered = allProxies.filter(function(p) { return (p.anonymity || '').toLowerCase() === 'elite'; });

      if (filtered.length === 0) {
        grid.innerHTML = '<div class="col-span-3 py-6 text-center text-xs text-[#8b8f9a]">Tidak ada proxy yang sesuai filter.</div>';
        return;
      }

      var cardsHtml = filtered.slice(0, 5).map(function(p, i) {
        var isFirst = (i === 0);
        var cardBg = isFirst ? 'bg-[#2563eb] text-white shadow-blue-600/20' : 'bg-[#1a1c24] text-slate-200';
        var subColor = isFirst ? 'text-blue-100' : 'text-[#8b8f9a]';
        var badgeColor = isFirst ? 'bg-white/20 text-white' : 'bg-black/30 text-[#d4ff32]';
        var lat = p.latency_ms || 0;
        var proxyStr = p.proxy || (p.ip + ':' + p.port);

        return '<div class="' + cardBg + ' rounded-2xl p-4 flex flex-col justify-between space-y-3 cursor-pointer hover:scale-[1.02] transition shadow-md group" onclick="copyText(\'' + proxyStr + '\')" title="Klik untuk copy">' +
          '<div class="flex items-center justify-between">' +
            '<span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded-full ' + badgeColor + ' font-mono">' + (p.protocol || 'HTTP').toUpperCase() + '</span>' +
            '<span class="text-xs opacity-70 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 transition">↗</span>' +
          '</div>' +
          '<div>' +
            '<div class="text-xs font-bold font-mono truncate">' + proxyStr + '</div>' +
            '<div class="text-[11px] ' + subColor + ' flex items-center gap-1.5 mt-0.5">' +
              '<span>[' + (p.country_code || '??') + '] ' + (p.country || 'Unknown') + '</span>' +
              '<span>•</span>' +
              '<span class="font-bold font-mono">' + lat + 'ms</span>' +
            '</div>' +
          '</div>' +
        '</div>';
      }).join('');

      cardsHtml += '<div onclick="switchTab(\'table\')" class="rounded-2xl p-4 border-2 border-dashed border-[#262933] hover:border-[#d4ff32] flex flex-col items-center justify-center text-center text-xs text-[#8b8f9a] hover:text-white transition cursor-pointer space-y-1">' +
        '<span class="text-lg font-bold text-[#d4ff32]">+</span>' +
        '<span>Lihat Semua (' + allProxies.length + ')</span>' +
      '</div>';

      grid.innerHTML = cardsHtml;
    }

    // Refresh Data from APIs
    async function refreshData() {
      try {
        var results = await Promise.all([
          fetch('/api/status').then(function(r) { return r.json(); }),
          fetch('/api/all').then(function(r) { return r.json(); })
        ]);
        var resStatus = results[0];
        var resAll = results[1];

        var stats = resStatus.stats || {};
        document.getElementById('stat-pool').innerText = stats.pool_size || 0;
        document.getElementById('stat-req').innerText = stats.total_routed_requests || 0;
        document.getElementById('stat-success').innerText = (stats.success_rate_percent || 100) + '%';
        document.getElementById('stat-sess').innerText = (stats.active_sticky_sessions || 0) + ' Active';

        allProxies = resAll.proxies || [];
        document.getElementById('proxy-count-hint').innerText = 'Tersedia ' + allProxies.length + ' amunisi proxy aktif siap tempur';
        document.getElementById('table-total-badge').innerText = allProxies.length + ' Live';

        if (allProxies.length > 0) {
          var avg = Math.round(allProxies.reduce(function(a, b) { return a + (b.latency_ms || 0); }, 0) / allProxies.length);
          document.getElementById('stat-ping').innerText = avg + 'ms';

          var countries = Array.from(new Set(allProxies.map(function(p) { return (p.country_code || '').toUpperCase(); }).filter(Boolean)));
          document.getElementById('stat-cc-count').innerText = countries.length + ' Countries';

          var ccGrid = document.getElementById('cc-matrix-grid');
          if (countries.length > 0) {
            var pills = countries.slice(0, 7).map(function(c) {
              return '<div class="p-2 rounded-xl bg-white/10 font-bold cursor-pointer hover:bg-white/20 transition" onclick="filterByCountry(\'' + c + '\')">' + c + '</div>';
            }).join('');
            pills += '<div class="p-2 rounded-xl bg-[#d4ff32] text-black font-extrabold shadow-lg cursor-pointer" onclick="forceRotate()">ROT</div>';
            ccGrid.innerHTML = pills;
          }

          var cSelect = document.getElementById('filter-country');
          var currentVal = cSelect.value;
          cSelect.innerHTML = '<option value="all">Country: All</option>' + countries.map(function(c) {
            return '<option value="' + c + '" ' + (c === currentVal ? 'selected' : '') + '>' + c + '</option>';
          }).join('');
        } else {
          document.getElementById('stat-ping').innerText = '0ms';
        }

        renderCards();
        onFilterChange();

      } catch (err) {
        console.error('Gagal memuat status gateway:', err);
      }
    }

    // Force Rotate API
    async function forceRotate() {
      try {
        var res = await fetch('/api/rotate').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          showToast('IP Berhasil Dirotasi', res.active_proxy + ' (' + res.country + ') • ' + res.latency_ms + 'ms', 'success');
          refreshData();
        } else {
          showToast('Gagal Rotasi', res.message || 'Pool proxy kosong', 'error');
        }
      } catch (e) {
        showToast('Kesalahan Jaringan', e.message, 'error');
      }
    }

    // Trigger Pool Refill API with Debounce Guard
    var isRefilling = false;
    async function triggerRefill() {
      if (isRefilling) return;
      isRefilling = true;
      var btn = document.getElementById('btn-refill-trigger');
      var originalHtml = btn ? btn.innerHTML : '';
      if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<svg class="animate-spin w-3 h-3 text-[#d4ff32] inline" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Refilling...</span>';
      }
      try {
        showToast('Memulai Refill', 'Menyaring amunisi proxy baru di background...', 'info');
        var res = await fetch('/api/refill').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          showToast('Refill Aktif', res.message || 'Auto-harvester proxy sedang bekerja', 'success');
          setTimeout(refreshData, 2500);
          setTimeout(refreshData, 6000);
        } else {
          showToast('Refill Gagal', res.message || 'Gagal memulai refill', 'error');
        }
      } catch (e) {
        showToast('Gagal Refill', e.message, 'error');
      } finally {
        setTimeout(function() {
          isRefilling = false;
          if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalHtml;
          }
        }, 3000);
      }
    }

    // Useful Scraping Presets
    function setUsefulPreset(type) {
      if (type === 'ecommerce') {
        document.getElementById('live-test-url').value = 'https://dummyjson.com/products/search?q=phone';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'E-Commerce Price & Product Info Scraper', 'info');
      } else if (type === 'crypto') {
        document.getElementById('live-test-url').value = 'https://api.coingecko.com/api/v3/simple/price?ids=bitcoin,ethereum,solana&vs_currencies=usd,idr&include_24hr_change=true';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'Crypto Live Market Scraper (BTC/ETH/SOL)', 'info');
      } else if (type === 'jobs') {
        document.getElementById('live-test-url').value = 'https://remoteok.com/api';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'Remote Developer Jobs & Salary Scraper', 'info');
      } else if (type === 'hackernews') {
        document.getElementById('live-test-url').value = 'https://hacker-news.firebaseio.com/v0/topstories.json?print=pretty';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'HackerNews AI News & Tech Trends Scraper', 'info');
      } else if (type === 'finance') {
        document.getElementById('live-test-url').value = 'https://query1.finance.yahoo.com/v8/finance/chart/NVDA';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'Yahoo Finance Stock Ticker Scraper', 'info');
      } else if (type === 'geo') {
        document.getElementById('live-test-url').value = 'https://ipwho.is/';
        document.getElementById('live-test-method').value = 'GET';
        showToast('Preset Dipilih', 'IP Geolocation & ISP Fraud Scraper', 'info');
      }
    }

    async function executeLiveTest() {
      var url = document.getElementById('live-test-url').value.trim() || 'https://dummyjson.com/products/search?q=phone';
      var sess = document.getElementById('live-test-session').value.trim();
      var method = document.getElementById('live-test-method').value;
      var ua = document.getElementById('live-test-ua').value;

      var btn = document.getElementById('btn-live-test');
      var statusEl = document.getElementById('live-test-status');
      var latEl = document.getElementById('live-test-latency');
      var ipEl = document.getElementById('live-test-ip');
      var jsonEl = document.getElementById('live-test-json');

      btn.disabled = true;
      btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-black" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Testing...</span>';
      statusEl.className = 'px-2 py-0.5 rounded-full bg-amber-500/20 text-amber-300 font-mono text-[10px] font-bold';
      statusEl.innerText = 'FETCHING VIA 8888';

      var endpoint = '/api/test-proxy?url=' + encodeURIComponent(url) + '&method=' + method + '&ua_preset=' + ua;
      if (sess) endpoint += '&session_id=' + encodeURIComponent(sess);

      try {
        var res = await fetch(endpoint).then(function(r) { return r.json(); });
        if (res.status === 'success') {
          statusEl.className = 'px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-mono text-[10px] font-bold';
          statusEl.innerText = 'STATUS ' + (res.status_code || 200) + ' OK';
          latEl.innerText = res.latency_ms + 'ms';
          ipEl.innerText = res.routed_ip || 'Masked Node';
          jsonEl.innerText = JSON.stringify(res.data, null, 2);
          showToast('Scraping Sukses', 'Berhasil tembus via Gateway (' + res.latency_ms + 'ms)', 'success');
        } else {
          statusEl.className = 'px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 font-mono text-[10px] font-bold';
          statusEl.innerText = 'ERROR ' + (res.status_code || 502);
          latEl.innerText = res.latency_ms + 'ms';
          ipEl.innerText = 'Failed';
          jsonEl.innerText = '// Error: ' + (res.message || 'Gagal tersambung');
          showToast('Scraping Gagal', res.message || 'Error', 'error');
        }
      } catch (err) {
        statusEl.className = 'px-2 py-0.5 rounded-full bg-rose-500/20 text-rose-400 font-mono text-[10px] font-bold';
        statusEl.innerText = 'NETWORK ERROR';
        jsonEl.innerText = '// Network Error: ' + err.message;
        showToast('Network Error', err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> <span>Jalankan Request</span>';
      }
    }

    // 1-Click Generate Cloudflare WARP
    async function generateWarpProfile() {
      var btn = document.getElementById('btn-warp-gen');
      btn.disabled = true;
      btn.innerText = 'Membuat Profil...';
      try {
        showToast('Cloudflare WARP', 'Mendaftarkan profil WireGuard ke Cloudflare REST API...', 'info');
        var res = await fetch('/api/pipeline/warp').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          showToast('WARP Siap', 'Profil WireGuard dibuat: ' + res.profile.v4, 'success');
          alert('Profil Cloudflare WARP WireGuard Berhasil Dibuat!\nIP WireGuard: ' + res.profile.v4 + '\nFile tersimpan di: output/warp/warp.conf');
        } else {
          showToast('Gagal WARP', res.message, 'error');
        }
      } catch (err) {
        showToast('Error', err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M13 10V3L4 14h7v7l9-11h-7z"/></svg> <span>+ Generate WARP WireGuard</span>';
      }
    }

    // Grok Breeder Modal & Job Execution
    function openGrokModal() {
      document.getElementById('grok-modal').classList.remove('hidden');
      checkGrokStatus();
    }

    function closeGrokModal() {
      document.getElementById('grok-modal').classList.add('hidden');
    }

    async function startGrokJob() {
      var count = parseInt(document.getElementById('grok-target-count').value, 10) || 1;
      var headless = document.getElementById('grok-headless').value === 'true';
      var btn = document.getElementById('btn-start-grok');
      var pBox = document.getElementById('grok-progress-box');

      btn.disabled = true;
      btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Menjalankan Ternak Grok...</span>';
      pBox.classList.remove('hidden');

      try {
        var res = await fetch('/api/pipeline/grok-farm?total=' + count + '&headless=' + headless).then(function(r) { return r.json(); });
        if (res.status === 'success') {
          showToast('Ternak Dimulai', 'Bot ternak Grok xAI berjalan di background...', 'info');
          pollGrokStatus();
        } else {
          showToast('Gagal Memulai', res.message, 'error');
          btn.disabled = false;
          btn.innerText = 'Mulai Ternak Akun Grok Sekarang';
        }
      } catch (err) {
        showToast('Error', err.message, 'error');
        btn.disabled = false;
        btn.innerText = 'Mulai Ternak Akun Grok Sekarang';
      }
    }

    function pollGrokStatus() {
      if (grokPollTimer) clearInterval(grokPollTimer);
      grokPollTimer = setInterval(checkGrokStatus, 2000);
    }

    async function checkGrokStatus() {
      try {
        var res = await fetch('/api/pipeline/grok-status').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          var data = res.data;
          var pBox = document.getElementById('grok-progress-box');
          var pBar = document.getElementById('grok-progress-bar');
          var pPct = document.getElementById('grok-progress-pct');
          var sText = document.getElementById('grok-status-text');
          var lPrev = document.getElementById('grok-log-preview');
          var btn = document.getElementById('btn-start-grok');

          if (data.status === 'running') {
            pBox.classList.remove('hidden');
            btn.disabled = true;
            btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Membuat Akun (' + data.current_account + '/' + data.total_accounts + ')...</span>';
            pBar.style.width = data.progress + '%';
            pPct.innerText = data.progress + '%';
            sText.innerText = 'Memproses Akun [' + data.current_account + '/' + data.total_accounts + '] (' + data.harvested_count + ' Akun Siap)';
            if (data.logs && data.logs.length > 0) {
              var logBox = document.getElementById('grok-terminal-logs');
              if (logBox) {
                logBox.innerHTML = data.logs.map(function(l) {
                  var cClass = 'text-slate-300';
                  if (l.indexOf('[+]') !== -1 || l.indexOf('SUKSES') !== -1) cClass = 'text-emerald-400 font-bold';
                  else if (l.indexOf('[!]') !== -1 || l.indexOf('Error') !== -1 || l.indexOf('Gagal') !== -1) cClass = 'text-rose-400';
                  else if (l.indexOf('[*]') !== -1) cClass = 'text-cyan-300';
                  return '<div class="' + cClass + '">' + l + '</div>';
                }).join('');
                logBox.scrollTop = logBox.scrollHeight;
              }
            }
            var sBadge = document.getElementById('grok-step-badge');
            if (sBadge && data.current_step) {
              sBadge.innerText = data.current_step.replace(/_/g, ' ').toUpperCase();
            }
          } else if (data.status === 'completed') {
            if (data.logs && data.logs.length > 0) {
              var logBox = document.getElementById('grok-terminal-logs');
              if (logBox) {
                logBox.innerHTML = data.logs.map(function(l) {
                  var cClass = (l.indexOf('[+]') !== -1 || l.indexOf('SUKSES') !== -1) ? 'text-emerald-400 font-bold' : 'text-slate-300';
                  return '<div class="' + cClass + '">' + l + '</div>';
                }).join('');
                logBox.scrollTop = logBox.scrollHeight;
              }
            }
            if (grokPollTimer) { clearInterval(grokPollTimer); grokPollTimer = null; }
            pBar.style.width = '100%';
            pPct.innerText = '100%';
            sText.innerText = 'Selesai! ' + data.harvested_count + ' Akun Grok xAI berhasil diternak.';
            btn.disabled = false;
            btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg> <span>Ternak Selesai! Mau Ternak Lagi?</span>';
          } else if (data.status === 'error') {
            if (grokPollTimer) { clearInterval(grokPollTimer); grokPollTimer = null; }
            sText.innerText = 'Error: ' + (data.last_error || 'Gagal');
            btn.disabled = false;
            btn.innerText = 'Coba Ternak Lagi';
          }
        }
      } catch (e) {
        console.error('Gagal cek status grok:', e);
      }
    }

    // Webshare Hunter Modal & Job Execution
    function openHunterModal() {
      document.getElementById('hunter-modal').classList.remove('hidden');
      checkHunterStatus();
    }

    function closeHunterModal() {
      document.getElementById('hunter-modal').classList.add('hidden');
    }

    async function startHunterJob() {
      var count = parseInt(document.getElementById('hunter-target-count').value, 10) || 1;
      var headless = document.getElementById('hunter-headless').value === 'true';
      var customDom = document.getElementById('hunter-custom-domain').value.trim();
      var btn = document.getElementById('btn-start-hunter');
      var pBox = document.getElementById('hunter-progress-box');

      btn.disabled = true;
      btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Sedang Memanen...</span>';
      pBox.classList.remove('hidden');

      try {
        var ep = '/api/pipeline/webshare?total=' + count + '&headless=' + headless;
        if (customDom) ep += '&custom_domain=' + encodeURIComponent(customDom);
        var res = await fetch(ep).then(function(r) { return r.json(); });
        if (res.status === 'success') {
          showToast('Panen Dimulai', 'Hunter berjalan di background dengan DNS MX domain valid...', 'info');
          pollHunterStatus();
        } else {
          showToast('Gagal Memulai', res.message, 'error');
          btn.disabled = false;
          btn.innerText = 'Mulai Panen Sekarang';
        }
      } catch (err) {
        showToast('Error', err.message, 'error');
        btn.disabled = false;
        btn.innerText = 'Mulai Panen Sekarang';
      }
    }

    function pollHunterStatus() {
      if (hunterPollTimer) clearInterval(hunterPollTimer);
      hunterPollTimer = setInterval(checkHunterStatus, 2000);
    }

    async function checkHunterStatus() {
      try {
        var res = await fetch('/api/pipeline/webshare-status').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          var data = res.data;
          var pBox = document.getElementById('hunter-progress-box');
          var pBar = document.getElementById('hunter-progress-bar');
          var pPct = document.getElementById('hunter-progress-pct');
          var sText = document.getElementById('hunter-status-text');
          var lPrev = document.getElementById('hunter-log-preview');
          var btn = document.getElementById('btn-start-hunter');

          if (data.status === 'running') {
            pBox.classList.remove('hidden');
            btn.disabled = true;
            btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Memanen Akun (' + data.current_account + '/' + data.total_accounts + ')...</span>';
            pBar.style.width = data.progress + '%';
            pPct.innerText = data.progress + '%';
            sText.innerText = 'Memproses Akun [' + data.current_account + '/' + data.total_accounts + '] (' + data.gathered_count + ' IP didapat)';
            if (data.logs && data.logs.length > 0) {
              var logBox = document.getElementById('hunter-terminal-logs');
              if (logBox) {
                logBox.innerHTML = data.logs.map(function(l) {
                  var cClass = 'text-slate-300';
                  if (l.indexOf('[+]') !== -1 || l.indexOf('✓') !== -1) cClass = 'text-emerald-400 font-bold';
                  else if (l.indexOf('[!]') !== -1 || l.indexOf('Error') !== -1) cClass = 'text-rose-400';
                  return '<div class="' + cClass + '">' + l + '</div>';
                }).join('');
                logBox.scrollTop = logBox.scrollHeight;
              }
            }
          } else if (data.status === 'completed') {
            if (data.logs && data.logs.length > 0) {
              var logBox = document.getElementById('hunter-terminal-logs');
              if (logBox) {
                logBox.innerHTML = data.logs.map(function(l) {
                  return '<div class="text-emerald-400 font-bold">' + l + '</div>';
                }).join('');
                logBox.scrollTop = logBox.scrollHeight;
              }
            }
            if (hunterPollTimer) { clearInterval(hunterPollTimer); hunterPollTimer = null; }
            pBar.style.width = '100%';
            pPct.innerText = '100%';
            sText.innerText = 'Panen Selesai! ' + data.gathered_count + ' IP Residential didapat.';
            btn.disabled = false;
            btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7"/></svg> <span>Panen Sukses! Panen Lagi?</span>';
            refreshData();
          } else if (data.status === 'error') {
            if (hunterPollTimer) { clearInterval(hunterPollTimer); hunterPollTimer = null; }
            sText.innerText = 'Error: ' + (data.last_error || 'Gagal');
            btn.disabled = false;
            btn.innerText = 'Coba Panen Lagi';
          }
        }
      } catch (e) {
        console.error('Gagal cek status hunter:', e);
      }
    }

    // Table Filtering, Sorting & Pagination
    function onFilterChange() {
      var q = (document.getElementById('table-search-input').value || '').toLowerCase();
      var proto = document.getElementById('filter-protocol').value.toLowerCase();
      var country = document.getElementById('filter-country').value.toUpperCase();
      var sort = document.getElementById('filter-sort').value;

      filteredTableProxies = allProxies.filter(function(p) {
        var matchQ = !q || (p.proxy || '').toLowerCase().indexOf(q) !== -1 || (p.isp || '').toLowerCase().indexOf(q) !== -1 || (p.country || '').toLowerCase().indexOf(q) !== -1 || (p.country_code || '').toLowerCase().indexOf(q) !== -1;
        var matchProto = (proto === 'all') || (p.protocol || '').toLowerCase() === proto;
        var matchCountry = (country === 'ALL') || (p.country_code || '').toUpperCase() === country;
        return matchQ && matchProto && matchCountry;
      });

      if (sort === 'latency-asc') {
        filteredTableProxies.sort(function(a, b) { return (a.latency_ms || 0) - (b.latency_ms || 0); });
      } else if (sort === 'latency-desc') {
        filteredTableProxies.sort(function(a, b) { return (b.latency_ms || 0) - (a.latency_ms || 0); });
      } else if (sort === 'country-asc') {
        filteredTableProxies.sort(function(a, b) { return (a.country_code || '').localeCompare(b.country_code || ''); });
      } else if (sort === 'protocol') {
        filteredTableProxies.sort(function(a, b) { return (a.protocol || '').localeCompare(b.protocol || ''); });
      }

      currentPage = 1;
      renderTablePage();
    }

    function filterByCountry(c) {
      switchTab('table');
      document.getElementById('filter-country').value = c;
      onFilterChange();
    }

    function changePageSize() {
      var val = document.getElementById('items-per-page').value;
      pageSize = (val === 'all') ? 99999 : parseInt(val, 10);
      currentPage = 1;
      renderTablePage();
    }

    function setPage(p) {
      currentPage = p;
      renderTablePage();
    }

    function renderTablePage() {
      var tbody = document.getElementById('proxy-table-rows');
      var total = filteredTableProxies.length;

      if (total === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="py-12 text-center text-[#8b8f9a]">Tidak ada proxy yang cocok dengan kriteria pencarian/filter.</td></tr>';
        document.getElementById('pagination-info').innerText = 'Menampilkan 0 dari 0 proxy';
        document.getElementById('pagination-buttons').innerHTML = '';
        return;
      }

      var totalPages = Math.ceil(total / pageSize);
      if (currentPage > totalPages) currentPage = totalPages;

      var startIdx = (currentPage - 1) * pageSize;
      var endIdx = Math.min(startIdx + pageSize, total);
      var currentSlice = filteredTableProxies.slice(startIdx, endIdx);

      tbody.innerHTML = currentSlice.map(function(p, idx) {
        var globalIdx = startIdx + idx + 1;
        var lat = p.latency_ms || 0;
        var latColor = lat < 500 ? 'text-[#d4ff32]' : (lat < 1500 ? 'text-amber-400' : 'text-rose-400');
        var proxyStr = p.proxy || (p.ip + ':' + p.port);

        return '<tr class="hover:bg-white/[0.03] transition group border-b border-white/[0.02]">' +
          '<td class="py-2.5 px-4 text-[#8b8f9a] text-center">' + globalIdx + '</td>' +
          '<td class="py-2.5 px-4 text-emerald-400 font-bold">' + (p.protocol || 'HTTP').toUpperCase() + '</td>' +
          '<td class="py-2.5 px-4 text-white font-medium cursor-pointer hover:text-[#d4ff32]" onclick="copyText(\'' + proxyStr + '\')" title="Klik untuk copy">' + proxyStr + '</td>' +
          '<td class="py-2.5 px-4">' + (p.anonymity || 'Elite') + '</td>' +
          '<td class="py-2.5 px-4 ' + latColor + ' font-bold">' + lat + 'ms</td>' +
          '<td class="py-2.5 px-4 text-slate-300"><span class="px-1.5 py-0.5 rounded bg-white/10 font-bold mr-1.5">' + (p.country_code || '??') + '</span> ' + (p.country || 'Unknown') + '</td>' +
          '<td class="py-2.5 px-4 text-[#8b8f9a] truncate max-w-[200px]" title="' + (p.isp || '-') + '">' + (p.isp || '-').substring(0, 26) + '</td>' +
          '<td class="py-2.5 px-4 text-center">' +
            '<button onclick="copyText(\'' + proxyStr + '\')" class="px-2 py-1 rounded bg-[#1e212b] hover:bg-white/20 text-[#8b8f9a] hover:text-white transition" title="Copy IP:Port">' +
              '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z"/></svg>' +
            '</button>' +
          '</td>' +
        '</tr>';
      }).join('');

      document.getElementById('pagination-info').innerText = 'Menampilkan ' + (startIdx + 1) + ' - ' + endIdx + ' dari ' + total + ' proxy';

      var pContainer = document.getElementById('pagination-buttons');
      var btns = [];
      
      btns.push('<button onclick="setPage(' + (currentPage - 1) + ')" ' + (currentPage === 1 ? 'disabled class="px-2 py-1 rounded-lg bg-[#111216] text-[#8b8f9a] opacity-40 cursor-not-allowed"' : 'class="px-2 py-1 rounded-lg bg-[#111216] hover:bg-slate-700 text-white"') + '>' +
        '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M15 19l-7-7 7-7"/></svg>' +
      '</button>');

      for (var p = 1; p <= totalPages; p++) {
        if (p === 1 || p === totalPages || (p >= currentPage - 1 && p <= currentPage + 1)) {
          btns.push('<button onclick="setPage(' + p + ')" class="px-2.5 py-1 rounded-lg text-xs font-mono font-bold ' + (p === currentPage ? 'lime-btn' : 'bg-[#111216] hover:bg-slate-700 text-slate-300') + '">' + p + '</button>');
        } else if (p === currentPage - 2 || p === currentPage + 2) {
          btns.push('<span class="px-1 text-[#8b8f9a]">...</span>');
        }
      }

      btns.push('<button onclick="setPage(' + (currentPage + 1) + ')" ' + (currentPage === totalPages ? 'disabled class="px-2 py-1 rounded-lg bg-[#111216] text-[#8b8f9a] opacity-40 cursor-not-allowed"' : 'class="px-2 py-1 rounded-lg bg-[#111216] hover:bg-slate-700 text-white"') + '>' +
        '<svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 5l7 7-7 7"/></svg>' +
      '</button>');

      pContainer.innerHTML = btns.join('');
    }

    // Identity Leak Radar Test
    async function runLeakTest() {
      var btn = document.getElementById('btn-leak-run');
      btn.disabled = true;
      btn.innerHTML = '<svg class="animate-spin w-4 h-4 text-white" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path></svg> <span>Sedang Menguji...</span>';

      try {
        var res = await fetch('/api/leak-test').then(function(r) { return r.json(); });
        if (res.status === 'success') {
          document.getElementById('leak-direct-ip').innerText = res.direct.ip || 'Unknown';
          document.getElementById('leak-direct-isp').innerText = res.direct.isp || '-';
          document.getElementById('leak-direct-loc').innerText = res.direct.country + ' [' + res.direct.country_code + ']';

          document.getElementById('leak-gw-ip').innerText = res.gateway.ip || 'Unknown';
          document.getElementById('leak-gw-isp').innerText = res.gateway.isp || '-';
          document.getElementById('leak-gw-loc').innerText = res.gateway.country + ' [' + res.gateway.country_code + ']';

          var vTitle = document.getElementById('leak-verdict-title');
          var vDesc = document.getElementById('leak-verdict-desc');
          var vScore = document.getElementById('leak-score');

          if (res.zero_leak) {
            vTitle.innerText = 'STATUS: TOPENG BERFUNGSI SEMPURNA (ZERO LEAK)';
            vTitle.className = 'text-xs font-bold text-emerald-400';
            vDesc.innerText = 'Target website hanya melihat IP Gateway rotasi. IP asli dan DNS perangkatmu 100% terlindungi.';
            vScore.innerText = '100% SECURE';
            vScore.className = 'font-mono text-sm font-bold text-emerald-400';
            showToast('Audit Selesai', 'Zero DNS/IP Leak terkonfirmasi aktif!', 'success');
          } else {
            vTitle.innerText = 'PERINGATAN: IP MASIH SAMA';
            vTitle.className = 'text-xs font-bold text-amber-400';
            vDesc.innerText = 'Koneksi gateway belum memantul atau sedang menggunakan IP lokal.';
            vScore.innerText = 'CHECK PROXY';
            vScore.className = 'font-mono text-sm font-bold text-amber-400';
          }
        }
      } catch (err) {
        showToast('Gagal Audit', err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg> <span>Jalankan Audit Ulang</span>';
      }
    }

    // UI Helpers & Copy
    function copyAllProxies() {
      var list = allProxies.map(function(p) { return p.proxy || (p.ip + ':' + p.port); }).join(String.fromCharCode(10));
      navigator.clipboard.writeText(list).then(function() {
        showToast('Amunisi Disalin', allProxies.length + ' proxy disalin ke clipboard', 'success');
      });
    }

    function copySnippet(id) {
      var el = document.getElementById(id);
      navigator.clipboard.writeText(el.innerText).then(function() {
        showToast('Snippet Disalin', 'Kode siap ditempel ke script bot kamu', 'success');
      });
    }

    function copyText(txt) {
      navigator.clipboard.writeText(txt).then(function() {
        showToast('Disalin', txt, 'success');
      });
    }

    function toggleExportMenu() {
      var el = document.getElementById('export-dropdown');
      el.classList.toggle('hidden');
    }

    document.addEventListener('click', function(e) {
      var btn = document.getElementById('btn-export');
      var menu = document.getElementById('export-dropdown');
      if (btn && menu && !btn.contains(e.target) && !menu.contains(e.target)) {
        menu.classList.add('hidden');
      }
    });

    function openShortcutsModal() {
      document.getElementById('shortcuts-modal').classList.remove('hidden');
    }

    function closeShortcutsModal() {
      document.getElementById('shortcuts-modal').classList.add('hidden');
    }

    // Toast Engine
    function showToast(title, desc, type) {
      if (!type) type = 'info';
      var container = document.getElementById('toast-container');
      var toast = document.createElement('div');
      var borderClr = type === 'success' ? 'border-emerald-500/40 text-emerald-400' : (type === 'error' ? 'border-rose-500/40 text-rose-400' : 'border-[#d4ff32]/40 text-[#d4ff32]');
      
      toast.className = 'p-3.5 rounded-2xl bg-[#161820] border ' + borderClr + ' shadow-2xl flex items-center gap-3 pointer-events-auto transition transform translate-y-2 opacity-0 text-xs w-72';
      toast.innerHTML = '<div class="flex-1">' +
        '<div class="font-bold text-white">' + title + '</div>' +
        '<div class="text-[11px] text-[#8b8f9a] truncate mt-0.5">' + desc + '</div>' +
      '</div>';
      container.appendChild(toast);

      setTimeout(function() {
        toast.classList.remove('translate-y-2', 'opacity-0');
      }, 20);

      setTimeout(function() {
        toast.classList.add('opacity-0', 'translate-y-2');
        setTimeout(function() { toast.remove(); }, 300);
      }, 2500);
    }

    // Keyboard Shortcuts Listener
    document.addEventListener('keydown', function(e) {
      if (e.key === 'Escape') {
        closeShortcutsModal();
        closeHunterModal();
        closeGrokModal();
      } else if (e.key === '1' && !isInputActive()) {
        switchTab('dashboard');
      } else if (e.key === '2' && !isInputActive()) {
        switchTab('table');
      } else if (e.key === '3' && !isInputActive()) {
        switchTab('radar');
      } else if (e.key === '4' && !isInputActive()) {
        switchTab('snippets');
      } else if ((e.key === 'g' || e.key === 'G') && !isInputActive()) {
        openGrokModal();
      } else if ((e.key === 'w' || e.key === 'W') && !isInputActive()) {
        openHunterModal();
      } else if ((e.key === 'r' || e.key === 'R') && !isInputActive()) {
        forceRotate();
      } else if (e.key === '/' && !isInputActive()) {
        e.preventDefault();
        var search = document.getElementById('table-search-input');
        switchTab('table');
        if (search) search.focus();
      } else if (e.key === '?' && !isInputActive()) {
        openShortcutsModal();
      }
    });

    function isInputActive() {
      var tag = document.activeElement ? document.activeElement.tagName : '';
      return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT';
    }

    function handleGlobalSearch(e) {
      var val = document.getElementById('filter-input').value;
      if (e.key === 'Enter' || val.length > 2) {
        switchTab('table');
        document.getElementById('table-search-input').value = val;
        onFilterChange();
      }
    }

    refreshData();
    setInterval(refreshData, 5000);
  </script>
</body>
</html>
"""

PAC_SCRIPT_TEMPLATE = """function FindProxyForURL(url, host) {
    if (isPlainHostName(host) || 
        shExpMatch(host, "127.0.0.1") || 
        shExpMatch(host, "localhost") || 
        shExpMatch(host, "192.168.*") || 
        shExpMatch(host, "10.*")) {
        return "DIRECT";
    }
    return "PROXY %HOST%:%PORT%; DIRECT";
}
"""

class RotatingProxyRequestHandler(BaseHTTPRequestHandler):
    pool_manager: ProxyPoolManager = None
    server_port: int = 8888

    def log_message(self, format, *args):
        pass

    def extract_session_id(self) -> Optional[str]:
        sess_hdr = self.headers.get("X-Session-ID") or self.headers.get("X-Sticky-Session")
        if sess_hdr:
            return sess_hdr.strip()
        
        if "?" in self.path:
            try:
                query_str = self.path.split("?", 1)[1]
                params = urllib.parse.parse_qs(query_str)
                if "session" in params:
                    return params["session"][0]
                if "session_id" in params:
                    return params["session_id"][0]
            except Exception:
                pass
        return None

    def sanitize_headers(self, headers_dict: Dict[str, str]) -> Dict[str, str]:
        clean = {}
        blocked_headers = {"x-forwarded-for", "via", "x-real-ip", "cf-connecting-ip", "x-proxy-user-agent"}
        
        has_ua = False
        for k, v in headers_dict.items():
            k_lower = k.lower()
            if k_lower in blocked_headers:
                continue
            if k_lower == "user-agent":
                has_ua = True
                if any(bot in v.lower() for bot in ("python-requests", "aiohttp", "curl", "urllib", "httpx")):
                    clean[k] = random.choice(COMMON_USER_AGENTS)
                else:
                    clean[k] = v
            else:
                clean[k] = v

        if not has_ua:
            clean["User-Agent"] = random.choice(COMMON_USER_AGENTS)

        return clean

    # --- REST API & Dashboard Endpoints ---
    def do_GET(self):
        path = self.path

        if path in ("/favicon.ico", "/favicon.svg"):
            self.send_response(200)
            self.send_header("Content-Type", "image/svg+xml")
            body = FAVICON_SVG.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/dashboard", "/dashboard/", "/gui", "/ui"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if path in ("/proxy.pac", "/pac", "/wpad.dat"):
            host_header = self.headers.get("Host", f"127.0.0.1:{self.server_port}")
            host_ip = host_header.split(":")[0] if ":" in host_header else "127.0.0.1"
            pac_body = PAC_SCRIPT_TEMPLATE.replace("%HOST%", host_ip).replace("%PORT%", str(self.server_port)).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ns-proxy-autoconfig")
            self.send_header("Content-Length", str(len(pac_body)))
            self.end_headers()
            self.wfile.write(pac_body)
            return

        if path.startswith("/api/") or path == "/api" or path == "/":
            self.handle_api_request(path)
            return

        self.handle_http_forward()

    def handle_api_request(self, path: str):
        if path in ("/api/random", "/api/random/"):
            p = self.pool_manager.get_random()
            if p:
                payload = {
                    "status": "success",
                    "proxy": p.get("proxy"),
                    "protocol": p.get("protocol", "http"),
                    "url": f"{p.get('protocol', 'http')}://{p['proxy']}",
                    "country": p.get("country", "Unknown"),
                    "country_code": p.get("country_code", "??"),
                    "anonymity": p.get("anonymity", "Elite"),
                    "latency_ms": p.get("latency_ms", 0)
                }
            else:
                payload = {"status": "error", "message": "Proxy pool is empty"}
            self.send_json_response(payload)

        elif path in ("/api/rotate", "/api/rotate/"):
            p = self.pool_manager.force_rotate()
            if p:
                self.send_json_response({
                    "status": "success",
                    "message": "Proxy successfully rotated to next node",
                    "active_proxy": p.get("proxy"),
                    "protocol": p.get("protocol", "http"),
                    "country": p.get("country", "Unknown"),
                    "latency_ms": p.get("latency_ms", 0)
                })
            else:
                self.send_json_response({"status": "error", "message": "Proxy pool is empty"}, status=503)

        elif path in ("/api/all", "/api/all/"):
            proxies = self.pool_manager.get_all()
            self.send_json_response({
                "status": "success",
                "count": len(proxies),
                "proxies": proxies
            })

        elif path.startswith("/api/test-proxy"):
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)
            target = params.get("url", ["https://dummyjson.com/products/search?q=phone"])[0]
            sess = params.get("session_id", [None])[0]
            method = params.get("method", ["GET"])[0].upper()
            ua_preset = params.get("ua_preset", ["chrome-win"])[0]

            ua_dict = {
                "chrome-win": COMMON_USER_AGENTS[0],
                "chrome-mac": COMMON_USER_AGENTS[2],
                "safari-ios": COMMON_USER_AGENTS[4],
                "edge-win": COMMON_USER_AGENTS[3]
            }
            chosen_ua = ua_dict.get(ua_preset, COMMON_USER_AGENTS[0])

            t0 = time.perf_counter()
            try:
                import requests
                proxies = {
                    "http": f"http://127.0.0.1:{self.server_port}",
                    "https": f"http://127.0.0.1:{self.server_port}"
                }
                req_hdrs = {"User-Agent": chosen_ua}
                if sess:
                    req_hdrs["X-Session-ID"] = sess
                
                if method == "POST":
                    r = requests.post(target, proxies=proxies, headers=req_hdrs, json={"test": "petani-proxy", "timestamp": time.time()}, timeout=10.0)
                else:
                    r = requests.get(target, proxies=proxies, headers=req_hdrs, timeout=10.0)
                
                lat = round((time.perf_counter() - t0) * 1000)
                try:
                    body_json = r.json()
                except Exception:
                    body_json = {"raw_text": r.text[:800]}

                routed = body_json.get("ip") if isinstance(body_json, dict) else None
                self.send_json_response({
                    "status": "success",
                    "status_code": r.status_code,
                    "latency_ms": lat,
                    "target_url": target,
                    "session_id": sess,
                    "headers_received": dict(r.headers),
                    "data": body_json,
                    "routed_ip": routed
                })
            except Exception as err:
                lat = round((time.perf_counter() - t0) * 1000)
                self.send_json_response({
                    "status": "error",
                    "message": str(err),
                    "latency_ms": lat,
                    "target_url": target
                }, status=502)

        elif path.startswith("/api/pipeline/grok-status"):
            try:
                from core.grok_farm import grok_farm_state, grok_lock
                with grok_lock:
                    self.send_json_response({
                        "status": "success",
                        "data": dict(grok_farm_state)
                    })
            except Exception as e:
                self.send_json_response({"status": "error", "message": str(e)}, status=500)

        elif path.startswith("/api/pipeline/grok-farm"):
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)
            total = int(params.get("total", ["1"])[0])
            headless = params.get("headless", ["true"])[0].lower() == "true"

            try:
                from core.grok_farm import grok_farm_state, grok_lock, run_grok_farm
                with grok_lock:
                    if grok_farm_state["status"] == "running":
                        self.send_json_response({"status": "error", "message": "Grok breeding job sedang berjalan!"}, status=409)
                        return
                    grok_farm_state["status"] = "running"
                    grok_farm_state["progress"] = 5
                    grok_farm_state["current_account"] = 0
                    grok_farm_state["total_accounts"] = total
                    grok_farm_state["harvested_count"] = 0
                    grok_farm_state["logs"] = ["Memulai Mesin Ternak Grok xAI..."]
                    grok_farm_state["last_error"] = None

                gw_url = f"http://127.0.0.1:{self.server_port}"
                threading.Thread(target=run_grok_farm, kwargs={"total": total, "headless": headless, "proxy_gateway": gw_url}, daemon=True).start()
                self.send_json_response({
                    "status": "success",
                    "message": f"Ternak Grok xAI dijalankan untuk {total} akun!"
                })
            except Exception as e:
                self.send_json_response({"status": "error", "message": str(e)}, status=500)

        elif path.startswith("/api/pipeline/warp"):
            try:
                from core.warp_generator import generate_and_save_warp
                profile = generate_and_save_warp(sync_db=False)
                if profile:
                    self.send_json_response({
                        "status": "success",
                        "message": "Profil Cloudflare WARP WireGuard berhasil dibuat!",
                        "profile": {
                            "v4": profile.get("v4"),
                            "v6": profile.get("v6"),
                            "endpoint": profile.get("endpoint"),
                            "conf_path": profile.get("conf_path")
                        }
                    })
                else:
                    self.send_json_response({"status": "error", "message": "Gagal generate WARP."}, status=500)
            except Exception as e:
                self.send_json_response({"status": "error", "message": str(e)}, status=500)

        elif path.startswith("/api/pipeline/webshare-status"):
            with webshare_lock:
                self.send_json_response({
                    "status": "success",
                    "data": dict(webshare_hunter_state)
                })

        elif path.startswith("/api/pipeline/webshare"):
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)
            total = int(params.get("total", ["1"])[0])
            headless = params.get("headless", ["true"])[0].lower() == "true"
            custom_domain = params.get("custom_domain", [None])[0]

            with webshare_lock:
                if webshare_hunter_state["status"] == "running":
                    self.send_json_response({"status": "error", "message": "Hunter job sedang berjalan!"}, status=409)
                    return
                webshare_hunter_state["status"] = "running"
                webshare_hunter_state["progress"] = 5
                webshare_hunter_state["current_account"] = 0
                webshare_hunter_state["total_accounts"] = total
                webshare_hunter_state["gathered_count"] = 0
                webshare_hunter_state["logs"] = ["Memulai Webshare Residential Hunter..."]
                webshare_hunter_state["last_error"] = None

            def _hunter_worker():
                try:
                    from core.webshare_hunter import run_webshare_hunter
                    gathered = run_webshare_hunter(total=total, headless=headless, custom_domain=custom_domain)
                    with webshare_lock:
                        webshare_hunter_state["status"] = "completed"
                        webshare_hunter_state["progress"] = 100
                        webshare_hunter_state["gathered_count"] = len(gathered)
                        webshare_hunter_state["logs"].append(f"Selesai! Total {len(gathered)} IP Residential berhasil dipanen.")
                except Exception as ex:
                    with webshare_lock:
                        webshare_hunter_state["status"] = "error"
                        webshare_hunter_state["last_error"] = str(ex)
                        webshare_hunter_state["logs"].append(f"Error: {str(ex)}")

            threading.Thread(target=_hunter_worker, daemon=True).start()
            self.send_json_response({
                "status": "success",
                "message": f"Webshare residential hunter dijalankan untuk {total} akun!"
            })

        elif path.startswith("/api/export"):
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)
            fmt = params.get("format", ["txt"])[0].lower()
            proxies = self.pool_manager.get_all()

            if fmt == "json":
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="petani_proxies.json"')
                body = json.dumps({"count": len(proxies), "proxies": proxies}, indent=2).encode("utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif fmt == "csv":
                import io
                import csv
                output = io.StringIO()
                writer = csv.writer(output)
                writer.writerow(["ip", "port", "protocol", "anonymity", "country_code", "country", "latency_ms", "isp"])
                for p in proxies:
                    writer.writerow([p.get("ip"), p.get("port"), p.get("protocol"), p.get("anonymity"), p.get("country_code"), p.get("country"), p.get("latency_ms"), p.get("isp")])
                body = output.getvalue().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="petani_proxies.csv"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            elif fmt == "urls":
                body = "\n".join([f"{p.get('protocol', 'http')}://{p.get('proxy')}" for p in proxies]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="petani_urls.txt"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            else:
                body = "\n".join([p.get("proxy", "") for p in proxies if p.get("proxy")]).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.send_header("Content-Disposition", 'attachment; filename="petani_live_all.txt"')
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

        elif path.startswith("/api/refill"):
            try:
                if self.pool_manager.health_checker:
                    threading.Thread(target=self.pool_manager.health_checker.trigger_refill, daemon=True).start()
                    self.send_json_response({"status": "success", "message": "Refill pool diaktifkan di background!"})
                else:
                    def _do_refill():
                        try:
                            from core.fast_validator import run_fast_harvester
                            fresh = run_fast_harvester(max_latency_ms=500, target_count=10, max_workers=150, sync_db=True)
                            if fresh:
                                existing_keys = {p["proxy"] for p in self.pool_manager.get_all()}
                                for np in fresh:
                                    if np["proxy"] not in existing_keys:
                                        self.pool_manager.proxies.append(np)
                                        existing_keys.add(np["proxy"])
                        except Exception:
                            pass
                    threading.Thread(target=_do_refill, daemon=True).start()
                    self.send_json_response({"status": "success", "message": "Refill mandiri diaktifkan di background!"})
            except Exception as ex:
                self.send_json_response({"status": "error", "message": str(ex)}, status=500)

        elif path.startswith("/api/leak-test"):
            direct_ip, direct_isp, direct_country, direct_cc = "Unknown", "Direct ISP", "Local", "--"
            gw_ip, gw_isp, gw_country, gw_cc = "Unknown", "Upstream ISP", "Rotating Gateway", "--"

            try:
                import requests
                try:
                    r1 = requests.get("https://ipwho.is/", timeout=2.5)
                    if r1.status_code == 200:
                        d1 = r1.json()
                        direct_ip = d1.get("ip", "Unknown")
                        direct_isp = d1.get("connection", {}).get("isp", d1.get("isp", "-"))
                        direct_country = d1.get("country", "-")
                        direct_cc = d1.get("country_code", "--")
                except Exception:
                    try:
                        r1 = requests.get("https://api.ipify.org?format=json", timeout=2.0)
                        if r1.status_code == 200:
                            direct_ip = r1.json().get("ip", "Unknown")
                    except Exception:
                        pass

                try:
                    gw_proxies = {
                        "http": f"http://127.0.0.1:{self.server_port}",
                        "https": f"http://127.0.0.1:{self.server_port}"
                    }
                    r2 = requests.get("https://ipwho.is/", proxies=gw_proxies, timeout=3.0)
                    if r2.status_code == 200:
                        d2 = r2.json()
                        gw_ip = d2.get("ip", "Unknown")
                        gw_isp = d2.get("connection", {}).get("isp", d2.get("isp", "-"))
                        gw_country = d2.get("country", "-")
                        gw_cc = d2.get("country_code", "--")
                except Exception:
                    current_p = self.pool_manager.get_random()
                    if current_p:
                        gw_ip = current_p.get("ip", "Unknown")
                        gw_isp = current_p.get("isp", "Upstream Proxy")
                        gw_country = current_p.get("country", "Unknown")
                        gw_cc = current_p.get("country_code", "??")
            except Exception:
                pass

            zero_leak = (direct_ip != gw_ip) and (gw_ip != "Unknown")
            self.send_json_response({
                "status": "success",
                "direct": {
                    "ip": direct_ip,
                    "isp": direct_isp,
                    "country": direct_country,
                    "country_code": direct_cc
                },
                "gateway": {
                    "ip": gw_ip,
                    "isp": gw_isp,
                    "country": gw_country,
                    "country_code": gw_cc
                },
                "zero_leak": zero_leak
            })

        elif path in ("/api/status", "/api/status/", "/", "/api"):
            accept_header = self.headers.get("Accept", "")
            if "text/html" in accept_header and path == "/":
                self.send_response(302)
                self.send_header("Location", "/dashboard")
                self.end_headers()
                return

            stats = self.pool_manager.get_stats()
            self.send_json_response({
                "service": "PetaniProxy Gateway & REST API",
                "version": "1.2.0",
                "maintainer": "@itzluthfi",
                "dashboard": "/dashboard",
                "pac_script": "/proxy.pac",
                "stats": stats,
                "endpoints": {
                    "dashboard": "/dashboard",
                    "pac": "/proxy.pac",
                    "rotate": "/api/rotate",
                    "random": "/api/random",
                    "all": "/api/all",
                    "test_proxy": "/api/test-proxy?url=...&method=GET|POST&ua_preset=...",
                    "warp": "/api/pipeline/warp",
                    "grok_farm": "/api/pipeline/grok-farm?total=1&headless=true",
                    "grok_status": "/api/pipeline/grok-status",
                    "webshare": "/api/pipeline/webshare?total=1&headless=true&custom_domain=...",
                    "webshare_status": "/api/pipeline/webshare-status",
                    "export": "/api/export?format=txt|urls|csv|json",
                    "refill": "/api/refill",
                    "leak_test": "/api/leak-test",
                    "status": "/api/status"
                },
                "forward_proxy_usage": f"Configure HTTP/HTTPS proxy to http://127.0.0.1:{self.server_port}"
            })
        else:
            self.send_error(404, "API endpoint not found")

    def send_json_response(self, data: dict, status: int = 200):
        body = json.dumps(data, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    # --- HTTPS CONNECT Tunneling ---
    def do_CONNECT(self):
        target_host, target_port = self.path.split(":")
        target_port = int(target_port)

        session_id = self.extract_session_id()
        max_retries = min(3, len(self.pool_manager.proxies) or 1)
        
        for attempt in range(max_retries):
            upstream_proxy = self.pool_manager.get_next(session_id=session_id)
            if not upstream_proxy:
                break

            u_ip = upstream_proxy["ip"]
            u_port = int(upstream_proxy["port"])

            try:
                upstream_sock = socket.create_connection((u_ip, u_port), timeout=4.0)
                connect_req = f"CONNECT {target_host}:{target_port} HTTP/1.1\r\nHost: {target_host}:{target_port}\r\n\r\n"
                upstream_sock.sendall(connect_req.encode("utf-8"))

                upstream_resp = upstream_sock.recv(4096).decode("utf-8", errors="ignore")
                if "200" not in upstream_resp:
                    upstream_sock.close()
                    self.pool_manager.mark_result(False)
                    continue

                self.send_response(200, "Connection Established")
                self.end_headers()

                self.pipe_sockets(self.connection, upstream_sock)
                self.pool_manager.mark_result(True)
                return

            except Exception:
                self.pool_manager.mark_result(False)
                continue

        try:
            self.send_error(504, "Gateway Timeout: All tested upstream proxies failed")
        except Exception:
            pass

    def handle_http_forward(self):
        session_id = self.extract_session_id()
        max_retries = min(3, len(self.pool_manager.proxies) or 1)

        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len) if content_len > 0 else b""

        clean_hdrs = self.sanitize_headers(dict(self.headers))
        req_line = f"{self.command} {self.path} {self.request_version}\r\n"
        headers_str = "".join([f"{k}: {v}\r\n" for k, v in clean_hdrs.items()])
        full_req = f"{req_line}{headers_str}\r\n".encode("utf-8") + body

        for attempt in range(max_retries):
            upstream_proxy = self.pool_manager.get_next(session_id=session_id)
            if not upstream_proxy:
                break

            u_ip = upstream_proxy["ip"]
            u_port = int(upstream_proxy["port"])

            try:
                upstream_sock = socket.create_connection((u_ip, u_port), timeout=4.0)
                upstream_sock.sendall(full_req)

                self.pipe_sockets(self.connection, upstream_sock)
                self.pool_manager.mark_result(True)
                return

            except Exception:
                self.pool_manager.mark_result(False)
                continue

        try:
            self.send_error(502, "Bad Gateway: All tested upstream proxies failed")
        except Exception:
            pass

    def pipe_sockets(self, sock1: socket.socket, sock2: socket.socket, buffer_size: int = 8192, timeout: float = 30.0):
        sockets = [sock1, sock2]
        while True:
            r_socks, _, _ = select.select(sockets, [], [], timeout)
            if not r_socks:
                break
            for s in r_socks:
                data = s.recv(buffer_size)
                if not data:
                    return
                other = sock2 if s is sock1 else sock1
                other.sendall(data)


def start_proxy_server(
    initial_proxies: List[Dict[str, Any]], 
    host: str = "127.0.0.1", 
    port: int = 8888, 
    background: bool = False,
    enable_health_check: bool = True,
    health_check_interval: int = 90,
    min_healthy_count: int = 5
) -> Tuple[HTTPServer, ProxyPoolManager]:
    pool_mgr = ProxyPoolManager(initial_proxies)

    if enable_health_check:
        try:
            from core.pool_scheduler import PoolHealthChecker
            checker = PoolHealthChecker(
                pool_manager=pool_mgr,
                check_interval_sec=health_check_interval,
                min_healthy_count=min_healthy_count,
                enable_auto_refill=True
            )
            checker.start()
            pool_mgr.health_checker = checker
        except Exception as e:
            print(f"[Warning] Failed to initialize PoolHealthChecker: {e}")

    class CustomHandler(RotatingProxyRequestHandler):
        pool_manager = pool_mgr
        server_port = port

    server = HTTPServer((host, port), CustomHandler)

    if background:
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
    else:
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            server.shutdown()

    return server, pool_mgr
