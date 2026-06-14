# RelativeQs — Operating Manual & User Guide

A plain-English reference for everything you see on the RelativeQs dashboard:
what each card, chip and number means, how it's worked out, and how to use it.
Keep this handy — it's written to answer "what am I looking at?" for any part
of the screen.

> **What RelativeQs is, in one line:** it reads the Nasdaq‑100 (QQQ) from the
> sectors and AI build‑out funds *underneath* it — telling you whether the
> current move is broad and trustworthy or narrow and fragile, who's leading,
> and how much of tech is now an AI‑infrastructure trade.
>
> **What it is not:** investment advice. It's analytics and education about
> Nasdaq‑100 internals. Past performance doesn't guarantee future results.

---

## 1. How to read the dashboard

The screen is built so you can get the gist in one glance and then drill in.

**The color language (the same everywhere):**

| Color | Meaning |
|-------|---------|
| 🟢 **Green (emerald)** | Healthy / strong / broad / confirmed / rising |
| 🟡 **Amber** | Mixed / cautious / transitional / "watch this" |
| 🔴 **Red (rose)** | Weak / fragile / narrow / broken / falling |
| 🔵 **Cyan** | The live intraday signal — a *leader*, an active reading |
| 🟣 **Fuchsia/magenta** | The AI‑dependency reading (a slower, structural measure) |
| ⚪ **Slate (grey)** | Neutral, flat, or "still warming up / no data yet" |

**Two clocks running at once.** Most of the dashboard is **intraday** — it
reacts within minutes to today's tape. One card, **AI build‑out dependency**,
is **structural/daily** — it moves over weeks, not minutes. They're deliberately
kept separate; don't expect the AI card to twitch with the live ones.

**Warming up.** When the app first starts (or early in a session) cards may say
*"Warming up"* or *"Gathering data — X sessions."* That's normal: some signals
need enough bars or enough past sessions before they mean anything. Cards stay
on screen while warming rather than disappearing.

**Hover the ⓘ.** Almost every card has an info tip — this manual expands on each
of those.

---

## 1a. The Overnight Board — pre‑market ribbon  🌙

> *In‑app tip: "The day's biggest Nasdaq‑100 movers before the open, set against
> the overnight tape. Descriptive context for the open — not a forecast of where
> price goes."*

A thin ribbon at the very top of the dashboard, all about **what happened
overnight and into the pre‑market**. It's most useful before the bell and
**auto‑collapses to a one‑line summary around 10am ET** (and on weekends), since
by then the day is its own story. Click the collapsed line to expand it.

**What you see, top to bottom:**

- **The overnight tape** — `NQ` and `ES` (US futures, the direct overnight read on
  the open), `Asia semis` (the Taiwan/Korea/Japan chip complex, closed hours
  before our open), and `Europe` (ASML/Euro tech). Green ▲ / red ▼. Plus a
  **breadth** figure (what % of the Nasdaq‑100 is gapping green).
- **The open lean** *(pre‑open only)* — e.g. *"→ tech open leans UP (~60% hist.)"*.
  This is the one forward hint, and it's deliberately modest: overnight Asia has
  historically called the *direction of the open* about 60% of the time. It's a
  lean, not a call, and it disappears once the bell rings.
- **The mover chips** — the top 5–10 Nasdaq‑100 names by overnight gap, each with
  a colored gap bar and one or two **tags** telling you *what kind* of move it is:

| Tag | Meaning |
|-----|---------|
| **with tape** | gapping the *same* way as the overnight futures — in step with the market |
| 🟡 **counter‑tape** | gapping *against* the futures — swimming upstream (watch it) |
| **{sector}‑wide** | its sector peers are gapping the same way — a broad, thematic move |
| 🟡 **lone** | moving *alone* — its sector isn't following, so it's stock‑specific (usually news) |
| 🟡 **fading** | the pre‑market move is rolling over rather than holding |

