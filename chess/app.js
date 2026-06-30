/*
 * app.js — UI controller binding the Chess engine and AI to the DOM.
 */

(function () {
  "use strict";

  const GLYPH = {
    w: { k: "♔", q: "♕", r: "♖", b: "♗", n: "♘", p: "♙" },
    b: { k: "♚", q: "♛", r: "♜", b: "♝", n: "♞", p: "♟" },
  };

  const boardEl = document.getElementById("board");
  const turnLabel = document.getElementById("turnLabel");
  const messageEl = document.getElementById("message");
  const moveListEl = document.getElementById("moveList");
  const promotionEl = document.getElementById("promotion");
  const capturedByWhiteEl = document.getElementById("capturedByWhite");
  const capturedByBlackEl = document.getElementById("capturedByBlack");

  let game = new Chess();
  let selected = null; // {row, col}
  let legalForSelected = [];
  let flipped = false;
  let lastMove = null; // {from, to}
  let mode = "human"; // 'human' | 'ai'
  let aiColor = "b";
  let aiLevel = 2;
  let gameOver = false;
  let pendingPromotion = null; // {from, to, color}
  let thinking = false;

  /* ------------------------- Rendering ------------------------- */

  function render() {
    boardEl.innerHTML = "";
    const rows = flipped ? [...Array(8).keys()].reverse() : [...Array(8).keys()];
    const cols = flipped ? [...Array(8).keys()].reverse() : [...Array(8).keys()];

    const kingInCheck = game.inCheck(game.turn) ? game.findKing(game.turn) : null;

    for (const r of rows) {
      for (const c of cols) {
        const sq = document.createElement("div");
        const light = (r + c) % 2 === 0;
        sq.className = "square " + (light ? "light" : "dark");
        sq.dataset.row = r;
        sq.dataset.col = c;

        if (lastMove &&
            ((lastMove.from.row === r && lastMove.from.col === c) ||
             (lastMove.to.row === r && lastMove.to.col === c))) {
          sq.classList.add("last-move");
        }
        if (selected && selected.row === r && selected.col === c) {
          sq.classList.add("selected");
        }
        if (kingInCheck && kingInCheck.row === r && kingInCheck.col === c) {
          sq.classList.add("in-check");
        }

        // Coordinate labels on edges
        if (c === (flipped ? 7 : 0)) {
          const rank = document.createElement("span");
          rank.className = "coord rank";
          rank.textContent = 8 - r;
          sq.appendChild(rank);
        }
        if (r === (flipped ? 0 : 7)) {
          const file = document.createElement("span");
          file.className = "coord file";
          file.textContent = String.fromCharCode("a".charCodeAt(0) + c);
          sq.appendChild(file);
        }

        const piece = game.board[r][c];
        if (piece) {
          const span = document.createElement("span");
          span.className = "piece " + (piece.color === "w" ? "white" : "black");
          span.textContent = GLYPH[piece.color][piece.type];
          sq.appendChild(span);
        }

        // Move hints
        const hint = legalForSelected.find((m) => m.to.row === r && m.to.col === c);
        if (hint) {
          const dot = document.createElement("span");
          dot.className = hint.capture ? "hint capture-hint" : "hint move-hint";
          sq.appendChild(dot);
        }

        sq.addEventListener("click", () => onSquareClick(r, c));
        boardEl.appendChild(sq);
      }
    }

    updateStatus();
    renderCaptured();
  }

  function renderCaptured() {
    // Count captured pieces by comparing to a full set.
    const full = { p: 8, n: 2, b: 2, r: 2, q: 1 };
    const counts = { w: {}, b: {} };
    for (let r = 0; r < 8; r++)
      for (let c = 0; c < 8; c++) {
        const p = game.board[r][c];
        if (p && p.type !== "k") {
          counts[p.color][p.type] = (counts[p.color][p.type] || 0) + 1;
        }
      }
    const order = ["q", "r", "b", "n", "p"];
    const build = (color) => {
      let html = "";
      for (const t of order) {
        const missing = full[t] - (counts[color][t] || 0);
        for (let i = 0; i < missing; i++) html += GLYPH[color][t];
      }
      return html;
    };
    // captured BY white = black pieces missing
    capturedByWhiteEl.textContent = build("b");
    capturedByBlackEl.textContent = build("w");
  }

  function updateStatus() {
    const colorName = game.turn === "w" ? "White" : "Black";
    if (gameOver) {
      // message already set by endGame
      return;
    }
    turnLabel.textContent = colorName + " to move";
    if (game.inCheck(game.turn)) {
      messageEl.textContent = colorName + " is in check.";
      messageEl.className = "message check";
    } else if (thinking) {
      messageEl.textContent = "Computer is thinking…";
      messageEl.className = "message";
    } else {
      messageEl.textContent = "";
      messageEl.className = "message";
    }
  }

  /* ------------------------- Interaction ------------------------- */

  function onSquareClick(row, col) {
    if (gameOver || thinking) return;
    if (mode === "ai" && game.turn === aiColor) return;

    const piece = game.board[row][col];

    if (selected) {
      // Clicking a legal destination?
      const move = legalForSelected.find((m) => m.to.row === row && m.to.col === col);
      if (move) {
        if (move.promotion) {
          openPromotion(selected, { row, col }, game.turn);
        } else {
          doMove(selected, { row, col });
        }
        return;
      }
      // Reselect own piece
      if (piece && piece.color === game.turn) {
        select(row, col);
        return;
      }
      // Otherwise deselect
      clearSelection();
      render();
      return;
    }

    if (piece && piece.color === game.turn) {
      select(row, col);
    }
  }

  function select(row, col) {
    selected = { row, col };
    legalForSelected = game.legalMovesFrom(row, col);
    render();
  }

  function clearSelection() {
    selected = null;
    legalForSelected = [];
  }

  function doMove(from, to, promotion) {
    const info = game.move(from, to, promotion);
    if (!info) return;
    lastMove = { from, to };
    clearSelection();
    addMoveToHistory(info);
    render();

    const status = game.gameStatus();
    if (status !== "ongoing") {
      endGame(status);
      return;
    }

    // AI reply
    if (mode === "ai" && game.turn === aiColor) {
      scheduleAiMove();
    }
  }

  function scheduleAiMove() {
    thinking = true;
    updateStatus();
    // defer so the UI repaints "thinking" before the (blocking) search.
    setTimeout(() => {
      const move = ChessAI.chooseMove(game, aiLevel);
      thinking = false;
      if (!move) {
        const status = game.gameStatus();
        endGame(status === "checkmate" ? "checkmate" : "stalemate");
        return;
      }
      const info = game.move(move.from, move.to, move.promotion || "q");
      lastMove = { from: move.from, to: move.to };
      addMoveToHistory(info);
      render();
      const status = game.gameStatus();
      if (status !== "ongoing") endGame(status);
    }, 180);
  }

  /* ------------------------- Promotion ------------------------- */

  function openPromotion(from, to, color) {
    pendingPromotion = { from, to, color };
    promotionEl.innerHTML = "";
    for (const t of ["q", "r", "b", "n"]) {
      const btn = document.createElement("button");
      btn.className = "promo-piece " + (color === "w" ? "white" : "black");
      btn.textContent = GLYPH[color][t];
      btn.title = { q: "Queen", r: "Rook", b: "Bishop", n: "Knight" }[t];
      btn.addEventListener("click", () => {
        promotionEl.classList.add("hidden");
        const p = pendingPromotion;
        pendingPromotion = null;
        doMove(p.from, p.to, t);
      });
      promotionEl.appendChild(btn);
    }
    promotionEl.classList.remove("hidden");
  }

  /* ------------------------- Move history ------------------------- */

  function addMoveToHistory(info) {
    if (info.color === "w" || (game.history.length && game.history[game.history.length - 1].move === info)) {
      // Determine whose move it was from the piece color we moved.
    }
    const movedColor = game.turn === "w" ? "b" : "w"; // turn already switched
    const items = moveListEl.children;
    if (movedColor === "w") {
      const li = document.createElement("li");
      const num = Math.ceil(game.history.length / 2);
      li.innerHTML = `<span class="moveno">${num}.</span>` +
        `<span class="san white-san">${info.san}</span>` +
        `<span class="san black-san"></span>`;
      moveListEl.appendChild(li);
    } else {
      let li = items[items.length - 1];
      if (!li) {
        li = document.createElement("li");
        const num = Math.ceil(game.history.length / 2);
        li.innerHTML = `<span class="moveno">${num}.</span>` +
          `<span class="san white-san">…</span>` +
          `<span class="san black-san"></span>`;
        moveListEl.appendChild(li);
      }
      li.querySelector(".black-san").textContent = info.san;
    }
    moveListEl.scrollTop = moveListEl.scrollHeight;
  }

  function rebuildHistory() {
    moveListEl.innerHTML = "";
    // Replay sans from stored history.
    const sans = game.history.map((h) => h.san).filter(Boolean);
    for (let i = 0; i < sans.length; i += 2) {
      const li = document.createElement("li");
      const num = i / 2 + 1;
      li.innerHTML = `<span class="moveno">${num}.</span>` +
        `<span class="san white-san">${sans[i] || ""}</span>` +
        `<span class="san black-san">${sans[i + 1] || ""}</span>`;
      moveListEl.appendChild(li);
    }
    moveListEl.scrollTop = moveListEl.scrollHeight;
  }

  /* ------------------------- Game end ------------------------- */

  function endGame(status) {
    gameOver = true;
    const moverLost = game.turn === "w" ? "White" : "Black";
    const winner = game.turn === "w" ? "Black" : "White";
    if (status === "checkmate") {
      turnLabel.textContent = "Checkmate";
      messageEl.textContent = `${winner} wins by checkmate. 🏆`;
      messageEl.className = "message win";
    } else if (status === "stalemate") {
      turnLabel.textContent = "Stalemate";
      messageEl.textContent = "Draw by stalemate.";
      messageEl.className = "message draw";
    } else {
      turnLabel.textContent = "Draw";
      messageEl.textContent = "Draw (insufficient material or 50-move rule).";
      messageEl.className = "message draw";
    }
  }

  /* ------------------------- Controls ------------------------- */

  function newGame() {
    game = new Chess();
    selected = null;
    legalForSelected = [];
    lastMove = null;
    gameOver = false;
    thinking = false;
    pendingPromotion = null;
    promotionEl.classList.add("hidden");
    moveListEl.innerHTML = "";
    render();
    // If AI plays white, let it open.
    if (mode === "ai" && aiColor === "w") {
      scheduleAiMove();
    }
  }

  function undo() {
    if (thinking) return;
    // In AI mode, undo a full move pair so it's the human's turn again.
    const steps = mode === "ai" ? 2 : 1;
    let undone = false;
    for (let i = 0; i < steps; i++) {
      if (game.undo()) undone = true;
      else break;
    }
    if (!undone) return;
    gameOver = false;
    selected = null;
    legalForSelected = [];
    const h = game.history[game.history.length - 1];
    lastMove = h ? { from: h.move.from, to: h.move.to } : null;
    rebuildHistory();
    render();
  }

  document.getElementById("newGameBtn").addEventListener("click", newGame);
  document.getElementById("undoBtn").addEventListener("click", undo);
  document.getElementById("flipBtn").addEventListener("click", () => {
    flipped = !flipped;
    render();
  });

  // Mode toggle
  document.getElementById("modeToggle").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-mode]");
    if (!btn) return;
    setActive("modeToggle", btn);
    mode = btn.dataset.mode;
    document.getElementById("aiOptions").classList.toggle("hidden", mode !== "ai");
    newGame();
  });

  document.getElementById("aiColorToggle").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-color]");
    if (!btn) return;
    setActive("aiColorToggle", btn);
    aiColor = btn.dataset.color;
    newGame();
  });

  document.getElementById("aiLevelToggle").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-level]");
    if (!btn) return;
    setActive("aiLevelToggle", btn);
    aiLevel = parseInt(btn.dataset.level, 10);
  });

  function setActive(containerId, btn) {
    const container = document.getElementById(containerId);
    container.querySelectorAll(".seg").forEach((b) => b.classList.remove("active"));
    btn.classList.add("active");
  }

  // Keyboard: Esc clears selection, Ctrl+Z undo.
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      clearSelection();
      render();
    } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z") {
      e.preventDefault();
      undo();
    }
  });

  /* ------------------------- Fullscreen ------------------------- */

  function fsElement() {
    return (
      document.fullscreenElement ||
      document.webkitFullscreenElement ||
      null
    );
  }

  function enterFullscreen() {
    const el = document.documentElement;
    const req =
      el.requestFullscreen ||
      el.webkitRequestFullscreen ||
      el.webkitRequestFullScreen;
    if (req) {
      try {
        const p = req.call(el);
        if (p && p.catch) p.catch(() => {});
      } catch (_) {
        /* fullscreen may be blocked; ignore */
      }
    }
  }

  function exitFullscreen() {
    const exit = document.exitFullscreen || document.webkitExitFullscreen;
    if (exit) {
      try {
        exit.call(document);
      } catch (_) {
        /* ignore */
      }
    }
  }

  function toggleFullscreen() {
    if (fsElement()) exitFullscreen();
    else enterFullscreen();
  }

  function updateFsLabel() {
    const btn = document.getElementById("fullscreenBtn");
    if (!btn) return;
    const active = !!fsElement();
    document.body.classList.toggle("fs", active);
    btn.textContent = active ? "⛶ Exit Fullscreen" : "⛶ Fullscreen";
  }

  const fsBtn = document.getElementById("fullscreenBtn");
  if (fsBtn) fsBtn.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", updateFsLabel);
  document.addEventListener("webkitfullscreenchange", updateFsLabel);

  /* ------------------------- Environment ------------------------- */

  const standalone =
    window.matchMedia("(display-mode: standalone)").matches ||
    window.matchMedia("(display-mode: fullscreen)").matches ||
    window.navigator.standalone === true;

  const isMobile =
    window.matchMedia("(pointer: coarse)").matches ||
    /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent);

  if (isMobile) document.body.classList.add("mobile");
  if (standalone) document.body.classList.add("standalone");

  // Auto-enter fullscreen on the first user gesture (browsers block it on
  // load). Only attempt on mobile or touch devices, and not when already
  // running as an installed standalone/fullscreen PWA.
  if (isMobile && !standalone) {
    const autoFs = () => {
      enterFullscreen();
      window.removeEventListener("pointerdown", autoFs);
      window.removeEventListener("touchend", autoFs);
    };
    window.addEventListener("pointerdown", autoFs, { once: true, passive: true });
    window.addEventListener("touchend", autoFs, { once: true, passive: true });
  }

  /* ------------------------- Service worker ------------------------- */

  if ("serviceWorker" in navigator && location.protocol.startsWith("http")) {
    window.addEventListener("load", () => {
      navigator.serviceWorker.register("sw.js").catch(() => {
        /* offline support is best-effort */
      });
    });
  }

  // Boot
  render();
})();
