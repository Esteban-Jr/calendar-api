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
- Share an event with your friends: they can read it, only the owner can change or delete it
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
| GET | `/api/events/` | List your events, plus events shared with you |
| GET | `/api/events/?start=...&end=...` | Only events that overlap that date range |
| POST | `/api/events/` | Create an event |
| GET | `/api/events/{id}/` | Get one event |
| PUT / PATCH | `/api/events/{id}/` | Replace / change part of an event (owner only) |
| DELETE | `/api/events/{id}/` | Delete an event (owner only) |
| GET | `/api/holidays/?year=2026` | Colombian public holidays for a year |
| GET | `/api/me/` | Who am I: `{"id": 1, "username": "anna"}` |
| GET | `/api/friends/` | My friends, requests sent to me (`incoming`) and requests I sent (`outgoing`) |
| POST | `/api/friends/` | Send a friend request (`username`). If they already asked you, you become friends |
| POST | `/api/friends/{id}/accept/` | Accept a request sent to you |
| DELETE | `/api/friends/{id}/` | Decline, cancel or unfriend. Unfriending also stops sharing between you, both ways |
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

# 5. Share event 1 with ben (view only)
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

## Accounts

- A new account is only created after the emailed code is confirmed, so an abandoned sign-up leaves nothing behind but one row.
- Codes are 6 digits, last 15 minutes, work once, and die after 5 wrong tries. Only a keyed hash of a code is stored.
- A new code can be sent once a minute per address. Passwords must pass Django's validators (length, not too common, not all digits).
- "Forgot password" answers identically for unknown emails, so it cannot be used to find out who has an account.
- Resetting a password signs out every other device.
- Sign-up can be switched off with `ALLOW_REGISTRATION=0`.

## Design notes

- **Permissions:** the queryset only contains events you own or that were shared with you, and a custom `IsOwnerOrReadOnly` permission blocks writes from anyone who is not the owner.
- **Friends:** one row per pair (`from_user` → `to_user`, `accepted`), with database rules against duplicates and against friending yourself. Sending requests is rate-limited (60 an hour) so usernames can't be guessed in bulk.
- **Validation:** the serializer checks that `end` is after `start`, and on a `PATCH` it falls back to the saved values for any date that was not sent.
- **Integration:** the holidays endpoint validates the year before using it, times out after 5 seconds, and turns any failure of the outside service into a 502, since that is not the client's fault.

## Built with

Python 3.12, Django 6, Django REST Framework, drf-spectacular, requests, gunicorn, PostgreSQL.