The amber tags (**counter‑tape**, **lone**, **fading**) are the "watch this" flags —
they mark moves that aren't backed by the tape, the sector, or their own momentum.
Example: *ARM +6%, counter‑tape · lone* = ARM is up while futures are down **and**
while the rest of semis aren't — an idiosyncratic, news‑driven pop, not a sector tide.

**Important — what it does NOT do:** it makes **no prediction** about whether a gap
will hold or fade during the day. We tested that directly and it doesn't hold up
(big "backed" gaps actually fade *slightly* more often). So the board is honest
situational awareness — *what moved, with or against what* — to help you read the
open and prepare, not a buy/sell signal. Expand the **table ↓** for the full list.

---

## 2. The headline — QQQ projection

> *In‑app tip: "Where QQQ may be headed over the next few minutes, with a
> likely price range and whether the move should continue, stall, or is
> fragile."*

**What you see:** a projected QQQ price and a price band (e.g. `$XXX.XX – $XXX.XX`),
a short horizon (`X‑min horizon`), an expected move (`±X.XX%`), a direction arrow
(▲ up / ▼ down / ■ flat), and a **verdict chip**:

- 🟢 **Continue** — the move looks supported and may keep going.
- 🟡 **Stall** — momentum is fading; the move may pause.
- 🔴 **Fragile** — looks strong on the surface but weak underneath; reversal risk.
- ⚪ **Warming up** — not enough data yet.

A small status badge (e.g. `bullish · 55%`) shows the lean and a rough
probability. On the side you'll see **Direction**, **Prob. up**, and
**Confidence** meters.

**How it's worked out:** from QQQ's recent intraday bars plus the health/fragility
read below — the projection isn't a price prediction so much as "given how the
move is currently supported, here's the likely near‑term path and how much to
trust it."

**How to use it:** treat the verdict, not the exact price, as the takeaway.
*Continue* with high confidence is a very different picture from *Fragile* at the
same projected price.

---

## 3. The three quick gauges (KPI row)

### 3a. Strongest sector · 30m  ⚡
> *In‑app tip: "The sector that's moved up the most in the last 30 minutes.
> Green = gaining, red = fading."*

**What you see:** the leading sector ETF (e.g. `XLK · Technology`) and its
30‑minute move. **How it's worked out:** each tracked sector ETF is ranked by its
rolling 30‑minute momentum; the top one shows here. **Use it:** a fast read of
"what's pulling tech right now."

### 3b. QQQ internal health  ❤  (0–100)
> *In‑app tip: "A 0–100 score for how broad and healthy the move under QQQ is.
> Higher = more sectors are backing it, so the move is more trustworthy.
> Below 50 = narrow and shaky."*

**What you see:** a circular gauge (🟢 ≥70 / 🟡 45–70 / 🔴 <45), a **regime label**
(e.g. *Broad Participation*, *Narrow Participation*, *AI Breadth Expansion*), and
a one‑line summary. **How it's worked out:** combines how many sectors back the
move (breadth/leadership) against how much hidden weakness there is (fragility).
**Use it:** the single best "should I trust this move?" number. High = broad and
trustworthy; low = a few names carrying a shaky tape.

### 3c. Fragility meter  ⚠
> *In‑app tip: "How much hidden weakness is under the move. LOW = well
> supported. HIGH = the surface looks strong but it's weak underneath, so it's
> more likely to reverse."*

**What you see:** a level — 🟢 **Low** / 🟡 **Elevated** / 🔴 **High** — a percentage,
and which sectors are diverging. **How it's worked out:** measures how many
sectors are pulling *against* the headline move. **Use it:** the counter‑weight
to "internal health." High fragility under a green price is the classic
"looks fine, about to wobble" setup.

---

## 4. AI build‑out dependency  🧠  *(flagship, structural · daily)*

> *In‑app tip: "How much of QQQ's day‑to‑day move now comes from the AI
> build‑out — memory, optics, networking, power and grid. The % is today's
> reading, the arrow shows if it's rising or falling versus a month ago, and the
> bars show which area QQQ leans on most. A big‑picture trend, separate from the
> live intraday signals."*

