# Kalman US/KR Macro Impact Registry v1.8

## Purpose

This registry adds **target-market priors** to the existing macro-event feature layer.

It separates:

- US domestic macro surprise
- KR domestic macro surprise
- US -> KR macro spillover surprise
- US event-family -> KR spillover score

The configured weights are **ordinal research priors**, not causal effect sizes and not production trading coefficients. They are intended for SHADOW use and should be re-estimated with the 2017-present Kalman historical event-study/backtest.

## Evidence used

1. Andersen, Bollerslev, Diebold & Vega, *Real-Time Price Discovery in Global Stock, Bond and Foreign Exchange Markets*, Federal Reserve IFDP 871 (2006/2007). High-frequency US macro news causes jumps in stock, bond and FX markets.
   - https://www.federalreserve.gov/econres/ifdp/real-time-price-discovery-in-global-stock-bond-and-foreign-exchange-markets.htm
2. Bernanke & Kuttner, *What Explains the Stock Market's Reaction to Federal Reserve Policy?*, Federal Reserve FEDS (2004; published 2005). Unexpected monetary-policy changes are associated with material broad-equity reactions.
   - https://www.federalreserve.gov/econres/feds/what-explains-the-stock-market39s-reaction-to-federal-reserve-policy.htm
3. Bank of Korea Working Paper 2016-21, *US Interest Rate Policy Spillover and International Capital Flow: Evidence from Korea*. Unexpected US monetary-policy shocks affect portfolio flows into Korea.
   - https://www.bok.or.kr/eng/bbs/E0002902/view.do?menuNo=400206&nttId=224903
4. Bank of Korea Working Paper 2026-3, *U.S.-Korea Yield Synchronization and Its Implications for Monetary Policy Transmission*. Documents high-frequency contemporaneous spillovers from US yields to Korean yields.
   - https://www.bok.or.kr/eng/bbs/E0002902/view.do?depth=400007&menuNo=600342&nttId=10096004
5. Bank of Korea Working Paper 2026-15, *Co-movement of Long-Term Interest Rates between Korea and the United States*. Finds global inflation and Fed policy are important sources of Korea-US yield co-movement.
   - https://www.bok.or.kr/eng/bbs/B0000196/view.do?depth=600341&menuNo=400067&nttId=11064888
6. Bank of Korea, *Recent Features and Implications of Korea's Exports* (Issue Note 2023-23), plus 2026 semiconductor/terms-of-trade research. These support retaining exports and the semiconductor-linked external cycle as major KR macro state variables.
   - https://www.bok.or.kr/eng/bbs/B0000354/view.do?menuNo=400409&nttId=10079580
   - https://www.bok.or.kr/eng/bbs/B0000354/view.do?depth=400409&menuNo=400409&nttId=11063486

## Initial hierarchy

### US target

**HIGH**
- CPI / Core CPI
- NFP / unemployment / hourly earnings
- FOMC event family

**MEDIUM**
- Core PCE
- ISM
- Retail sales
- PPI

**CONTEXTUAL**
- GDP
- JOLTS
- Initial claims
- Industrial production

### KR target

**Domestic HIGH**
- BOK Base Rate
- KR CPI
- KR exports

**Domestic MEDIUM**
- Trade balance
- GDP
- Industrial production

**US -> KR spillover**
- FOMC: HIGH
- US CPI/Core CPI: HIGH
- NFP/labor: MEDIUM
- Core PCE: MEDIUM

## Generated feature fields

- `us_priority_surprise_index`
- `kr_priority_surprise_index`
- `kr_domestic_priority_surprise_index`
- `kr_us_spillover_surprise_index`
- `us_target_macro_event_score`
- `kr_us_spillover_event_score`

All remain challenger/shadow-only in v1.8.
