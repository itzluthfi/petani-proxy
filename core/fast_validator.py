"""
PetaniProxy v1.1 - Ultra-Fast Public Proxy Validator (<350ms)
High-performance asynchronous proxy harvester and latency validator.
Uses a shared aiohttp ClientSession and tests candidates in quick batches
so it finds the fastest working proxies in seconds.
"""
import os
import re
import sys
import time
import json
import uuid
import sqlite3
import datetime
import asyncio
from typing import List, Dict, Any, Optional

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

try:
    from aiohttp_socks import ProxyConnector
    HAS_SOCKS = True
except ImportError:
    HAS_SOCKS = False

PROXY_REGEX = re.compile(
    r"(?:(?P<proto>https?|socks4|socks5)://)?"
    r"(?P<ip>(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?:\.(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)){3})"
    r":(?P<port>\d{2,5})",
    re.IGNORECASE
)

FAST_SOURCES = {
    "http": [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=http&timeout=3000&country=all&ssl=all&anonymity=elite",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
        "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
        "https://raw.githubusercontent.com/sunny9577/proxy-scraper/master/proxies.txt",
        "https://raw.githubusercontent.com/roosterkid/openproxylist/main/HTTPS_RAW.txt"
    ],
    "socks5": [
        "https://api.proxyscrape.com/v2/?request=displayproxies&protocol=socks5&timeout=3000&country=all",
        "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
        "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
        "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt"
    ]
}

DEFAULT_TEST_TARGET = "http://api.ipify.org?format=json"

async def fetch_feed(session: aiohttp.ClientSession, url: str, protocol: str) -> List[Dict[str, Any]]:
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=6)) as resp:
            if resp.status == 200:
                text = await resp.text()
                proxies = []
                for match in PROXY_REGEX.finditer(text):
                    ip = match.group("ip")
                    port = int(match.group("port"))
                    if 1 <= port <= 65535:
                        proxies.append({
                            "ip": ip,
                            "port": port,
                            "proxy": f"{ip}:{port}",
                            "protocol": protocol
                        })
                return proxies
    except Exception:
        pass
    return []

