# Ivory Design Studio — Docker setup

The existing site design and contact-form database/admin behavior are preserved.
Successful contact submissions also send a branded visitor confirmation email.
The homepage chat now provides persisted human support, a five-minute automated
handoff, studio FAQs, and an optional server-side AI fallback.

## Local development — automatic reload

1. Install and start Docker Desktop (Docker Compose 2.24.4 or newer).
2. Open a terminal in this folder.
3. Build and start the development environment the first time:

   ```sh
   docker compose -f compose.yml -f compose.dev.yml up --build
   ```

4. Open <http://localhost:8000>. The Django admin is at <http://localhost:8000/admin/>.

Leave that terminal running while you edit. It starts the web server, Redis,
Celery worker, and Celery scheduler. The development override mounts this folder
into `/app` and explicitly starts Django's development server with its automatic
reloader enabled. The site is exposed only on your own computer.
Existing `db.sqlite3` data and uploaded `media` files stay in this folder.
Database migrations run automatically when the container starts.

- **Python changes:** save the file; Django restarts automatically. Wait for the
  server-ready message, then refresh the page. No rebuild is needed.
- **HTML, CSS, JavaScript, and image changes:** save and refresh the browser.
  This is server reload, not automatic browser refresh. If a stylesheet appears
  cached, use a hard refresh (`Cmd+Shift+R` on Mac, `Ctrl+Shift+R` on Windows/Linux).
- **Later starts:** use the same command without `--build`:

  ```sh
  docker compose -f compose.yml -f compose.dev.yml up
  ```

- **`requirements.txt` or Dockerfile changes:** rerun the first command with
  `--build`. These change the installed environment, not just the source code.
- **`.env` changes:** recreate the service using the command in the Gmail section
  below. Environment variables are loaded at container creation, not on code save.
- **Database schema changes:** create/apply migrations as usual; saving a model
  alone does not migrate the database. To apply existing migrations while running:

  ```sh
  docker compose -f compose.yml -f compose.dev.yml exec web python manage.py migrate
  ```

If port 8000 is busy, add `IVORY_DEV_PORT=8001` to `.env`, restart development, and
open <http://localhost:8001> instead.

Stop the site with `Ctrl+C`, then remove the stopped container with:

```sh
docker compose -f compose.yml -f compose.dev.yml down
```

## Create an admin login

```sh
docker compose -f compose.yml -f compose.dev.yml run --rm web python manage.py createsuperuser
```

## Live human support

1. Start the full Compose stack. Keep **web**, **redis**, **worker**, and **beat**
   running; the five-minute handoff is not a browser timer.
2. Sign in at <http://localhost:8000/admin/> and open **Live Support** in the top
   menu, or visit <http://localhost:8000/admin/support/>.
3. New visitor questions appear under **Waiting**. Open one, then **Claim / take
   over** or send a reply. A reply automatically claims the thread. Staff can take
   over a conversation currently handled by the automated assistant.
4. Use **Resolve** when finished. The next visitor message after resolution starts
   a new thread.

Messages, sender type, ordering, timestamps, assignment, unread state, handoff
state, and collected lead details are stored in Django. The automated assistant
starts only after the database deadline is due and no staff reply won the race.
Celery schedules the deadline; Celery Beat also reconciles overdue database rows
every 30 seconds so a broker/worker restart cannot permanently miss a handoff.

After taking over, the automated assistant clearly identifies itself, explains
how contact details will be used, asks for a name and phone separately, validates
Nepal/local and international formats, and permits corrections such as “change my
phone to +977…”. Staff can edit the name/phone on the conversation in Django admin.
Do not copy payment details, passwords, medical data, or unrelated personal data
into chat. The default `IVORY_SUPPORT_RETENTION_DAYS=90` automatically deletes
resolved conversations and their messages/lead details after 90 days. Set a
documented policy appropriate to your business and applicable law before launch.

Useful local settings in `.env`:

- `IVORY_SUPPORT_TIMEOUT_SECONDS=300` — keep 300 for the promised five minutes.
- `IVORY_SUPPORT_RATE_LIMIT=20` and `IVORY_SUPPORT_RATE_WINDOW=60` — shared
  Redis-backed per-session and per-IP abuse limits.
