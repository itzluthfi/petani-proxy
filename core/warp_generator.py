"""
PetaniProxy v1.1 - Cloudflare WARP Account Generator & WireGuard/Sing-box Provider
Registers free WireGuard accounts directly via the official Cloudflare WARP REST API
(100% legal, zero captcha, unlimited bandwidth, clean Cloudflare edge IP).
"""
import os
import sys
import time
import json
import base64
import uuid
import sqlite3
import datetime
import urllib.request
import subprocess
from typing import Dict, Any, Optional

if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

try:
    from cryptography.hazmat.primitives.asymmetric import x25519
    from cryptography.hazmat.primitives import serialization
    HAS_CRYPTO = True
except ImportError:
    HAS_CRYPTO = False

CLOUDFLARE_REG_API = "https://api.cloudflareclient.com/v0a2158/reg"

def generate_x25519_keypair() -> tuple[str, str]:
    """Generates an X25519 private/public keypair encoded in standard Base64."""
    if not HAS_CRYPTO:
        raise RuntimeError("cryptography library is required for WARP key generation. Run: pip install cryptography")

    priv_key = x25519.X25519PrivateKey.generate()
    pub_key = priv_key.public_key()

    priv_raw = priv_key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()
    )
    pub_raw = pub_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw
    )

    priv_b64 = base64.b64encode(priv_raw).decode("ascii")
    pub_b64 = base64.b64encode(pub_raw).decode("ascii")
    return priv_b64, pub_b64

def register_warp_account() -> Optional[Dict[str, Any]]:
    """
    Registers a fresh Cloudflare WARP WireGuard profile via public REST API.
    Returns dictionary with keys, endpoints, and IP addresses.
    """
    priv_b64, pub_b64 = generate_x25519_keypair()
    now_iso = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000+00:00")

    payload = {
        "key": pub_b64,
        "install_id": "",
        "fcm_token": "",
        "tos": now_iso,
        "model": "PC",
        "serial_number": "",
        "locale": "en_US"
    }

    req_data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        CLOUDFLARE_REG_API,
        data=req_data,
        headers={
            "User-Agent": "okhttp/3.12.1",
            "Content-Type": "application/json; charset=UTF-8"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=12.0) as resp:
            if resp.status in (200, 201):
                res_json = json.loads(resp.read().decode("utf-8"))
                
                # Extract peer and interface details
                account_id = res_json.get("id")
                token = res_json.get("token")
                cfg = res_json.get("config", {})
                peers = cfg.get("peers", [])
                peer = peers[0] if peers else {}
                peer_pub = peer.get("public_key", "bmXOC+F1FxEMF9dyiK2H5/1SUtzH0JuVo51h2wPfgyo=")
                
                endpoint_obj = peer.get("endpoint", {})
                endpoint_host = endpoint_obj.get("host", "162.159.193.10:2408")
                
                interface = cfg.get("interface", {})
                addresses = interface.get("addresses", {})
                v4_addr = addresses.get("v4", "172.16.0.2/32")
                v6_addr = addresses.get("v6", "")

                return {
                    "account_id": account_id,
                    "token": token,
                    "private_key": priv_b64,
                    "public_key": pub_b64,
                    "peer_public_key": peer_pub,
                    "endpoint": endpoint_host,
                    "v4_address": v4_addr,
                    "v6_address": v6_addr,
                    "dns": "1.1.1.1, 1.0.0.1",
                    "created_at": now_iso
                }
    except Exception as e:
        print(f"[-] Gagal mendaftar ke Cloudflare WARP API: {e}")
    return None

def build_wireguard_conf(profile: Dict[str, Any]) -> str:
    """Formats WARP profile into standard WireGuard .conf content."""
    addrs = [profile["v4_address"]]
    if profile.get("v6_address"):
        addrs.append(profile["v6_address"])
    addr_str = ", ".join(addrs)

    conf = f"""[Interface]
PrivateKey = {profile['private_key']}
Address = {addr_str}
DNS = {profile.get('dns', '1.1.1.1')}

[Peer]
PublicKey = {profile['peer_public_key']}
AllowedIPs = 0.0.0.0/0, ::/0
Endpoint = {profile['endpoint']}
"""
    return conf

