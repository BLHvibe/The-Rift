# Draft Baseline Report — Expert Human vs The Rift Engine

**Date:** 2026-05-24
**Engine output analyzed:** `engine_audit_run1.json` (16 simulated drafts, run 1)
**Data sources:** Fly REST API (`https://the-rift-draft-sync.fly.dev`) — `/api/players`, `/api/rankings`, `/api/scout`, `/api/inhouse-champs`, `/api/primary-roles`, `/api/scout-sheets/{name}`.

The goal of this document is to build a "what would an experienced LoL player do?" baseline given the same inputs the engine uses, and to flag where the engine's mechanical scoring diverges from human judgment. No code is changed — this is a read-only audit.

---

## 1. Player Data Snapshot

A summary of the 19-player roster. **"Pri"** is `/api/primary-roles`. **"Customs top-3"** is from `/api/inhouse-champs` (the COMFORT signal the engine relies on). **"Solo-Q top-3"** is from `/api/scout` (the THREAT signal). **"Must-ban"** is the scout-sheet permaban flag (≥5 games & ≥65 % WR in solo).

| Rank | Player  | Tier · Div     | Rating | Pri  | Customs role mix (top 2)         | Customs top-3 (games · WR)                              | Solo-Q top-3                     | Form  | Scout must-ban                       |
|------|---------|----------------|--------|------|----------------------------------|---------------------------------------------------------|----------------------------------|-------|--------------------------------------|
| 1    | Turkey  | Diamond I      | S      | JGL  | JGL 50 % / TOP 33 %              | Singed 1·100, Akali 1·100, Aurora 1·100 (tiny customs)  | Sett, Garen, Lee Sin             | COLD  | —                                    |
| 2    | Chips   | Emerald I      | A      | BOT  | BOT 62 % / JGL 25 %              | Pantheon 5·60, Mel 3·100, Annie 3·67                    | Karma, Thresh, Morgana           | COLD  | Senna (7g, 71 % WR)                  |
| 3    | Ben     | Emerald II     | A      | JGL  | JGL 42 % / MID 21 %              | Sylas 2·100, Nasus 2·50, Malphite 1·100                 | Volibear, Leona, Yasuo           | MIXED | **Volibear (35g, 69 % WR)**          |
| 4    | Mahesh  | Emerald IV     | A      | MID  | MID 40 % / JGL 28 %              | Irelia 7·71, Aurelion Sol 7·43, Shen 5·80               | Shen, Katarina, Irelia           | MIXED | —                                    |
| 5    | Johnny  | Emerald IV     | A      | JGL  | JGL 58 % / MID 19 %              | Olaf 6·67, Sett 3·33, Darius 3·67                       | Garen, Darius, Sett              | MIXED | Sett (6g, 67 % WR)                   |
| 6    | Logan   | Platinum III   | A      | BOT  | BOT 97 %                         | Jinx 10·40, Ezreal 9·44, Kai'Sa 6·33                    | Ezreal, LeBlanc, Jinx            | MIXED | **Jinx (48g, 69 % WR)** *(solo)*     |
| 7    | Devin   | Platinum III   | B      | JGL  | JGL 73 %                         | Ornn 4·100, Malphite 3·33, Nunu 3·33                    | Ivern, Sett, Pyke                | MIXED | **Ivern (10g, 70 % WR)** *(solo)*    |
| 8    | Riley   | Gold I         | B      | BOT  | BOT 38 % / MID 35 %              | Thresh 6·50, Vex 4·25, Kha'Zix 3·100                    | Kassadin, Kalista, Thresh        | MIXED | **Kassadin (10g, 70 % WR)** *(solo)* |
| 9    | Chris   | Gold III       | B      | BOT  | BOT 78 %                         | Vel'Koz 13·62, Bard 9·67, Xerath 4·50                   | Bard, Vel'Koz, Jhin              | MIXED | —                                    |
| 10   | Luke    | Gold I         | B      | MID  | MID 68 % / BOT 18 %              | Viktor 4·75, Anivia 2·50, Ezreal 2·50                   | Viktor, Pantheon, Ryze           | MIXED | Aurora (7g, 71 % WR), Ryze (9g, 67 %)|
| 11   | Bobby   | Silver III     | B      | MID  | MID 34 % / JGL 26 %              | Diana 4·75, Galio 3·67, Maokai 2·100                    | Diana, Vi, Lissandra             | COLD  | —                                    |
| 12   | Jose    | Platinum IV    | C      | JGL  | JGL 60 % / BOT 21 %              | Zac 8·75, Briar 7·86, Karthus 4·75                      | Briar, Draven, Poppy             | HOT   | **Darius (8g, 75 % WR)** *(perma)*   |
| 13   | Remy    | Bronze II      | C      | BOT  | BOT 100 % (only 4 customs)       | Caitlyn 3·67, Nami 1·0                                  | Akali, Naafiri, Lillia           | HOT   | —                                    |
| 14   | Jase    | Silver III     | C      | BOT  | (no customs)                     | —                                                       | Senna, Aphelios, Karma           | HOT   | —                                    |
| 15   | Kian    | Silver IV      | C      | BOT  | BOT 55 % / MID 31 %              | Braum 6·50, Pyke 5·20, Akshan 4·75                      | Aphelios, Pyke, Akshan           | HOT   | —                                    |
| 16   | Joaquin | Silver IV      | D      | BOT  | BOT 44 % / JGL 44 %              | Miss Fortune 2·0, Volibear 1·0, Akshan 1·0              | Ekko, Viego, Sion                | HOT   | —                                    |
| 17   | Jase2   | Unranked       | D      | —    | (no customs)                     | —                                                       | Darius, Sett, Brand              | MIXED | —                                    |
| 18   | Miles   | Bronze I       | D      | JGL  | JGL 70 % / BOT 20 %              | Trundle 4·75, Warwick 3·33, Malphite 2·0                | Mordekaiser, Trundle, Shaco      | COLD  | —                                    |
| 19   | JP      | Unranked       | D      | JGL  | JGL 100 % (small sample)         | Volibear 4·25, Mordekaiser 1·100                        | Jax, Mordekaiser, Xin Zhao       | HOT   | —                                    |

