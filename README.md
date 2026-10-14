# fsi-scraper

![Python](https://img.shields.io/badge/python-3.11%2B-3776ab?logo=python&logoColor=white)
![Postgres](https://img.shields.io/badge/postgres-16-336791?logo=postgresql&logoColor=white)
![Docker](https://img.shields.io/badge/container-non--root-2496ed?logo=docker&logoColor=white)
![tests](https://img.shields.io/badge/tests-32%20passing-3b6d11)

The US government wrote a Portuguese course in the 1970s and then left it on the internet for free. I turned it into a Postgres database. Five stages: find the files, download them, pull the dialogs out, load them, export a sample for the homelab. I can run any of them twice and nothing breaks, which I know because I did.

This is the data behind [Laboratório Brasil](https://github.com/CravenCraven/homelab-brasil). I wanted to learn DevOps and Kubernetes on something real, and I wanted to learn Brazilian Portuguese. This does both. It's a homelab, but I run it like production, because that's the part I'm here to learn: everything in Git, nothing applied by hand, containers that don't run as root. The books are fifty-year-old scans, the text layer is mostly right, and every lesson broke a different rule.

Write-up: [Scraping a 1970s language course into Postgres](https://projectpattie.com/blog/scraping-a-1970s-language-course-into-postgres/) · Homelab: [homelab-brasil](https://github.com/CravenCraven/homelab-brasil) · Build log: [projectpattie.com](https://projectpattie.com)

---

## Contents

- [How it works](#how-it-works)
- [Sources](#sources)
- [Database](#database)
- [Design decisions](#design-decisions)
- [Repo layout](#repo-layout)
- [Getting started](#getting-started)
- [Run it in a container](#run-it-in-a-container)
- [Security](#security)
- [Known issues](#known-issues)
- [Roadmap](#roadmap)
- [Write-ups](#write-ups)

---

## How it works

![The five stages of fsi-scraper](docs/pipeline.svg)

| Stage | What it does | What it produces |
|---|---|---|
| `discover` | Reads a course page and finds every downloadable file. Reads the file URLs, not the page layout, because layouts change and CDN paths don't. | A list of resources: 36 for FAST, 35 for Conversa Brasileira |
| `fetch` | Downloads each file into `data/raw/`. Streams in 64 KB chunks, writes to `.part`, checks the size against `Content-Length`, renames only when complete. Resumes an interrupted download with a `Range` request. | Files on disk, each with a SHA-256 |
| `parse` | Reads the text layer of the scanned PDFs and pulls out the dialogs. Tolerant of OCR mistakes: `LESSON3`, `81.` for `B1.`, a missing heading in lesson 30. | 30 lessons and 351 dialog lines for FAST |
| `load` | Writes resources, lessons and lines into Postgres. Every write is an upsert, and the file hash and size are recorded for every file on disk. | Four tables |
| `export` | Reads a small sample back out of the database as JSON. Deterministic: same data in, byte-identical file out. | `corpus-sample.json`, read by the homelab's demo page at build time |

Every stage is safe to run again. `fetch` skips files it has, `load` upserts, `export` writes the same bytes. The scraper waits one second between requests, identifies itself with a User-Agent that links here, and checks `robots.txt` before every fetch.

---

## Sources

| Course | Provider | What it is | License | Credit line |
|---|---|---|---|---|
| FSI Brazilian Portuguese FAST | US Foreign Service Institute, via [fsi-language-courses.org](https://www.fsi-language-courses.org/) | Two student books (1970s scans with a text layer) and 34 tapes. 30 lessons. | Public domain | FSI Brazilian Portuguese FAST, US Foreign Service Institute (public domain) |
| Conversa Brasileira | [COERLL](https://cob.coerll.utexas.edu/brazilpod/cob/), The University of Texas at Austin | Short filmed conversations with transcripts and translations. 35 lessons. | CC BY | Conversa Brasileira, COERLL, The University of Texas at Austin |

The license and credit live in the `course` table, so anything that shows a line of dialog can show the credit next to it. CC BY requires it.

Adding a source means writing one class that implements `parse` (files on a page) and optionally `follow` (more pages to visit). The crawl, the download, and the database don't change.

---

## Database

```mermaid
erDiagram
  course ||--o{ lesson : has
  lesson ||--o{ dialog_line : has
  course {
    text slug PK
    text title
    text provider
    text license
    text credit
  }
  resource {
    bigint id PK
    text url UK
    text course
    text kind
    text filename
    text sha256
    bigint fetched_bytes
    timestamptz discovered_at
  }
  lesson {
    bigint id PK
    text course FK
    integer number
    text location
    text title
  }
  dialog_line {
    bigint id PK
    bigint lesson_id FK
    integer seq
    text speaker
    text text
    text translation
    integer page
  }
```

- `resource.url` is unique. The URL comes off the page, never constructed, so it's the natural key and `discover` can run forever without duplicates.
- `resource.sha256` and `fetched_bytes` are empty until the file is on disk. One query tells me what's still missing.
- `dialog_line` rows are deleted and reinserted per lesson on every load, because a parser fix can change how many lines a lesson has.
- `ON DELETE CASCADE` on `lesson_id`: lines have no meaning without their lesson.

The schema is one file, `db/schema.sql`, and it's safe to apply twice.

---

## Design decisions

| Decision | Why | Trade-off |
|---|---|---|
| **Postgres, not SQLite** | One `DATABASE_URL` switches between the laptop and the cluster. Flashcards, the demo page and the slang database all read the same data. | A running database, even locally |
| **Read the CDN URLs, not the page tables** | Lesson and volume numbers are in the file paths. Tables get redesigned, object keys don't. | A new source needs its own URL patterns |
| **A lookup table for the 14 broken lesson titles** | The OCR mangled `Checking In` into `Checkingln`. Rules that fix that would break real words. Thirty titles from a book printed once is a table, not a rule. | Won't scale to a source that changes |
| **Write to `.part`, rename when complete** | A rename is one step. The real filename never points at half a file. | A failed run leaves a `.part` behind, on purpose, so the next run can resume it |
| **Resume with `Range`, start over on `200`** | New sources mean bigger files. Not every server honors ranges, so a `200` reply resets the hash and the file. | If the remote file changed between runs, a resumed file would be corrupt. Not a risk for archives from the 1970s. See known issues. |
| **Delete-then-insert for dialog lines** | There's no clean way to match old line 7 to new line 7 after a line is inserted. The whole load is one transaction, so there's no half state. | Line ids change on every load |
| **Export reads from Postgres, not from the parser** | The sample file is proof the whole chain worked. | One more query |
| **Files on disk, facts in the database** | 330 MB of audio in Postgres makes every backup huge. The table holds the path and the hash. | Two things to back up |
| **Multi-stage image, non-root** | Build tools don't ship. The scraper only writes to one folder, so it runs as `uid 1000`. | A little more Dockerfile |

---

## Repo layout

```
src/fsi_scraper/
├── cli.py              # the five commands, the Fetcher (delay, cache, robots.txt)
├── fetch.py            # download: stream, hash, .part, resume
├── parse_fast.py       # FSI FAST: dialogs out of the PDF text layer
├── parse_cob.py        # Conversa Brasileira: dialogs with translations
├── load.py             # upserts into Postgres, saves file hashes
├── export.py           # deterministic JSON sample
├── models.py           # Resource: one row per downloadable file
└── sources/
    ├── base.py         # CourseParser: parse() and follow()
    ├── fsi_fast.py     # one page, 36 files
    └── coerll_cob.py   # index page plus one page per lesson
db/schema.sql           # four tables, safe to apply twice
tests/                  # 32 tests: parsers, fetch, robots.txt, load
docs/pipeline.svg
Dockerfile              # two stages, runs as uid 1000
docker-compose.yml      # local Postgres for development and tests only
```

`data/` is where downloads land and it's in `.gitignore`. Nothing from the courses is committed.

---

## Getting started

### Prerequisites

- Python 3.11 or newer
- Docker, for the local Postgres
- Git

### Install

```bash
git clone git@github.com:CravenCraven/fsi-scraper.git
cd fsi-scraper
python3 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
```

### Start Postgres and create the tables

```bash
docker compose up -d
docker compose exec -T db psql -U postgres -d corpus < db/schema.sql
```

The default `DATABASE_URL` points at this database. Set the variable to point anywhere else.

### Run the pipeline

```bash
fsi-scraper discover --cache .cache
fsi-scraper fetch --kind pdf --cache .cache     # --kind audio for the tapes, ~330 MB
fsi-scraper parse
fsi-scraper load --cache .cache
fsi-scraper export --out corpus-sample.json
```

Every command takes `--course`. The default is `brazilian-portuguese-fast`; the other option is `conversa-brasileira`.

### Check it

```bash
ruff check .
pytest -q
```

The `load` tests need the Docker Postgres running. They use their own `corpus_test` database and skip if Postgres isn't there.

---

## Run it in a container

```mermaid
flowchart LR
  subgraph build [Build stage, thrown away]
    S[source] --> T[python -m build] --> W[wheel]
  end
  subgraph runtime [Runtime stage, ships]
    I[installed wheel] --> U[user scraper, uid 1000, /corpus]
  end
  W -->|only this crosses| I
```

```bash
docker build -t fsi-scraper:dev .
docker run --rm fsi-scraper:dev                                  # prints help
docker run --rm \
  -e DATABASE_URL=postgresql://postgres:postgres@host.docker.internal:5432/corpus \
  -v "$PWD/data:/corpus/data" \
  fsi-scraper:dev load
```

`ENTRYPOINT` is `fsi-scraper` and `CMD` is `--help`, so whatever follows the image name is the subcommand. One image runs every stage; the job supplies the command.

Inside a container `localhost` is the container, so the database address is `host.docker.internal` on a Mac and the service name on the cluster. That's why it's a variable.

The image is about 54 MB compressed. `docker run --rm --entrypoint id fsi-scraper:dev` prints `uid=1000(scraper)`.

---

## Security

| Area | Today | Planned |
|---|---|---|
| User | Non-root, `uid 1000`, no login shell, one writable folder | `readOnlyRootFilesystem` on the cluster |
| Image | Multi-stage: no compiler, no source, no pip cache in the runtime stage | Pin the base image digest, let Renovate bump it |
| Scan | Trivy: 0 findings in Python packages. 44 HIGH in the Debian base, none with a fix available yet | Rebuild on a schedule; fail CI on fixable findings |
| Secrets | None in the repo or the image. `DATABASE_URL` comes from the environment | Sealed Secrets on the cluster |
| Scraping | 1 s delay, honest User-Agent, `robots.txt` checked before every request | |
| Downloads | Size verified against `Content-Length`, SHA-256 stored | Compare `ETag` before resuming |

---

## Known issues

| Issue | Impact | Fix |
|---|---|---|
| A `5xx` from `robots.txt` is treated as "no rules" | The standard says treat it as "nothing allowed" until the server recovers | Check the status code and refuse on `5xx` |
| Resume trusts that the remote file hasn't changed | A file replaced on the server between runs would be glued to a stale partial | Store and compare `ETag` or `Last-Modified` |
| Schema is applied by hand with `psql` | Nobody is there to do that on the cluster | A migration step in the job, or an init container |
| No CI | Tests run when I remember to run them | GitHub Actions: ruff, pytest, Trivy, push to GHCR |
| Only runs on my Mac | The cluster has no image to pull yet | Push to GHCR, build for `amd64`, CronJob in `homelab-brasil` |

---

## Roadmap

**Now**
- [ ] Push the image to GHCR, built for `amd64`
- [ ] Database, volume and CronJob in [`homelab-brasil`](https://github.com/CravenCraven/homelab-brasil), as the first app in the `apps/base` layout
- [ ] First run on the cluster
- [ ] Runbook

**Next**
- [ ] CI: ruff, pytest, Trivy, push to GHCR on every merge
- [ ] Fetch the audio into its own volume
- [ ] `ETag` check before resuming
- [ ] Flashcard export (the Fichas tile)

**Later**
- [ ] A third source
- [ ] Flux image automation, so a new image deploys itself

---

## Write-ups

- [Scraping a 1970s language course into Postgres](https://projectpattie.com/blog/scraping-a-1970s-language-course-into-postgres/): the five stages, the OCR, the schema
- Part 2, putting it in a container and running it on the cluster: coming once it's running
