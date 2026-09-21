# Kalman US/KR Macro Indicator Evidence Registry V1

Status: challenger / observation layer only. This registry does not change production trade gates.

## 1. Design principle

Kalman separates three concepts that must not be conflated:

1. **Indicator relevance** — supported by academic or official research.
2. **Release surprise** — actual minus consensus, normalized into an engineering feature.
3. **Market confirmation** — observed rates / asset-price reaction after the release.

The papers below justify which release families deserve collection. They do **not**
justify the current normalization scale as a causal coefficient or an optimal trading
weight. Values under `indicator_normalization.scale` are initial engineering scales and
must be re-estimated with point-in-time historical data before production promotion.

## 2. United States

### Core collection set

| Release family | Kalman keys | Rationale |
| --- | --- | --- |
| Federal Reserve policy | FOMC official-news anchor + policy repricing | Monetary-policy surprises have documented equity-price effects; keep statement/communication separate from simple target-rate changes. |
| CPI / Core CPI | CPI_HEADLINE_MOM/YOY, CORE_CPI_MOM/YOY | Inflation surprises are major scheduled macro shocks and are directly relevant to Treasury repricing. |
| Employment | NFP, UNEMPLOYMENT_RATE, AVERAGE_HOURLY_EARNINGS_MOM | Employment releases are among the major announcements associated with intraday Treasury yield jumps. |
| GDP | GDP_QOQ | Growth data are part of the major macro announcement set studied in high-frequency bond-market research. |
| Core PCE | CORE_PCE_MOM/YOY | Directly relevant to inflation assessment and Fed reaction-function context. |
| Activity / demand | RETAIL_SALES_MOM, INDUSTRIAL_PRODUCTION_MOM, ISM_MANUFACTURING, ISM_SERVICES | Adds real-economy demand and production information between payroll/CPI cycles. |
| Producer / labor pressure | PPI_MOM, JOLTS_OPENINGS, INITIAL_JOBLESS_CLAIMS | Adds pipeline inflation and labor-tightness context. |

### Evidence

- Bernanke, B. S. & Kuttner, K. N. (2005), *What Explains the Stock Market's Reaction to Federal Reserve Policy?*, Journal of Finance. NBER working-paper version: https://www.nber.org/papers/w10402
- BIS Working Paper No. 1361 (2026), *Bond yield responses to macro news: the role of macro forecast disagreement and monetary policy uncertainty*. It studies intraday US Treasury responses to six major announcements, including inflation, employment and GDP: https://www.bis.org/publications/working-paper-1361-bond-yield-responses-macro-news-role-macro-forecast-disagreement-and-monetary-policy-uncertainty
- U.S. Bureau of Labor Statistics release calendars show key CPI and Employment Situation releases are scheduled events, commonly at 08:30 ET: https://www.bls.gov/schedule/2026/

## 3. South Korea

### Core collection set

| Release family | Kalman keys | Rationale |
| --- | --- | --- |
| Bank of Korea monetary policy | KR_BOK_BASE_RATE + BOK official-news layer | BOK research finds monetary-policy announcements produce a larger KOSPI 200 options implied-volatility response than other macro announcements after controlling for news surprise. |
| CPI | KR_CPI_MOM, KR_CPI_YOY | Inflation announcement / policy-pressure input. |
| GDP | KR_GDP_QOQ, KR_GDP_YOY | Domestic growth announcement input. |
| Labor | KR_UNEMPLOYMENT_RATE | Labor-market surprise input. |
| External balance | KR_TRADE_BALANCE | Korea-specific external-demand / FX-sensitive macro input. |
| Industrial production | KR_INDUSTRIAL_PRODUCTION_MOM | Domestic production-cycle input. |

`KR_EXPORTS_YOY` is included as a **secondary Korea-specific extension** because the
economy is highly trade-sensitive. It should not be interpreted as being ranked above
the core announcement families by the BOK paper.

### Evidence

- Bank of Korea Working Paper No. 2019-2, Lee & Ryu, *The Impacts of Macroeconomic News Announcements on Intraday Implied Volatility*: https://www.bok.or.kr/imerEng/bbs/E0002902/view.do?menuNo=600342&nttId=10049383&pageIndex=3
- Bank of Korea Working Paper No. 2019-11, *Measuring Monetary Policy Surprises Using Text Mining: The Case of Korea*. The study reports that base-rate changes are more closely related to short-term rates while communication-based monetary-policy surprise better explains longer-term rate changes: https://www.bok.or.kr/imerEng/bbs/E0002902/view.do?menuNo=600342&nttId=10050398&pageIndex=
- Bank of Korea Issue Note 2025-07, *Reconstructing the Bank of Korea's Global Projection Model: Framework and Analysis*. This supports keeping external US/global shocks in the Korean macro context rather than treating KR as a closed system: https://www.bok.or.kr/eng/bbs/B0000354/view.do?depth=400409&menuNo=400409&nttId=10092449

## 4. Cross-market rule

US FOMC / CPI / employment shocks remain available to the KR feature layer as external
context. However, the first implementation does not convert KR macro surprises directly
into an executable trading score.

Current contract:

```text
US structured release
  -> surprise
  -> US 2Y reaction
  -> policy repricing confirmation
  -> existing US shadow macro score

KR structured release
  -> surprise
  -> KR surprise snapshot only
  -> no KOSPI / KR3Y confirmation yet
  -> no production score / no trade gate
```

The next empirical promotion gate is a point-in-time event study using KOSPI/KOSDAQ,
USD/KRW and Korean government-bond yields around the exact release timestamps.

## 5. Provider / provenance rule

Trading Economics is used only as the structured **actual / consensus / previous**
calendar feed. It is not treated as the official authority for the release.

The official-news layer remains separate (BLS/BEA/Federal Reserve and BOK/statistical
authorities). Every structured release stores provider, provider timestamp, source
metadata and market in `macro_release_observation`.

## 6. Scheduling

The Trading Economics calls are quota-aware. The provider is active only during local
release windows:

- US: 07:30–11:30 America/New_York, weekdays
- KR: 07:30–11:30 Asia/Seoul, weekdays

The feature builder may still run every 15 minutes; outside those windows the
structured-consensus provider returns `OUTSIDE_ACTIVE_WINDOW` without making a
calendar request.

## 7. Promotion criteria

Do not connect a new KR macro score to strategy selection or execution until all are
satisfied:

- historical point-in-time actual/consensus data are available;
- exact release timestamp quality is audited;
- event-window KOSPI/KOSDAQ, USD/KRW and KR-rate reactions are measured;
- normalization scales are estimated from historical surprise distributions;
- leakage tests pass;
- out-of-sample / walk-forward tests pass;
- SHADOW comparison is stable across multiple release cycles.
