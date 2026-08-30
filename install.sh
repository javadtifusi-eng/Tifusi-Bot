#!/bin/bash
# ============================================================
#   Tifusi Bot — One-Line Installer (v4.0)
#   Telegram VPN Shop Bot for vpn-ui panels
#   Protocols: L2TP / PPTP / IKEv2 / OpenVPN
# ============================================================
REPO_URL="https://raw.githubusercontent.com/javadtifusi-eng/Tifusi-Bot/main"

BOT_FILE="/root/bot.py"
SERVICE="bot"

# ---------- Colors ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------- Banner ----------
banner() {
    clear
    echo -e "${MAGENTA}${BOLD}"
    cat << 'EOF'
  _____ ___ _____ _   _ ____ ___
 |_   _|_ _|  ___| | | / ___|_ _|
   | |  | || |_  | | | \___ \| |
   | |  | ||  _| | |_| |___) || |
   |_| |___|_|    \___/|____/___|
          ____   ___ _____
         | __ ) / _ \_   _|
         |  _ \| | | || |
         | |_) | |_| || |
         |____/ \___/ |_|
EOF
    echo -e "${NC}"
    echo -e "${CYAN}  Tifusi Bot — Telegram VPN Shop Bot | v4.0${NC}"
    echo -e "${YELLOW}  Protocols: L2TP / PPTP / IKEv2 / OpenVPN${NC}"
    echo -e "${GREEN}  --------------------------------------------${NC}"
    echo ""
}

# ---------- Helpers ----------
ok()   { echo -e "${GREEN}[OK] $1${NC}"; }
err()  { echo -e "${RED}[ERROR] $1${NC}"; }
info() { echo -e "${CYAN}[INFO] $1${NC}"; }
warn() { echo -e "${YELLOW}[WARN] $1${NC}"; }
ask()  { echo -e "${MAGENTA}[?] $1${NC}"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        err "Please run as root!"
        exit 1
    fi
}

# ---------- Install dependencies ----------
install_deps() {
    info "Installing dependencies... (this may take a few minutes)"
    apt update -y >/dev/null 2>&1
    apt install -y python3 python3-pip curl >/dev/null 2>&1
    pip3 install python-telegram-bot "python-telegram-bot[job-queue]" requests qrcode pillow --break-system-packages >/dev/null 2>&1 \
        || pip3 install python-telegram-bot "python-telegram-bot[job-queue]" requests qrcode pillow >/dev/null 2>&1
    if python3 -c "import telegram, requests, qrcode, PIL" 2>/dev/null; then
        ok "Dependencies installed"
    else
        err "Dependency installation failed — check server internet connection"
        exit 1
    fi
}

# ---------- Download latest bot ----------
download_bot() {
    info "Downloading latest bot.py from GitHub..."
    curl -Ls "$REPO_URL/bot.py" -o "$BOT_FILE"
    if [ ! -s "$BOT_FILE" ] || ! python3 -m py_compile "$BOT_FILE" 2>/dev/null; then
        err "Download failed! Check REPO_URL inside install.sh"
        exit 1
    fi
    ok "Bot downloaded"
}

# ---------- Create systemd service ----------
make_service() {
    cat > /etc/systemd/system/bot.service << 'EOF'
[Unit]
Description=Tifusi VPN Shop Bot
After=network.target
[Service]
ExecStart=/usr/bin/python3 /root/bot.py
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable bot >/dev/null 2>&1
    ok "systemd service created and enabled"
}

# ---------- Shortcut command: tifusi ----------
make_shortcut() {
    cp "$0" /usr/local/bin/tifusi 2>/dev/null || curl -Ls "$REPO_URL/install.sh" -o /usr/local/bin/tifusi
    chmod +x /usr/local/bin/tifusi
    ln -sf /usr/local/bin/tifusi /usr/local/bin/qashang 2>/dev/null
    ok "Shortcut ready! Type 'tifusi' anytime to open this menu"
}

