[Unit]
Description=KairosAgent Public Tunnel (cloudflared Quick Tunnel)
After=network-online.target kairos-agent-ui.service
Wants=network-online.target
Requires=kairos-agent-ui.service

[Service]
Type=simple
ExecStart=/usr/local/bin/cloudflared tunnel --no-autoupdate --url http://127.0.0.1:8080
Restart=always
RestartSec=5
StandardOutput=append:/var/log/kairos-cloudflared.log
StandardError=append:/var/log/kairos-cloudflared.log

[Install]
WantedBy=multi-user.target
