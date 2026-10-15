---
name: app-check
description: >-
  Run the Dagobert Streamlit app for a check and take screenshots: a test server on a copy of
  data/ in tmp/rt, Playwright as a desktop and as a phone (412 x 915 portrait, 915 x 412
  landscape, phone user agent, touch), a restart after each code change, and the stop of the
  server together with the workers of the explorer pool. Use it to launch or run the app, after
  every change under src/dagobert/ui/ (a page, page.css, a figure of the app), and for UI
  screenshots in a review. Never use `dagobert app` for a check: it opens a browser window.
---

# Check the app

- For the app, run `DAGOBERT_DATA=$PWD/tmp/rt uv run streamlit run src/dagobert/ui/main.py
  --server.headless=true --server.address=localhost
  --server.port=8399` on a copy of `data/` and take screenshots with
  Playwright (`uv run --with playwright`, `launch(channel="chrome",
  args=["--password-store=basic"])`). The Chrome
  `--screenshot` flag fires before Streamlit renders. The default page (`Overview`) is served at `/`, a
  URL path for it shows "Page not found". `dagobert app` itself opens a browser
  window, do not use it for checks. `.streamlit/config.toml` gives a server started in the
  repository root the toolbar and the session lifetime of `dagobert app` and turns off the
  usage statistics. Without a `data/`, `uv run dagobert init --example --data tmp/rt` starts the
  example there. An empty or missing `tmp/rt` shows the page `Start a plan`: the server reads
  the directory on every run, so removing it starts that check again without a restart.
- A full-page screenshot needs the viewport grown to the scroll height of `stMain` first
  (`page.set_viewport_size` with `document.querySelector('[data-testid=stMain]').scrollHeight`):
  Streamlit scrolls inside the main section, so `full_page=True` alone takes one screen.
- The date input of Streamlit 1.65 (`stDateInput`) hides a native `input[type=date]`: `fill` it
  with an ISO date, then click (on a phone tap) a day of the calendar it opens
  (`[aria-label^="Friday, March 15, 1985"]`), else the value does not reach the server. The date
  of birth of the start page is a text field: `fill` it (`20.05.1986`) and press Enter.
- For the phone, take the screenshots with the user agent of a phone, `is_mobile=True`,
  `has_touch=True` and a viewport of 412 x 915 (portrait) or 915 x 412 (landscape): the CSS of
  `ui/page.css` keys on the width, on `pointer: coarse` and on `hover: none`, the Python
  branches on the user agent. `?mobile=1` on a desktop shows the Python branches of the phone
  (not the CSS) for the rest of the session, `?mobile=0` ends that.
- A page of `i18n_check.TRANSLATED` (rule `i18n`) needs the check in German too: `?lang=de` sets the
  language for the session (the query goes after the first run), and so does a context with
  `locale="de-DE"`, whose language the browser reports. The switch `Sprache · Language` ends the
  sidebar and keeps a choice in the cookie `dagobert-lang`, which a new session of the context
  reads: a fresh context starts without it.
- The Streamlit test server does not load an edited module again. Restart it after a code
  change. Stop it with `for p in $(fuser 8399/tcp 2>/dev/null); do pkill -P "$p"; kill "$p";
  done`: `fuser -k` alone leaves the workers of the explorer pool running. `pkill -f` and
  `pgrep -f` with its command line also match the calling shell, and a kill then ends that
  shell.
