# ♞ Chess

A clean, dependency-free chess game that runs entirely in the browser. No build
step, no libraries — just open `index.html` and play.

## Features

- **Full chess rules** — legal move generation including castling, en passant,
  pawn promotion, check, checkmate, and stalemate.
- **Two ways to play** — local two-player (hotseat) or against a built-in
  computer opponent.
- **Adjustable AI** — Easy / Medium / Hard, powered by minimax with alpha-beta
  pruning and piece-square tables. Choose whether the computer plays White or
  Black.
- **Polished UI** — move hints, last-move and check highlighting, captured-piece
  trays, algebraic move list, board flip, and undo.
- **Color themes** — Forest, Wood, Ocean, Slate, Berry, and Sunset schemes,
  derived from the base palette. Your choice is remembered between visits.
- **Installable PWA** — add it to your home screen / desktop and it runs as a
  standalone, fullscreen app that **works offline** (service worker caches the
  app shell).
- **Mobile-friendly** — responsive board that fits any screen, large touch
  targets, safe-area handling for notches, and auto-fullscreen on first tap.
- **Promotion picker** — choose queen, rook, bishop, or knight when a pawn
  reaches the back rank.
- **Keyboard shortcuts** — `Esc` to deselect, `Ctrl/Cmd+Z` to undo.

## Play

Open `index.html` in any modern browser. To serve it locally:

```bash
cd chess
python3 -m http.server 8000
# then visit http://localhost:8000
```

Click a piece to select it; legal destinations are marked with dots (rings for
captures). Click a highlighted square to move.

## Project structure

| File         | Responsibility                                              |
|--------------|-------------------------------------------------------------|
| `index.html` | Markup and layout                                           |
| `style.css`  | Styling and board theme                                     |
| `chess.js`   | Rules engine: move generation, legality, SAN, game status   |
| `ai.js`      | Computer opponent (minimax + alpha-beta + evaluation)       |
| `app.js`     | UI controller wiring the engine and AI to the DOM           |

## Correctness

The move generator is validated with [perft](https://www.chessprogramming.org/Perft)
(move-path enumeration) against the standard reference positions — the starting
position, "Kiwipete", and positions 3–5 — matching the published node counts
through depth 4. This exercises castling, en passant, promotions, pins,
discovered checks, and checkmate/stalemate detection.
