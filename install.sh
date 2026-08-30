#!/bin/bash
# ============================================================
#   Qashang VPN Shop Bot — نصب یک‌خطی (One-Line Installer)
#   v4.0
# ============================================================
#   ⚠️ فقط این خط اول رو بعد از ساخت ریپو عوض کن:
#   به‌جای YOUR_USER/YOUR_REPO آدرس گیت‌هاب خودت رو بزار
# ============================================================
REPO_URL="https://raw.githubusercontent.com/javadtifusi-eng/Tifusi-Bot/main"

BOT_FILE="/root/bot.py"
SERVICE="bot"

# ---------- رنگ‌ها ----------
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
MAGENTA='\033[0;35m'
BLUE='\033[0;34m'
BOLD='\033[1m'
NC='\033[0m' # No Color

# ---------- بنر ----------
banner() {
    clear
    echo -e "${MAGENTA}${BOLD}"
    cat << 'EOF'
  _____ ___ _____ _   _ ____ ___ 
 |_   _|_ _|  ___| | | / ___|_ _|
   | |  | || |_  | | | \___ \ | | 
   | |  | ||  _| | |_| |___) || | 
   |_| |___|_|    \___/|____/___| 
          ____   ___ _____ 
         | __ ) / _ \_   _|
         |  _ \| | | || |  
         | |_) | |_| || |  
         |____/ \___/ |_|  
EOF
    echo -e "${NC}"
    echo -e "${CYAN}  🤖 Tifusi Bot — ربات فروش اشتراک VPN | نسخه 4.0${NC}"
    echo -e "${YELLOW}  پروتکل‌ها: L2TP / PPTP / IKEv2 / OpenVPN${NC}"
    echo -e "${GREEN}  ──────────────────────────────────────────────${NC}"
    echo ""
}

