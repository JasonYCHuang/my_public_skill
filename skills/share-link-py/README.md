# share-link-py

把檔案（尤其 visitor-profile-builder-py 的 html/png）發佈成**不可猜的
自架 URL**，微信只傳連結——繞開「html 附件點不開」與「傳圖 CDN upload
HTTP 500」兩個附件通道死穴。

- `scripts/share.py`：token 目錄 + ASCII 檔名（html→`index.html`，URL 即
  `<base>/<token>/`）+ 預設 7 天過期 + robots.txt
- `scripts/cleanup.py`：真正刪過期分享（systemd user timer 每小時）
- `scripts/install_systemd.py`：裝/查/卸 cleanup timer
- `assets/Caddyfile.example`：Caddy 站台設定（自動 HTTPS、擋索引）

隨機 URL 不是身份驗證；個人背調資料靠**過期**控制暴露窗口。
部署needs：公網域名 + Caddy（hermes Ubuntu 主機）；大陸收件人先測可達性。

測試：`python -m pytest tests`（27 tests，stdlib only）。