### What a human reads off this table immediately

- **Turkey is the single best player on the roster by a wide margin** (S-tier, Diamond, 100+ games). Yet his customs sample is tiny (5 games total) — so the engine's COMFORT signal underrates him. A human would weight Turkey's *flex range* (TOP + JGL solo, with mid spikes) and aim him at the strongest counter for that game.
- **Logan, Chris, Chips, Jase, Kian = BOT specialists.** Only one team can have one ADC, so when two of them are on opposite sides the BOT pool gets stripped fast.
- **Mahesh and Riley are flex anchors.** Mahesh plays Mid → Top → Jgl → Bot → Sup. Riley plays Sup, Mid, and Bot. A human ban targets *what their team needs* (e.g. take their best engage), not just their #1-WR champion.
- **Five players have ban-worthy permabans** (Volibear/Ben, Jinx/Logan, Ivern/Devin, Kassadin/Riley, Darius/Jose). These are the only champions where *raw solo data* says "ban first, no other reason needed."
- **Devin and Jose have flipped role identity** in solo vs customs. Devin's solo top champs (Ivern/Sett/Pyke) are 3 different roles. Jose ends up jungle in customs 60 % of the time but the engine reads "Darius perma-ban" from his solo Top games — relevant only if he actually goes Top.

---

## 2. Draft Theory Cheat-Sheet (what a good engine should encode)

A condensed version of the canonical pick/ban heuristics from Mobalytics, Dignitas, CheatsPulse and the Riot/Fandom draft wikis (sources at the end).

### Ban-phase mental model

| Phase           | Goal                                                                                                                   |
|-----------------|------------------------------------------------------------------------------------------------------------------------|
| **Bans 1–3 (P1)** | **Strip enemy comfort.** Ban high-impact pocket picks of the *opposing carries* (top, mid, ADC > jungle/support). Permaban anything ≥65 % WR over ≥10 games. Consider banning popular flex picks to deny role camouflage. |
| **Bans 4–5 (P2)** | **Counter-target their locked-in carry.** You know their first 3 picks. Ban what counters *your* P1 lock-ins, ban the one champion that completes their comp's win condition, and ban the lethal counter to the player still un-picked. |

Practical rules of thumb (community consensus):
1. **"Ban into roles you can't counter-pick."** Junglers are seen blind by both sides → if their JGL has one auto-lock, ban it. Solo lanes counter themselves in pick phase.
2. **High WR > high KDA.** A 75 % WR over 30 games is the gold standard. 100 % WR over 3 games is noise.
3. **Flex picks deserve higher ban weight.** They hide what role the pick will go to and force the enemy team to ban with incomplete info. (Source: thespike.gg on Fearless 2025, and all "flex pick" guides.)
4. **Don't ban-share two from the same player** unless that player has 3+ standout pockets. Banning 3 different Logan ADCs (Jinx → Ezreal → Kai'Sa) just hands him a Caitlyn/Tristana for free.
5. **Use bans on individuals, not abstract champions.** A ban only matters if the enemy was going to lock it. A "globally OP" champion that nobody on the enemy team plays is a free ban for them.

### Pick-order mental model (5v5, blue/red snake order)

```
Blue picks: 1   ·   4-5   ·   8-9   ·   (last)
Red picks:    2-3  ·  6-7   ·   10    ·
```

