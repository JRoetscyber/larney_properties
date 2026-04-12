#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Larney Properties – Linux deployment script
# Usage (first run):  sudo bash deploy.sh
# Usage (update):     sudo bash deploy.sh --update
#
# Tested on Ubuntu 22.04 / Debian 12.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colour helpers ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'
info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
die()     { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }

# ── Configuration  (edit these if needed) ─────────────────────────────────────
REPO_URL="https://github.com/JRoetscyber/larney_properties.git"
APP_DIR="/opt/larney_properties"
APP_USER="larney"
SERVICE_NAME="larney"
APP_PORT=64000
NGINX_CONF="/etc/nginx/sites-available/${SERVICE_NAME}"
ENV_FILE="${APP_DIR}/.env"

# ─────────────────────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && die "Please run as root:  sudo bash deploy.sh"

UPDATE_ONLY=false
[[ "${1:-}" == "--update" ]] && UPDATE_ONLY=true

# ═══════════════════════════════════════════════════════════════════════════════
# UPDATE PATH  – pull latest code and restart
# ═══════════════════════════════════════════════════════════════════════════════
if $UPDATE_ONLY; then
  [[ ! -d "$APP_DIR/.git" ]] && die "App not installed yet. Run without --update first."
  info "Pulling latest code …"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull origin main
  info "Installing/upgrading Python dependencies …"
  "$APP_DIR/.venv/bin/pip" install -q --upgrade -r "$APP_DIR/requirements.txt"
  info "Restarting service …"
  systemctl restart "$SERVICE_NAME"
  success "Update complete. Service is running."
  systemctl status "$SERVICE_NAME" --no-pager
  exit 0
fi

# ═══════════════════════════════════════════════════════════════════════════════
# FRESH INSTALL
# ═══════════════════════════════════════════════════════════════════════════════
echo -e "\n${BOLD}━━━  Larney Properties – Server Setup  ━━━${NC}\n"

# ── 1. System packages ────────────────────────────────────────────────────────
info "Updating package lists …"
apt-get update -qq

info "Installing system packages …"
apt-get install -y -qq \
  python3 python3-pip python3-venv \
  git nginx curl \
  libglib2.0-0 libnss3 libnspr4 libdbus-1-3 libatk1.0-0 \
  libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
  libxcomposite1 libxdamage1 libxfixes3 libxrandr2 libgbm1 \
  libpango-1.0-0 libcairo2 libasound2 \
  > /dev/null
success "System packages installed."

# ── 2. App user ───────────────────────────────────────────────────────────────
if ! id -u "$APP_USER" &>/dev/null; then
  useradd -r -s /usr/sbin/nologin -d "$APP_DIR" -m "$APP_USER"
  success "Created system user '$APP_USER'."
else
  info "User '$APP_USER' already exists — skipping."
fi

# ── 3. Clone repository ───────────────────────────────────────────────────────
if [[ -d "$APP_DIR/.git" ]]; then
  warn "$APP_DIR already contains a git repo. Pulling latest instead …"
  sudo -u "$APP_USER" git -C "$APP_DIR" pull origin main
else
  info "Cloning repository …"
  git clone "$REPO_URL" "$APP_DIR"
  chown -R "$APP_USER:$APP_USER" "$APP_DIR"
  success "Repository cloned to $APP_DIR."
fi

# ── 4. Python virtual environment ─────────────────────────────────────────────
info "Creating Python virtual environment …"
python3 -m venv "$APP_DIR/.venv"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/.venv"

info "Installing Python dependencies (this may take a minute) …"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" gunicorn
success "Python dependencies installed."

# ── 5. Playwright browser (used by the valuation / HPE feature) ───────────────
info "Installing Playwright Chromium browser …"
"$APP_DIR/.venv/bin/playwright" install chromium 2>/dev/null \
  && success "Playwright Chromium installed." \
  || warn  "Playwright install failed — the Home Price Estimation feature may not work."

