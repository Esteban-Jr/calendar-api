#!/bin/bash
# One-time setup for push reminders (reminders while the app is closed).
# Run it on the server after deploying, with:
#   sudo bash /srv/calendar/app/scripts/setup-push.sh
#
# It:
#  1. makes a pair of push keys and adds them to /srv/calendar/.env
#     (only if they aren't there yet; a backup of .env is kept first),
#  2. installs a timer that runs `send_reminders` every minute,
#  3. restarts the calendar API so it picks up the keys.
# Safe to run again: it keeps existing keys and just reinstalls the timer.
set -euo pipefail

ENV_FILE=/srv/calendar/.env
[ "$(id -u)" = 0 ] || { echo "Please run with sudo." >&2; exit 1; }

# 1. Keys
if grep -q '^VAPID_PRIVATE_KEY=' "$ENV_FILE"; then
    echo "1/3 Push keys are already in $ENV_FILE, keeping them."
else
    read -rp "Contact email for the push services (Apple/Google may use it if something goes wrong): " email
    [ -n "$email" ] || { echo "An email is needed." >&2; exit 1; }
    cp -p "$ENV_FILE" "$ENV_FILE.bak-$(date +%Y%m%d-%H%M%S)"
    keys=$(calendar-manage make_push_keys)
    printf '\n# Push notifications (added by scripts/setup-push.sh)\n%s\nVAPID_SUBJECT=mailto:%s\n' "$keys" "$email" >> "$ENV_FILE"
    echo "1/3 Push keys added to $ENV_FILE (backup made next to it)."
fi

# 2. A timer that runs send_reminders every minute, as the calendar user.
cat > /etc/systemd/system/calendar-reminders.service <<'UNIT'
[Unit]
Description=Send due calendar reminders (push)
After=network.target postgresql.service

[Service]
Type=oneshot
User=calendar
Group=calendar
WorkingDirectory=/srv/calendar/app
EnvironmentFile=/srv/calendar/.env
ExecStart=/srv/calendar/venv/bin/python manage.py send_reminders
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true
UNIT

cat > /etc/systemd/system/calendar-reminders.timer <<'UNIT'
[Unit]
Description=Send due calendar reminders every minute

[Timer]
OnCalendar=*-*-* *:*:00
AccuracySec=1s

[Install]
WantedBy=timers.target
UNIT

systemctl daemon-reload
systemctl enable --now calendar-reminders.timer >/dev/null
echo "2/3 Timer installed: calendar-reminders.timer (every minute)."

# 3. Restart the API so it reads the new keys.
systemctl restart calendar
echo "3/3 Calendar API restarted."
echo
systemctl list-timers calendar-reminders.timer --no-pager | head -2
echo
echo "Done. Check it any time with:  systemctl status calendar-reminders.timer"
echo "See what it sent with:         journalctl -u calendar-reminders -n 20"