async def harvest_raw_candidates(protocols: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    target_protos = protocols or ["http", "socks5"]
    tasks = []
    headers = {"User-Agent": "Mozilla/5.0"}
    timeout = aiohttp.ClientTimeout(total=8)
    async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
        for proto in target_protos:
            for u in FAST_SOURCES.get(proto, []):
                tasks.append(fetch_feed(session, u, proto))
        results = await asyncio.gather(*tasks)

    seen = set()
    deduped = []
    for batch in results:
        for item in batch:
            key = f"{item['protocol']}://{item['proxy']}"
            if key not in seen:
                seen.add(key)
                deduped.append(item)
    return deduped

async def check_http_proxy(
    session: aiohttp.ClientSession,
    candidate: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    max_latency_ms: int,
    test_target: str
) -> Optional[Dict[str, Any]]:
    proxy_url = f"http://{candidate['proxy']}"
    async with semaphore:
        t0 = time.perf_counter()
        try:
            timeout = aiohttp.ClientTimeout(total=max_latency_ms / 1000.0 * 2.0, connect=max_latency_ms / 1000.0)
            async with session.get(test_target, proxy=proxy_url, ssl=False, timeout=timeout) as resp:
                if resp.status == 200:
                    elapsed_ms = int((time.perf_counter() - t0) * 1000)
                    if elapsed_ms <= max_latency_ms:
                        return {
                            "ip": candidate["ip"],
                            "port": candidate["port"],
                            "proxy": candidate["proxy"],
                            "protocol": "http",
                            "url": proxy_url,
                            "latency_ms": elapsed_ms,
                            "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                        }
        except Exception:
            pass
    return None

async def check_socks_proxy(
    candidate: Dict[str, Any],
    semaphore: asyncio.Semaphore,
    max_latency_ms: int,
    test_target: str
) -> Optional[Dict[str, Any]]:
    if not HAS_SOCKS:
        return None
    proto = candidate["protocol"]
    proxy_url = f"{proto}://{candidate['proxy']}"
    async with semaphore:
        t0 = time.perf_counter()
        try:
            connector = ProxyConnector.from_url(proxy_url, ssl=False)
            timeout = aiohttp.ClientTimeout(total=max_latency_ms / 1000.0 * 2.0, connect=max_latency_ms / 1000.0)
            async with aiohttp.ClientSession(connector=connector, timeout=timeout) as session:
                async with session.get(test_target) as resp:
                    if resp.status == 200:
                        elapsed_ms = int((time.perf_counter() - t0) * 1000)
                        if elapsed_ms <= max_latency_ms:
                            return {
                                "ip": candidate["ip"],
                                "port": candidate["port"],
                                "proxy": candidate["proxy"],
                                "protocol": proto,
                                "url": proxy_url,
                                "latency_ms": elapsed_ms,
                                "tested_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                            }
        except Exception:
            pass
    return None

async def validate_batch(
    session: aiohttp.ClientSession,
    candidates: List[Dict[str, Any]],
    semaphore: asyncio.Semaphore,
    max_latency_ms: int,
    target_count: int,
    test_target: str,
    live_list: List[Dict[str, Any]],
    on_live: Optional[callable] = None
):
    tasks = []
    for c in candidates:
        if c["protocol"] == "http":
            tasks.append(asyncio.create_task(check_http_proxy(session, c, semaphore, max_latency_ms, test_target)))
        else:
            tasks.append(asyncio.create_task(check_socks_proxy(c, semaphore, max_latency_ms, test_target)))

    for f in asyncio.as_completed(tasks):
        res = await f
        if res:
            live_list.append(res)
            if on_live:
                on_live(res)
            if len(live_list) >= target_count:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                break

def find_9router_db() -> Optional[str]:
    env_db = os.environ.get("ROUTER_DB_PATH") or os.environ.get("BANSOS_ROUTER_DB") or os.environ.get("NINEROUTER_DB")
    if env_db and os.path.exists(env_db):
        return env_db
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.normpath(os.path.join(base_dir, "..", "eLrouter", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router-mibp-version", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "9router", "data", "db", "data.sqlite")),
        os.path.normpath(os.path.join(base_dir, "..", "bansos-router", "data", "db", "data.sqlite")),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None

def sync_to_9router(proxies: List[Dict[str, Any]], db_path: Optional[str] = None) -> int:
    target_db = db_path or find_9router_db()
    if not target_db or not os.path.exists(target_db):
        return 0
    conn = sqlite3.connect(target_db)
    cur = conn.cursor()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    inserted = 0
    for p in proxies:
        pid = str(uuid.uuid4())
        name = f"Fast Free ({p['protocol'].upper()} - {p['latency_ms']}ms)"
        payload = {
            "name": name,
            "proxyUrl": p["url"],
            "noProxy": "",
            "type": p["protocol"],
            "strictProxy": False,
            "lastTestedAt": now_iso,
            "lastError": None,
            "latency": round(p["latency_ms"] / 1000.0, 2),
            "egressIp": p["ip"]
        }
        try:
            cur.execute("""
                INSERT INTO proxyPools (id, isActive, testStatus, data, createdAt, updatedAt)
                VALUES (?, 1, 'working', ?, ?, ?)
            """, (pid, json.dumps(payload), now_iso, now_iso))
            inserted += 1
        except Exception:
            pass
    conn.commit()
    conn.close()
    return inserted

async def run_fast_harvester_async(
    max_latency_ms: int = 350,
    target_count: int = 15,
    max_workers: int = 200,
    batch_size: int = 400,
    protocols: Optional[List[str]] = None,
    sync_db: bool = True,
    output_file: Optional[str] = None
) -> List[Dict[str, Any]]:
    t0 = time.time()
    print("\n⚡ [FAST HARVESTER] Mengunduh feed proxy publik...")
    candidates = await harvest_raw_candidates(protocols=protocols)
    print(f"📦 Total kandidat terkumpul: {len(candidates):,} kandidat.")

    if not candidates:
        print("❌ Tidak ada kandidat ditemukan.")
        return []

    print(f"🚀 Memulai testing paralel (Filter: Latency <= {max_latency_ms}ms, Target: {target_count} proxy)...")
    semaphore = asyncio.Semaphore(max_workers)
    live_proxies: List[Dict[str, Any]] = []

    def on_live(p):
        print(f"  🟢 LIVE & FAST! {p['protocol'].upper()}://{p['proxy']} | {p['latency_ms']}ms")

    connector = aiohttp.TCPConnector(limit=max_workers, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        for i in range(0, len(candidates), batch_size):
            batch = candidates[i:i + batch_size]
            await validate_batch(
                session=session,
                candidates=batch,
                semaphore=semaphore,
                max_latency_ms=max_latency_ms,
                target_count=target_count,
                test_target=DEFAULT_TEST_TARGET,
                live_list=live_proxies,
                on_live=on_live
            )
            if len(live_proxies) >= target_count:
                break

    live_proxies.sort(key=lambda x: x["latency_ms"])
    elapsed = round(time.time() - t0, 2)
    print(f"\n🎉 Panen selesai dalam {elapsed} detik! Ditemukan {len(live_proxies)} proxy ultra-fast.")

    if not output_file:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_file = os.path.join(base_dir, "output", "fast_elite.txt")

    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        for p in live_proxies:
            f.write(f"{p['url']}\n")
    print(f"💾 Disimpan ke: {output_file}")

    if sync_db and live_proxies:
        inserted = sync_to_9router(live_proxies)
        if inserted > 0:
            print(f"🔄 Berhasil menyinkronkan {inserted} proxy ke SQLite 9Router!")

    return live_proxies

def run_fast_harvester(
    max_latency_ms: int = 350,
    target_count: int = 15,
    max_workers: int = 200,
    sync_db: bool = True
) -> List[Dict[str, Any]]:
    return asyncio.run(
        run_fast_harvester_async(
            max_latency_ms=max_latency_ms,
            target_count=target_count,
            max_workers=max_workers,
            sync_db=sync_db
        )
    )

if __name__ == "__main__":
    run_fast_harvester(max_latency_ms=350, target_count=5)
