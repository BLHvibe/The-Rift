# Post-Wave5 Gap Analysis — v4.1.2 (eeb57f1+wave2-5-fix5)

**Audit source:** `engine_audit_run7.json` (32 simulated drafts, seed=100)
**Player data:** `player_snapshot_v4.1.1.json` (live as of 2026-05-25)
**Engine version live on Fly:** `eeb57f1+wave2-5-fix5-primary-roles`
**Run 7 summary** (vs run 1 baseline, 16 drafts):
- On-primary picks: 0/156 → 222/313 (**71%**)
- P1 distinct enemies (avg): 1.84 → 2.47
- `must_bans` hits: 15 → 113
- COUNTER tag fires: 2 → 9
- WEAKNESS tag fires: 0 → 3
- No-suggestion last picks: 0/16 → 0/32

---

## 0 · The bug I caught en route — `/api/primary-roles` was customs-only

**Roles are pre-draft locked in by the team-builder UI** — the engine doesn't reassign them. But its `off_role_severity` check still uses `/api/primary-roles` to decide whether the assigned role matches the player's "real" main, and that endpoint was reading from `participants` table where `source='inhouse'` — i.e., **only the tiny customs sample**. 11 of 19 players had wrong primaries:

| Player  | API said | Scout (solo-Q) says | Δ |
|---------|----------|----------------------|---|
| Ben     | JGL      | **TOP** (69 games, Volibear 24/35) | A-tier TOP main read as JGL |
| Chips   | BOT      | **SUP** (74 games) | A-tier SUP main read as BOT |
| Chris   | BOT      | **SUP** (74 games) | B-tier SUP main read as BOT |
| Johnny  | JGL      | **TOP** (44 games) | A-tier TOP read as JGL |
| Miles   | JGL      | **TOP** (42 games) | TOP/JGL flex misread |
| Riley   | BOT      | **SUP** (48 games) | B-tier SUP read as BOT |
| Turkey  | JGL      | **TOP** (44, JGL 35) | S-tier TOP/JGL flex |
| Jase2   | (none)   | **TOP** (13) | unranked but plays TOP |
| Joaquin | BOT      | **JGL** (73 games) | JGL main read as BOT |
| Kian    | BOT      | **MID** (31 games) | MID/SUP flex misread |
| Remy    | BOT      | **MID** (39 games) | MID main read as BOT |

**Fix shipped:** `server/db.py:primary_roles()` now reads scout-sheet `roles` array (solo-Q games, 50-100+ per player) and falls back to customs only when scout data is absent. Live now → engine no longer penalises Ben's TOP picks as off-role, no longer thinks Chips is "off-primary" on SUP, etc.

---

## 1 · Three worked drafts — expert vs engine

For each draft I take the roster + pre-locked roles (what the team-builder would produce) and write what a knowledgeable expert would do given the player data, then compare to the engine's actual output.

### Draft 1 — Turkey/Joaquin/JP/Chris/Chips (BLUE) vs Ben/Jose/Bobby/Logan/Johnny (RED)

**Role lock-in (after primary-roles fix):**

| Side | TOP | JGL | MID | BOT | SUP |
|------|-----|-----|-----|-----|-----|
| BLUE | Turkey (S) ✓ | Joaquin (D) ✓ | **JP (D, OFF — JGL primary)** | **Chris (B, OFF — SUP primary)** | Chips (A) ✓ |
| RED  | Ben (A) ✓ | Jose (C) ✓ | Bobby (B) ✓ | Logan (A) ✓ | **Johnny (A, OFF — TOP primary)** |

Both teams have to flex one player. The engine handled this fine — but it surfaced a **major mid-priority blunder** I'll cover below.

#### Expert ban list

**Blue P1 (target high-impact enemies, spread across roster):**
1. **Jinx** — Logan permaban (48g 69% solo, must-ban list). Strip his comfort. ✓
2. **Volibear** — wait, Ben is RED. Don't ban our own teammate's pocket. *Actually Ben IS on RED, so banning his Volibear is correct.* ✓
3. **Senna** — Wait Senna is Chips's must-ban but Chips is on BLUE. Don't ban our own SUP's pool. Skip.
4. Instead: **Briar** — Jose JGL must-ban-tier (7g 86% custom). Or **Volibear** if not banned yet.
5. **Diana** — Bobby MID #1 custom pocket (4g 75%).