# ── 6. Runtime directories ────────────────────────────────────────────────────
info "Creating upload directories …"
mkdir -p "$APP_DIR/static/uploads/agents"
chown -R "$APP_USER:$APP_USER" "$APP_DIR/static/uploads"
success "Upload directories ready."

# ── 7. Environment / secrets file ─────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
  warn ".env already exists — not overwriting. Edit $ENV_FILE manually if needed."
else
  info "Creating .env template …"
  cat > "$ENV_FILE" <<'EOF'
# ── Larney Properties – Environment Variables ─────────────────────────────────
# Edit this file with your real credentials, then restart the service:
#   sudo systemctl restart larney

# Flask secret key – change to a long random string
FLASK_SECRET_KEY=change-me-to-a-long-random-string

# SMTP settings (Gmail example)
MAIL_SERVER=smtp.gmail.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=your_email@gmail.com
MAIL_PASSWORD=your_gmail_app_password

# Where contact-form emails are forwarded
ADMIN_EMAIL=admin@yourdomain.com
EOF
  chown "$APP_USER:$APP_USER" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  success ".env created at $ENV_FILE"
  echo -e "${YELLOW}  !! Edit $ENV_FILE with real credentials before going live !!${NC}"
fi

# ── 8. Systemd service ────────────────────────────────────────────────────────
info "Writing systemd service …"
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=Larney Properties Flask app (Gunicorn)
After=network.target

[Service]
User=${APP_USER}
Group=${APP_USER}
WorkingDirectory=${APP_DIR}
EnvironmentFile=${ENV_FILE}
ExecStart=${APP_DIR}/.venv/bin/gunicorn \\
    --workers 3 \\
    --bind 127.0.0.1:${APP_PORT} \\
    --timeout 120 \\
    --access-logfile ${APP_DIR}/access.log \\
    --error-logfile  ${APP_DIR}/error.log  \\
    app:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
success "Systemd service '$SERVICE_NAME' registered."

# ── 9. Nginx reverse proxy ────────────────────────────────────────────────────
info "Writing Nginx config …"
cat > "$NGINX_CONF" <<EOF
server {
    listen 80;
    server_name _;          # replace _ with your domain name

    client_max_body_size 10M;

    # Static files served directly by Nginx (fast)
    location /static/ {
        alias ${APP_DIR}/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    # Everything else → Gunicorn
    location / {
        proxy_pass         http://127.0.0.1:${APP_PORT};
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto \$scheme;
        proxy_read_timeout 120s;
    }
}
EOF

# Enable site
ln -sf "$NGINX_CONF" "/etc/nginx/sites-enabled/${SERVICE_NAME}"

# Remove default site if it's still there (it blocks port 80)
if [[ -f /etc/nginx/sites-enabled/default ]]; then
  rm /etc/nginx/sites-enabled/default
  warn "Removed default Nginx site (was blocking port 80)."
fi

nginx -t && success "Nginx config is valid." || die "Nginx config test failed — check $NGINX_CONF"

# ── 10. Start everything ──────────────────────────────────────────────────────
info "Starting services …"
systemctl start "$SERVICE_NAME"
systemctl reload nginx

echo ""
echo -e "${BOLD}${GREEN}━━━  Setup complete!  ━━━${NC}"
echo ""
echo -e "  App service:  ${BOLD}systemctl status ${SERVICE_NAME}${NC}"
echo -e "  App logs:     ${BOLD}tail -f ${APP_DIR}/error.log${NC}"
echo -e "  Secrets file: ${BOLD}${ENV_FILE}${NC}  ← edit before going live"
echo ""
echo -e "  To update later:  ${BOLD}sudo bash ${APP_DIR}/deploy.sh --update${NC}"
echo ""

# Quick smoke test
sleep 2
if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:${APP_PORT}" | grep -qE "^(200|302|301)"; then
  success "App is responding on port ${APP_PORT}."
else
  warn "App may not be up yet. Check: sudo systemctl status ${SERVICE_NAME}"
fi
