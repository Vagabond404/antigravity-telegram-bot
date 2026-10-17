#!/usr/bin/env python3
"""
browser_tool.py - Cross-Platform Autonomous Web Browser & Scraping Tool
Supports headless Chrome / Chromium / Edge on both Windows and Linux, with automatic HTTP fallback.
Features:
- Web Search (DuckDuckGo instant search without API key)
- Webpage Content Extractor (Dump DOM + clean Markdown converter)
- Webpage Screenshot Capturer (High-res PNG + optional auto-Telegram send)
"""

import sys
import os
import re
import html
import shutil
import argparse
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path
from config import BASE_DIR, TEMP_DIR, IS_WINDOWS


def find_browser_binary() -> str:
    candidates = [
        "chromium",
        "chromium-browser",
        "google-chrome",
        "google-chrome-stable",
        "chrome",
        "msedge",
        "brave-browser",
    ]
    for c in candidates:
        found = shutil.which(c)
        if found:
            return found

    if IS_WINDOWS:
        win_paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
        ]
        for wp in win_paths:
            if Path(wp).is_file():
                return wp
    else:
        unix_paths = [
            "/usr/bin/chromium",
            "/usr/bin/chromium-browser",
            "/usr/bin/google-chrome",
            "/snap/bin/chromium",
        ]
        for up in unix_paths:
            if Path(up).is_file():
                return up
    return ""


def clean_html_to_markdown(html_content: str) -> str:
    title_match = re.search(r"<title>(.*?)</title>", html_content, re.IGNORECASE | re.DOTALL)
    title = title_match.group(1).strip() if title_match else "Sans titre"

    clean = re.sub(
        r"<(script|style|svg|noscript|header|footer|nav)[^>]*>.*?</\1>",
        "",
        html_content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    clean = re.sub(r"<h1[^>]*>(.*?)</h1>", r"\n# \1\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<h2[^>]*>(.*?)</h2>", r"\n## \1\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<h3[^>]*>(.*?)</h3>", r"\n### \1\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<p[^>]*>(.*?)</p>", r"\n\1\n", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r"<br\s*/?>", "\n", clean, flags=re.IGNORECASE)
    clean = re.sub(r"<li[^>]*>(.*?)</li>", r"\n• \1", clean, flags=re.IGNORECASE | re.DOTALL)
    clean = re.sub(r'<a\s+[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r"[\2](\1)", clean, flags=re.IGNORECASE | re.DOTALL)

    text = re.sub(r"<[^>]+>", " ", clean)
    text = html.unescape(text)

    lines = [line.strip() for line in text.split("\n")]
    non_empty = [line for line in lines if line]
    body_md = "\n\n".join(non_empty)
    return f"# {title}\n\n{body_md}"


def fetch_page(url: str, timeout: int = 20) -> str:
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    browser_bin = find_browser_binary()
    if browser_bin:
        cmd = [
            browser_bin,
            "--headless",
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            "--disable-software-rasterizer",
            f"--timeout={timeout * 1000}",
            "--dump-dom",
            url,
        ]
        try:
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=timeout + 5)
            if res.stdout and len(res.stdout) > 200:
                return clean_html_to_markdown(res.stdout)
        except Exception:
            pass

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            content = resp.read().decode("utf-8", errors="replace")
            return clean_html_to_markdown(content)
    except Exception as e:
        return f"❌ Erreur lors de la récupération de {url} : {e}"


def take_screenshot(
    url: str,
    out_path: str = None,
    width: int = 1280,
    height: int = 800,
    send_tg: bool = False,
    caption: str = "",
) -> str:
    if not url.startswith("http://") and not url.startswith("https://"):
        url = "https://" + url

    browser_bin = find_browser_binary()
    if not browser_bin:
        return "❌ Aucun navigateur headless (Chrome/Chromium/Edge) trouvé sur le système pour la capture d'écran."

    if not out_path:
        domain = urllib.parse.urlparse(url).netloc.replace(".", "_").replace(":", "_")
        out_path = str(TEMP_DIR / f"screenshot_{domain}.png")

    cmd = [
        browser_bin,
        "--headless",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        f"--window-size={width},{height}",
        f"--screenshot={out_path}",
        url,
    ]

    try:
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            res_msg = f"✅ Capture d'écran enregistrée : {out_path} ({os.path.getsize(out_path)} octets)"
            if send_tg:
                cap = caption or f"📸 Capture de {url}"
                tg_script = str(BASE_DIR / "tg_send.py")
                subprocess.run(
                    [sys.executable, tg_script, "--photo", out_path, "--caption", cap],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
                res_msg += "\n📲 Envoyée directement sur Telegram !"
            return res_msg
        return f"❌ Échec de la capture d'écran pour {url}"
    except Exception as e:
        return f"❌ Erreur capture d'écran : {e}"


def search_web(query: str, limit: int = 5) -> str:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded}"

    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            },
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html_text = resp.read().decode("utf-8", errors="replace")

        results = []
        matches = re.findall(r'<div class="result\s+results_links[^"]*"[^>]*>(.*?)</div>\s*</div>', html_text, re.DOTALL)

        for block in matches[:limit]:
            title_m = re.search(r'<a class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            snip_m = re.search(r'<a class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)
            if title_m:
                raw_url = title_m.group(1)
                if "uddg=" in raw_url:
                    parsed_uddg = urllib.parse.parse_qs(urllib.parse.urlparse(raw_url).query).get("uddg", [""])[0]
                    target_url = urllib.parse.unquote(parsed_uddg) if parsed_uddg else raw_url
                else:
                    target_url = raw_url

                t_clean = re.sub(r"<[^>]+>", "", title_m.group(2)).strip()
                s_clean = re.sub(r"<[^>]+>", "", snip_m.group(1)).strip() if snip_m else ""
                results.append(f"🔹 **[{t_clean}]({target_url})**\n   _{s_clean}_")

        if results:
            return f"🔍 **Résultats de recherche pour :** `{query}`\n\n" + "\n\n".join(results)
        return f"ℹ️ Aucun résultat trouvé pour la recherche : `{query}`"
    except Exception as e:
        return f"❌ Erreur recherche web : {e}"


def main():
    parser = argparse.ArgumentParser(description="Autonomous Cross-Platform Browser Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch and parse webpage content")
    fetch_parser.add_argument("url", help="URL to fetch")

    screen_parser = subparsers.add_parser("screenshot", help="Take screenshot of webpage")
    screen_parser.add_argument("url", help="URL to capture")
    screen_parser.add_argument("--out", help="Output PNG path", default=None)
    screen_parser.add_argument("--send-tg", action="store_true", help="Automatically send to user on Telegram")
    screen_parser.add_argument("--caption", help="Telegram caption", default="")

    search_parser = subparsers.add_parser("search", help="Search the web")
    search_parser.add_argument("query", help="Search keywords")
    search_parser.add_argument("--limit", type=int, default=5, help="Number of results")

    args = parser.parse_args()

    if args.command == "fetch":
        print(fetch_page(args.url))
    elif args.command == "screenshot":
        print(take_screenshot(args.url, args.out, send_tg=args.send_tg, caption=args.caption))
    elif args.command == "search":
        print(search_web(args.query, limit=args.limit))


if __name__ == "__main__":
    main()