/* KALMAN_LEDGER_SEMANTICS_V1
 * Presentation-only guardrail for the R5.1 US annual ledger.
 * Shadow Entry is a model reference price, never a broker fill.
 */
;(() => {
  if (window.__KALMAN_LEDGER_SEMANTICS_V1__) return;
  window.__KALMAN_LEDGER_SEMANTICS_V1__ = true;

  const normalize = (s) => String(s ?? "").replace(/\s+/g, " ").trim();
  const labels = new Map([
    ["2026 전체 Ledger", "2026 전체 Ledger · Shadow"],
    ["Entry", "Shadow Entry"],
    ["Entry Price", "Shadow Entry"],
    ["entry_price", "Shadow Entry"],
    ["진입가", "Shadow Entry"],
    ["진입 가격", "Shadow Entry"],
    ["Raw Return", "Price Return"],
    ["raw_return", "Price Return"],
    ["가격 수익률", "Price Return"],
    ["Price PnL", "Price Return"],
    ["Position Weight", "Weight"],
    ["position_weight", "Weight"],
    ["비중", "Weight"],
    ["Gross Return", "Gross Strategy Return"],
    ["Gross Weighted Return", "Gross Strategy Return"],
    ["gross_weighted_return", "Gross Strategy Return"],
    ["Return", "Net Strategy Return"],
    ["Return %", "Net Strategy Return"],
    ["return_pct", "Net Strategy Return"],
    ["Net10 Return", "Net Strategy Return"],
    ["net10_return", "Net Strategy Return"],
    ["PnL", "Net Strategy Return"],
    ["PnL %", "Net Strategy Return"],
    ["수익률", "Net Strategy Return"],
    ["전략 수익률", "Net Strategy Return"],
  ]);

  const noteText =
    "Shadow Entry = 모델 기준가격(브로커 체결가 아님) · " +
    "Price Return = 종목 자체 가격수익률 · " +
    "Net Strategy Return = 포지션 비중 + 10bp 비용 반영 · " +
    "실제 체결 기준은 내 계좌의 Broker Avg. Price(매입평균가)";

  function textLength(el) {
    return normalize(el?.textContent).length;
  }

  function ledgerScope() {
    const candidates = Array.from(
      document.querySelectorAll(
        "[data-ledger-panel],.ledger-panel,section,article,.panel,.card,.card2,.box,div"
      )
    ).filter((el) => {
      const t = normalize(el.textContent);
      return (
        t.includes("2026 전체 Ledger") &&
        (
          t.includes("LIVE_SHADOW") ||
          t.includes("BACKTEST") ||
          t.includes("Forward") ||
          t.includes("Reconstructed") ||
          t.includes("Shadow")
        )
      );
    });

    if (candidates.length) {
      candidates.sort((a, b) => textLength(a) - textLength(b));
      return candidates[0];
    }

    const anchor = Array.from(
      document.querySelectorAll("button,h1,h2,h3,h4,h5,.title,.panel-title,.card-title,span,div")
    ).find((el) => normalize(el.textContent).includes("2026 전체 Ledger"));

    if (!anchor) return null;
    return (
      anchor.closest("[data-ledger-panel],.ledger-panel,.panel,.card,.card2,.box,section,article") ||
      anchor.parentElement
    );
  }

  function leaf(el) {
    return !!el && !el.matches("script,style,input,textarea,select,option") && el.children.length === 0;
  }

  function relabel(scope) {
    for (const el of scope.querySelectorAll(
      "th,span,div,p,label,strong,em,small,button,h1,h2,h3,h4,h5"
    )) {
      if (!leaf(el)) continue;
      const t = normalize(el.textContent);
      const next = labels.get(t);
      if (!next || next === t) continue;
      el.textContent = next;
      el.dataset.kalmanLedgerSemantic = "1";
    }
  }

  function ensureNote(scope) {
    if (scope.querySelector(".kalman-ledger-semantics-note")) return;

    const styleId = "kalman-ledger-semantics-style";
    if (!document.getElementById(styleId)) {
      const style = document.createElement("style");
      style.id = styleId;
      style.textContent = `
        .kalman-ledger-semantics-note{
          margin:10px 0 12px;padding:10px 12px;
          border:1px solid rgba(148,163,184,.35);
          border-radius:10px;font-size:12px;line-height:1.5;opacity:.9
        }`;
      document.head.appendChild(style);
    }

    const note = document.createElement("div");
    note.className = "kalman-ledger-semantics-note";
    note.setAttribute("role", "note");
    note.textContent = noteText;

    const table = scope.querySelector("table");
    const heading = Array.from(scope.querySelectorAll(
      "h1,h2,h3,h4,h5,.title,.panel-title,.card-title"
    )).find((el) => normalize(el.textContent).includes("2026 전체 Ledger"));

    if (table?.parentElement) table.parentElement.insertBefore(note, table);
    else if (heading) heading.insertAdjacentElement("afterend", note);
    else scope.insertBefore(note, scope.firstChild);
  }

  function annotateBrokerAccount() {
    const scopes = Array.from(
      document.querySelectorAll("[data-account-panel],.account-panel,.account-card,.holdings-card,section,.card")
    ).filter((el) => {
      const t = normalize(el.textContent);
      return (
        (t.includes("내 계좌") || t.includes("Account") || t.includes("보유 종목")) &&
        (t.includes("매입평균") || t.includes("평균매입") || t.includes("평단") || t.includes("Average"))
      );
    });
    if (!scopes.length) return;
    scopes.sort((a, b) => textLength(a) - textLength(b));
    const scope = scopes[0];

    for (const el of scope.querySelectorAll("th,span,div,p,label,strong,small")) {
      if (!leaf(el)) continue;
      const t = normalize(el.textContent);
      if (["매입평균", "매입평균가", "평균매입가", "평단", "Average Price", "Avg. Price"].includes(t)) {
        el.textContent = "Broker Avg. Price";
        el.dataset.kalmanBrokerSemantic = "1";
      }
    }
  }

  let queued = false;
  function apply() {
    queued = false;
    const scope = ledgerScope();
    if (scope) {
      relabel(scope);
      ensureNote(scope);
    }
    annotateBrokerAccount();
  }

  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(apply);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", schedule, { once: true });
  } else schedule();

  new MutationObserver(schedule).observe(document.documentElement, {
    childList: true,
    subtree: true,
  });
})();