This is the signature RelativeQs lens: **how much of the Nasdaq is now an AI‑capex
trade.**

**What you see:**
- A **headline %** — how much of QQQ's daily moves are explained by the AI
  build‑out complex.
- A **trend** (`▲ XX pts over [window]`) — rising or falling versus a month ago.
- An optional **◆ highest** badge when the reading is at a peak for the window.
- A **mini trend chart** of the dependency over time.
- **Coupling bars** — one per bottleneck theme (Memory, Optics / EUV,
  Servers / Networking, Power, Grid build‑out), each showing how tightly that
  area tracks QQQ, with an up/down trend arrow and the member tickers in
  parentheses.

**Window selector** (`Window`):
> *In‑app tip: "How far back to measure which bottleneck QQQ is leaning on.
> Shorter windows catch recent shifts; longer ones show the bigger trend. 2
> weeks is the floor — anything shorter is too few days to be reliable, so it
> gets noisy."*

Pick *Since inception* for the big picture or *Last N days* for recent shifts.
Windows under ~30 days show a *"short window · noisier"* caution — read those
with a grain of salt.

**How it's worked out:** measured from **real daily returns** of the bottleneck
baskets against QQQ — not index weights, not guesswork. The basket is
configurable as new AI‑infrastructure funds and companies emerge.

**How to use it:** this is a *regime* read, not a trade trigger. A rising number
means tech's fortunes are leaning harder on the AI supply chain; the tallest
coupling bar tells you which bottleneck is doing the carrying right now.

---

## 5. Lead / lag detection  *(Pro)*

> *In‑app tip: "Which sector reliably moves BEFORE QQQ, measured on 15‑min (or
> 5‑min) bars. A lead is only reported once it REPEATS on 3 bars in a row — so
> most of the time it honestly says 'no repeating lead.' 'Broke ranks' flags a
> sector that usually moves with QQQ but just decoupled. The hit‑rate below
> scores follow‑through on the confirmed lead."*

**What it answers:** does any sector reliably move *before* QQQ, so it can act as
an early tell?

**Timeframe toggle:** `5m` (faster, noisier, more false leads), `15m` (default,
steadier), `Daily` (cross‑day, ~1 year lookback).

**The headline has three honest states:**
1. **Confirmed leader** — e.g. `XLK leads QQQ by 15m`, with a `confirmed ×3`
   badge and a coupling %. This only appears once the same lead repeats on **3
   bars in a row**.
2. **Possible lead** — `confirming X/3…`: a lead is forming but not yet trusted.
3. **No repeating lead** — sectors are just moving together. This is the honest
   default most of the time; the tool deliberately refuses to cry "leader" on
   noise.

**Broke ranks (decoupling watch):** ⚠ flags a sector that *usually* tracks QQQ
but just diverged, e.g. `XLY (usually 85% → now 62%)`. An early warning that
something's changing.

**Stability badge:**
> *In‑app tip: "Whether the same sector keeps leading day after day. TRADEABLE =
> a consistent leader. UNSTABLE = it keeps changing. GATHERING = not enough
> sessions yet."*

🟢 **Tradeable** (a consistent leader), 🟡 **Unstable** (it keeps changing),
⚪ **Gathering** (need more sessions).

**Hit rate:**
> *In‑app tip: "How often QQQ actually followed the leader in the past. Compare
> it to the baseline — being above it is what counts."*

Shows how often QQQ actually followed the leader over a chosen horizon
(`Auto · ~XXm`, or pick manually). The number only matters **relative to the
baseline** — beating it is the signal.

**The lead/lag table** lists each sector's role:

| Role | Color | Meaning |
|------|-------|---------|
| **Leader** | 🔵 cyan | moves ahead of QQQ |
| **Confirmer** | 🟢 emerald | moves with QQQ (coincident support) |
| **Diverging** | 🔴 rose | moving opposite to QQQ |
| **Weak** | ⚪ slate | little relationship |