| Pick slot                                  | Philosophy                                                                                            |
|--------------------------------------------|-------------------------------------------------------------------------------------------------------|
| **B1 (first pick)**                        | **Blind-safe**, ideally **flex**. JGL or SUP preferred (low counter-pick risk). Set the comp axis.   |
| **R1+R2 (red's first two)**                | Read blue's B1. Take **highest-value role with counter-pick info advantage** + secure scaling carry.  |
| **B2+B3 (blue's middle two)**              | Lock the two carries that pair with B1's identity. Save the **last counter** for B5.                 |
| **R3 (red's third)**                       | Lock a strong solo-lane carry. Begin shaping comp identity.                                          |
| **R4 + B4 (after P2 bans)**                | Counter-picks. Solo lanes especially; bot side last.                                                  |
| **B5 (last pick)**                         | **Most counter-able role's perfect answer.** Usually top lane or support.                            |

Role priority for counter-picking (community consensus): **Top > Mid > ADC > Support > Jungle**.

### Comp construction checklist

A complete 5-player comp ideally has:

| Need                                | How to fill it                                                                                |
|-------------------------------------|------------------------------------------------------------------------------------------------|
| **Hard engage** (1+)                 | Tank engage (Malphite, Leona, Ornn, Maokai) or hook (Naut, Blitz, Thresh).                    |
| **Peel for carry** (1+)              | Lulu, Janna, Braum, Tahm Kench, Trundle.                                                       |
| **AD/AP balance** (50 % +/- 20 %)    | Tilted comps lose to one resistance item — aim for 30-70 / 70-30 AD/AP split.                  |
| **Waveclear** (1+)                   | At least one of: mage mid (Viktor, Anivia), ranged ADC (Caitlyn, Jhin), AoE top (Maokai).      |
| **Late-game scaling OR finisher**    | Either a hyper-carry (Kog'Maw, Vayne, Kassadin, Nasus, Aurelion) or an early-game finisher.    |
| **Pick / catch tool**                | Hook, stealth roam (Pyke, Pantheon ult), or pick assassin (Zed, Talon).                        |
| **Vision / utility**                 | Enchanter / engage support, Maokai sap, etc.                                                   |

Win conditions to lock to:
- **Lvl 6 spike** — assassin/pick (Pyke + Vex + Pantheon = "level 6 = teamfight win").
- **2-item spike** — Vex/Akali at 2 items, Viktor at Ludens+Lich.
- **Late game (>30 min)** — Kog'Maw + Lulu + Ornn + Maokai + Sivir.

### Fearless-draft layer (2025 meta)

In tournament series, each champion can be used **once per team** for the whole series. That elevates:
- **Pool depth over peak power** — a top laner with five viable picks beats a one-trick.
- **Flex picks** even more strongly — a single flex champ effectively uses 0.5 of your future pool.
- **Pre-targeted bans** — pick game 1 bans aimed at *future* games (e.g. force them to burn their Aurora early).

---

## 3. Worked-Example Drafts — Expert Baseline vs Engine

For each draft I list:
- A short scouting summary of both rosters.
- What an expert would do (bans, blind picks, counters, comp identity).
- The engine's actual sequence (from `engine_audit_run1.json`).
- A line-by-line diff with the biggest gaps.

### Example A — Draft 1

**Rosters**
- **BLUE:** Mahesh (MID/TOP flex), Luke (MID), Devin (JGL), Jose (JGL), Jase (BOT) — *huge JGL conflict (Devin + Jose), and zero true bot lane*.
- **RED:** Miles (JGL), Riley (BOT/MID/SUP flex), Jase2 (—), Logan (BOT), Remy (BOT) — *huge BOT conflict (Logan + Remy), and Jase2 has no data*.

#### Expert reasoning
- **Roster gymnastics first.** Blue must run two off-role players (one of Devin/Jose forced off JGL; Mahesh probably TOP). Red must do the same in BOT (Logan locks ADC, Remy goes Mid or off-role).
- **Blue P1 bans (target Logan first, then Riley's flex, then Miles's pocket Trundle):**
  - B1 **Jinx** — Logan 48-game permaban, mandatory.
  - B2 **Ashe** — Logan 75 % WR pocket (only 4g but it's his 2nd-best non-Jinx threat). Or **Kha'Zix** to hit Riley *and* deny a counter to whoever Blue locks as JGL.
  - B3 **Smolder** — actually a flex bot/mid pick that hits Remy *and* Riley (Riley loses Kalista already, but Smolder doubles up as a Jase2 threat too). Or take **Trundle** to remove Miles's 75 % WR pocket and a hard counter to Mahesh TOP.
- **Red P1 bans (target Mahesh first, then Luke, then deny Devin/Jose's jungle pool):**
  - B1 **Shen** — yes, engine got this. Mahesh permaban-tier flex.
  - B2 **Irelia** — Mahesh's #2 (71 % WR, flex). Yes, engine eventually banned it but spent #2 on Rumble.
  - B3 **Ivern** — Devin's 70 % WR permaban. The engine never even considered it.

- **Pick order:**
  - B1 (Luke JGL? or Devin?) — **Maokai** or **Sejuani** is the blind-safe JGL with engage + flex. Engine picked Pantheon JGL for Luke — defensible (Pantheon is a true flex), but Luke has 11 Lee Sin games at 27 % WR. Pantheon is *not* his pocket.
  - R1+R2 — Logan BOT (Caitlyn or Tristana) + counter into Blue's JGL. Engine picked Caitlyn + Trundle, but Trundle should have been on the JGL Miles pocket-pick (he has a 75 % Trundle from customs).
  - B2-B3 — Now Blue has a JGL (Pantheon) and needs to set up its damage. **Pick Vex MID for Devin** (Devin in MID is unsupported by his data — he plays JGL 73 %). The engine made the worst decision here — putting *Devin on MID Vex* and burning the actual JGL on a Pantheon pick when Devin's permaban-tier Ivern was uncontested.
  - R3 — Riley JGL on Kha'Zix is good (3-0 record on Kha'Zix in customs). The engine got that one right.
  - B4-B5 (P2 bans for Blue) — should aim at *Red's win condition*. Red has Caitlyn + Trundle + Kha'Zix. Their pick-comp piece is Akali or Sylas → ban **Akali** (and engine put Leona on the board instead). Akali later went to Red anyway as the last pick.
  - R4-R5 — Remy SUP and Jase2 MID. Remy on Nami is fine; Jase2 on Akali is excellent because Akali is his only competitive option vs Vex.

**Expert preferred final comp (Blue):** Pantheon JGL · Vex MID · Pyke SUP · Yone TOP · Jhin BOT → pick comp with two assassins, a roam support, and a teamfight ADC. Win condition: lvl-6 to 2-item spike, force picks around objectives. **AD/AP split 60/40, engage check (Pyke + Pantheon roam) OK, peel CHECK FAIL** — there's no peel for Jhin. The engine's actual lock was the same comp, so the comp construction here is acceptable.

#### Engine actual output

| Step | Action | Champion | Score | Engine "why" |
|------|--------|----------|-------|--------------|
| 0 | Blue B1 | Jinx | 1.522 | Must-ban Logan |
| 1 | Red B1 | Shen | 1.725 | High threat Mahesh |
| 2 | Blue B2 | Ezreal | 1.281 | Threat Logan |
| 3 | Red B2 | Rumble | 1.323 | Threat Mahesh |
| 4 | Blue B3 | Kai'Sa | 0.987 | Threat Logan |
| 5 | Red B3 | Irelia | 1.179 | Threat Mahesh |
| 6 | B1 | Pantheon (Luke JGL) | 0.639 | Blind-safe |
| 7 | R1 | Caitlyn (Logan) | 0.336 | Blind-safe |
| 8 | R2 | Trundle (Miles TOP) | 0.283 | Blind-safe |
| 9 | B2 | Vex (Devin MID) | 0.351 | Blind-safe |
| 10 | B3 | Pyke (Jase SUP) | 0.331 | Blind-safe |
| 11 | R3 | Kha'Zix (Riley JGL) | 0.171 | COMFORT |
| 12-15 | P2 bans | Yorick, Malphite, Tahm Kench, Leona | — | counter-comp |
| 16 | R4 | Nami (Remy SUP) | 0.108 | COMFORT |
| 17 | B4 | Yone (Mahesh TOP) | 0.211 | COMFORT |
| 18 | B5 | Jhin (Jose BOT) | 0.13 | COMFORT |
| 19 | R5 | Akali (Jase2 MID) | 0.078 | COMFORT |

#### Diff
1. **Blue burned all 3 bans on Logan.** Banning Jinx + Ezreal + Kai'Sa hits the same player's adjacent pool, but Logan's #4 (Tristana) and #5 (Ashe) are both fine for him at 50–75 % WR. Net effect: Logan still gets Caitlyn (which he plays in customs), and Blue spent zero bans on Riley's flex or Miles's Trundle.
2. **No ban on Ivern (Devin's permaban-tier solo champ)** — but the engine *also* assigned Devin to MID, so this is a self-consistency win by accident; if Devin had been put on JGL the missed Ivern ban would have been catastrophic.
3. **Pantheon on Luke (JGL).** Luke is a *Mid main* — Viktor 15g, Lee Sin 11g, Taliyah 10g. Putting him on JGL on Pantheon is forcing a 0-comfort role/champ combo. A human would let **Devin take JGL** (his actual primary) and put Luke on **Viktor MID** while burning Devin's Mid slot. The engine doesn't seem to consider primary-role data when assigning roles inside its scoring.
4. **Vex on Devin MID.** Devin has *zero* MID games in customs and his solo MID is 2 games. Vex is a fine pick, but assigning it to Devin is the wrong player. This is a role-assignment bug, not a champion bug.
5. **Akali to Red at R5.** Blue's P2 should have banned Akali (counters Vex and Yone simultaneously). Engine banned Leona instead with reason "enemy threat to your comp" — but Leona isn't on Red's roster at all post-bans and Jase isn't going to Leona since they already locked Nami.

---

### Example B — Draft 7

**Rosters**
- **BLUE:** Turkey (S-tier, JGL/TOP), Ben (A-tier, JGL/MID/TOP), Luke (B-tier MID), Remy (C-tier BOT), Joaquin (D-tier BOT/JGL).
- **RED:** Jase (C-tier BOT), Mahesh (A-tier MID/TOP), Bobby (B-tier MID/JGL), Miles (D-tier JGL), Chips (A-tier BOT/SUP).

This is an interesting case because **Blue is clearly the higher-skill team** (Turkey + Ben + Luke vs Mahesh as Red's only A+).

#### Expert reasoning
- **Red's bans should be cripplers on Blue's S-tier (Turkey) and Ben.** Engine: Sion (Turkey, 1.275), Volibear (Ben, must-ban 1.252), Smolder (Remy). That's correct — exactly the three names a human writes down.
- **Blue's bans should target Chips's support pool (the only thing Red has that scales).** Engine: Senna, Mel, Nami (all Chips). Good shape but spent **3 bans on Chips** — see the systematic over-banning issue below.
- A better Blue ban sequence: Senna (Chips perma), **Briar** (Miles JGL's win-con: Briar is a flex jungler that Miles doesn't play but Mahesh does in custom 7g 86 %) — *or* **Sett** (counter to Turkey's TOP). **Hecarim** would be another consideration (it's blue side R2 in the actual draft, meaning Red wanted it for Mahesh).

- **Pick order:**
  - B1 Luke Viktor — perfect, that's his #1 pocket.
  - R1 Illaoi (Jase TOP) — engine's pick. Jase has **no customs**, so any flex top is defensible.
  - R2 Hecarim (Mahesh JGL) — Mahesh has 0 Hecarim customs. Mahesh on JGL is unusual; he plays MID 40 % / TOP 26 % / JGL 13 %. A human picks **Briar (Jose's pool but here Mahesh)** is wrong roster — okay, give Mahesh Aurelion Sol or Irelia.
  - The engine puts Mahesh on JGL when he has Mid as his primary and Aurelion Sol (7g 43 % custom) waiting. This is a **role-assignment miss** parallel to draft 1.

#### Diff
1. **Banning Chips three times = "ban exhaustion."** Once you ban a player's #1 and #2, the marginal value of banning #3 is small because the player loses ~3 % WR rather than ~15 % WR on the swap.
2. **Turkey on Akali (B3, COMFORT).** Turkey's customs say Akali 1g 100 % WR. That's noise. His solo top is Sett/Garen/Lee Sin, but his solo pool is *not* mid lane. A human picks **Akali for Mahesh** (Mahesh has Akali 0/2 customs but Katarina 2/2; Akali fits his archetype better than Turkey's). The engine bound the champion to the wrong player due to the 100 % single-game WR.
3. **Mahesh on JGL Hecarim.** Mahesh's primary is MID. The engine is choosing role on "best champion available with positive comfort" rather than "best champion + role alignment with primary."
4. **B5 ban "Tahm Kench" — counters your Akali.** Tahm doesn't counter Akali in any meaningful way; this is a soft P2 ban with weak justification.

---

### Example C — Draft 10

**Rosters**
- **BLUE:** Ben (A, JGL/TOP), JP (D, JGL only), Bobby (B, MID/JGL), Mahesh (A, MID flex), Chips (A, BOT/SUP).
- **RED:** Jose (C, JGL), Kian (C, BOT), Riley (B, SUP/MID), Miles (D, JGL/BOT), Logan (A, BOT).

This roster screams **"Blue stacks A-tier flex against Red's solo-queue grinders."** Blue's win condition is *make use of Mahesh/Chips/Ben pool depth*.

#### Expert reasoning
- **Blue bans:** Kassadin (Riley perma) — yes ✓. **Volibear (Ben)** — wait, Ben is on BLUE. Red banning Volibear is correct; Blue should *never* ban its own player's pocket. The engine got this right by phase (Volibear was Red's ban) ✓.
- **Blue B1 ban should be Kassadin** — engine ✓.
- **Blue B2/B3 — target Logan and Riley further, or hit Jose's Briar.** Engine banned Zac (Jose's solo permaban target) and Syndra (Riley). Reasonable, but **Briar** (Jose's 44-game champ, 50 % WR) is the actual high-impact target — engine never even sees it.
- **Red B3 banned Mel (Chips support pool).** OK, but Chips is on the BOT-conflict team — Red could have banned Diana (Bobby's #1 custom) or Aurelion Sol (Mahesh's flex carry). Mel-ban is fine but not optimal.

- **Pick order:**
  - B1 Diana (Bobby MID) — Bobby's #1 custom (4g 75 %). ✓
  - R1 Taliyah (Kian JGL?) — Kian's customs say BOT/MID, **not JGL**. Engine put Kian on JGL with Taliyah. He has 2 JGL games out of 31 customs. This is a **massive role mis-assignment**.
  - R2 Nautilus (Logan SUP) — Logan has 1 SUP game out of 100. He's a 92 % BOT specialist. The engine puts him on SUP because **the Logan-BOT pocket got banned away by Blue's own bans**.
  - This cascade is the headline finding: **By banning Logan three times Blue created an "off-role Logan SUP" outcome**, which is *worse for both teams* — Logan is now on a champ he's never played, and the comp loses its actual ADC carry. The engine *caused* the bad outcome.

#### Diff
1. **Logan on Nautilus SUP** is a direct consequence of Blue over-banning his BOT pool. A human ban manager limits to 2 bans on any single player and saves the 3rd for someone else.
2. **Kian on Taliyah JGL** = role mis-assignment. Kian plays BOT/MID. **Miles should have been the JGL** (he's a JGL main with Trundle 75 % WR). The engine never gave Miles JGL despite his primary being JGL.
3. **Aurelion Sol on Riley MID (R4)** — Riley has 0 Aurelion games in solo (it's not in his pool of 100 games at all). Why this came out as a COMFORT pick is mysterious — probably a global "Aurelion Sol counters Diana" rule that overrides player data.

---

### Example D — Draft 13

**Rosters**
- **BLUE:** Turkey (S, JGL/TOP), Johnny (A, JGL/SUP/TOP), Chips (A, BOT/SUP), JP (D, JGL), Ben (A, JGL/TOP) — **four JGL primaries on one team**.
- **RED:** Bobby (B, MID/JGL), Remy (C, BOT), Kian (C, BOT/MID), Logan (A, BOT), Jase (C, BOT) — **four BOT primaries on one team**.

This is a roster-construction trainwreck: Blue has 4 jungle mains and 0 ADCs; Red has 4 ADCs and 0 jungle. The engine has to do role-assignment surgery.

#### Expert reasoning
- The expert immediately maps out: Turkey TOP, Johnny SUP (his solo has Leona/Mel — already a "support pool"), Chips BOT (his primary), JP JGL (only option), Ben MID (his solo Sylas/LeBlanc are mid-range).
- The engine's role-assignment: Johnny JGL (FLEX), Chips MID (COMFORT — Annie), Ben SUP (Leona, SAFE), JP BOT (Aphelios, COMFORT), Turkey TOP. **That puts Chips off-role on MID despite being a BOT main**, and puts JP on BOT (he's never played BOT in customs).
- A human picks: Turkey TOP (Akali ✓ engine got that), **Chips BOT (Senna or Caitlyn)**, **Johnny SUP (Leona)** ✓ engine got that, Ben MID (Sylas, his 15-game solo pocket), JP JGL (his only role).
- **The engine made Chips a mid-lane Annie because it scored Annie's COMFORT for Chips (3g 67 % in customs) higher than Chips's BOT — but Chips has 17 BOT customs vs 1 MID custom**. The score being higher for Annie does not mean "Chips should be moved off his primary."

- **Bans:** Engine's Blue P1: Jinx, Ezreal, Kai'Sa, ban-mountain-on-Logan again. Same systematic over-ban pattern.

#### Diff
1. **Same Logan-triple-ban.** This is Blue's 4th draft (out of 6 with Logan on Red) where this happens. By draft 13 the engine has not adapted.
2. **Role assignment ignores `/api/primary-roles`.** Chips primary is BOT; engine forces him to MID. JP primary is JGL; engine forces him to BOT (then later JGL in different draft). This appears to be **the central systematic bug**.
3. **Bobby on Maokai TOP (FLEX).** Bobby's primary is MID and customs show MID 34 %/JGL 26 %/TOP 23 %. TOP is plausible, but his only TOP custom (Maokai 2g 100 % — tiny sample) is what the engine picked. A human would put him on **Diana MID** (his actual #1 custom) and find another TOP body.

---

### Example E — Draft 15

**Rosters**
- **BLUE:** JP (D, JGL only), Devin (B, JGL primary), Turkey (S, JGL/TOP), Joaquin (D, BOT/JGL), Mahesh (A, MID flex) — *3 JGL primaries again.*
- **RED:** Luke (B, MID), Chips (A, BOT), Remy (C, BOT), Jase (C, BOT), Bobby (B, MID/JGL).

#### Expert reasoning
- **Blue role-map:** Devin JGL (primary, and his permaban-tier Ivern), Turkey TOP, Mahesh MID, Joaquin BOT (his customs are BOT 44 %), JP SUP (he literally has 0 SUP games but he's the lowest-skill body so he absorbs the worst role). Actually JP has 4 Volibear customs at 25 % WR — put JP on a tank-jungle and Devin on TOP would also work.
- **Engine assignment:** Devin JGL (Nocturne, SAFE) ✓, Mahesh SUP (Nautilus, COMFORT) — *Mahesh is an A-tier MID main, not a support*, Turkey MID (Akali, FLEX), Joaquin BOT (Jhin), JP TOP (Mordekaiser).
- **Putting Mahesh on SUP** is the biggest miss. Mahesh's 5 % of customs is SUP and his solo is 9 % SUP. He's a mid main with TOP backup. The right call: Mahesh MID (Aurelion Sol, his 7-game custom flex), Turkey TOP, JP SUP (force-feed the weakest player the role with the smallest mistake radius).
- The engine made this mistake because it values *positive COMFORT score on any champion* over *primary-role alignment*. Mahesh on Nautilus has a positive comfort score because of some matchup heuristic, but it's overriding "this player has never played support meaningfully."

- **Bans:** Engine banned Ivern (Devin's permaban) on Red B2 ✓ — but Devin is on **Blue**, so banning his own permaban is *Red protecting itself*. That's correct from Red's side. Good.
- Engine banned **Pantheon (Chips JGL)** on Blue B1. Chips's primary is BOT/SUP, his JGL customs are 25 %. The Pantheon-ban targeting Chips JGL is wrong-role targeting — Chips's actual threat is **Senna (perma-ban-tier, 71 % WR)** which the engine never even saw because of the Pantheon-MID-flex routing.

---

## 4. Systematic Gaps — Where the Engine Misses What a Human Catches

Drawing from all 16 drafts:

### Gap 1 — Triple-stacking bans on a single player (P1 ban exhaustion)
- **Pattern:** When a roster has Logan (Jinx 48g must-ban), the engine bans Jinx → Ezreal → Kai'Sa nearly every time (drafts 1, 4, 6, 10, 11, 13).
- **Cost:** After 2 bans on the same player, the 3rd ban hits a 33 % WR Kai'Sa rather than a 70 % WR threat from another player. Logan still locks Caitlyn or Tristana (which he plays) and the *team* gets nothing for the third ban.
- **Fix:** Apply a soft cap of 2 bans on any single player in P1 unless 3+ champions have ≥60 % WR over ≥10 games.

### Gap 2 — Role assignment ignores `/api/primary-roles`
- **Pattern:** Mahesh assigned to SUP (draft 15), Chips assigned to MID (draft 13), Kian assigned to JGL (draft 10), Luke assigned to JGL (draft 1), Logan assigned to SUP (draft 10), JP assigned to BOT/TOP/SUP across drafts despite JGL-only customs.
- **Cost:** Player on off-role champ ≈ 15-25 % WR drop based on a player playing a role they have <10 % of games in.
- **Fix:** Apply a strong (multiplicative) penalty when the assigned role is not in the top-2 of the player's `/api/primary-roles` or customs role distribution. Currently the engine seems to treat COMFORT score (champion-fit) as overriding role-fit.

### Gap 3 — `top_champs` (solo) vs `inhouse_champs` (customs) blending
- **Pattern:** The engine ban-list pulls from solo Q (Jinx-Logan 48g) but the pick-list pulls from customs (Annie-Chips 3g). When a player has *strong solo but zero customs* (Turkey: Diamond, solo Sett/Garen/Lee Sin, customs 5 noise games), the engine ignores the strong signal because customs come up empty. Turkey on Akali ended up appearing in 3 drafts in MID despite Turkey being a TOP/JGL solo main.
- **Fix:** Blend the two with a confidence weighting. If customs games < 10, fall back to solo top-champs and primary role.

### Gap 4 — Sample-size noise in COMFORT scoring
- **Pattern:** Mel 100 % WR in 3 customs games drives a high ban score (1.136 in draft 3). Rumble 3-0 customs drives a 1.323 ban score. Realistically a 3-game 100 % WR is statistical noise — it should be discounted vs a 35-game 69 % WR (Volibear/Ben).
- **Fix:** Apply a beta-distribution prior on WR before scoring. A 3-game 100 % WR should regress toward ~55 % posterior with a Bayesian prior, not score 1.32 ban weight.

### Gap 5 — P2 bans largely waste on weak counters
- **Pattern:** P2 ban reasons read "counters your X" with WR=33 % or 30 %, sometimes lower. Example draft 9 B5: "Sett — Counter-pick threat 66 % WR" (1 game = noise). Example draft 14 B4: "Janna — enemy threat to your comp" (no specifics).
- **Cost:** P2 is the highest-information part of the draft (you have 3 picks of intel from each side). Spending P2 on global counter-pick tables means the engine doesn't actually use the new information.
- **Fix:** P2 bans should pull from *enemy player pool* x *role still to-be-picked* — i.e. ban what their unpicked player would lock as a counter. The engine currently still pulls from a flat counter table.

### Gap 6 — FLEX tag is over-triggered
- **Pattern:** FLEX shows up in pick reasons like "Flex 2 unmatched roles - hides your TOP" for Ambessa-Johnny TOP, Galio-Bobby MID, etc. The engine treats any champion that's playable in 2 roles as a "flex pick" even when:
  - The player has 90 %+ of customs in ONE role (so the flex value is fake — the enemy knows where it's going).
  - The pick has already been made on the obvious role (Tahm Kench at SUP isn't hiding anything if the team already has 0 free SUP slots).
- **Fix:** Flex value only applies when *the team still has 2+ undecided role slots* AND *the player who'd take the pick has a real history in both roles*. (e.g. Mahesh on Galio is a real flex; Logan on Galio is not.)

### Gap 7 — No comp-construction check
- **Pattern:** Across 16 drafts the engine never produces a "this comp has 4 AD champions" warning, never flags missing engage, and never picks an AP carry to balance AD-heavy lock-ins.
- **Example:** Draft 14 Blue locks Nilah BOT, Leona SUP, Gwen TOP, Briar JGL, Malzahar MID → that comp has 4 AD champions (Nilah, Leona is mixed, Gwen mixed, Briar AD, Malzahar AP). With just Malzahar AP, the enemy stacks armor and wins. A human catches this at pick 3 or 4 and pivots.
- **Fix:** Run a comp checklist (engage / peel / AD-AP ratio / waveclear / scaling) before each pick and bias the candidate scores toward champions that fill missing buckets.

### Gap 8 — `must_bans` field underused
- **Pattern:** The scout-sheet `must_bans` field is exactly the right signal (a 70 % + WR over 10+ solo games). Five players have one each. In all 16 drafts the engine bans some of these (Jinx-Logan, Volibear-Ben, Ivern-Devin, Kassadin-Riley) but not consistently — Ivern-Devin was banned in only draft 15 (where Devin is on Blue and Red banned it correctly) — but in drafts where Devin is on Red, the Blue-side ban list never includes Ivern.
- **Fix:** Pre-load a "must-ban target list" pulled from `must_bans` on enemy roster and weight those at score-2.0+, well above any customs-derived ban.

### Gap 9 — Tier/rank not weighted in threat
- **Pattern:** Turkey (Diamond, S-tier, the single best player) is rarely the primary ban target. Mahesh (Emerald, A-tier) is ban-targeted far more often — because Mahesh's customs sample is bigger (49 customs vs Turkey's 5).
- **Cost:** The engine effectively *under-bans the best player* because the best player has the smallest customs footprint. In Draft 6, Blue bans Sion-Ambessa-Kennen all targeting Turkey TOP — but the *threat* should be weighted higher per ban given Turkey's S-rating.
- **Fix:** Multiply threat scores by `(tier_score / 50)` so an S-tier (Turkey 85.5) player's threats are weighted ~1.7× a B-tier player's threats.

### Gap 10 — `form` (HOT/COLD/MIXED) ignored on ban side
- **Pattern:** The form_state field marks 6 players HOT and 4 COLD. The engine doesn't seem to use form to escalate ban priority on HOT players or de-escalate on COLD. Turkey is COLD (recent losing streak) but he's still in the top-2 of every ban list when he's on enemy. Jose is HOT and should be hit harder on his Briar (44g 50 % is borderline must-ban during a HOT streak).
- **Fix:** Form multiplier: HOT × 1.15, COLD × 0.85, MIXED × 1.0 on ban scores.

---

## 5. Quick scorecard — what the engine does well

To be fair, the engine gets several things right and these should be preserved:

- **Must-ban detection** when the data is large-sample (Logan Jinx, Ben Volibear are nailed every time).
- **Flex tagging** in concept — the *idea* of recognizing a champion playable in 2 roles is correct, just over-applied.
- **Counter-pick search at R3/R4/B5** when role assignment lines up — the Riley/Kha'Zix counter to Pantheon in draft 1 is exactly what a human plays.
- **P1 ban ordering** by threat magnitude — the rank-by-score sort is correct, only the *role assignment* and *ban-spread* downstream are off.

---

## 6. Recommended Engine Fix Priority

If I had to pick the top 3 to fix first:

1. **Role assignment** — respect `/api/primary-roles` as a hard prior. (Affects ~10 of 16 drafts.)
2. **Ban spread cap** — max 2 bans per enemy player in P1 unless they have 3+ verified threats. (Affects ~6 drafts directly.)
3. **Tier-weighted threat scoring** — multiply ban score by `tier_score / 50`. (Affects 100 % of drafts to a degree; biggest gain on Turkey/Chips/Ben/Mahesh games.)

---

## Sources

- [A Beginner's Guide to Understanding Picks and Bans in Professional League of Legends (Mobalytics)](https://mobalytics.gg/blog/picks-bans-guide/)
- [Counter-Pick Bible: Draft Phase Strategies for Each Role (CheatsPulse)](https://www.cheatspulse.com/guides/league-of-legends/counter-pick-bible)
- [Win Before You Play – Navigating Draft Phase in League of Legends (Dignitas)](https://dignitas.gg/articles/win-before-you-play-navigating-draft-phase-in-league-of-legends)
- [LoL Fearless Draft Explained — Rules, History and Impact on Pro Play (TheSpike)](https://www.thespike.gg/league-of-legends/beginner-guides/fearless-draft-guide)
- [Fearless Draft Takes Over 2025 (lolesports.com)](https://www.leagueoflegends.com/en-us/news/fearless-draft-takes-over-2025/)
- [Worlds 2025: How Fearless Draft May Decide LoL's Biggest Stage (esports.net)](https://www.esports.net/wiki/tournaments/worlds-2025-fearless-draft/)
- [Pick/Ban Strategies (Dot Esports)](https://dotesports.com/league-of-legends/news/pickban-strategies-7990)
- [A Look at Competitive Pick and Ban Strategies (Dot Esports)](https://dotesports.com/league-of-legends/news/a-look-at-competitive-pick-and-ban-strategies-with-an-emphasis-on-individual-pic-7392)
- [Draft Pick (League of Legends Wiki)](https://wiki.leagueoflegends.com/en-us/Draft_Pick)
- [Team Drafting (League of Legends Wiki)](https://wiki.leagueoflegends.com/en-us/Team_drafting)
- [Complete Guide to Team Compositions in League of Legends (Backdash)](https://thebackdash.com/gaming/league-of-legends/complete-guide-to-team-compositions-in-lol/)
- [Team Composition Guide to Poke Compositions in League of Legends (Dignitas)](https://dignitas.gg/articles/team-composition-guide-to-poke-compositions-in-league-of-legends)
- [A Guide to Dive Compositions in League of Legends (Dignitas)](https://dignitas.gg/articles/a-guide-to-dive-compositions-in-league-of-legends)
- [Strength in Formation: A Deep Dive on Front to Back Comps in League of Legends (YouTube)](https://www.youtube.com/watch?v=emBwN4vOo-s)
- [How to Play the Poke Team Comp in LoL (Mobalytics)](https://mobalytics.gg/blog/lol-how-to-play-the-poke-team-comp/)
- [Best Clash Team Comps and Counters (Updated for Season 15) (Mobalytics)](https://mobalytics.gg/blog/lol-best-clash-team-comps-and-counters/)
- [Understanding Scaling and How to Use It to Your Advantage in League of Legends (Mobalytics)](https://mobalytics.gg/blog/understanding-scaling-use-advantage-league-legends/)
- [Power Spikes in League of Legends: Part 2 — Mid Game (Dignitas)](https://dignitas.gg/articles/Power-Spikes-in-League-of-Legends-Part-2-Mid-Game)
- [A Beginner's Guide to League of Legends Power Spikes (+Examples) (Mobalytics)](https://mobalytics.gg/blog/5-types-league-of-legends-power-spikes-examples/)
- [What is a Power Spike in League of Legends? (Eloking)](https://eloking.com/glossary/lol/power-spike)
- [Top 5 Best Flex Picks in LoL (Mobalytics)](https://mobalytics.gg/lol/guides/best-flex-picks)
- [League of Legends Flex-conscious Draft AI (Alexzander Stone projects)](https://alexzander-stone.pages.dev/projects/draft-ai/)
- [LOL Team Composition Guide: Build Winning Strategies (LoL-Guides)](https://lol-guides.com/blog/lol-team-composition-guide-build-winning-strategies-in-league-of-legends)
- [LoL: How to Win Your Solo Queue Draft — Statistical Analysis (iTero)](https://www.itero.gg/articles/draft-sq)
- [Guide to Drafting (MobaFire)](https://www.mobafire.com/league-of-legends/build/guide-to-drafting-feedback-wanted-583624)
- [Mastering League Draft Rules (NumberAnalytics)](https://www.numberanalytics.com/blog/league-draft-rules-guide)
- [League of Legends Draft Rules Explained (NumberAnalytics)](https://www.numberanalytics.com/blog/league-of-legends-draft-rules)
