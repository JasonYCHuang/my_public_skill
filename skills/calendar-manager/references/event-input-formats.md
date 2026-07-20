# Terse 行事曆 input formats actually used in practice

The `calendar-manager` skill maps a natural-language request like "時間、地點、事項"
into a calendar event. In practice two terse formats dominate, both seen
repeatedly in the same session — handle them confidently without asking
for clarification.

## Format A: 「行事曆加入：M/D HHMM 城市 事項」

```
行事曆加入：7/15 1930 深圳 印度文A1 chap 04
行事曆加入：7/13晚上19:00閱讀印度文A1第1章
```

- **`M/D`** — month/day with NO year. The year is always the current year
  of the conversation. The agent should not ask "which year?" if the
  date is in the past for the current year — instead default to the same
  M/D in the current year. If the user says something like "明年 7/15"
  then it's the next year.
- **`HHMM`** — 24-hour, no colon, no space. So `1930` = 19:30, `0930`
  = 09:30. The user can also write `晚上19:00` (with colon) or
  `早上09:30` — treat all of these as the same.
- **Default end time** — start + 1 hour, unless the user specifies
  "到 HH:MM" / "until HH:MM". Do NOT ask for end time when only start
  is given.
- **Location** — the word right after the time. Common values: 淮安,
  深圳, 台灣, 在家. Maps directly into the `location` field.
- **Item (summary)** — everything after the location. May contain spaces,
  punctuation, English, and chapter numbers ("chap 04" / "第1章" /
  "chap02" — all valid). Preserve verbatim; don't translate "chap" to
  "第X章" or vice versa.
- **No closing punctuation** is normal — don't add period/句號.

### Mistake to avoid
Don't reach for the `icloud-calendar` skill's `add_event.py` here — the
sibling skill is off-limits per the user's stored memory. Use
`scripts/icloud/create_event.py` from this skill (positional args,
`YYYY-MM-DD HH:MM` format).

### Companion operations
When the user later says "改到當天早上0930" (move to 09:30), update via
`scripts/icloud/update_event.py` with the *same* UID — never create a
new event and delete the old one for a simple time-shift, the user
wants the UID stable so any linked alarms / shared invites keep working.

## Format B: "改 X / 刪 X / 那個是 Y"

When the user follows up with a short reference like
"改 7/16 那個 chap 04" or "那個是 7/17", they're almost always referring
to the **most recently mentioned event** in the conversation. Don't ask
"which event?", just operate on the last one. If multiple were created
in a row and it's genuinely ambiguous (more than 2 events in the last
few turns), ask with a multiple-choice question showing the candidate
UIDs/summaries rather than free-form.

## Sequence pattern: 「連續 N 天同章」

```text
7/13 19:00 深圳 印度文A1 chap 01
7/15 19:30 深圳 印度文A1 chap 04
7/16 19:30 深圳 印度文A1 chap 04
7/17 09:30 深圳 印度文A1 chap 05
```

The user often enters 3-7 days in a row with the same chapter and *will
make a typo* on one of them. The exact failure shape that triggered
this reference was a real session: the user typed `chap 05` for both
7/16 and 7/17 in succession, the agent wrote both as-is, and only the
follow-up `"7/16 那個改成 chap 04"` revealed that 7/16 was meant to be
a re-read of chap 04 (the user only read it once that day). Best
practice:

1. **Create all the events first**, then run `list_events.py` to show
   them back in a table.
2. **Read the chapter sequence aloud** (in your own head if not in the
   response). If you see `01, 04, 04, 05` that's plausible (started,
   re-read, advanced). If you see `01, 04, 05, 05` and the user only
   said "印度文 A1 chap XX" without further context, that's the typo
   shape — *before* confirming all writes succeeded, ask:
   `"7/16 那個 chap 05 是不是應該改成 chap 04？"` with a multiple-choice
   of (A. 留著 / B. 改成 chap 04 / C. 刪除).
3. If the user explicitly picks "A. 留著" then respect that — they may
   actually be reviewing yesterday's chapter on purpose. But ask first
   rather than assuming — silent duplicate-chapter entries are the
   single most common mistake in 連續學習 sessions, and the fix is
   one `update_event.py` call if caught within the same session.

The same shape recurs for any 連續學習 plan: language chapters,
course lectures, training videos, book sections. The chapter/lecture
number is in the summary, the typo is one digit different, and the user
is typing fast — assume at least one typo per 4-5 entries and check
explicitly.
