#!/usr/bin/env python3
"""Import JSON cookies (from browser extension export) into Chrome profile."""
import json
import sqlite3
import os
import sys
from pathlib import Path
import time

PROFILE_DIR = os.environ.get("BROWSER_PROFILE_DIR", "/app/profiles")

def import_cookies(json_path: str, profile_name: str):
    profile_path = Path(PROFILE_DIR) / profile_name
    profile_path.mkdir(parents=True, exist_ok=True)
    
    # Chrome cookie DB path
    default_dir = profile_path / "Default"
    default_dir.mkdir(exist_ok=True)
    cookies_db = default_dir / "Cookies"
    
    with open(json_path, 'r') as f:
        cookies = json.load(f)
    
    # Create/connect to Chrome cookies DB
    conn = sqlite3.connect(str(cookies_db))
    cursor = conn.cursor()
    
    # Create cookies table if not exists (Chrome schema)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS cookies (
            creation_utc INTEGER NOT NULL,
            host_key TEXT NOT NULL,
            top_frame_site_key TEXT NOT NULL,
            name TEXT NOT NULL,
            value TEXT NOT NULL,
            encrypted_value BLOB NOT NULL,
            path TEXT NOT NULL,
            expires_utc INTEGER NOT NULL,
            is_secure INTEGER NOT NULL,
            is_httponly INTEGER NOT NULL,
            last_access_utc INTEGER NOT NULL,
            has_expires INTEGER NOT NULL,
            is_persistent INTEGER NOT NULL,
            priority INTEGER NOT NULL,
            samesite INTEGER NOT NULL,
            source_scheme INTEGER NOT NULL,
            source_port INTEGER NOT NULL,
            last_update_utc INTEGER NOT NULL,
            source_type INTEGER NOT NULL,
            has_cross_site_ancestor INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (host_key, top_frame_site_key, name, path)
        )
    ''')
    
    now = int((time.time() + 11644473600) * 1000000)  # Chrome time format
    
    imported = 0
    for cookie in cookies:
        host_key = cookie.get('domain', '')
        if host_key.startswith('.'):
            host_key = host_key[1:]
        
        name = cookie.get('name', '')
        value = cookie.get('value', '')
        path = cookie.get('path', '/')
        is_secure = 1 if cookie.get('secure') else 0
        is_httponly = 1 if cookie.get('httpOnly') else 0
        
        # Convert expirationDate to Chrome time
        exp = cookie.get('expirationDate')
        if exp:
            expires_utc = int((exp + 11644473600) * 1000000)
            has_expires = 1
            is_persistent = 1
        else:
            expires_utc = 0
            has_expires = 0
            is_persistent = 0
        
        # SameSite mapping
        same_site_str = cookie.get('sameSite')
        if same_site_str == 'no_restriction':
            samesite = 0
        elif same_site_str == 'lax':
            samesite = 1
        elif same_site_str == 'strict':
            samesite = 2
        else:
            samesite = -1
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO cookies 
                (creation_utc, host_key, top_frame_site_key, name, value, encrypted_value,
                 path, expires_utc, is_secure, is_httponly, last_access_utc, has_expires,
                 is_persistent, priority, samesite, source_scheme, source_port, last_update_utc, source_type, has_cross_site_ancestor)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                now, host_key, '', name, value, b'',
                path, expires_utc, is_secure, is_httponly, now, has_expires,
                is_persistent, 1, samesite, 2, 443, now, 1, 0
            ))
            imported += 1
        except Exception as e:
            print(f"Warning: failed to import {name}: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"[import] Successfully imported {imported} cookies to {cookies_db}")
    return imported

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: import_json_cookies.py <cookies.json> <profile_name>")
        sys.exit(1)
    
    import_cookies(sys.argv[1], sys.argv[2])
