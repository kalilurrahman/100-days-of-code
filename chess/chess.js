/*
 * chess.js — a self-contained chess rules engine.
 * Board is an 8x8 array of squares indexed [row][col], row 0 = rank 8 (top),
 * row 7 = rank 1 (bottom). col 0 = file a, col 7 = file h.
 * Pieces are objects: { type: 'p'|'n'|'b'|'r'|'q'|'k', color: 'w'|'b' }.
 */

(function (global) {
  "use strict";

  const START_FEN = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1";

  const PIECE_VALUE = { p: 1, n: 3, b: 3, r: 5, q: 9, k: 0 };

  function cloneBoard(board) {
    return board.map((row) => row.map((sq) => (sq ? { type: sq.type, color: sq.color } : null)));
  }

  function inBounds(r, c) {
    return r >= 0 && r < 8 && c >= 0 && c < 8;
  }

  function opposite(color) {
    return color === "w" ? "b" : "w";
  }

  class Chess {
    constructor(fen) {
      this.loadFen(fen || START_FEN);
    }

    loadFen(fen) {
      const parts = fen.trim().split(/\s+/);
      const [placement, turn, castling, ep, half, full] = parts;
      const board = [];
      const rows = placement.split("/");
      for (let r = 0; r < 8; r++) {
        const row = [];
        let c = 0;
        for (const ch of rows[r]) {
          if (/\d/.test(ch)) {
            const n = parseInt(ch, 10);
            for (let i = 0; i < n; i++) row.push(null);
            c += n;
          } else {
            const color = ch === ch.toUpperCase() ? "w" : "b";
            row.push({ type: ch.toLowerCase(), color });
            c++;
          }
        }
        board.push(row);
      }
      this.board = board;
      this.turn = turn || "w";
      this.castling = castling && castling !== "-" ? castling : "";
      this.enPassant = ep && ep !== "-" ? this.algebraicToCoords(ep) : null;
      this.halfmove = half ? parseInt(half, 10) : 0;
      this.fullmove = full ? parseInt(full, 10) : 1;
      this.history = [];
    }

    algebraicToCoords(sq) {
      const col = sq.charCodeAt(0) - "a".charCodeAt(0);
      const row = 8 - parseInt(sq[1], 10);
      return { row, col };
    }

    coordsToAlgebraic(row, col) {
      return String.fromCharCode("a".charCodeAt(0) + col) + (8 - row);
    }

    get(row, col) {
      return this.board[row][col];
    }

    findKing(color) {
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const p = this.board[r][c];
          if (p && p.type === "k" && p.color === color) return { row: r, col: c };
        }
      }
      return null;
    }

    /* Is the given square attacked by `byColor`? */
    isSquareAttacked(row, col, byColor) {
      const b = this.board;
      // Pawn attacks: a pawn attacks in its direction of motion, so an attacker
      // of `square` sits one row *behind* the square (at row - pawnDir).
      const pawnDir = byColor === "w" ? -1 : 1; // white pawns move up (toward row 0)
      for (const dc of [-1, 1]) {
        const r = row - pawnDir;
        const c = col + dc;
        if (inBounds(r, c)) {
          const p = b[r][c];
          if (p && p.color === byColor && p.type === "p") return true;
        }
      }
      // Knight attacks
      const knightMoves = [
        [-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1],
      ];
      for (const [dr, dc] of knightMoves) {
        const r = row + dr, c = col + dc;
        if (inBounds(r, c)) {
          const p = b[r][c];
          if (p && p.color === byColor && p.type === "n") return true;
        }
      }
      // King attacks
      for (let dr = -1; dr <= 1; dr++) {
        for (let dc = -1; dc <= 1; dc++) {
          if (dr === 0 && dc === 0) continue;
          const r = row + dr, c = col + dc;
          if (inBounds(r, c)) {
            const p = b[r][c];
            if (p && p.color === byColor && p.type === "k") return true;
          }
        }
      }
      // Sliding: rook/queen (orthogonal)
      const orth = [[-1, 0], [1, 0], [0, -1], [0, 1]];
      for (const [dr, dc] of orth) {
        let r = row + dr, c = col + dc;
        while (inBounds(r, c)) {
          const p = b[r][c];
          if (p) {
            if (p.color === byColor && (p.type === "r" || p.type === "q")) return true;
            break;
          }
          r += dr; c += dc;
        }
      }
      // Sliding: bishop/queen (diagonal)
      const diag = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
      for (const [dr, dc] of diag) {
        let r = row + dr, c = col + dc;
        while (inBounds(r, c)) {
          const p = b[r][c];
          if (p) {
            if (p.color === byColor && (p.type === "b" || p.type === "q")) return true;
            break;
          }
          r += dr; c += dc;
        }
      }
      return false;
    }

    inCheck(color) {
      const king = this.findKing(color);
      if (!king) return false;
      return this.isSquareAttacked(king.row, king.col, opposite(color));
    }

    /* Generate pseudo-legal moves for the piece at (row,col), ignoring self-check. */
    pseudoMoves(row, col) {
      const piece = this.board[row][col];
      if (!piece) return [];
      const moves = [];
      const b = this.board;
      const color = piece.color;
      const add = (r, c, extra) => {
        moves.push(Object.assign({ from: { row, col }, to: { row: r, col: c } }, extra || {}));
      };

      if (piece.type === "p") {
        const dir = color === "w" ? -1 : 1;
        const startRow = color === "w" ? 6 : 1;
        const promoRow = color === "w" ? 0 : 7;
        // forward one
        if (inBounds(row + dir, col) && !b[row + dir][col]) {
          if (row + dir === promoRow) {
            for (const pt of ["q", "r", "b", "n"]) add(row + dir, col, { promotion: pt });
          } else {
            add(row + dir, col);
          }
          // forward two
          if (row === startRow && !b[row + 2 * dir][col]) {
            add(row + 2 * dir, col, { double: true });
          }
        }
        // captures
        for (const dc of [-1, 1]) {
          const r = row + dir, c = col + dc;
          if (!inBounds(r, c)) continue;
          const target = b[r][c];
          if (target && target.color !== color) {
            if (r === promoRow) {
              for (const pt of ["q", "r", "b", "n"]) add(r, c, { promotion: pt, capture: true });
            } else {
              add(r, c, { capture: true });
            }
          } else if (
            this.enPassant &&
            this.enPassant.row === r &&
            this.enPassant.col === c
          ) {
            add(r, c, { enPassant: true, capture: true });
          }
        }
      } else if (piece.type === "n") {
        const deltas = [
          [-2, -1], [-2, 1], [-1, -2], [-1, 2], [1, -2], [1, 2], [2, -1], [2, 1],
        ];
        for (const [dr, dc] of deltas) {
          const r = row + dr, c = col + dc;
          if (!inBounds(r, c)) continue;
          const t = b[r][c];
          if (!t) add(r, c);
          else if (t.color !== color) add(r, c, { capture: true });
        }
      } else if (piece.type === "k") {
        for (let dr = -1; dr <= 1; dr++) {
          for (let dc = -1; dc <= 1; dc++) {
            if (dr === 0 && dc === 0) continue;
            const r = row + dr, c = col + dc;
            if (!inBounds(r, c)) continue;
            const t = b[r][c];
            if (!t) add(r, c);
            else if (t.color !== color) add(r, c, { capture: true });
          }
        }
        // Castling
        this.addCastling(row, col, color, moves);
      } else {
        // sliding pieces
        let dirs = [];
        if (piece.type === "r") dirs = [[-1, 0], [1, 0], [0, -1], [0, 1]];
        else if (piece.type === "b") dirs = [[-1, -1], [-1, 1], [1, -1], [1, 1]];
        else dirs = [
          [-1, 0], [1, 0], [0, -1], [0, 1], [-1, -1], [-1, 1], [1, -1], [1, 1],
        ];
        for (const [dr, dc] of dirs) {
          let r = row + dr, c = col + dc;
          while (inBounds(r, c)) {
            const t = b[r][c];
            if (!t) {
              add(r, c);
            } else {
              if (t.color !== color) add(r, c, { capture: true });
              break;
            }
            r += dr; c += dc;
          }
        }
      }
      return moves;
    }

    addCastling(row, col, color, moves) {
      if (this.inCheck(color)) return;
      const enemy = opposite(color);
      const rights = this.castling;
      const backRow = color === "w" ? 7 : 0;
      if (row !== backRow || col !== 4) return;
      // King side
      const kSide = color === "w" ? "K" : "k";
      if (rights.includes(kSide)) {
        if (
          !this.board[backRow][5] &&
          !this.board[backRow][6] &&
          this.board[backRow][7] &&
          this.board[backRow][7].type === "r" &&
          this.board[backRow][7].color === color &&
          !this.isSquareAttacked(backRow, 5, enemy) &&
          !this.isSquareAttacked(backRow, 6, enemy)
        ) {
          moves.push({
            from: { row, col }, to: { row: backRow, col: 6 }, castle: "k",
          });
        }
      }
      const qSide = color === "w" ? "Q" : "q";
      if (rights.includes(qSide)) {
        if (
          !this.board[backRow][3] &&
          !this.board[backRow][2] &&
          !this.board[backRow][1] &&
          this.board[backRow][0] &&
          this.board[backRow][0].type === "r" &&
          this.board[backRow][0].color === color &&
          !this.isSquareAttacked(backRow, 3, enemy) &&
          !this.isSquareAttacked(backRow, 2, enemy)
        ) {
          moves.push({
            from: { row, col }, to: { row: backRow, col: 2 }, castle: "q",
          });
        }
      }
    }

    /* Fully legal moves for the side to move (or a specific color). */
    legalMoves(color) {
      color = color || this.turn;
      const all = [];
      for (let r = 0; r < 8; r++) {
        for (let c = 0; c < 8; c++) {
          const p = this.board[r][c];
          if (!p || p.color !== color) continue;
          for (const m of this.pseudoMoves(r, c)) {
            if (this.isLegal(m, color)) all.push(m);
          }
        }
      }
      return all;
    }

    legalMovesFrom(row, col) {
      const p = this.board[row][col];
      if (!p) return [];
      return this.pseudoMoves(row, col).filter((m) => this.isLegal(m, p.color));
    }

    /* Apply a move on a cloned state and check the mover isn't left in check. */
    isLegal(move, color) {
      const snapshot = this.snapshot();
      this.applyMove(move, true);
      const ok = !this.inCheck(color);
      this.restore(snapshot);
      return ok;
    }

    snapshot() {
      return {
        board: cloneBoard(this.board),
        turn: this.turn,
        castling: this.castling,
        enPassant: this.enPassant ? { ...this.enPassant } : null,
        halfmove: this.halfmove,
        fullmove: this.fullmove,
      };
    }

    restore(s) {
      this.board = s.board;
      this.turn = s.turn;
      this.castling = s.castling;
      this.enPassant = s.enPassant;
      this.halfmove = s.halfmove;
      this.fullmove = s.fullmove;
    }

    /* Execute a move. If `silent`, don't push to history (used for legality probing). */
    applyMove(move, silent) {
      const { from, to } = move;
      const piece = this.board[from.row][from.col];
      const color = piece.color;
      const captured = move.enPassant
        ? this.board[from.row][to.col]
        : this.board[to.row][to.col];

      if (!silent) {
        this.history.push({
          snapshot: this.snapshot(),
          move,
          captured: captured ? { ...captured } : null,
        });
      }

      // Move the piece
      this.board[to.row][to.col] = { type: piece.type, color };
      this.board[from.row][from.col] = null;

      // En passant capture removes the pawn behind
      if (move.enPassant) {
        this.board[from.row][to.col] = null;
      }

      // Promotion
      if (move.promotion) {
        this.board[to.row][to.col] = { type: move.promotion, color };
      }

      // Castling: move the rook
      if (move.castle) {
        const backRow = from.row;
        if (move.castle === "k") {
          this.board[backRow][5] = this.board[backRow][7];
          this.board[backRow][7] = null;
        } else {
          this.board[backRow][3] = this.board[backRow][0];
          this.board[backRow][0] = null;
        }
      }

      // Update castling rights
      this.updateCastlingRights(from, to, piece, captured);

      // En passant target
      this.enPassant = move.double
        ? { row: (from.row + to.row) / 2, col: from.col }
        : null;

      // Halfmove clock
      if (piece.type === "p" || captured) this.halfmove = 0;
      else this.halfmove++;

      if (color === "b") this.fullmove++;
      this.turn = opposite(color);

      return { captured };
    }

    updateCastlingRights(from, to, piece, captured) {
      let rights = this.castling;
      const remove = (ch) => {
        rights = rights.replace(ch, "");
      };
      if (piece.type === "k") {
        if (piece.color === "w") {
          remove("K"); remove("Q");
        } else {
          remove("k"); remove("q");
        }
      }
      if (piece.type === "r") {
        if (from.row === 7 && from.col === 0) remove("Q");
        if (from.row === 7 && from.col === 7) remove("K");
        if (from.row === 0 && from.col === 0) remove("q");
        if (from.row === 0 && from.col === 7) remove("k");
      }
      // Rook captured on its home square
      if (to.row === 7 && to.col === 0) remove("Q");
      if (to.row === 7 && to.col === 7) remove("K");
      if (to.row === 0 && to.col === 0) remove("q");
      if (to.row === 0 && to.col === 7) remove("k");
      this.castling = rights;
    }

    /* Public move: validates against legal moves, returns rich move info or null. */
    move(from, to, promotion) {
      const legal = this.legalMovesFrom(from.row, from.col);
      const match = legal.find(
        (m) =>
          m.to.row === to.row &&
          m.to.col === to.col &&
          (!m.promotion || m.promotion === (promotion || "q"))
      );
      if (!match) return null;
      const san = this.toSan(match);
      const result = this.applyMove(match, false);
      const info = {
        ...match,
        san,
        captured: result.captured,
        check: this.inCheck(this.turn),
        checkmate: false,
        stalemate: false,
      };
      const status = this.gameStatus();
      info.checkmate = status === "checkmate";
      info.stalemate = status === "stalemate" || status === "draw";
      info.san = san + (info.checkmate ? "#" : info.check ? "+" : "");
      // patch the stored history entry's san for display
      const h = this.history[this.history.length - 1];
      if (h) h.san = info.san;
      return info;
    }

    undo() {
      const last = this.history.pop();
      if (!last) return false;
      this.restore(last.snapshot);
      return true;
    }

    gameStatus() {
      const moves = this.legalMoves(this.turn);
      if (moves.length === 0) {
        return this.inCheck(this.turn) ? "checkmate" : "stalemate";
      }
      if (this.halfmove >= 100) return "draw"; // 50-move rule
      if (this.insufficientMaterial()) return "draw";
      return "ongoing";
    }

    insufficientMaterial() {
      const pieces = [];
      for (let r = 0; r < 8; r++)
        for (let c = 0; c < 8; c++) {
          const p = this.board[r][c];
          if (p && p.type !== "k") pieces.push(p);
        }
      if (pieces.length === 0) return true; // K vs K
      if (pieces.length === 1 && (pieces[0].type === "b" || pieces[0].type === "n"))
        return true; // K+minor vs K
      if (
        pieces.length === 2 &&
        pieces.every((p) => p.type === "b")
      ) {
        return true; // K+B vs K+B (loose check)
      }
      return false;
    }

    /* Standard Algebraic Notation (without trailing +/#, added by caller). */
    toSan(move) {
      if (move.castle === "k") return "O-O";
      if (move.castle === "q") return "O-O-O";
      const piece = this.board[move.from.row][move.from.col];
      const dest = this.coordsToAlgebraic(move.to.row, move.to.col);
      const isCapture = move.capture;
      if (piece.type === "p") {
        let s = "";
        if (isCapture) {
          s += String.fromCharCode("a".charCodeAt(0) + move.from.col) + "x";
        }
        s += dest;
        if (move.promotion) s += "=" + move.promotion.toUpperCase();
        return s;
      }
      const letter = piece.type.toUpperCase();
      // Disambiguation
      let disamb = "";
      const others = [];
      for (let r = 0; r < 8; r++)
        for (let c = 0; c < 8; c++) {
          const p = this.board[r][c];
          if (
            p &&
            p.type === piece.type &&
            p.color === piece.color &&
            !(r === move.from.row && c === move.from.col)
          ) {
            const ms = this.legalMovesFrom(r, c);
            if (ms.some((m) => m.to.row === move.to.row && m.to.col === move.to.col)) {
              others.push({ row: r, col: c });
            }
          }
        }
      if (others.length > 0) {
        const sameFile = others.some((o) => o.col === move.from.col);
        const sameRank = others.some((o) => o.row === move.from.row);
        if (!sameFile) disamb = String.fromCharCode("a".charCodeAt(0) + move.from.col);
        else if (!sameRank) disamb = String(8 - move.from.row);
        else disamb = this.coordsToAlgebraic(move.from.row, move.from.col);
      }
      return letter + disamb + (isCapture ? "x" : "") + dest;
    }

    /* Material balance from white's perspective. */
    materialScore() {
      let score = 0;
      for (let r = 0; r < 8; r++)
        for (let c = 0; c < 8; c++) {
          const p = this.board[r][c];
          if (!p) continue;
          score += (p.color === "w" ? 1 : -1) * PIECE_VALUE[p.type];
        }
      return score;
    }
  }

  Chess.PIECE_VALUE = PIECE_VALUE;
  Chess.opposite = opposite;
  Chess.START_FEN = START_FEN;

  global.Chess = Chess;
})(typeof window !== "undefined" ? window : globalThis);