- `IVORY_SUPPORT_RETENTION_DAYS=90` — resolved-thread retention.
- `IVORY_TRUST_PROXY_HEADERS=false` — change to true only when a trusted proxy
  always overwrites `X-Forwarded-For`; otherwise clients could spoof IP identity.

## Run Django checks in Docker

```sh
docker compose -f compose.yml -f compose.dev.yml run --rm web python manage.py check
docker compose -f compose.yml -f compose.dev.yml run --rm web python manage.py test
```

## Future AWS deployment

`compose.dev.yml` is only for local editing. Do not use its source mount or Django
development server in AWS. The image defaults to Daphne/ASGI, but `compose.yml`
still mounts this local folder and SQLite, so it is **not** a complete production
deployment configuration. A normal AWS layout is: immutable web and Celery images
on ECS/Fargate (separate web, worker, and one beat service), ElastiCache Redis for
Channels/cache/Celery broker, RDS PostgreSQL for durable/concurrent data, an ALB
configured for WebSocket upgrades and idle timeouts, HTTPS, Secrets Manager, S3/
CloudFront for media/static files, `DEBUG=False`, and explicit allowed hosts/origins.
Run exactly one beat scheduler, use private networking/security groups, enable
database/Redis backups and monitoring, and deploy migrations as a controlled task.
Set `IVORY_TRUST_PROXY_HEADERS=true` only when the ALB/proxy chain is locked down
and overwrites forwarding headers. The email/OpenAI settings remain server secrets.

## Automated assistant — after human-support timeout

The **Ask Ivory** button first waits for a human team member. If no staff reply is
recorded within five minutes, the automated assistant takes over and works without
an API key. After the visitor voluntarily supplies contact details, it answers
questions about the studio's published services, portfolio, location/contact
details, team/client profile counts, social profiles, and how to start a project.
Pricing is quote-only by default; an owner-approved rate can enable indicative
area estimates. Final quotes, timelines, availability, and bookings require team
confirmation; the chat cannot book an appointment. The existing contact
form and confirmation email remain unchanged.

### Edit the business FAQs in Django admin — no API key required

1. Apply the new migration once (normal container startup also applies it):

   ```sh
   docker compose -f compose.yml -f compose.dev.yml exec web python manage.py migrate
   ```

   If the site is stopped, first run
   `docker compose -f compose.yml -f compose.dev.yml up -d`.
2. Sign in at <http://localhost:8000/admin/> as an owner/admin.
3. Open **Ivory → Chat business information → Ivory Design — public chat
   answers**, or go directly to
   <http://localhost:8000/admin/Ivory/businessinformation/1/change/>.
4. Edit the public information and click **Save**. The next question uses the
   updated values immediately—no restart/rebuild or OpenAI key is required.

The migration creates one settings record. It contains safe quote/appointment
guidance and the already-published city, **Kathmandu, Nepal**. It does **not**
invent a price, currency, detailed address, landmark, booking URL, or social
handle. No existing enquiry, project, team, or client record is overwritten.

- **Pricing:** leave **Pricing mode = Quote only** unless you want automatic
  estimates. To enable them, select **Estimate = rate × stated floor area in
  square feet**, then enter **Currency**, **Rate per sq ft**, and **Pricing
  scope**. Scope must explain exactly what the rate includes/excludes. The admin
  rejects missing currency/scope, zero/negative/non-finite rates, and invalid
  values. Pricing guidance is your public explanation or quote-only message.
  Even a saved rate is ignored while Quote only is selected.
- **Estimate rule:** one explicit positive area in sq ft × the owner-approved
  rate, rounded to two currency decimal places. For example, a visitor can ask
  “Cost for 1,000 sq ft?” No visitor-provided rate overrides your setting. Missing
  units, multiple areas, ranges, dimensions such as `10 × 20`, other units, and
  areas above 1,000,000 sq ft require clarification/a quote. There is no automatic
  unit conversion, tiered pricing, tax calculation, extra fee, or booking.
  If your pricing needs those rules, use Quote only. Estimates are clearly
  marked indicative and non-binding; the team must confirm scope and final cost.
