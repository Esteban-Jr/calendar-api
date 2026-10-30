# Calendar API

A REST API for personal calendars, built with Django REST Framework. Users keep their own events, share them with others (view only), and look up Colombian public holidays through an outside API.

## Features

- Events with full CRUD, validation and token login
- Filter events by date range
- Share an event with other users: they can read it, only the owner can change or delete it
- Colombian public holidays, fetched from [Nager.Date](https://date.nager.at) and returned in this API's own format
- Time zone aware: times are stored in UTC and shown in `America/Bogota`
- Interactive API docs (Swagger UI) generated from the code
- Automated tests

## Endpoints

All endpoints except the login and the docs need the header `Authorization: Token <your token>`.

| Method | Path | What it does |
|---|---|---|
| POST | `/api-auth/` | Log in with `username` and `password`, get a token |
| GET | `/api/events/` | List your events, plus events shared with you |
| GET | `/api/events/?start=...&end=...` | Only events that overlap that date range |
| POST | `/api/events/` | Create an event |
| GET | `/api/events/{id}/` | Get one event |
| PUT / PATCH | `/api/events/{id}/` | Replace / change part of an event (owner only) |
| DELETE | `/api/events/{id}/` | Delete an event (owner only) |
| GET | `/api/holidays/?year=2026` | Colombian public holidays for a year |
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
  "reminder": 30,
  "shared_with": [2]
}
```

- `owner` and `id` are set by the server and cannot be sent by the client.
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

# 4. Share event 1 with user 2 (view only)
curl -X PATCH \
  -H "Authorization: Token YOUR_TOKEN" -H "Content-Type: application/json" \
  -d '{"shared_with":[2]}' http://127.0.0.1:8000/api/events/1/
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

They cover: no token gives 401, `end` before `start` gives 400, a stranger gets 404, and a shared user cannot delete an event (403).

## Configuration

Settings come from environment variables. With none set, the app runs in development mode with SQLite.

| Variable | Meaning | Default |
|---|---|---|
| `SECRET_KEY` | Django secret key | insecure development key |
| `DEBUG` | `1` for debug mode, `0` for production | `1` |
| `ALLOWED_HOSTS` | Comma-separated host names | `127.0.0.1,localhost` |
| `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST` | Use PostgreSQL when `DB_NAME` is set | SQLite |

## Design notes

- **Permissions:** the queryset only contains events you own or that were shared with you, and a custom `IsOwnerOrReadOnly` permission blocks writes from anyone who is not the owner.
- **Validation:** the serializer checks that `end` is after `start`, and on a `PATCH` it falls back to the saved values for any date that was not sent.
- **Integration:** the holidays endpoint validates the year before using it, times out after 5 seconds, and turns any failure of the outside service into a 502, since that is not the client's fault.

## Built with

Python 3.12, Django 6, Django REST Framework, drf-spectacular, requests, gunicorn, PostgreSQL.