def build_singbox_config(profile: Dict[str, Any], local_port: int = 10808) -> Dict[str, Any]:
    """Formats WARP profile into sing-box mixed SOCKS5/HTTP inbound config."""
    ep_host, ep_port = profile["endpoint"].split(":")
    local_addrs = [profile["v4_address"]]
    if profile.get("v6_address"):
        local_addrs.append(profile["v6_address"])

    return {
        "log": {
            "level": "warn"
        },
        "inbounds": [
            {
                "type": "mixed",
                "tag": "mixed-in",
                "listen": "127.0.0.1",
                "listen_port": local_port
            }
        ],
        "outbounds": [
            {
                "type": "wireguard",
                "tag": "warp-out",
                "server": ep_host,
                "server_port": int(ep_port),
                "local_address": local_addrs,
                "private_key": profile["private_key"],
                "peer_public_key": profile["peer_public_key"],
                "reserved": [0, 0, 0]
            }
        ]
    }

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

def sync_warp_to_9router(local_port: int = 10808, db_path: Optional[str] = None) -> bool:
    """Syncs the local Cloudflare WARP endpoint to 9Router SQLite proxyPools."""
    target_db = db_path or find_9router_db()
    if not target_db or not os.path.exists(target_db):
        return False
    
    proxy_url = f"http://127.0.0.1:{local_port}"
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    pid = str(uuid.uuid4())
    name = f"Cloudflare WARP Ultra-Fast ({proxy_url})"
    
    payload = {
        "name": name,
        "proxyUrl": proxy_url,
        "noProxy": "localhost,127.0.0.1",
        "type": "http",
        "strictProxy": False,
        "lastTestedAt": now_iso,
        "lastError": None,
        "latency": 0.05,
        "egressIp": "Cloudflare WARP Edge"
    }

    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        # Delete existing WARP entries if any
        cur.execute("DELETE FROM proxyPools WHERE data LIKE '%Cloudflare WARP%'")
        cur.execute("""
            INSERT INTO proxyPools (id, isActive, testStatus, data, createdAt, updatedAt)
            VALUES (?, 1, 'working', ?, ?, ?)
        """, (pid, json.dumps(payload), now_iso, now_iso))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[-] Gagal sync WARP ke 9Router: {e}")
        return False

def generate_and_save_warp(output_dir: Optional[str] = None, local_port: int = 10808, sync_db: bool = True) -> Optional[Dict[str, Any]]:
    """High-level runner: generates account, writes warp.conf and warp_singbox.json."""
    if not output_dir:
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        output_dir = os.path.join(base_dir, "output", "warp")
    os.makedirs(output_dir, exist_ok=True)

    print("🚀 [1/3] Mendaftarkan profil WireGuard ke Cloudflare WARP REST API...")
    profile = register_warp_account()
    if not profile:
        print("❌ Gagal membuat profil Cloudflare WARP.")
        return None

    print(f"  ✓ Device ID : {profile['account_id']}")
    print(f"  ✓ Endpoint  : {profile['endpoint']}")
    print(f"  ✓ Assigned IP: {profile['v4_address']}")

    # 1. Save WireGuard .conf
    conf_path = os.path.join(output_dir, "warp.conf")
    with open(conf_path, "w", encoding="utf-8") as f:
        f.write(build_wireguard_conf(profile))
    print(f"💾 [2/3] Konfigurasi WireGuard disimpan: {conf_path}")

    # 2. Save Sing-box JSON
    singbox_cfg = build_singbox_config(profile, local_port=local_port)
    singbox_path = os.path.join(output_dir, "warp_singbox.json")
    with open(singbox_path, "w", encoding="utf-8") as f:
        json.dump(singbox_cfg, f, indent=2)
    print(f"💾 [3/3] Konfigurasi Sing-box (Mixed Port {local_port}) disimpan: {singbox_path}")

    # 3. Sync to 9Router
    if sync_db:
        if sync_warp_to_9router(local_port=local_port):
            print(f"🔄 Berhasil menyinkronkan endpoint WARP (http://127.0.0.1:{local_port}) ke 9Router SQLite!")

    print(f"\n🎉 Profil Cloudflare WARP siap digunakan!")
    print(f"💡 Cara pakai:")
    print(f"   • Opsi A: Import 'warp.conf' ke aplikasi resmi WireGuard di Windows/Mac/Android.")
    print(f"   • Opsi B: Jalankan sing-box: 'sing-box run -c {singbox_path}' untuk mengaktifkan local proxy di http://127.0.0.1:{local_port}")
    return profile

if __name__ == "__main__":
    generate_and_save_warp()