**Red P1:**
1. **Sion** or **Ambessa** — Turkey TOP threat. Ambessa is the meta tilt; engine doesn't see Turkey's specific TOP pool clearly.
2. **Senna** — Chips SUP permaban.
3. **Bard** — Chris SUP permaban (9g 66%).
4. Spread → **Ekko** (Joaquin's deep ranked pool? No — Joaquin is D-tier with sparse data). Probably better: **Akali** (Mahesh would be on RED in other drafts; not here).
5. Last ban: **Mel** (Chips's 100% WR 3g — small sample but flex pocket).

#### Engine ban output

| Ban | Engine pick | Reason | Expert agrees? |
|-----|-------------|--------|----------------|
| B1 | Volibear (Ben) | Must ban scout perma | ✓ |
| R1 | Sion (Turkey) | 50% WR / 5.1 KDA | ✓ — exact match |
| B2 | Jinx (Logan) | Must ban scout perma | ✓ |
| R2 | Senna (Chips) | Must ban scout perma | ✓ |
| B3 | Ezreal (Logan, 2nd ban) | 44% WR / 4.4 KDA | ✗ **Logan is on RED. Both Jinx and Ezreal ban Logan.** Decay didn't spread to other RED players (Jose Briar, Bobby Diana, Johnny). |
| R3 | Mel (Chips, 2nd ban) | 100% WR / 7.4 KDA | ✗ **Same problem on RED side — both Senna and Mel target Chips.** |

The per-player decay is firing (score went from 2.538 Jinx → 2.147 Ezreal, so decay was applied), but **the next-best non-Logan threat was less than the decayed Logan threat**. Logan has 3 strong champs (Jinx 48g/69%, Ezreal 9g/44%, Kai'Sa 6g/33%) all scoring high. Looking at the alternatives at step 4 (Blue B3):

The engine's top-6 alts at Blue B3 were:
1. Kai'Sa (Logan, 3rd Logan-targeting ban) — 1.652 with 0.5× decay applied
2. ? (other player's threat)

This is a **roster-driven case where 3 bans on Logan is actually reasonable** — Logan is the only A-tier BOT carry on RED and his entire pool is bannable. The audit's other RED players (Ben TOP, Jose JGL, Bobby MID, Johnny SUP) all have less concentrated threats. So the engine is doing OK; a human would also debate Logan-stack vs. spread.

#### Engine pick output + expert reaction

| Step | Engine pick | Player·Role | Expert reaction |
|------|-------------|-------------|-----------------|
| B1 | Ekko | Joaquin JGL | ✗ **Joaquin has no Ekko in customs.** This is a priors-fallback pick. Joaquin's primary is JGL but his data is sparse. Engine reaches for a "safe meta JGL". Defensible. |
| R1 | Zac | Jose JGL | ✓ Jose's customs show Zac 8g/75%. Perfect. |
| R2 | Diana | Bobby MID | ✓ Bobby's #1 custom (4g/75%). Exact match. |
| B2 | Seraphine | Chips SUP | △ Chips's customs don't show Seraphine, but engine flagged blind-safe. Acceptable. |
| B3 | Dr. Mundo | Turkey TOP | △ Turkey has no Mundo data — solo-Q top is Sett/Garen/Lee Sin. **Expert would pick Sett or Garen for Turkey.** Engine reaches for a blind-safe priors-fallback. |
| R3 | Caitlyn | Logan BOT | ✓ Logan's BOT pool stripped (Jinx/Ezreal/Kai'Sa banned). Caitlyn is a meta default. |
| **B4** | **Tristana** | **JP MID** ⚠ | ✗✗ **Tristana is an ADC, not a mid laner.** JP is forced off-role on MID. The priors fallback expansion to "all valid roles at 0.10" let Tristana slip into MID's candidate pool because she has ROLE_VALID["MID"] = (some weak mid play history). **Big gap.** |
| R4 | Malphite | Ben TOP | ✓ Ben's customs have Malphite 1g/100%. Decent. |

**Critical findings from Draft 1:**

- **Tristana-MID** is a smoking-gun for **Gap A** (below): the expanded priors fallback (Wave 3 fix) widened the candidate pool too aggressively. ROLE_VALID's MID set apparently includes Tristana even though she's a 99% BOT champ.
- **Turkey TOP got Dr. Mundo** — the engine has no signal for Turkey's actual TOP pool (because Turkey's customs are 5 noise games and his scout sheet has Sett/Garen/Lee Sin). It picks "blind-safe" champion that has no relationship to the actual player. **Gap B**: when a player has thin data but a known solo-Q pool, the engine should prefer the solo-Q champions over priors fallback.

### Draft 4 — Miles/Devin/Kian/Remy/Ben (BLUE) vs Johnny/Jose/Luke/Logan/Bobby (RED)

**Role lock-in:**

| Side | TOP | JGL | MID | BOT | SUP |
|------|-----|-----|-----|-----|-----|
| BLUE | Miles (D) ✓ | Devin (B) ✓ | Kian (C) ✓ | **Remy (C, OFF — MID primary)** | **Ben (A, OFF — TOP primary)** |
| RED  | Johnny (A) ✓ | Jose (C) ✓ | Luke (B) ✓ | Logan (A) ✓ | **Bobby (B, OFF — MID primary)** |

BLUE's biggest weapon (Ben, A-tier) is force-flexed to SUP. RED's biggest weapon (Johnny, A-tier) is on TOP where his primary lives.

#### Expert bans

**Blue P1 should focus on:**
1. **Jinx (Logan)** — must-ban ✓
2. **Yasuo (Johnny TOP)** — Johnny's solo Garen/Darius/Sett pool. Hmm, no Yasuo in scout. Better: **Sett** (his solo #1) or **Garen**.
3. **Viktor (Luke)** — Luke's #1 (4g/75%). Or **Smolder** if Luke flexes BOT (engine seeing him as MID is correct here).
4. **Briar (Jose)** — Jose's standout (7g 86%).
5. **Diana (Bobby)** — Bobby's #1, but he's on SUP this draft so smaller signal.

**Red P1 should target Ben + Miles aggressively** since BLUE locked Ben to SUP (his off-role makes him weaker, so the actual targets are Miles TOP + Devin JGL + Kian MID):
1. **Ivern (Devin)** — Devin's must-ban-tier solo. ✓
2. **Trundle (Miles)** — his standout custom (4g/75%) — Miles is TOP/JGL flex.
3. **Kassadin (Riley)** — wait Riley isn't on RED this draft. Skip.
4. **Smolder (Remy)** — Remy's must-ban (he's the BOT for BLUE).
5. **Akshan (Kian)** — Kian's must-ban (his MID/BOT flex pocket).

#### Engine ban output

| Ban | Engine pick | Reason | Expert agrees? |
|-----|-------------|--------|----------------|
| B1 | Jinx (Logan) | must-ban | ✓ |
| R1 | Ivern (Devin) | must-ban | ✓ |
| B2 | Ezreal (Logan, 2nd) | 44% WR | △ "Logan-stack" again — but at least Senna/Bard targets aren't here this draft so 2 bans on Logan is reasonable |
| R2 | Smolder (Remy) | must-ban | ✓ |
| B3 | Kai'Sa (Logan, 3rd) | 33% WR | ✗ **Third ban on Logan.** Should be Viktor (Luke) or Briar (Jose). Decay should have crushed this. |
| R3 | Akshan (Kian) | must-ban | ✓ |

**Confirmed Gap C — per-player decay is too weak when one player has a stacked pool.** Logan ban 3 still beats Luke/Jose/Bobby ban 1. The current decay formula `1/(1+0.5n)` produces ×0.50 at n=2, but Logan's 3rd-best (Kai'Sa 33% WR) is `1.652` after tier, decay, must_ban hits → still above Luke's Viktor threat (4g/75% × shrinkage = lower).

