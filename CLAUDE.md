# CLAUDE.md

Guidance for AI assistants (Claude Code and others) working in this repository.

## Repository overview

This is a personal fork of the **#100DaysOfCode challenge** template repo
(originally by @ka11away). It serves two purposes:

1. **Challenge tracking** — markdown logs, rules, FAQ, and resources for the
   100-days-of-code challenge, plus community translations under `intl/`.
2. **Project code** — small self-contained projects added over time. The main
   one is a **browser chess game** in `chess/`, a dependency-free PWA deployed
   to GitHub Pages.

There is no package manager, no build system, no test runner, and no linter
configured. Everything runs directly in the browser or as standalone scripts.

## Directory structure

```
.
├── README.md                  # Challenge intro and links (from upstream template)
├── log.md                     # Daily challenge log (owner's progress entries)
├── r1-log.md                  # Alternative "Round 1" rapid log
├── rules.md, FAQ.md, resources.md  # Challenge docs from upstream template
├── intl/                      # Community translations (bn, ca, ch, de, el, es,
│                              #   fr, it, ja, ko, no, pl, pt-br, ru, ua)
├── GoogleSlides.js            # Google Apps Script: generates Slides from Sheets data
├── StockDownload_Script.ipynb # Jupyter notebook: stock data download script
├── LIPollQuizAnalysis.ipynb   # Jupyter notebook: LinkedIn poll/quiz analysis
├── Untitled Diagram.drawio    # draw.io diagram file
├── .github/workflows/
│   └── deploy-chess-pages.yml # Deploys chess/ to GitHub Pages
└── chess/                     # The chess game (see below)
```

## The chess app (`chess/`)

A full-rules chess game written in **vanilla JavaScript, HTML, and CSS** —
no libraries, no build step, no modules/bundler. It is an installable,
offline-capable PWA.

### Architecture

Scripts are plain browser globals loaded in order by `index.html`
(`chess.js` → `ai.js` → `app.js`). Each file is wrapped in an IIFE with
`"use strict"` and exposes at most one global.

| File                   | Responsibility |
|------------------------|----------------|
| `index.html`           | Markup, layout, PWA meta tags, script load order |
| `style.css`            | All styling, board themes, responsive/mobile rules |
| `chess.js`             | Rules engine (`Chess` class): FEN parsing, legal move generation, castling, en passant, promotion, SAN, check/checkmate/stalemate |
| `ai.js`                | Computer opponent: minimax + alpha-beta pruning + piece-square tables, depth 1–3 (Easy/Medium/Hard), runs synchronously |
| `app.js`               | UI controller: rendering, input handling, game modes (hotseat vs AI), themes, undo, promotion picker, fullscreen |
| `sw.js`                | Service worker: precaches the app shell, serves cache-first for offline play |
| `manifest.webmanifest` | PWA manifest (name, icons, display mode) |
| `icon*.svg/png`, `apple-touch-icon.png` | App icons, including maskable variants |

### Key engine conventions (`chess.js`)

- Board is an 8×8 array indexed `[row][col]`; **row 0 = rank 8** (top),
  row 7 = rank 1; col 0 = file a, col 7 = file h.
- Pieces are plain objects `{ type: 'p'|'n'|'b'|'r'|'q'|'k', color: 'w'|'b' }`.
- Piece-square tables in `ai.js` are written from White's perspective with the
  same row-0-equals-rank-8 orientation.

### UI conventions (`app.js`)

- Piece glyphs use the *solid* Unicode chess characters for both colors,
  each suffixed with U+FE0E (variation selector-15) to force text
  presentation — this prevents phones from rendering them as color emoji.
  White vs. black is distinguished purely by CSS fill color. Preserve this
  when touching piece rendering.
- Mobile matters: the board sizes itself to the screen, touch targets are
  large, and safe-area insets are handled. Test changes at small viewports.
- Theme choice is persisted in `localStorage`.

### Service worker cache (`sw.js`)

The `CACHE` constant (e.g. `"chess-v3"`) versions the precache.
**When you add, remove, or rename any cached asset — or change existing
assets and want installed clients to pick them up — bump the cache version
and keep the `ASSETS` list in sync with the actual files.** Forgetting this
leaves offline/installed users on stale code.

### Correctness expectations

The move generator has been validated with
[perft](https://www.chessprogramming.org/Perft) against the standard
reference positions (start position, Kiwipete, positions 3–5) to depth 4.
There is no committed test harness — if you modify move generation or
legality logic in `chess.js`, re-run a perft check (a quick Node script
loading `chess.js` works, since it exports via a `global` shim) and confirm
the published node counts still match before committing.

### Running locally

No install step. Either open `chess/index.html` directly, or serve it
(required for the service worker to register):

```bash
cd chess
python3 -m http.server 8000
# visit http://localhost:8000
```

## Deployment

`.github/workflows/deploy-chess-pages.yml` deploys the `chess/` folder as the
site root to GitHub Pages. It triggers on pushes to `master`/`main` that touch
`chess/**` or the workflow file itself, and can be run manually via
`workflow_dispatch`. Pages enablement is automatic (`enablement: true`), so no
repo-settings toggle is needed. Only one deployment runs at a time; newer runs
cancel in-progress ones.

Implication: merging any chess change to `master` publishes it live.

## Development workflow and conventions

- **Default branch:** `master`. Work happens on feature branches merged via
  pull requests (recent history is PR merges with descriptive titles).
- **Commit messages:** imperative, descriptive one-liners, e.g.
  "Fix piece colors on mobile and size pieces/board to the screen".
- **No dependencies:** keep the chess app dependency-free and buildless. Do
  not introduce npm, bundlers, or frameworks for it.
- **Code style:** the existing JS uses double quotes, semicolons, 2-space
  indent, IIFE wrappers, and block comments at the top of each file
  explaining its role. Match this style; comment only non-obvious invariants
  (see the existing files for the expected density).
- **Docs:** `chess/README.md` documents features and file responsibilities —
  update it when adding user-visible features or new files to `chess/`.
- **Challenge files:** `log.md`, `r1-log.md`, `rules.md`, etc. are the
  owner's personal challenge tracking; don't rewrite them except when asked.
  `intl/` contains community translations of the upstream template — treat as
  read-only reference material unless a task is specifically about them.
- **Standalone scripts/notebooks:** `GoogleSlides.js` is a Google Apps Script
  (runs in the Apps Script environment, not Node). The `.ipynb` notebooks are
  one-off explorations; they have no supporting environment files in the repo.

## What to check before committing chess changes

1. Game still loads with no console errors (serve locally, don't just open
   the file, so the service worker path is exercised).
2. If engine logic changed: perft counts still match the reference positions.
3. If any cached asset changed/was added/removed: `sw.js` `ASSETS` list is
   current and `CACHE` version is bumped.
4. Mobile layout still works (narrow viewport, touch targets).
5. `chess/README.md` reflects any new feature or file.