*"Lead = minutes ahead of QQQ · 0 = coincident."*

**How it's worked out:** by lining up each sector's moves against QQQ's at
different time offsets and seeing which offset fits best — then requiring it to
repeat before calling it a lead.

**How to use it:** when there's a *confirmed, tradeable* leader with a hit‑rate
above baseline, that sector is a genuine early tell. Otherwise, take "no
repeating lead" at face value. Always cross‑check the **Correlation regime**
card (§9) — leads mean little when sectors aren't coupled.

---

## 6. Confirmation gate  *(Pro)*

> *In‑app tip: "A quick pre‑trade check. CONFIRMED = the move has broad sector
> backing. UNCONFIRMED = only a few sectors are in, so fade risk. FRAGILE =
> shaky underneath, trade with caution."*

**What you see:** a big state pill — 🟢 **CONFIRMED** / 🟡 **UNCONFIRMED** /
🔴 **FRAGILE** — the target direction (`QQQ UP/DOWN/FLAT`), a message, and three
numbers: **Participation** (how many sectors are in), **Leaders agree** (yes/no),
**Fragility** (%). **How it's worked out:** rolls up breadth, leader agreement
and fragility into one go/caution read. **Use it:** the "should I act on this
move?" gut‑check, in one pill.

---

## 7. What's moving QQQ (attribution)  *(Pro)*

> *In‑app tip: "What's pushing QQQ right now — how much of its move comes from
> semis, software and mega‑caps. 'Explained' is how much these account for; the
> rest is everything else."*

**What you see:** a sentence describing the main drivers, then a ranked list of
contributors (e.g. `Software (IGV) · rising +68%`) each with a bar, and a footer
`Explained XX% · residual YY% · over ZZm`. **How it's worked out:** attributes
QQQ's recent move across the key theme ETFs; "residual" is everything not
captured by them. **Use it:** to know *what kind* of move this is — semis‑led,
software‑led, mega‑cap‑led — and how much is left unexplained.

---

## 8. QQQ breadth · 100 stocks  *(Pro)*

> *In‑app tip: "How many of QQQ's ~100 stocks are rising. Equal‑weight = how
> many names are up. Cap‑weight = whether the big names are doing the lifting.
> Cap well above equal = a few giants carrying a narrow market; equal above cap
> = broad strength."*

**What you see:** a state pill — 🟢 **BROAD** / 🟡 **MIXED** / 🔴 **NARROW** — an
advancing count (`XX/YY advancing`), and two numbers: **Equal‑weight** (% of
*names* up) and **Cap‑weight** (% of index *weight* up).

**The key insight:** compare the two.
- **Equal‑weight above cap‑weight** → broad, healthy strength (lots of names up).
- **Cap‑weight well above equal‑weight** → a few giants carrying a narrow market.

**How it's worked out:** by checking all ~100 Nasdaq‑100 constituents, counting
how many are up, both by simple count and weighted by size. **Use it:** the
ground truth on whether a rally is real or just the megacaps.

You can turn on **email alerts** here (🔔) to be notified when this flips between
broad / mixed / narrow — see §12.

---

## 9. Correlation regime  *(Pro)*

> *In‑app tip: "Whether the tech sectors are moving together right now. Together
> = the lead/lag and rotation signals are reliable. Doing their own thing =
> treat those signals as noise today."*

**What you see:** a pill — 🟢 **COUPLED** / 🟡 **TRANSITIONAL** / 🔴 **FRAGMENTED** —
an average correlation, and a reliability message. **How it's worked out:** the
average correlation across the tech sectors right now. **Use it as the master
switch:** when **Fragmented**, treat the lead/lag and rotation cards as noise.
When **Coupled**, those signals are meaningful. Read this card *first*.

---

## 10. Rolling correlations · 4h  *(Pro, chart)*

> *In‑app tip: "How closely QQQ tracks XLK and SMH over time (1.0 = moving in
> lock‑step). Falling = leadership is breaking down, often an early warning."*