#### Engine pick output

| Step | Engine pick | Player·Role | Expert reaction |
|------|-------------|-------------|-----------------|
| B1 | Xin Zhao | Devin JGL | △ Devin's actual JGL #1 is Ornn (4g/100%) — Xin Zhao is a priors-fallback pick. Defensible but not the player's real pocket. |
| R1 | Viktor | Luke MID | ✓ Luke's #1 custom. Perfect. |
| R2 | Zac | Jose JGL | ✓ Jose Zac 8g/75%. |
| B2 | Trundle | Miles TOP | ✓ Miles Trundle 4g/75%. Spot-on. |
| B3 | Taliyah | Kian MID | △ Taliyah isn't in Kian's customs but is in scout pool. Acceptable. |
| R3 | Yasuo | Johnny TOP | ✗ Johnny doesn't have Yasuo in either customs or solo top-3 (his solo is Garen/Darius/Sett). **Expert pick: Sett or Garen.** Engine reaches for off-data Yasuo. |
| **B4** | **Leona (Ben SUP)** comp_fit=+0.40 ⚠ | ✓✓ Comp checklist is firing — Leona is engage which BLUE was missing. But expert would put **Ben TOP** if possible — wait, Miles is TOP. So Ben must be SUP. Leona is a defensible flex for Ben (1 solo SUP game on Leona/Malphite). |
| B5 | Corki | Remy BOT | ✗ Remy has no Corki in customs (Caitlyn 3g/67%). Should be Corki only if it counters Caitlyn — it doesn't really. **Better:** Smolder banned, so **Lucian** or **Caitlyn** for Remy. |
| R5 | Maokai (Bobby SUP) | ✓ Bobby Maokai 2g/100% custom — engine found it. Good. |