- **Location / Nearby landmark:** enter verified public details. Missing values
  are acknowledged; “near me” never fabricates a distance or uses geolocation.
  These settings update chat answers, not unrelated page/footer text.
- **Appointment instructions / URL:** enter your actual request process and,
  optionally, an http(s) booking-page URL. Otherwise visitors are directed to
  `/contact/`. Chat never claims an appointment is booked or confirmed.
- **Public social profiles** at the bottom of the same edit page: add a platform
  and its verified handle and/or http(s) URL. One entry per platform is allowed;
  blank/unverified profiles are not guessed. URLs are shown as safe plain text
  in chat and can be copied. No remote content is fetched from these links.
- **Team counts:** edit **Ivory → Team members**. Chat counts only **Is active**
  profiles and uses the **Designation** text for architect/designer counts
  (whole words, case-insensitive). A dual designation counts in both groups;
  “Architectural Technician” is not assumed to be an architect. The reply says
  these are published profiles, not a verified complete staff headcount.
- **Client counts:** edit **Ivory → Clients**. Only **Is active** client profiles
  count—not contact enquiries, projects, or inactive entries. Chat calls this a
  showcase count, not a lifetime total of clients served. With no active profiles,
  it asks visitors to confirm with the studio rather than claiming zero clients.

All these questions are answered locally and still display progressively.
Try “Price per square foot?”, “How many architects and designers do you have?”,
“Nearby location?”, “How many clients have you worked with?”, “Book a
consultation”, and “What are your Instagram and Facebook handles?”. Keep secrets
and private customer data out of these public admin fields.

Broader interior-design questions can optionally use OpenAI. To enable this:

1. If you do not already have `.env`, copy `.env.example` to `.env`. **Do not
   overwrite an existing `.env` containing your email settings.**
2. Create a project API key in your **OpenAI Platform** account and enable API
   billing there. A ChatGPT subscription alone does not provide API billing.
   Add the key privately as `OPENAI_API_KEY` in `.env`. Never paste it into chat,
   source code, browser scripts, screenshots, or shared logs.
3. Keep `OPENAI_CHAT_MODEL=gpt-4.1-mini`, or select another Responses-compatible
   model available to your Platform project. Review model pricing and configure
   project usage/budget alerts and suitable rate limits before enabling public use.
4. Build once to install the added Python SDK and recreate the container:

   ```sh
   docker compose -f compose.yml -f compose.dev.yml up -d --build --force-recreate web
   ```

After later `.env` changes, recreate with the same command without `--build`.
To disable AI, clear `OPENAI_API_KEY` and recreate; FAQs continue to work. Outside
Docker, install `requirements.txt` and export these variables before starting
Django (Django does not read `.env` by itself).

