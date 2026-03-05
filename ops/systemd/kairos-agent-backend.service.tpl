[Unit]
Description=KairosAgent Backend Stack (Docker Compose)
Requires=docker.service
After=docker.service network-online.target
Wants=network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory={{REPO_DIR}}
ExecStart=/usr/bin/docker compose up -d postgres redis api celery-worker celery-beat
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
