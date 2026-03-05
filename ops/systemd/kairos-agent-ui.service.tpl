[Unit]
Description=KairosAgent Web Panel (Vite)
After=network-online.target kairos-agent-backend.service
Wants=network-online.target
Requires=kairos-agent-backend.service

[Service]
Type=simple
User={{KAIROS_USER}}
Group={{KAIROS_USER}}
WorkingDirectory={{REPO_DIR}}/ui/kairos-rain-chat
Environment=HOME={{KAIROS_HOME}}
Environment=NVM_DIR={{KAIROS_HOME}}/.nvm
ExecStart=/bin/bash -lc '. "$NVM_DIR/nvm.sh" && nvm use 20 >/dev/null && npm run dev -- --host 0.0.0.0 --port 8080'
Restart=always
RestartSec=5
KillSignal=SIGINT

[Install]
WantedBy=multi-user.target
