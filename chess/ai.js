/*
 * ai.js — a lightweight chess AI using minimax with alpha-beta pruning
 * and piece-square tables. Designed to run synchronously in the browser
 * at shallow depths (1-3 ply) for a casual opponent.
 */

(function (global) {
  "use strict";

  const Chess = global.Chess;
  const VAL = { p: 100, n: 320, b: 330, r: 500, q: 900, k: 20000 };

  // Piece-square tables (from white's perspective, row 0 = rank 8).
  const PST = {
    p: [
      [0, 0, 0, 0, 0, 0, 0, 0],
      [50, 50, 50, 50, 50, 50, 50, 50],
      [10, 10, 20, 30, 30, 20, 10, 10],
      [5, 5, 10, 25, 25, 10, 5, 5],
      [0, 0, 0, 20, 20, 0, 0, 0],
      [5, -5, -10, 0, 0, -10, -5, 5],
      [5, 10, 10, -20, -20, 10, 10, 5],
      [0, 0, 0, 0, 0, 0, 0, 0],
    ],
    n: [
      [-50, -40, -30, -30, -30, -30, -40, -50],
      [-40, -20, 0, 0, 0, 0, -20, -40],
      [-30, 0, 10, 15, 15, 10, 0, -30],
      [-30, 5, 15, 20, 20, 15, 5, -30],
      [-30, 0, 15, 20, 20, 15, 0, -30],
      [-30, 5, 10, 15, 15, 10, 5, -30],
      [-40, -20, 0, 5, 5, 0, -20, -40],
      [-50, -40, -30, -30, -30, -30, -40, -50],
    ],
    b: [
      [-20, -10, -10, -10, -10, -10, -10, -20],
      [-10, 0, 0, 0, 0, 0, 0, -10],
      [-10, 0, 5, 10, 10, 5, 0, -10],
      [-10, 5, 5, 10, 10, 5, 5, -10],
      [-10, 0, 10, 10, 10, 10, 0, -10],
      [-10, 10, 10, 10, 10, 10, 10, -10],
      [-10, 5, 0, 0, 0, 0, 5, -10],
      [-20, -10, -10, -10, -10, -10, -10, -20],
    ],
    r: [
      [0, 0, 0, 0, 0, 0, 0, 0],
      [5, 10, 10, 10, 10, 10, 10, 5],
      [-5, 0, 0, 0, 0, 0, 0, -5],
      [-5, 0, 0, 0, 0, 0, 0, -5],
      [-5, 0, 0, 0, 0, 0, 0, -5],
      [-5, 0, 0, 0, 0, 0, 0, -5],
      [-5, 0, 0, 0, 0, 0, 0, -5],
      [0, 0, 0, 5, 5, 0, 0, 0],
    ],
    q: [
      [-20, -10, -10, -5, -5, -10, -10, -20],
      [-10, 0, 0, 0, 0, 0, 0, -10],
      [-10, 0, 5, 5, 5, 5, 0, -10],
      [-5, 0, 5, 5, 5, 5, 0, -5],
      [0, 0, 5, 5, 5, 5, 0, -5],
      [-10, 5, 5, 5, 5, 5, 0, -10],
      [-10, 0, 5, 0, 0, 0, 0, -10],
      [-20, -10, -10, -5, -5, -10, -10, -20],
    ],
    k: [
      [-30, -40, -40, -50, -50, -40, -40, -30],
      [-30, -40, -40, -50, -50, -40, -40, -30],
      [-30, -40, -40, -50, -50, -40, -40, -30],
      [-30, -40, -40, -50, -50, -40, -40, -30],
      [-20, -30, -30, -40, -40, -30, -30, -20],
      [-10, -20, -20, -20, -20, -20, -20, -10],
      [20, 20, 0, 0, 0, 0, 20, 20],
      [20, 30, 10, 0, 0, 10, 30, 20],
    ],
  };

  function evaluate(game) {
    let score = 0;
    for (let r = 0; r < 8; r++) {
      for (let c = 0; c < 8; c++) {
        const p = game.board[r][c];
        if (!p) continue;
        const base = VAL[p.type];
        const pst = PST[p.type];
        if (p.color === "w") {
          score += base + pst[r][c];
        } else {
          score -= base + pst[7 - r][c];
        }
      }
    }
    return score; // positive favors white
  }

  // Order moves so captures are searched first (improves alpha-beta).
  function orderMoves(game, moves) {
    return moves
      .map((m) => {
        let s = 0;
        if (m.capture) {
          const victim = m.enPassant
            ? "p"
            : game.board[m.to.row][m.to.col]
            ? game.board[m.to.row][m.to.col].type
            : "p";
          const attacker = game.board[m.from.row][m.from.col].type;
          s = 10 * VAL[victim] - VAL[attacker];
        }
        if (m.promotion) s += VAL[m.promotion];
        return { m, s };
      })
      .sort((a, b) => b.s - a.s)
      .map((x) => x.m);
  }

  function minimax(game, depth, alpha, beta, maximizing) {
    if (depth === 0) return evaluate(game);

    const moves = game.legalMoves(game.turn);
    if (moves.length === 0) {
      if (game.inCheck(game.turn)) {
        // Checkmate: prefer faster mates. Sign depends on who is mated.
        return maximizing ? -100000 - depth : 100000 + depth;
      }
      return 0; // stalemate
    }

    const ordered = orderMoves(game, moves);

    if (maximizing) {
      let best = -Infinity;
      for (const m of ordered) {
        game.applyMove(m, false);
        const val = minimax(game, depth - 1, alpha, beta, false);
        game.undo();
        if (val > best) best = val;
        if (best > alpha) alpha = best;
        if (beta <= alpha) break;
      }
      return best;
    } else {
      let best = Infinity;
      for (const m of ordered) {
        game.applyMove(m, false);
        const val = minimax(game, depth - 1, alpha, beta, true);
        game.undo();
        if (val < best) best = val;
        if (best < beta) beta = best;
        if (beta <= alpha) break;
      }
      return best;
    }
  }

  /*
   * Choose a move for the side to move.
   * level 1 = depth 1 with randomness (easy)
   * level 2 = depth 2 (medium)
   * level 3 = depth 3 (hard)
   */
  function chooseMove(game, level) {
    const depthByLevel = { 1: 1, 2: 2, 3: 3 };
    const depth = depthByLevel[level] || 2;
    const color = game.turn;
    const maximizing = color === "w";
    const moves = orderMoves(game, game.legalMoves(color));
    if (moves.length === 0) return null;

    let bestVal = maximizing ? -Infinity : Infinity;
    const scored = [];
    for (const m of moves) {
      game.applyMove(m, false);
      let val = minimax(game, depth - 1, -Infinity, Infinity, !maximizing);
      game.undo();
      // small random jitter on easy to make it less predictable
      if (level === 1) val += (hashMove(m) % 60) - 30;
      scored.push({ m, val });
      if (maximizing ? val > bestVal : val < bestVal) bestVal = val;
    }

    // Collect near-best moves and pick among them for variety.
    const margin = level === 1 ? 40 : level === 2 ? 10 : 0;
    const pool = scored.filter((s) =>
      maximizing ? s.val >= bestVal - margin : s.val <= bestVal + margin
    );
    const pick = pool[deterministicIndex(game, pool.length)];
    return pick.m;
  }

  // Deterministic-ish but varied move hash (avoids Math.random for reproducibility).
  function hashMove(m) {
    return (
      (m.from.row * 8 + m.from.col) * 64 + (m.to.row * 8 + m.to.col) + 1
    ) * 2654435761 % 1000;
  }

  function deterministicIndex(game, n) {
    if (n <= 1) return 0;
    // Use board hash + move number for pseudo-variety.
    let h = game.fullmove * 2654435761;
    for (let r = 0; r < 8; r++)
      for (let c = 0; c < 8; c++) {
        const p = game.board[r][c];
        if (p) h = (h * 31 + (p.type.charCodeAt(0) + (p.color === "w" ? 1 : 17))) >>> 0;
      }
    return h % n;
  }

  global.ChessAI = { chooseMove, evaluate };
})(typeof window !== "undefined" ? window : globalThis);
