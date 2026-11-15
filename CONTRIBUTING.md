# Contributing

How we work on the Calendar App. The same rules apply in both repos:

| Code | Repo | What it is |
|---|---|---|
| **BE** | `calendar-api` | Django REST API |
| **FE** | `calendar-app` | React + Vite web app |

Merging to `main` **deploys to production**, so everything goes through a reviewed pull request.

---

## 1. From ticket to merge

1. **Pick a ticket** from the Todo column on the project board. Assign it to yourself and move it to **In progress**.
2. **Create a branch** from an up-to-date `main` using the naming pattern (section 2).
3. **Commit** in small steps, each message using the pattern.
4. **Open a Draft PR** early. Fill in the template.
5. When it's finished, read your own diff top to bottom and check CI is green. Then click **Ready for review**, and the ticket moves to **In review**.
6. **Review:** reply to every comment, push fixes, and re-request review.
7. **Approved:** the ticket goes to **QA**. QA follows your "How to test it" steps.
8. **QA passed:** squash-merge. Check that the deploy went through, and move the ticket to **Done**.

## 2. Naming: branches, commits, PR titles

```
<SQUAD>/<REPO><issue#>/<description>
```

| Part | Values |
|---|---|
| SQUAD | `CO` 🗓️ Core (events, views, reminders, holidays, UI) · `SO` 👥 Social (friends, sharing, invites, notifications) · `PL` 🛡️ Platform (accounts, security, tests, CI/CD, performance) |
| REPO | `BE` calendar-api · `FE` calendar-app |
| issue# | The issue number **in this repo**. `BE12` means calendar-api#12. |

| Where | Rule | Example |
|---|---|---|
| Branch | Description in lowercase with hyphens | `CO/BE12/validate-event-dates` |
| Commit | Prefix + short, plain-English summary | `CO/BE12/return 400 for bad dates instead of crashing` |
| PR title | Prefix + descriptive title | `CO/BE12/Validate event dates: return 400 instead of a 500` |

- The squad comes from the ticket's `squad:*` label: `squad:core` → CO, `squad:social` → SO, `squad:platform` → PL.
- The **`naming` check** runs on every PR and fails if the branch, the title or any commit doesn't follow the pattern, or if the REPO code is for the other repo.
- Merges are **squash only**, so the PR title becomes the commit on `main`. Make it good.

## 3. Tickets

- **Use a form:** ✨ Feature, 🐛 Bug or 🧰 Task. Blank issues are turned off.
- **Labels:** exactly one `squad:*` label and one type label (`bug`, `enhancement`, `documentation`, `chore`, `security`, `tech-debt`).
- **Board:**
  - Columns: Backlog → Todo → In progress → In review → QA → Done
  - Fields: Size (S/M/L), Priority (P0–P3), Sprint
- **Ready rule:** a ticket only moves to **Todo** when it has acceptance criteria, a squad and a size.
- **Work that touches both repos** gets two linked issues, one BE and one FE. **BE merges first.**

## 4. Pull requests

- Fill in every section of the template. "n/a" is fine where something doesn't apply.
- **"How to test it"** must be steps someone else can follow without asking you.
- Aim for **under ~400 changed lines**. If it's bigger, split it into several PRs.
- One ticket per PR. Unrelated fixes get their own ticket.

## 5. Code review

**Comment prefixes:**

| Prefix | Meaning |
|---|---|
| `blocking:` | Must change before merge |
| `suggestion:` | Recommended, but you decide |
| `question:` | Help me understand |
| `nit:` | Tiny, optional |
| `praise:` | Good, keep doing this |

- Reviews happen within **1 working day**.
- **Reply to every comment.** "Done", "Fixed in abc123", or why you disagree are all fine. Then re-request review.
- Resolve a conversation only once it's really settled. All conversations must be resolved before merge.
- New commits dismiss earlier approvals.

## 6. Definition of Done

A ticket is **Done** when:
- [ ] The PR is approved and squash-merged
- [ ] CI is green and the deploy succeeded
- [ ] QA passed every acceptance criterion
- [ ] README or docs are updated, if behaviour or the API changed
- [ ] The ticket is closed and in **Done**

## 7. Standards for each repo

### BE (calendar-api)
- Every behaviour change comes with a test: `python manage.py test` passes.
- Bad input returns **400** with a clear message, never a 500.
- Model changes include their migration (`python manage.py makemigrations`).
- A change to an API response or URL updates the README endpoint table, and gets a linked FE issue.
- Never commit `.env`, `venv/`, `db.sqlite3` or `.DS_Store`.

### FE (calendar-app)
- `npm run lint` and `npm run build` pass.
- All API calls go through `src/api.js`.
- Check every change at **phone width** (~400px) and on desktop.
- Keep the accessibility basics: every button and field has a label, and Escape closes modals.
- Use relative `/api/...` URLs. Never hard-code a server address.