Only the server reads the key. It calls the official Responses API with a focused
studio instruction, a bounded output, no tools, a 12-second timeout, and no
automatic retries. Missing keys, unrelated questions, API failures, or empty /
incomplete answers return useful studio/contact guidance. AI suggestions are
labelled and may be inaccurate; the studio must confirm all project commitments.
See the [official API quickstart](https://developers.openai.com/api/docs/quickstart?language=python).

### Progressive replies, persistence, and live delivery

Every visitor send is first stored through a same-origin, CSRF-protected HTTP
request with a client-generated idempotency key. WebSockets are deliberately
read-only and deliver new persisted messages/status changes in real time. On a
disconnect the browser reconnects with backoff and reloads database history, so
missed WebSocket events do not lose messages. The visitor socket is authorized by
an opaque, hashed browser-session identity; staff sockets require an active staff
login plus the Django support-view permission.

Automated and staff replies appear progressively. Reduced-motion users receive
immediate text; **Show available reply now** completes the current local animation.
Screen readers receive the finished message once. History restores immediately
instead of replaying old animations. All visitor/staff content is inserted with
`textContent`, never as HTML.

The optional OpenAI call remains server-side and uses the existing Responses API
integration with `store=False`, bounded input/output and no browser key. The
support flow calls it only after automated takeover, completed lead capture, and
no deterministic FAQ match. Provider failures/quota problems become honest local
guidance; raw provider errors and secrets are never sent to visitors. The legacy
`/chatbox/ask/` endpoint and mocked streaming tests remain for compatibility, but
the live support UI uses its persisted HTTP/WebSocket transport.

### AI not activating: minimal safe troubleshooting

**Confirmed during the current investigation:** the configured key matched the
running container, authenticated successfully, and could look up the selected
model. A minimal generation request returned `insufficient_quota` (HTTP 429).
This requires available **OpenAI Platform API billing/quota for the organization
and project that own the key**—it cannot be fixed by changing the widget or by
rebuilding Docker. Check Platform billing/credits and organization/project limits
privately, with the account owner if necessary. A ChatGPT subscription does not
fund API usage. Once quota is restored, try one ordinary design question again;
no container recreation is needed if the key and model stay the same.

- **FAQ versus AI:** Services/portfolio/contact/quotes/bookings intentionally use
  local FAQs even with a key. Test AI with “Suggest lighting for a small room” or
  “Which rug works with a dark sofa?” Genuine design questions about “how much
  light” or curtain length are no longer mistaken for prices/project timelines.
- **After editing `.env`:** run the following, keeping the existing Gmail values:

  ```sh
  docker compose -f compose.yml -f compose.dev.yml up -d --force-recreate web
  ```

  `docker compose restart` and Python auto-reload do not reload container
  environment values. A saved key that differs from the container needs this
  recreation, not a code change. Do not paste keys into the browser or logs.
- **Authentication / model access:** a rejected or revoked key needs replacement
  in `.env`; missing model permission needs a Responses-compatible model that
  the project can access. Then recreate the container using the command above.
- **Temporary rate limit / outage:** pause and retry later. Repeated retries
  cannot resolve exhausted quota. Server logs contain only allowlisted categories
  such as `billing_or_quota`, `authentication`, `model_access`, or `rate_limit`;
  the public UI only says AI guidance is unavailable and offers studio FAQs/contact.
- **Local site limit:** the live support default is 20 messages per minute for
  both the browser session and source IP. Its pause message is not a provider
  billing error. The legacy FAQ endpoint retains its separate 10/minute limit.

Avoid sharing `.env`, `docker inspect`, or expanded Compose configuration.
Use `docker compose -f compose.yml -f compose.dev.yml config --quiet` for safe
configuration validation.

### Privacy and safeguards

`POST /chatbox/support/message/` accepts only a message (1–600 characters) and
UUID idempotency key in an 8 KB JSON body. Staff replies are capped at 1,800
characters. Send/action endpoints require CSRF and same-origin checks. Redis
applies shared fixed-window limits to a hashed session identifier and hashed
source IP; deploy additional ALB/WAF limits for public abuse resistance. Phone
numbers are never included in public staff broadcasts or application logs.

Support transcripts and voluntarily supplied lead details are stored because
human staff need to reply and resume conversations. The widget says so before the
first send and explains phone use again during automated capture. Only authorized
staff can open the inbox; Django model permissions should be granted narrowly.
Resolved conversations are deleted after the configured retention period. Review
the text with legal/privacy owners, publish a privacy notice, define access/export/
deletion procedures, and verify backups do not retain data longer than intended.

When AI is enabled, only the current broader design question and public studio
instructions are sent to OpenAI—not the saved name, phone, contact enquiries, or
full support transcript. Requests use `store=False`, but that is not a promise of
zero provider retention. Review the [official data controls](https://developers.openai.com/api/docs/guides/your-data)
and your OpenAI project settings before enabling the optional fallback.

### Check the chat without sending live API requests

```sh
docker compose -f compose.yml -f compose.dev.yml config --quiet
docker compose -f compose.yml -f compose.dev.yml run --rm --no-deps --entrypoint python web manage.py test Ivory
```

Tests cover the support schema, permissions, session isolation/history, WebSocket
authorization/delivery, message ordering/idempotency, staff-vs-timeout races,
restart reconciliation, lead validation/correction, shared throttling, retention,
FAQ routing, optional/error fallbacks, and mocked Responses API calls, plus the
existing contact/email tests. Tests never call OpenAI or Gmail. For a fast handoff
smoke test, temporarily set `IVORY_SUPPORT_TIMEOUT_SECONDS=30` (the enforced safe
minimum), recreate the stack, send one message, and confirm that the identified
automated prompt appears after roughly 30 seconds. Restore 300 afterward.

Keyboard users can open the chat, use Enter to send, Shift+Enter for a new line,
and Escape to close. Frontend helpers can be tested with Node.js 18+:

```sh
node --test tests/chat-transport.test.cjs
```

Those tests cover progressive text, reduced motion, reveal/cancel controls,
split UTF-8/SSE frames, buffered fallback, and interrupted/malformed streams.

## Visitor confirmation email (Gmail)

By default, confirmations are printed to the server console and **are not sent**.
Each confirmation has HTML and plaintext versions and embeds the existing company
PNG logo, so the visitor does not need access to a hosted logo URL. The subject and
message are fixed; the visitor's submitted message is not copied into the email.

The MIME layout is `multipart/alternative` with a plaintext part and a
`multipart/related` HTML+PNG part. The HTML references the PNG's Content-ID; the
PNG is `image/png`, base64-encoded, and marked `inline`, with no filename or
separate attachment wrapper. Alt text and the text brand remain usable when
images are blocked. Some clients may still offer a download action for inline
images; the sender cannot control every client's UI. Previously received emails
do not change—inspect a newly generated confirmation after updating the app.

To enable live email:

1. Copy `.env.example` to `.env` in this folder.
2. Set `IVORY_GMAIL_ADDRESS` to Ivory Design's actual company Gmail or Google
   Workspace address. This same address is used to authenticate, send, and receive
   replies; the sender display name is **Ivory Design**.
3. Turn on 2-Step Verification for that Google account, then create an app password
   for this site using [Google's app-password instructions](https://support.google.com/accounts/answer/185833).
   Enter it in `IVORY_GMAIL_APP_PASSWORD`. Use an **app password**, not the account's
   normal password. Some managed accounts disallow app passwords; check with the
   account administrator if the option is unavailable.
4. Set `IVORY_EMAIL_MODE=smtp` and recreate the container:

   ```sh
   docker compose -f compose.yml -f compose.dev.yml up -d --force-recreate web
   ```

Docker Compose reads `.env` and passes these three values to Django. Gmail uses
`smtp.gmail.com:587` with STARTTLS, certificate verification, and a 10-second
network timeout. Missing credentials or an invalid sender address in SMTP mode
stop startup with a configuration error rather than silently enabling delivery.
No credentials are included in the repository or Docker image: `.env` and its
variants are ignored by both Git and Docker. Never paste the app password into
source files, screenshots, logs, or chat. Avoid sharing `docker compose config`
output after adding secrets; validate development configuration without exposing
values using `docker compose -f compose.yml -f compose.dev.yml config --quiet`.

Without Docker, export the same three environment variables before running Django;
Django itself does not automatically load `.env`. Restart Django after changing
them. Set the mode back to `console` for non-delivering local previews.

The form is saved first, exactly as before. Email is attempted synchronously after
the save; a delivery/asset error is logged with the enquiry ID and exception type,
without credentials or form contents. It does not delete the saved enquiry or
change the existing success message and redirect. There is no automatic retry or
delivery queue. After configuration, submit one real enquiry with an inbox you
control and check that inbox (including spam); Gmail inbox delivery cannot be
verified until the company account and app password are supplied.

Focused tests use Django's in-memory mail backend and never contact Gmail:

```sh
docker compose -f compose.yml -f compose.dev.yml run --rm web python manage.py test Ivory
```

### Spam and inbox placement

Fixing MIME improves logo rendering, not a guarantee of inbox placement. The
app keeps a clear From/Reply-To matching the configured company Gmail account,
an accurate subject, text+HTML bodies, a unique Message-ID using the sender's
domain (not a container hostname), and an `Auto-Submitted: auto-generated`
header. These headers do **not** authenticate the sender or override spam filters.

For a reliable production sending setup, use a company-owned custom domain
through an authenticated provider such as Google Workspace, and configure
**SPF, DKIM, and DMARC** in that domain's DNS. The authenticated domain must align
with the From domain. Google handles authentication for personal `@gmail.com`
addresses; you cannot add DNS records for gmail.com. Do not replace From with an
unverified custom-domain address or add fake authentication headers in code.
See [Google's sender guidelines](https://support.google.com/mail/answer/81126).

In Gmail, inspect a newly received message using **Show original** to check
SPF/DKIM/DMARC results (do not share private message contents or credentials).
Authentication failures, sender/domain reputation, recipient spam reports, and
unsolicited or high-volume traffic can affect placement. The exact reason for a
particular spam decision cannot be established from the logo screenshot alone.
AWS hosting by itself does not fix email reputation or domain authentication;
those must be configured with the email provider and domain owner at deployment.

### Services, team portfolios, and client logos

- **Admin → Services:** add a title, description, and optional image. Use **Order** to arrange services (lower numbers first) and **Is active** to publish or hide them. The Services navigation opens `/services/`.
- **Admin → Team members:** open a member and add their work in **Team portfolio entries**. Each entry supports a title, image, description, location, year, display order, and active setting. Entries can also be managed from **Team portfolio entries** in the admin sidebar. Visitors click a team card on About to open that member’s portfolio. Inactive members and portfolio entries are hidden.
- **Admin → Clients:** upload client logos/images, set their order, and enable **Is active**. Active logos appear at a medium size in a straight, continuously looping right-to-left marquee. Reduced-motion preferences show a static layout.

For another installation, apply the new tables with `python manage.py migrate` before serving the updated pages. Content checks: `python manage.py test Ivory.test_content_pages`.

### Homepage drawing animation

The hero draws a furnished two-level interior cutaway with a living area, kitchen, bedroom, bathroom, and open staircase with a small moving pencil, then signs “Ivory Design” at the lower right. It retains the warm background and existing navigation, headline, and project links. Once the pencil drawing and yellow signature finish, three painters arrive in their own vehicles: a loader truck from the left, an excavator from the right, and a pickup truck from the bottom. Each vehicle carries an Ivory Design label and a seated driver visible inside the cab. Doors open before boarding or dismounting and close before departure. All three painters use the same male character, hard hat, and Ivory Design workwear, with matching seated appearances. All three retain the same walking, waving, painting, and reversing sequence. They park with a little extra clearance, dismount, walk around the parked vehicles to the interior, wave to the visitor, paint, and wave goodbye. Each walks back to their own parked vehicle, boards, closes the door, and reverses along the arrival path through the original entry side. Head turns follow their travel direction and greetings use waves without speech bubbles. The pencil drawing and signature take about 54 seconds. After the first crew departs and a short hold, a second interior starts: a two-storey residence with upstairs study, bedroom and balcony, a downstairs lounge, dining area and kitchen, central stairs, and a landscaped courtyard. Each scene has its own 54-second pencil/signature timeline and repeats the complete vehicle and painter sequence. After the second crew departs, a third scene draws an overhead three-bedroom apartment with bathrooms, dining room, kitchen island, central lounge, and an entry terrace, then repeats the same full crew sequence. The three scenes play consecutively and loop continuously, pause when off screen, and show only the completed first interior for reduced-motion preferences. Choreography checks: `node tests/hero-drawing.test.cjs`. Artwork is in `templates/components/hero_drawing.html`; styling and timing are in `static/hero-drawing.css` and `static/hero-drawing.js`.

Interior artwork: `templates/components/interior_drawing.html` contains continuous pencil strokes; `templates/components/interior_paint.html` supplies matching layered colour fills.

Second-scene artwork: `templates/components/residence_drawing.html` and `templates/components/residence_paint.html`. Scene changes occur only after the full crew departure and hold; painter models and vehicles are shared between scenes.

Third-scene artwork: `templates/components/apartment_drawing.html` and `templates/components/apartment_paint.html`. The apartment starts after both preceding interiors finish, using the same small pencil and 54-second drawing/signature timing.