**What you see:** a bar chart in 4‑hour buckets with two series — 🔵 **QQQ·XLK**
(tech) and 🟣 **QQQ·SMH** (semis). 1.0 = moving in lock‑step. **Use it:** watch
the *trend*. Falling bars mean QQQ and its usual leaders are drifting apart —
often an early warning that leadership is breaking down.

---

## 11. ETF signal universe  *(Pro)*

> *In‑app tip: "Live stats for each sector ETF — daily change, momentum and
> relative strength — so you can see which sectors agree or disagree with QQQ's
> move."*

**What you see:** a grid of tiles for the top 8 sector ETFs by 30‑minute
momentum, each with its symbol, name, a momentum badge (▲ cyan gaining / ▼ rose
fading), and a strength meter. A **⤓ Export CSV** button saves the signal
history. **Use it:** a scan of which sectors agree or disagree with QQQ right
now.

---

## 12. Breadth‑shift email alerts  🔔  *(Pro)*

**What it does:** emails you when Nasdaq‑100 participation flips between **broad**,
**mixed** and **narrow** — so you don't have to watch the screen. Toggle it on in
the breadth card (or its own card), and use **send test** to confirm delivery.

---

## 13. Quick reference

### Status chips at a glance
| Card | 🟢 Green | 🟡 Amber | 🔴 Red |
|------|---------|---------|--------|
| Projection verdict | Continue | Stall | Fragile |
| Confirmation gate | Confirmed | Unconfirmed | Fragile |
| Breadth | Broad | Mixed | Narrow |
| Correlation regime | Coupled | Transitional | Fragmented |
| Internal health | ≥70 | 45–70 | <45 |
| Fragility | Low | Elevated | High |

### Lead/lag roles
🔵 Leader (ahead of QQQ) · 🟢 Confirmer (with QQQ) · 🔴 Diverging (against QQQ) ·
⚪ Weak (no relationship). *Lead is in minutes; 0 = coincident.*

### Glossary
- **Breadth** — how many stocks/sectors are participating in a move.
- **Equal‑weight vs cap‑weight** — counting every name the same vs weighting by
  company size; the gap tells you if a few giants are carrying the market.
- **Coupling / correlation** — how tightly two things move together (1.0 = lock‑step).
- **Confirmed (×3)** — a lead that repeated on 3 bars in a row before being reported.
- **Decoupling / "broke ranks"** — a sector that usually tracks QQQ just diverged.
- **Fragility** — hidden weakness pulling against the headline move.
- **Hit rate** — how often QQQ historically followed the leader; judge it against
  the baseline.
- **Regime** — the current "weather" (e.g. coupled vs fragmented); sets whether
  other signals are reliable.
- **AI build‑out dependency** — how much of QQQ's daily move is explained by the
  AI‑capex supply chain (memory, optics, networking, power, grid).
- **Residual** — the part of QQQ's move not explained by the tracked themes.
- **Horizon** — the look‑ahead window a projection or hit‑rate is measured over.

---

## 14. Putting it together — a sensible reading order

1. **Correlation regime** — are signals reliable today? (If *Fragmented*, lower
   your trust in lead/lag and rotation.)
2. **QQQ internal health + Fragility** — is the move broad or shaky?
3. **Confirmation gate** — the one‑pill go/caution read.
4. **Breadth** — is it real strength or just the megacaps?
5. **Lead/lag** — is there a confirmed, tradeable early tell right now?
6. **What's moving QQQ + ETF universe** — what kind of move is this?
7. **AI build‑out dependency** — the slow backdrop: how AI‑driven is this regime?

A move you'd trust looks like: **Coupled** regime, **high health / low
fragility**, **Confirmed** gate, **Broad** breadth. The opposite — *Fragmented,
low health, high fragility, Narrow* — is exactly the kind of rally that looks
fine on price and isn't.

---

*RelativeQs is Nasdaq‑100 internals analytics and education — not investment
advice. Past performance does not guarantee future results.*
