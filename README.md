# Calendar API

A REST API for personal calendars, built with Django REST Framework. Users keep their own events, share them with others (view only), and look up Colombian public holidays through an outside API.

**Live:**
- The calendar app built on it: https://calendar.206.189.176.206.sslip.io
- Interactive API docs (Swagger): https://calendar.206.189.176.206.sslip.io/api/docs/
- The app's code: https://github.com/Esteban-Jr/calendar-app

## Features

- Events with full CRUD, validation and token login
- Filter events by date range
- Friends: send a request by username, the other person accepts or declines
- Change your username once a week; friends are told "anna is now called annabel"
- Share an event with your friends: they get an invite to accept or decline, and it only shows in their calendar once they accept. They can read it; only the owner can change or delete it
- Reminders as push notifications, even when the app is closed (Web Push, sent by a job that runs every minute)
- Colombian public holidays, fetched from [Nager.Date](https://date.nager.at) and returned in this API's own format
- Time zone aware: times are stored in UTC and shown in `America/Bogota`
- Interactive API docs (Swagger UI) generated from the code
- Automated tests

## Endpoints

All endpoints except the login and the docs need the header `Authorization: Token <your token>`.

| Method | Path | What it does |
|---|---|---|
| POST | `/api-auth/` | Log in with `username` and `password`, get a token |
| POST | `/api/auth/register/` | Start creating an account (`username`, `email`, `password`). Emails a 6-digit code |
| POST | `/api/auth/verify/` | Confirm the code (`email`, `code`). Creates the account and returns a token |
| POST | `/api/auth/resend/` | Send a fresh sign-up code (`email`) |
| POST | `/api/auth/forgot/` | Email a password-reset code (`email`). Same answer whether or not the account exists |
| POST | `/api/auth/reset/` | Choose a new password (`email`, `code`, `password`). Signs out other devices |
| GET | `/api/events/` | List your events, plus shared events you've accepted |
| GET | `/api/events/?start=...&end=...` | Only events that overlap that date range |
| POST | `/api/events/` | Create an event |
| GET | `/api/events/{id}/` | Get one event. `shares` lists each person it's shared with and their answer (`waiting`, `accepted`, `declined`); `my_status` is yours |
| PUT / PATCH | `/api/events/{id}/` | Replace / change part of an event (owner only). People added to `shared_with` get an invite; people removed before answering are told it was cancelled |
| DELETE | `/api/events/{id}/` | Delete an event (owner only). People who accepted are told it was deleted, people who hadn't answered that it was cancelled |
| GET | `/api/events/invites/` | Events shared with me that I haven't answered yet, soonest first |
| POST | `/api/events/{id}/accept/` | Accept an invite: the event goes into my calendar. The owner is notified |
| POST | `/api/events/{id}/decline/` | Decline an invite: it never shows in my calendar. The owner is notified |
| POST | `/api/events/{id}/invite-again/` | Owner only: send a fresh invite to someone who declined (`username`) |
| GET | `/api/holidays/?year=2026` | Colombian public holidays for a year |
| GET | `/api/me/` | Who am I: `id`, `username`, `email`, and `next_username_change` (when I can change it again, or `null`) |
| PATCH | `/api/me/` | Change my username (`username`): same rules as signing up, once a week. Friends and pending friend requests are told, unless only the capitals changed |
| GET | `/api/friends/` | My friends, requests sent to me (`incoming`) and requests I sent (`outgoing`) |
| POST | `/api/friends/` | Send a friend request (`username`). If they already asked you, you become friends |
| POST | `/api/friends/{id}/accept/` | Accept a request sent to you |
| DELETE | `/api/friends/{id}/` | Decline, cancel or unfriend. Unfriending also stops sharing between you, both ways |
| GET | `/api/push/key/` | The public key a browser needs to turn on push (503 if push isn't set up) |
| POST | `/api/push/subscribe/` | Save this device's push subscription (`endpoint`, `keys`) |
| POST | `/api/push/unsubscribe/` | Stop pushing to a device (`endpoint`) |
| POST | `/api/events/{id}/leave/` | Remove a shared event you accepted from your calendar. The owner is notified |
| GET | `/api/notifications/` | My latest notifications (`message`, `read`...) and the `unread` count. Invites have an `event` id and `invite_status` (`waiting`, `accepted`, `declined` or `cancelled`) |
| POST | `/api/notifications/read/` | Mark all my notifications as read |
| GET | `/api/docs/` | Swagger UI |
| GET | `/api/schema/` | OpenAPI schema |

### An event

```json
{
  "id": 1,
  "title": "Chelsea vs Man United",
  "description": "",
  "location": "My Home",
  "start": "2026-10-31T07:30:00-05:00",
  "end": "2026-10-31T10:00:00-05:00",
  "owner": 1,
  "owner_username": "anna",
  "reminder": 30,
  "color": "blueberry",
  "shared_with": ["ben"]
}
```

- `owner`, `owner_username` and `id` are set by the server and cannot be sent by the client.
- `shared_with` is a list of usernames, and they must be your friends. Anyone else (or a username that does not exist) gives a 400.
- `color` is one of `strawberry`, `peach`, `vanilla`, `pistachio`, `mint`, `blueberry` (default), `lavender`, `bubblegum`.
- `reminder` is minutes before the start, from 0 to 10080 (one week).
- A time sent without an offset is read as Bogota time.

### Status codes

| Code | When |
|---|---|
| 200 | Read or update succeeded |
| 201 | Event created |
| 204 | Event deleted (no body) |
| 400 | Invalid input: `end` not after `start`, reminder out of range, missing or non-numeric `year` |
| 401 | No token, or an invalid one |
| 403 | You can see the event (it was shared with you) but you are not the owner |
| 404 | The event does not exist, or it is not yours or shared with you |
| 429 | Too many tries from one address (login, sign-up, emailed codes) |
| 502 | The holidays service is down or returned an error |

A stranger gets a 404 and not a 403 on purpose, so the API never confirms that someone else's event exists.

## Try it

```bash
# 1. Get a token
curl -X POST -d "username=anna&password=YOURPASSWORD" http://127.0.0.1:8000/api-auth/

# 2. Create an event
curl -X POST \
  -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"title":"Dentist","start":"2026-11-10T10:00:00-05:00","end":"2026-11-10T11:00:00-05:00"}' \
  http://127.0.0.1:8000/api/events/

# 3. Events in November
curl -H "Authorization: Token YOUR_TOKEN" \
  "http://127.0.0.1:8000/api/events/?start=2026-11-01T00:00:00&end=2026-11-30T23:59:59"

# 4. Ask ben to be friends (ben accepts with POST /api/friends/{id}/accept/)
curl -X POST \
  -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"username":"ben"}' http://127.0.0.1:8000/api/friends/

# 5. Invite ben to event 1 (he accepts with POST /api/events/1/accept/)
curl -X PATCH \
  -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"shared_with":["ben"]}' http://127.0.0.1:8000/api/events/1/
```

## Run it locally

Needs Python 3.12 or newer.

```bash
git clone https://github.com/Esteban-Jr/calendar-api.git
cd calendar-api
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Then open http://127.0.0.1:8000/api/docs/.

## Tests

```bash
python manage.py test
```

They cover: no token gives 401, `end` before `start` gives 400, a stranger gets 404, a shared user cannot delete an event (403), the sign-up and password-reset codes, and friends (requests, accepting, only sharing with friends, unfriending removes shares).

## Continuous integration and deployment

GitHub Actions (`.github/workflows/deploy.yml`) runs the tests on every pull request. After a merge to `main` it runs them again and, if they pass, deploys to the server. The SSH key it uses (the `DEPLOY_SSH_KEY` secret) can only run the server's `deploy calendar` command, which pulls the code, installs packages, runs migrations and restarts the API. It can't open a shell.

## Configuration

Settings come from environment variables. With none set, the app runs in development mode with SQLite.

| Variable | Meaning | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | insecure development key |
| `DEBUG` | `1` for debug mode, `0` for production | `1` |
| `ALLOWED_HOSTS` | Comma-separated host names | `127.0.0.1,localhost` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | Use PostgreSQL when `DB_NAME` is set | SQLite |
| `ALLOW_REGISTRATION` | `0` closes sign-up | `1` |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` | SMTP server for the emailed codes. With no `EMAIL_HOST`, emails are printed in the console | console |
| `DEFAULT_FROM_EMAIL` | The sender address | `My Calendar <no-reply@localhost>` |
| `VAPID_PUBLIC_KEY`, `VAPID_PRIVATE_KEY` | Push keys, made with `python manage.py make_push_keys`. Without them push is off | none |
| `VAPID_SUBJECT` | Contact for the push services, e.g. `mailto:me@example.com` | `mailto:no-reply@localhost` |

## Accounts

- A new account is only created after the emailed code is confirmed, so an abandoned sign-up leaves nothing behind but one row.
- Codes are 6 digits, last 15 minutes, work once, and die after 5 wrong tries. Only a keyed hash of a code is stored.
- A new code can be sent once a minute per address. Passwords must pass Django's validators (length, not too common, not all digits).
- "Forgot password" answers identically for unknown emails, so it cannot be used to find out who has an account.
- Resetting a password signs out every other device.
- Sign-up can be switched off with `ALLOW_REGISTRATION=0`.

## Notifications

- When someone removes an event you shared with them, you get a notification ("ben removed “Dinner” from their calendar"). When you delete an event, everyone it was shared with gets one ("anna deleted “Dinner”").
- They're saved (the app shows them in a list) and also pushed to the person's devices. The event's title and time are copied into the notification, since the event itself may be gone.
- Removing yourself only takes you off that event: the owner keeps it, and can share it with you again.
- A push problem never stops the action itself.

## Push reminders

- When someone turns on notifications, their browser subscribes with the push service (Apple, Google or Mozilla) and the app saves the subscription here.
- `python manage.py send_reminders` sends every reminder that is due, to the event owner's devices. On the server a systemd timer runs it every minute (`scripts/setup-push.sh` installs the timer and the keys).
- Each reminder is sent once per start time: `Event.reminder_sent_for` remembers it, so moving an event reminds again.
- The message uses the same wording and the same notification tag as the web app's own reminders, so a phone with the app open shows one notification, not two.
- Devices the push service reports as gone (404/410) are deleted. Only real push service addresses are accepted, so the server can't be made to send requests anywhere else.

## Design notes

- **Permissions:** the queryset only contains events you own or that were shared with you, and a custom `IsOwnerOrReadOnly` permission blocks writes from anyone who is not the owner.
- **Friends:** one row per pair (`from_user` → `to_user`, `accepted`), with database rules against duplicates and against friending yourself. Sending requests is rate-limited (60 an hour) so usernames can't be guessed in bulk.
- **Validation:** the serializer checks that `end` is after `start`, and on a `PATCH` it falls back to the saved values for any date that was not sent.
- **Integration:** the holidays endpoint validates the year before using it, times out after 5 seconds, and turns any failure of the outside service into a 502, since that is not the client's fault.

## Built with

Python 3.12, Django 6, Django REST Framework, drf-spectacular, requests, gunicorn, PostgreSQL.