# ---------- ابزار ----------
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; }
info() { echo -e "${CYAN}ℹ️  $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
ask()  { echo -e "${MAGENTA}❓ $1${NC}"; }

check_root() {
    if [ "$EUID" -ne 0 ]; then
        err "باید با کاربر root اجرا کنی!"
        exit 1
    fi
}

# ---------- نصب پیش‌نیازها ----------
install_deps() {
    info "در حال نصب پیش‌نیازها... (چند دقیقه صبر کن)"
    apt update -y >/dev/null 2>&1
    apt install -y python3 python3-pip curl >/dev/null 2>&1
    pip3 install python-telegram-bot "python-telegram-bot[job-queue]" requests qrcode pillow --break-system-packages >/dev/null 2>&1 \
        || pip3 install python-telegram-bot "python-telegram-bot[job-queue]" requests qrcode pillow >/dev/null 2>&1
    if python3 -c "import telegram, requests, qrcode, PIL" 2>/dev/null; then
        ok "پیش‌نیازها نصب شدند"
    else
        err "نصب پیش‌نیازها کامل نشد — اینترنت سرور رو چک کن"
        exit 1
    fi
}

# ---------- دانلود آخرین نسخه ربات ----------
download_bot() {
    info "در حال دانلود آخرین نسخه ربات از گیت‌هاب..."
    curl -Ls "$REPO_URL/bot.py" -o "$BOT_FILE"
    if [ ! -s "$BOT_FILE" ] || ! python3 -m py_compile "$BOT_FILE" 2>/dev/null; then
        err "دانلود ربات ناموفق بود! آدرس گیت‌هاب (REPO_URL) رو چک کن"
        exit 1
    fi
    ok "ربات دانلود شد"
}

# ---------- ساخت سرویس ----------
make_service() {
    cat > /etc/systemd/system/bot.service << 'EOF'
[Unit]
Description=Qashang VPN Shop Bot
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
    ok "سرویس systemd ساخته و فعال شد"
}

# ---------- میانبر tifusi / qashang ----------
make_shortcut() {
    cp "$0" /usr/local/bin/tifusi 2>/dev/null || curl -Ls "$REPO_URL/install.sh" -o /usr/local/bin/tifusi
    chmod +x /usr/local/bin/tifusi
    ln -sf /usr/local/bin/tifusi /usr/local/bin/qashang 2>/dev/null
    ok "از این به بعد با دستور «tifusi» هر وقت خواستی این منو میاد! 🎩"
}

# ---------- نصب کامل ----------
install_bot() {
    banner
    echo -e "${BOLD}🚀 شروع نصب...${NC}"
    echo ""

    install_deps
    download_bot

    echo ""
    echo -e "${YELLOW}${BOLD}📝 حالا چند تا سؤال — یکی‌یکی جواب بده:${NC}"
    echo ""

    # توکن
    while true; do
        ask "توکن ربات از @BotFather (مثل 123456:ABC-DEF...):"
        read -r TOKEN < /dev/tty
        if [[ "$TOKEN" == *":"* ]] && [ ${#TOKEN} -gt 20 ]; then
            break
        fi
        err "توکن معتبر نیست! دوباره وارد کن"
    done
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$TOKEN\"|" "$BOT_FILE"
    ok "توکن ذخیره شد"

    # آیدی ادمین
    while true; do
        ask "آیدی عددی ادمین از @userinfobot (مثل 105455518):"
        read -r ADMINID < /dev/tty
        if [[ "$ADMINID" =~ ^[0-9]+$ ]]; then
            break
        fi
        err "فقط عدد وارد کن!"
    done
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $ADMINID        # آیدی عددی ادمین|" "$BOT_FILE"
    ok "آیدی ادمین ذخیره شد"

    # سقف پیش‌فرض پنل
    ask "سقف پیش‌فرض کاربر هر پنل؟ (Enter = 200):"
    read -r MAXU < /dev/tty
    MAXU=${MAXU:-200}
    sed -i "s|^DEFAULT_PANEL_MAX_USERS = .*|DEFAULT_PANEL_MAX_USERS = $MAXU|" "$BOT_FILE"
    ok "سقف پیش‌فرض: $MAXU"

    # PSK
    ask "کلید PSK پنل (Enter = 123456 — باید با Secret پنل یکی باشه):"
    read -r PSK < /dev/tty
    PSK=${PSK:-123456}
    sed -i "s|^DEFAULT_PSK = .*|DEFAULT_PSK = \"$PSK\"|" "$BOT_FILE"
    ok "PSK ذخیره شد"

    make_service
    make_shortcut

    systemctl restart $SERVICE
    sleep 3
    echo ""
    if systemctl is-active --quiet $SERVICE; then
        ok "ربات نصب و روشن شد! 🎉🎉"
        echo ""
        journalctl -u $SERVICE -n 8 --no-pager
        echo ""
        info "برو تو تلگرام ربات رو /start کن 🌹"
    else
        err "ربات بالا نیومد! لاگ:"
        journalctl -u $SERVICE -n 15 --no-pager
    fi
    echo ""
    read -r -p "Enter بزن برای برگشت به منو..." < /dev/tty
}

# ---------- ویرایش توکن ----------
edit_token() {
    if [ ! -f "$BOT_FILE" ]; then err "ربات نصب نیست!"; return; fi
    ask "توکن جدید:"
    read -r TOKEN < /dev/tty
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$TOKEN\"|" "$BOT_FILE"
    systemctl restart $SERVICE
    ok "توکن عوض شد و ربات ری‌استارت شد ✅"
    read -r -p "Enter..." < /dev/tty
}

# ---------- ویرایش ادمین ----------
edit_admin() {
    if [ ! -f "$BOT_FILE" ]; then err "ربات نصب نیست!"; return; fi
    ask "آیدی عددی ادمین جدید:"
    read -r ADMINID < /dev/tty
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $ADMINID        # آیدی عددی ادمین|" "$BOT_FILE"
    systemctl restart $SERVICE
    ok "ادمین عوض شد و ربات ری‌استارت شد ✅"
    read -r -p "Enter..." < /dev/tty
}

# ---------- آپدیت ربات (تنظیمات حفظ میشه) ----------
update_bot() {
    if [ ! -f "$BOT_FILE" ]; then err "ربات نصب نیست!"; return; fi
    info "خواندن تنظیمات فعلی..."
    OLD_TOKEN=$(grep -m1 "^BOT_TOKEN" "$BOT_FILE" | sed -E 's/.*"(.*)".*/\1/')
    OLD_ADMIN=$(grep -m1 "^ADMIN_ID" "$BOT_FILE" | grep -oE "[0-9]+" | head -1)
    OLD_MAXU=$(grep -m1 "^DEFAULT_PANEL_MAX_USERS" "$BOT_FILE" | grep -oE "[0-9]+" | head -1)
    OLD_PSK=$(grep -m1 "^DEFAULT_PSK" "$BOT_FILE" | sed -E 's/.*"(.*)".*/\1/')
    cp "$BOT_FILE" /root/bot.py.bak
    download_bot
    sed -i "s|^BOT_TOKEN = .*|BOT_TOKEN = \"$OLD_TOKEN\"|" "$BOT_FILE"
    sed -i "s|^ADMIN_ID = .*|ADMIN_ID = $OLD_ADMIN        # آیدی عددی ادمین|" "$BOT_FILE"
    [ -n "$OLD_MAXU" ] && sed -i "s|^DEFAULT_PANEL_MAX_USERS = .*|DEFAULT_PANEL_MAX_USERS = $OLD_MAXU|" "$BOT_FILE"
    [ -n "$OLD_PSK" ] && sed -i "s|^DEFAULT_PSK = .*|DEFAULT_PSK = \"$OLD_PSK\"|" "$BOT_FILE"
    systemctl restart $SERVICE
    sleep 2
    if systemctl is-active --quiet $SERVICE; then
        ok "ربات آپدیت شد و تنظیماتت حفظ شد 🎉 (بکاپ قبلی: /root/bot.py.bak)"
    else
        err "نسخه جدید مشکل داشت — نسخه قبلی برگشت"
        cp /root/bot.py.bak "$BOT_FILE"
        systemctl restart $SERVICE
    fi
    read -r -p "Enter..." < /dev/tty
}

# ---------- حذف کامل ----------
uninstall_bot() {
    warn "مطمئنی می‌خوای ربات رو کامل پاک کنی؟ (y/n)"
    read -r CONF < /dev/tty
    if [ "$CONF" = "y" ]; then
        systemctl stop $SERVICE 2>/dev/null
        systemctl disable $SERVICE 2>/dev/null
        rm -f /etc/systemd/system/bot.service "$BOT_FILE" /root/bot.py.bak
        systemctl daemon-reload
        ok "ربات کامل حذف شد 🗑"
    else
        info "لغو شد"
    fi
    read -r -p "Enter..." < /dev/tty
}

# ---------- منو ----------
menu() {
    banner
    if systemctl is-active --quiet $SERVICE 2>/dev/null; then
        echo -e "  وضعیت ربات: ${GREEN}${BOLD}🟢 روشن${NC}"
    else
        echo -e "  وضعیت ربات: ${RED}${BOLD}🔴 خاموش / نصب‌نشده${NC}"
    fi
    echo ""
    echo -e "  ${CYAN}1)${NC} 🚀 نصب / نصب مجدد ربات"
    echo -e "  ${CYAN}2)${NC} 🔄 آپدیت ربات (از گیت‌هاب — تنظیمات حفظ میشه)"
    echo -e "  ${CYAN}3)${NC} 🔑 ویرایش توکن"
    echo -e "  ${CYAN}4)${NC} 👤 ویرایش آیدی ادمین"
    echo -e "  ${CYAN}5)${NC} 🔁 ری‌استارت ربات"
    echo -e "  ${CYAN}6)${NC} 📊 وضعیت ربات"
    echo -e "  ${CYAN}7)${NC} 📜 مشاهده لاگ زنده (خروج: Ctrl+C)"
    echo -e "  ${CYAN}8)${NC} 🗑  حذف کامل ربات"
    echo -e "  ${CYAN}0)${NC} 🚪 خروج"
    echo ""
    echo -ne "${YELLOW}  یه عدد انتخاب کن: ${NC}"
    read -r CHOICE < /dev/tty
    case $CHOICE in
        1) install_bot ;;
        2) update_bot ;;
        3) edit_token ;;
        4) edit_admin ;;
        5) systemctl restart $SERVICE && ok "ری‌استارت شد ✅"; sleep 1 ;;
        6) systemctl status $SERVICE --no-pager; read -r -p "Enter..." < /dev/tty ;;
        7) journalctl -u $SERVICE -f ;;
        8) uninstall_bot ;;
        0) clear; echo -e "${GREEN}قشنگ منتظرته 🌹${NC}"; exit 0 ;;
        *) err "عدد درست وارد کن!"; sleep 1 ;;
    esac
}

# ---------- شروع ----------
check_root
while true; do
    menu
done
