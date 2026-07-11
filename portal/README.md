# KR Portal — Kalilur Rahman

A self-contained, installable personal portal (PWA) for **Kalilur Rahman** —
Global IT Executive & AI Leader. No build step, no dependencies: plain HTML,
CSS and vanilla JavaScript.

## What's inside

| Section | Content |
| --- | --- |
| Hero + stat tiles | Headline, badges, and career-at-a-glance numbers |
| Executive summary | Three-paragraph professional narrative |
| Signature impact | Six measurable outcome cards (GCC scale-up, budget, testing, margin…) |
| Career | Timeline: TCS/Cognizant → Accenture → Novartis → Strategic Advisor |
| Frameworks | ACUITAS (AI Quality Engineering) and CLARITY (AI Product Management) |
| Digital ecosystem | Searchable, filterable directory of the 80+ app portfolio — including the chess PWA in this repo |
| Books | Python Data Visualisation Essentials Guide · Science of Selenium · Innovations in Testing |
| Recommendations | Six peer quotes from Novartis, Accenture, Aviva and Arm leaders |
| Awards | Thinkers360 #3, Innovative CIO, IT NEXT100, eLets Pharma, Kaggle Legacy Grandmaster, Addo Agnitio |
| Connect | Email plus all public profiles (LinkedIn, GitHub, Kaggle, Amazon, Scholar…) |

## Features

- **Installable PWA** — manifest + service worker; works offline after first visit.
- **Light/dark theme** — follows system preference, toggleable, persisted.
- **Live search & category filters** over the app directory.
- **Scrollspy navigation**, reveal-on-scroll animations, reduced-motion support.
- **Single source of truth** — all content lives in [`data.js`](data.js); edit it to update the portal.

## Content sources

Compiled from public profiles: [kalilurrahman.com](https://kalilurrahman.com),
the [KR Knowledge Hub](https://kalilurrahman.github.io/KR_Knowledge_Hub.html),
[LinkedIn](https://www.linkedin.com/in/kalilurrahman/) and
[Linktree](https://linktr.ee/kalilur.rahman).

## Local development

```bash
npx http-server portal   # or: python3 -m http.server -d portal
```

## Deployment

Deployed by `.github/workflows/deploy-pages.yml`: the portal is served at the
repository's GitHub Pages root, and the chess game at `/chess/`.
