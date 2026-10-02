---
name: settings-sync
description: Add, rename or remove a profile field (a session setting such as KEEP_TRANSCRIPT or a new SUBTITLES) without the profile, the interactive questions, the "Run again?" round and the shipped samples drifting apart. Use for any change to what a session can be told, or when a profile field is ignored, asked again every round, or leaks into the environment.
---

# Settings sync

A session setting is answered at the console or read from a profile, and both go through one
function (`_configure`) reading one table (`SETTINGS`): AGENTS.md invariant 2. A field still
lives in several places, and a place missed fails quietly:

| # | Where | What it holds | Missed, and |
|---|---|---|---|
| 1 | `YouTubeTranscriber.DEFAULT_FIELDS` | Every field a profile holds, in the order `create_profile` writes them | A saved profile leaves it out |
| 2 | `SETTINGS` | `Setting(field, absent=, blank=, legacy=, one_video=)`: what a profile without it, or with it blank, means | A profile hands it to the environment as configuration (`_Profile.__init__`) |
| 3 | `_configure` | Asks or takes the answer, stores it on `cfg`, and records it in `used_fields` | Never settled; a profile saved from the session holds a blank |
| 4 | `SessionConfig` | The settled value | Nowhere to keep it |
| 5 | `_Remembered.carry` | What the round before a "Run again?" passes on | Asked again every round |
| 6 | The step that acts on it | `_run_pipeline`, a `_Pass` step, or what they call | Settled and never used |
| 7 | `OpenAIYouTubeTranscriber/Profile/profile*.txt` | The four shipped samples, each holding every field but `AI_PROVIDER` and `MODEL` | The samples disagree with a saved profile |
| 8 | `README.md`, `docs/USAGE.md` | The field, its values and what a blank means | Users never learn it exists |
| 9 | `CHANGELOG.md` `[Unreleased]` | What the user can now do | |

## Procedure

1. **Decide what absent and blank mean, and ask the owner if it is not obvious** (AGENTS.md,
   *How to work here*). Profiles written before the field existed do not carry it: **a field
   that turns something on is off when absent** (`absent="n"`), so an old profile does what
   it always did. `ASK` (the default) means the session asks; a profile run unattended will
   then stop and wait, so prefer a real answer for anything a profile run should not stop on.
2. **Table.** Add it to `DEFAULT_FIELDS` where it reads naturally in a saved profile, and its
   `Setting` to `SETTINGS`. `one_video=True` if the value names one video's own file (a
   `*_RENAME`), which the next video of a repeat would be written over.
3. **Settle it in `_configure`.** A yes/no goes through `_yes_no(transcriber, answers, FIELD,
   question, default=...)`; follow the nearest similar field. Ask it only where it means
   something (`KEEP_TRANSCRIPT` is asked only when enhancement runs), set the `cfg` attribute,
   and record the answer in `used_fields[FIELD]` in the form a profile stores (`_yn(...)` for a
   yes/no). The value goes into the profile through `env_value`: never write a profile line by
   hand.
4. **Remember it** in `_Remembered.carry`, in the form the field is stored, and as nothing
   (a falsy value, as the entries around it are written) when the round never asked it.
5. **Use it** in the step it belongs to.
6. **Samples, docs, changelog.** Add the line to all four shipped profiles with the value each
   sample means; document the field; add the changelog entry.
7. **Tests.**
   - `test_the_settings_table_covers_every_field` holds rows 1 and 2 together; it fails on its
     own if one is missed.
   - Add the field to `test_a_profile_and_a_repeat_settle_alike`'s `stated` answers: the same
     answers from a profile and from a remembered round must settle the same session.
   - Test what an old profile without the field does, and what a blank does.
8. **Verify:** `make lint` and `make test`, then run the app once from a profile that sets
   the field and once interactively with "Run again?", and say that you did.

## Renaming a field

Give the new `Setting` `legacy="OLD_NAME"` (as `VIDEO_RESOLUTION` keeps `RESOLUTION` and
`AI_REFINEMENT` keeps `AI_ENHANCEMENT`). `_Profile.lookup` reads the old name when the new one
is unset and reports it under the name the profile used. Profiles in the wild are never
rewritten, so the old name is read forever.

## Removing a field

Delete rows 1-9, then grep for every read of it (`"FIELD"`, `cfg.attribute`) before assuming
it is unused. **Old profiles still carry the line.** A key outside `_PROFILE_FIELDS` is
exported to the environment as configuration, so add the retired name to `_PROFILE_FIELDS`
explicitly, with a comment saying it is read and ignored. A profile must never stop loading
because it was saved by an older version.

## Shipping a new prompt or sample profile

Add the file to `[tool.setuptools.package-data]` in `pyproject.toml`; it is listed file by
file, never globbed (AGENTS.md invariant 9). `test_an_installed_copy_starts_with_the_sample_profiles`
covers the samples.
