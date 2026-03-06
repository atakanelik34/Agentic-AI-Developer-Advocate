[Unit]
Description=KairosAgent Public Tunnel (cloudflared Quick Tunnel)
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8081
Restart=always
RestartSec=5
StandardOutput=append:/var/log/kairos-cloudflared.log
StandardError=append:/var/log/kairos-cloudflared.log

[Install]
WantedBy=multi-user.target
