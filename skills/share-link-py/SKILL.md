---
name: share-link-py
description: Publish files (esp. visitor-profile-builder-py outputs) as unguessable self-hosted URLs so WeChat contacts open them in a phone browser - the workaround for WeChat's two attachment failure modes - html attachments can't be previewed in-chat, and image sends often die with CDN upload HTTP 500. scripts/share.py copies files into a token directory under a Caddy-served webroot (html becomes index.html so the URL is just <base>/<token>/), records a default 7-day expiry, and prints the URLs to paste into chat; cleanup.py (hourly systemd user timer) deletes expired shares. Use when the user wants to 傳連結 instead of attachments, asks to share a 個人檔案/報告 to 微信, or when a WeChat file/image send keeps failing.
compatibility: Agent-agnostic Agent Skills package (agentskills.io format). share.py/cleanup.py are Python 3 stdlib only, run anywhere. Serving needs a host with a public domain + Caddy (assets/Caddyfile.example) - built for the hermes Ubuntu agent host; expiry scheduling needs systemd user timers. Mainland-China reachability of the domain must be verified once at deploy time.
metadata:
  built-for: "sharing vpb dossiers to WeChat as URLs after CDN-500 made attachments unreliable (2026-07-23)"
  origin: "Claude Code"
  variant: "python-orchestrated (share.py + cleanup.py + systemd timer + Caddy)"
---

# Share Link（微信傳 URL，不傳附件）

微信附件通道兩個死法：html 傳過去點不開、圖片常遇 `CDN upload HTTP 500`。
這個 skill 繞開整條附件通道——檔案發佈到自架 web 目錄，微信只傳一條
URL，對方點開（或複製到手機 Chrome）就能看。

> **策略保持柔性，執行保持剛性。** 你判斷「該不該分享、分享多久」；
> `share.py` 剛性執行 token、複製、過期記錄、robots，`cleanup.py` 剛性刪檔。

## 隱私（先讀這段）

分享出去的常是**個人背調資料**。隨機 URL 不是身份驗證——拿到連結的任何人
都能開。所以：

- **預設 7 天過期**，由 cleanup timer 真正刪檔。`--ttl never` 要有明確理由。
- 只分享**已驗證的產物**（vpb job dir 輸入自動略過 unverified artifact，
  且永不分享 `profile.json` 原始資料）。
- 搜尋引擎雙保險：`pub/robots.txt`（自動生成）+ Caddy `X-Robots-Tag`。
- 不要把分享 URL 貼到比請求者預期更廣的地方；對方轉傳你控制不了，
  能控制的是過期時間。

## 用法

```bash
# vpb job dir：自動抓已驗證的 html + png
python3 scripts/share.py ~/mein-agent-storage/vpb-out/202607/20260723-120000-wang/

# 或任意檔案；--ttl 可改 24h / never
python3 scripts/share.py 報告.html 圖.png --ttl 24h
```

輸出長這樣，整行 URL 直接貼進微信：

```
已發佈（2026-07-30 14:00 過期）：
  王小明 個人檔案.html  →  https://share.example.com/Kx3...pQ/
  王小明 個人檔案.png   →  https://share.example.com/Kx3...pQ/card.png
```

html 會改名 `index.html`（URL 就是目錄本身，最短最好點）、png 改名
`card.png`——微信聊天視窗的連結不能斷在非 ASCII 字元上，所以分享檔名
一律 ASCII。原始檔名記在 meta 裡。`--json` 給機器可讀摘要。

**傳到微信後提醒對方：** 微信內建瀏覽器多半開得了；開不了就長按連結
複製、貼到手機 Chrome。

## Setup（一次性，hermes 主機）

1. **域名 + DNS**：一個 A record 指到主機公網 IP。收件人有中國大陸的，
   **裝完先測大陸可達性**（請對方開 `https://<域名>/robots.txt`）；
   不通就得換域名/線路，這一步沒過整個 skill 白搭。
2. **Caddy**：`sudo apt install -y caddy`，把 `assets/Caddyfile.example`
   併進 `/etc/caddy/Caddyfile`（webroot 指到 `<root>/pub`），
   `sudo systemctl reload caddy`。HTTPS 憑證 Caddy 自動處理。
3. **設定檔**，之後 share.py 不用帶參數：
   ```bash
   mkdir -p ~/.config/share-link
   echo '{"base_url": "https://share.example.com"}' > ~/.config/share-link/config.json
   ```
4. **過期清理 timer**：
   ```bash
   python3 scripts/install_systemd.py install   # 每小時 :15 跑 cleanup.py
   loginctl enable-linger $USER                 # 無人值守必開
   ```

儲存布局（`--root`，預設 `~/mein-agent-storage/share-link/`）：

```
share-link/
  pub/            ← Caddy webroot；pub/<token>/ 一個分享一夾
    robots.txt    ← 自動生成，全站 Disallow
  meta/<token>.json  ← 過期記錄，在 webroot 之外，永不被 serve
  .tmp/           ← 先組好再整包 rename 進 pub，沒有半成品可見
```

## 維運

```bash
python3 scripts/cleanup.py --dry-run     # 看哪些會被刪
python3 scripts/install_systemd.py status
```

- **手動提前撤下**某個分享：刪 `pub/<token>/` 與 `meta/<token>.json` 即可。
- **cleanup 規則**：meta 過期 → 刪；`expires_at: null` → 永留；pub/ 裡
  沒 meta 的孤兒夾超過 1 天 → 刪（share.py 中途死掉的殘骸）。
- **微信打不開連結**：先確認手機瀏覽器直接開 OK（排除微信域名攔截），
  再看 Caddy log。域名被微信攔的話只能換域名。