# ---------- Full install ----------
install_bot() {
    banner
    echo -e "${BOLD}Starting installation...${NC}"
    echo ""

    install_deps
    download_bot

    echo ""
    echo -e "${YELLOW}${BOLD}A few questions — answer one by one:${NC}"
    echo ""

    # Bot token
    while true; do
        ask "Bot token from @BotFather (e.g. 123456:ABC-DEF...):"
        read -r TOKEN < /dev/tty
        if [[ "$TOKEN" == *":"* ]] && [ ${#TOKEN} -gt 20 ]; then
            break
        fi
        err "Invalid token! Try again"
    done
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$TOKEN\"|" "$BOT_FILE"
    ok "Token saved"

    # Admin ID
    while true; do
        ask "Admin numeric ID from @userinfobot (e.g. 105455518):"
        read -r ADMINID < /dev/tty
        if [[ "$ADMINID" =~ ^[0-9]+$ ]]; then
            break
        fi
        err "Numbers only!"
    done
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $ADMINID        # admin numeric id|" "$BOT_FILE"
    ok "Admin ID saved"

    # Default panel capacity
    ask "Default max users per panel? (Enter = 200):"
    read -r MAXU < /dev/tty
    MAXU=${MAXU:-200}
    sed -i "s|^DEFAULT_PANEL_MAX_USERS = .*|DEFAULT_PANEL_MAX_USERS = $MAXU|" "$BOT_FILE"
    ok "Default panel capacity: $MAXU"

    # PSK
    ask "Panel PSK key (Enter = 123456 — must match the panel Secret):"
    read -r PSK < /dev/tty
    PSK=${PSK:-123456}
    sed -i "s|^DEFAULT_PSK = .*|DEFAULT_PSK = \"$PSK\"|" "$BOT_FILE"
    ok "PSK saved"

    make_service
    make_shortcut

    systemctl restart $SERVICE
    sleep 3
    echo ""
    if systemctl is-active --quiet $SERVICE; then
        ok "Bot installed and running!"
        echo ""
        journalctl -u $SERVICE -n 8 --no-pager
        echo ""
        info "Open Telegram and /start your bot now"
    else
        err "Bot failed to start! Log:"
        journalctl -u $SERVICE -n 15 --no-pager
    fi
    echo ""
    read -r -p "Press Enter to return to menu..." < /dev/tty
}

# ---------- Edit token ----------
edit_token() {
    if [ ! -f "$BOT_FILE" ]; then err "Bot is not installed!"; return; fi
    ask "New token:"
    read -r TOKEN < /dev/tty
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$TOKEN\"|" "$BOT_FILE"
    systemctl restart $SERVICE
    ok "Token updated and bot restarted"
    read -r -p "Press Enter..." < /dev/tty
}

# ---------- Edit admin ----------
edit_admin() {
    if [ ! -f "$BOT_FILE" ]; then err "Bot is not installed!"; return; fi
    ask "New admin numeric ID:"
    read -r ADMINID < /dev/tty
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $ADMINID        # admin numeric id|" "$BOT_FILE"
    systemctl restart $SERVICE
    ok "Admin updated and bot restarted"
    read -r -p "Press Enter..." < /dev/tty
}

# ---------- Update bot (settings preserved) ----------
update_bot() {
    if [ ! -f "$BOT_FILE" ]; then err "Bot is not installed!"; return; fi
    info "Reading current settings..."
    OLD_TOKEN=$(grep -m1 "^BOT_TOKEN" "$BOT_FILE" | sed -E 's/.*"(.*)".*/\1/')
    OLD_ADMIN=$(grep -m1 "^ADMIN_ID" "$BOT_FILE" | grep -oE "[0-9]+" | head -1)
    OLD_MAXU=$(grep -m1 "^DEFAULT_PANEL_MAX_USERS" "$BOT_FILE" | grep -oE "[0-9]+" | head -1)
    OLD_PSK=$(grep -m1 "^DEFAULT_PSK" "$BOT_FILE" | sed -E 's/.*"(.*)".*/\1/')
    cp "$BOT_FILE" /root/bot.py.bak
    download_bot
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$OLD_TOKEN\"|" "$BOT_FILE"
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $OLD_ADMIN        # admin numeric id|" "$BOT_FILE"
    [ -n "$OLD_MAXU" ] && sed -i "s|^DEFAULT_PANEL_MAX_USERS = .*|DEFAULT_PANEL_MAX_USERS = $OLD_MAXU|" "$BOT_FILE"
    [ -n "$OLD_PSK" ] && sed -i "s|^DEFAULT_PSK = .*|DEFAULT_PSK = \"$OLD_PSK\"|" "$BOT_FILE"
    systemctl restart $SERVICE
    sleep 2
    if systemctl is-active --quiet $SERVICE; then
        ok "Bot updated, settings preserved (backup: /root/bot.py.bak)"
    else
        err "New version failed — rolling back to previous version"
        cp /root/bot.py.bak "$BOT_FILE"
        systemctl restart $SERVICE
    fi
    read -r -p "Press Enter..." < /dev/tty
}

# ---------- Uninstall ----------
uninstall_bot() {
    warn "Are you sure you want to completely remove the bot? (y/n)"
    read -r CONF < /dev/tty
    if [ "$CONF" = "y" ]; then
        systemctl stop $SERVICE 2>/dev/null
        systemctl disable $SERVICE 2>/dev/null
        rm -f /etc/systemd/system/bot.service "$BOT_FILE" /root/bot.py.bak
        systemctl daemon-reload
        ok "Bot completely removed"
    else
        info "Cancelled"
    fi
    read -r -p "Press Enter..." < /dev/tty
}

# ---------- Menu ----------
menu() {
    banner
    if systemctl is-active --quiet $SERVICE 2>/dev/null; then
        echo -e "  Bot status: ${GREEN}${BOLD}[ RUNNING ]${NC}"
    else
        echo -e "  Bot status: ${RED}${BOLD}[ STOPPED / NOT INSTALLED ]${NC}"
    fi
    echo ""
    echo -e "  ${CYAN}1)${NC} Install / Reinstall bot"
    echo -e "  ${CYAN}2)${NC} Update bot (from GitHub — settings preserved)"
    echo -e "  ${CYAN}3)${NC} Edit bot token"
    echo -e "  ${CYAN}4)${NC} Edit admin ID"
    echo -e "  ${CYAN}5)${NC} Restart bot"
    echo -e "  ${CYAN}6)${NC} Bot status"
    echo -e "  ${CYAN}7)${NC} Live logs (exit: Ctrl+C)"
    echo -e "  ${CYAN}8)${NC} Uninstall bot"
    echo -e "  ${CYAN}0)${NC} Exit"
    echo ""
    echo -ne "${YELLOW}  Choose an option: ${NC}"
    read -r CHOICE < /dev/tty
    case $CHOICE in
        1) install_bot ;;
        2) update_bot ;;
        3) edit_token ;;
        4) edit_admin ;;
        5) systemctl restart $SERVICE && ok "Restarted"; sleep 1 ;;
        6) systemctl status $SERVICE --no-pager; read -r -p "Press Enter..." < /dev/tty ;;
        7) journalctl -u $SERVICE -f ;;
        8) uninstall_bot ;;
        0) clear; echo -e "${GREEN}Goodbye!${NC}"; exit 0 ;;
        *) err "Invalid option!"; sleep 1 ;;
    esac
}

# ---------- Start ----------
check_root
while true; do
    menu
done
