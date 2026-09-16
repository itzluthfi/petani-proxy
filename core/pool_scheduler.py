"""
PetaniProxy v1.1 - 24/7 Resilient Pool Scheduler & Dynamic Health Checker
Continuously monitors the active proxy pool, evicts dead/laggy nodes,
and automatically triggers ultra-fast background refills when healthy capacity drops.
"""
import os
import sys
import time
import json
import logging
import threading
import urllib.request
from typing import List, Dict, Any, Optional

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

class PoolHealthChecker(threading.Thread):
    """
    Background daemon thread that performs periodic health probes
    on all proxies inside ProxyPoolManager.
    """
    def __init__(
        self,
        pool_manager,
        check_interval_sec: int = 90,
        min_healthy_count: int = 5,
        max_probe_timeout_sec: float = 3.0,
        enable_auto_refill: bool = True
    ):
        super().__init__(daemon=True)
        self.pool_manager = pool_manager
        self.check_interval_sec = check_interval_sec
        self.min_healthy_count = min_healthy_count
        self.max_probe_timeout_sec = max_probe_timeout_sec
        self.enable_auto_refill = enable_auto_refill
        self.is_running = True
        self.last_check_time = 0
        self.last_refill_time = 0
        self.total_evicted = 0
        self.total_refilled = 0

    def stop(self):
        self.is_running = False

    def probe_single_proxy(self, proxy_item: Dict[str, Any]) -> bool:
        """Lightweight HTTP check against Cloudflare / ipify."""
        proto = proxy_item.get("protocol", "http").lower()
        proxy_str = proxy_item["proxy"]
        proxy_url = f"{proto}://{proxy_str}"

        try:
            handler = urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request(
                "https://cloudflare.com/cdn-cgi/trace",
                headers={"User-Agent": "Mozilla/5.0"}
            )
            with opener.open(req, timeout=self.max_probe_timeout_sec) as resp:
                return resp.status == 200
        except Exception:
            return False

    def check_and_prune(self):
        """Tests every proxy in the pool, removing dead nodes."""
        current_proxies = self.pool_manager.get_all()
        if not current_proxies:
            return

        healthy = []
        evicted = 0
        for p in current_proxies:
            is_ok = self.probe_single_proxy(p)
            if is_ok:
                healthy.append(p)
            else:
                evicted += 1
                self.total_evicted += 1

        if evicted > 0:
            self.pool_manager.update_pool(healthy)
            print(f"[HealthCheck] 🧹 Pruned {evicted} unresponsive proxies. Sisa sehat: {len(healthy)}")

    def trigger_refill(self):
        """Refills pool in background when healthy proxies fall below threshold."""
        try:
            from core.fast_validator import run_fast_harvester
            print(f"[Auto-Refill] ⚠️ Pool tersisa {len(self.pool_manager.proxies)} (< {self.min_healthy_count}). Mengisi ulang secara otomatis...")
            new_proxies = run_fast_harvester(
                max_latency_ms=500,
                target_count=10,
                max_workers=150,
                sync_db=True
            )
            if new_proxies:
                existing_keys = {p["proxy"] for p in self.pool_manager.get_all()}
                added = 0
                for np in new_proxies:
                    if np["proxy"] not in existing_keys:
                        self.pool_manager.proxies.append(np)
                        existing_keys.add(np["proxy"])
                        added += 1
                self.total_refilled += added
                self.last_refill_time = time.time()
                print(f"[Auto-Refill] ✅ Berhasil menambahkan {added} proxy baru ke active pool! Total pool sekarang: {len(self.pool_manager.proxies)}")
        except Exception as e:
            print(f"[Auto-Refill] Gagal melakukan auto-refill: {e}")

    refill_pool = trigger_refill

    def run(self):
        print(f"[HealthCheck] 🛡️ 24/7 Pool Health Checker aktif (Interval: {self.check_interval_sec}s, Min Threshold: {self.min_healthy_count})")
        while self.is_running:
            try:
                time.sleep(self.check_interval_sec)
                self.check_and_prune()
                self.last_check_time = time.time()

                if self.enable_auto_refill and len(self.pool_manager.proxies) < self.min_healthy_count:
                    # Debounce refill to avoid spamming within 60s
                    if time.time() - self.last_refill_time > 60:
                        self.trigger_refill()

            except Exception as e:
                print(f"[HealthCheck Error] {e}")