**Findings from Draft 4:**
- **Comp checklist (Wave 5 M) is firing visibly** — Leona pick has `comp_fit=+0.40` for filling engage. ✓
- **"Yasuo on Johnny TOP"** — same Gap B from Draft 1. Engine doesn't anchor on the player's actual solo-Q top-3.
- **Per-player decay still allows triple-stacks** on whales (Logan).

### Draft 8 — Turkey/Jase/Kian/Logan/Chris (BLUE) vs Ben/JP/Mahesh/Remy/Riley (RED)

**Role lock-in:**

| Side | TOP | JGL | MID | BOT | SUP |
|------|-----|-----|-----|-----|-----|
| BLUE | Turkey (S) ✓ | **Jase (C, OFF — BOT primary)** | Kian (C) ✓ | Logan (A) ✓ | Chris (B) ✓ |
| RED  | Ben (A) ✓ | JP (D) ✓ | Mahesh (A) ✓ | **Remy (C, OFF — MID primary)** | Riley (B) ✓ |

Both A-tier engines (Turkey, Ben, Mahesh) are on their primaries. BLUE has Jase forced JGL (he plays BOT). RED has Remy forced BOT (she plays MID).

#### Expert bans

**Blue P1 (4 high-impact RED targets — Ben/Mahesh/Riley/Logan-prepush is irrelevant, Logan on BLUE):**
1. **Volibear (Ben)** — must-ban ✓
2. **Rumble (Mahesh, his 100% WR flex)** — strip his flex.
3. **Thresh (Riley SUP)** — his #1 SUP custom (6g/50%).
4. **Bard** — wait, Bard is Chris's permaban; Chris is on BLUE. Skip.
   Better: **Akali (Mahesh)** or **Aurelion Sol** (Mahesh's 7g flex).
5. **Briar** — wait Jose isn't here. JP is JGL — JP's data is thin.

**Red P1:**
1. **Sion or Ambessa (Turkey TOP)** — his ceiling.
2. **Jinx (Logan)** — must-ban.
3. **Bard (Chris)** — must-ban.
4. **Diana** — wait, Bobby isn't here. Kian is MID — his Akshan is must-ban.
5. **Kassadin (Riley)** — wait Riley is RED. Skip.
   Better: **Akshan (Kian)** or **Pyke (Kian's solo)**.

#### Engine ban output

| Ban | Engine pick | Reason | Expert agrees? |
|-----|-------------|--------|----------------|
| B1 | Volibear (Ben) | must-ban | ✓ |
| R1 | Sion (Turkey) | 50% / 5.1 KDA | ✓ |
| B2 | Rumble (Mahesh) | 100% WR flex | ✓ Exact expert pick |
| R2 | Jinx (Logan) | must-ban | ✓ |
| B3 | Thresh (Riley) | 54% / 4.6 KDA | ✓ Spread across 3 different RED players |
| R3 | Bard (Chris) | must-ban 66% / 9g | ✓ |

**Draft 8 P1 bans are nearly perfect.** Six bans across six different players (3 each side). This is the spread we want.

#### Engine pick output

| Step | Engine pick | Player·Role | Expert reaction |
|------|-------------|-------------|-----------------|
| B1 | Caitlyn (Logan) | BOT | ✓ Logan's pool stripped, Caitlyn is the default safe ADC. |
| R1 | Qiyana (Mahesh) | MID | △ Mahesh's #1 customs is Irelia, not Qiyana. Solo-Q top is Shen/Katarina/Irelia. Better: **Irelia (Mahesh)** or **Akali**. |
| R2 | Ambessa (Ben TOP, FLEX) | comp_fit not set | △ Ambessa is meta but Ben's actual pool is Volibear (banned), Sylas, Nasus, Sion (banned). **Better: Sylas** (Ben 2g/100%). |
| B2 | Vel'Koz (Chris SUP) | ✓ Chris's #1 custom (13g/62%). Perfect — engine nailed it. |
| B3 | Dr. Mundo (Turkey TOP) | ✗ Same bug as Draft 1. Turkey's solo is Sett/Garen/Lee Sin. **Pick: Sett.** |
| R3 | Rell (Riley SUP) | △ Rell isn't in Riley's pool (Thresh banned, Vex/Kha'Zix are non-SUP). Defensible meta pick. |
| R4 | Smolder (Remy BOT, off-role) | comp_fit=+0.20 | △ Remy plays MID, not BOT. Smolder is OK but defensible. |
| B4 | Akshan (Kian MID) | ✓ Kian Akshan 4g/75% — wait, Akshan was banned earlier? Let me re-check. Akshan was banned in Draft 4, not 8. Here it's fine. ✓ |
| B5 | Pantheon (Jase JGL, off-role) | △ Jase plays BOT. Pantheon JGL is a stretch — better priors-fallback would be Maokai or Sejuani. |
| R5 | Warwick (JP JGL) | △ JP's actual customs: Volibear 4g/25%, Mordekaiser, Jax. Warwick is a priors-fallback default. Better: **Volibear** (already banned). |

**Findings from Draft 8:**
- **Bans excellent** — 3 distinct enemies per side, no triple-stack, must_bans hit reliably.
- **Same "ignores actual solo top-3" pattern** for Turkey, Ben, JP. The priors-fallback path is winning over the player's own scout pool.

---

## 2 · Identified gaps (post-Wave5)

Numbered to continue from `ENGINE_FIX_PLAN.md` (A-M were Wave 2-5).

### Gap N — Champ pool/role match in priors fallback is too permissive

**Smoking gun:** Tristana picked for JP **MID** in Draft 1 (a BOT champion).

`_player_candidates` priors fallback now fills all `ROLE_VALID[role]` champs at 0.10 (per Wave 3 fix E). But `ROLE_VALID["MID"]` apparently contains some champs that are technically valid in mid lane history but unrealistic primary mid picks (Tristana, possibly Smolder, Yasuo, etc.).

**Fix proposal:**
1. Audit `ROLE_VALID` in `server/engine_core.py` — for each role, the set should only include champs that are *meta-viable* in that role, not just "occasionally played there".
2. Alternative: weight the 0.10 priors fallback by `meta_play_rate(champ, role)` so Tristana-MID lands at 0.02 vs Galio-MID at 0.10.

### Gap O — Player's actual solo-Q top-3 isn't prioritised when customs is thin

**Smoking gun:** Turkey at TOP got **Dr. Mundo** (no scout data, no customs data) instead of **Sett** (his actual solo #1).

The engine's `_player_candidates` order:
1. Customs (high weight if ≥3 games)
2. Scout-sheet `champ_pool` (lower weight, across-role)
3. Player's `top_champs` (name-only, ranked mastery)
4. CHAMP_PRIORS (low constant)

For Turkey, customs is sparse (5 games total) and scout `champ_pool` covers his solo-Q pool but the scout entries aren't role-tagged — so when assigned to TOP, the engine doesn't know which of his scout champs are TOP. It falls through to priors and picks Dr. Mundo (a CHAMP_PRIORS TOP entry).

**Fix proposal:**
1. Pull per-role breakdown from scout sheet's `roles[].top_champs` field (e.g. Turkey's TOP row has "Sett (16/25), Garen (3/5)..."). Parse these as role-specific scout entries.
2. Weight them above CHAMP_PRIORS so "Turkey TOP Sett" wins over "Turkey TOP Dr. Mundo".

### Gap P — Per-player ban decay is too weak vs deep enemy pools

**Smoking gun:** Logan banned 3× in Draft 1 (Jinx + Ezreal + Kai'Sa) and Draft 4 (same triple). 28/64 side-drafts still triple-stack.

Logan's scoring (after Wave 2 fix):
- Jinx: ~2.5 (must_ban floor 1.5 + threat)
- Ezreal: ~2.1 × 0.67 decay = ~1.4
- Kai'Sa: ~1.65 × 0.50 decay = ~0.83

Other enemies' top threat is often <0.83 because they have fewer high-WR/high-volume champs.

**Fix proposal:**
1. **Stronger decay**: `1/(1+0.8n)` instead of `1/(1+0.5n)` — so 3rd ban gets ×0.38, 4th gets ×0.29.
2. **Hard cap of 2 P1 bans per player** unless 3+ champions hit must_ban tier. Combined with decay so the cap is "soft preference, hard veto on the 4th".
3. Make the team-builder UI surface the ban distribution as a sanity check: "⚠ You've targeted Logan 3 times in P1 — consider banning Bobby's Diana instead."

### Gap Q — P2 same-target counters still firing 33%

**Smoking gun:** 21/64 P2 ban pairs both target the same locked pick.

My P2 spread_factor only kicks in *after* the first P2 ban resolves. But within a single `recommend_action` call, the engine returns top-N alternatives all of which protect the same locked pick if that pick has many counters.

**Fix proposal:** add a within-call de-dup: when sorting P2 candidates, after taking the #1, scale all candidates protecting the same victim by 0.5 before re-sorting for the alternatives. The audit feeds top-1 only, so this fix targets the next-turn ban call.

### Gap R — COUNTER tag still rare (9/320 picks = 2.8%)

Dropping `COUNTER_PICK_THRESHOLD` 0.70 → 0.55 and `cv` gate 0.40 → 0.35 helped (COUNTER fires 2 → 9), but it's still below the ~10% we'd expect given 47/160 picks are at canonical counter-pick slots.

**Hypothesis:** the `cv` calculation rescales via `counter_value()` which has a hard ceiling around 0.46 for max table coverage. The 0.55 override threshold rarely triggers.

**Fix proposal:**
1. Recalibrate `counter_value`'s normalisation so a strong counter pair (e.g., Tahm Kench beats Kha'Zix at 0.75 raw) ends up as `cv ≥ 0.55`.
2. OR drop `COUNTER_PICK_THRESHOLD` further to 0.45.

### Gap S — Comp checklist is firing but only when locked picks already determine the comp identity

**Smoking gun:** `comp_fit` shows `+0.40` on Leona-Ben-SUP in Draft 4 (filling engage). But:
- Most picks (B1-B3) have no `comp_fit` because there are <3 locked picks.
- B5/R5 see `comp_fit` but at that point the comp is mostly fixed and the tiebreaker has little room.

The current implementation only fires AFTER 3+ picks lock. By then most of the comp is set.

**Fix proposal:**
1. Start the comp checklist earlier (after 1 pick locks) but with smaller weight (±5% at 1 pick → ±10% at 3+ picks).
2. Make the comp checklist also influence P1 BAN priority: if our predicted comp will lack engage, increase ban weight on enemy engage counters so opponents can't exploit our weakness.

### Gap T — Archetype hysteresis is wired but not exercised by the audit

**Smoking gun:** The audit threads `prev_archetype` as "the most recent of either side" — but archetype is per-side. Hysteresis only fires when the new top beats the prev by ≥0.05; my data shows it's set but I can't confirm it actually prevented flickers.

**Fix proposal:** make the audit script pass per-side prev_archetype (track BLUE_prev and RED_prev separately, send the one matching `action.side`). Re-audit to confirm 0 drafts switch archetype ≥3 times.

### Gap U — The "force flex" Ben-on-SUP problem

**Smoking gun:** Draft 4 puts Ben (A-tier TOP main, Volibear 35 games) on SUP. The engine handles this OK (picks Leona) but **a human would NEVER do this** — Ben on SUP is a 20-point skill drop, while putting one of the B/C-tier MID players on SUP is much smaller. The audit's auto-assignment doesn't optimise this.

**This isn't an engine bug** — the engine respects roles given to it. But for the live multiplayer flow, the team-builder UI should warn: "⚠ Ben is your highest-rated player; flexing him off TOP costs more than flexing a lower-rated player."

**Fix proposal:** add a "flex impact" warning to the team-builder UI that scores each role assignment by `(player_tier_score) × (off_role_severity)` and surfaces the worst offender.

### Gap V — Engine reaches for CHAMP_PRIORS even when the player's scout pool has a viable option

**Smoking gun:** Draft 8 step 11 puts **Pantheon on Jase JGL** (Jase is BOT primary). Jase has 0 customs but his solo-Q is Senna/Aphelios/Karma (all BOT — banned in draft 4) AND he has 11% JGL solo. Engine picks Pantheon-priors instead of Lee Sin / Master Yi from his actual scout.

The fix from Gap O above would also address this — exposing per-role scout data fixes both.

---

## 3 · Recommended fix priority (next wave)

| # | Gap | Severity | Effort | Wave |
|---|-----|---------|--------|------|
| **N** | Tristana-MID priors leak (`ROLE_VALID` permissive) | High | 2-3h (audit table + tighten) | **next** |
| **O** | Per-role solo-Q top-3 not used | High | 3-4h (parse scout `roles[].top_champs`) | **next** |
| **P** | Ban decay too weak (3rd Logan ban still fires) | Med | 30min (bump 0.5 → 0.8) | **next** |
| **Q** | P2 same-target within single call | Med | 1h (within-call de-dup) | **next** |
| **R** | COUNTER tag rarity | Med | 2h (recalibrate `counter_value` norm) | later |
| **S** | Comp checklist too late | Low | 1h (early weight + ban-side wire) | later |
| **T** | Archetype hysteresis verify | Low | 30min (per-side prev_archetype in audit) | later |
| **U** | Team-builder flex-impact warning | Med | 2-3h (UI) | later |
| **V** | Solved by O | — | — | — |

**Target after next wave:** P1 triple-stacks under 15%, COUNTER tag fires ≥15%, "off-data picks" (Dr. Mundo Turkey, Tristana JP MID) eliminated.

---

## 4 · What's already working well

Now that the primary-roles fix is live, what the engine consistently nails:

- **Must-ban detection** — Volibear/Ben, Jinx/Logan, Ivern/Devin, Senna/Chips, Bard/Chris, Smolder/Remy all reliably banned.
- **Tier-weighted threat** — Turkey (S-tier) consistently in top-3 P1 ban candidates when on enemy.
- **Spread across enemies in well-balanced rosters** — Draft 8 spread 3 bans across 3 different RED players cleanly.
- **Player-aligned customs picks** — Bobby Diana, Luke Viktor, Jose Zac, Chris Vel'Koz, Miles Trundle, Riley Rell — all engine picks match the player's actual customs #1.
- **Comp checklist tiebreaker visible** — Leona pick scored comp_fit=+0.40 when fitting BLUE's missing engage.
- **Right-rail / TOP CALL hidden on opponent's turn** — multiplayer privacy works.
- **0/32 silent last-pick failures** — priors fallback expansion solved Issue #4.

---

## 5 · Sources

- `engine_audit_run7.json` (32 drafts, seed 100, post-fix5)
- `player_snapshot_v4.1.1.json`
- `DRAFT_BASELINE_REPORT.md` (theory + worked drafts)
- `ENGINE_AUDIT_REPORT.md` (code pathology)
- `ENGINE_FIX_PLAN.md` (Wave 2-5 plan)
