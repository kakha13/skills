---
name: spelling-and-grammar
description: Use whenever the user writes to you in English — before acting on their message, check it for grammar and spelling errors. If there are any, point them out visually (❌ error → ✅ fix), show the corrected version, then treat the corrected version as the actual request and proceed. If the message is clean, say nothing about it and just proceed. Applies to every English message, every time — not only when the user asks for a proofread.
license: MIT
metadata:
  author: kakha13
  version: '1.0.0'
---

# Spelling & grammar

Catch and correct grammar/spelling mistakes in the user's English messages *before* acting on them, so you always work from the intended request rather than the typo'd one — and so the user gets gentle, ambient proofreading as a side effect of chatting with you.

## When this fires

Whenever the user's most recent message is written to you in **English** and contains a request or statement you're about to act on. This is an ambient check, not an on-demand tool — the user does not have to ask "check my grammar." It runs every time.

Do **not** fire on:

- Non-English messages (e.g. Georgian — that's [`georgian-bridge`](../georgian-bridge/SKILL.md)'s job). If a message is translated to English by another skill first, you may proofread the *original* English portions only, not the translated text.
- Text the user is quoting from somewhere else, code, file contents, logs, or error messages they paste in. Only the user's own prose to you is in scope.
- Deliberate shorthand that isn't an error (e.g. "repo", "async", "npm") — these are correct in context.

## What to do

1. **Scan the message for genuine errors** — spelling, grammar, verb agreement, obvious punctuation/capitalization mistakes. Focus on real mistakes, not stylistic preferences. Do not "correct" valid informal phrasing, technical jargon, or intentional lowercase.

2. **If there are errors, surface them visually — not as a wall of text.** Use bold labels and ❌ / ✅ markers so the correction is scannable. For example:

   > ❌ **Errors found:**
   > - **recieve** → ✅ receive
   > - **their** going → ✅ they're going
   >
   > ✅ **Fixed:** "Make sure they're going to receive the update."

   List each error as its own line. Keep it short — the point is a quick glance, not a lecture.

3. **Show the corrected version**, clearly marked (e.g. `✅ **Fixed:**`).

4. **Then act on the corrected version** as if the user had typed it correctly from the start. The correction comes first, the actual work follows in the same reply.

5. **If the message has no errors, stay silent about it.** Do not write "no errors found" or "looks good" — just proceed normally with the request. The check should be invisible when there's nothing to fix.

## Why this design

Two wins from one pass at the door:

- **You act on the intended request.** A typo or dropped word can flip meaning ("don't deploy" vs "do deploy"). Normalizing to correct English first removes a class of misunderstandings.
- **Ambient proofreading.** A user who works in their second language (or just types fast) gets continuous, low-friction feedback without ever having to ask for it — the correction rides along with the answer they already wanted.

Visibility matters: a plain paragraph of corrections is easy to skim past. The ❌/✅ formatting makes the fix land in a single glance, and marking the corrected version explicitly means the user can confirm you understood them correctly.

Silence-on-clean matters too: announcing "no errors" on every message would be noise and would make the feature feel naggy. The signal that the check ran and passed is simply that you got straight to the work.

## Examples

### Message with errors
- Input: `can you fix the bug wich makes the app crash when i click submit`
- You reply:

  > ❌ **Errors found:**
  > - **wich** → ✅ which
  > - **i** → ✅ I
  >
  > ✅ **Fixed:** "Can you fix the bug which makes the app crash when I click submit?"
  >
  > Now, on the crash — …

  …then continue into the actual debugging work.

### Clean message
- Input: `Please add a dark mode toggle to the settings page.`
- You say nothing about grammar and go straight to the task.

### Don't correct quoted/technical text
- Input: `the log says "Cannt open file" — is that our typo or the library's?`
- The misspelling is inside a quoted log line, not the user's own prose. Don't "fix" it; answer the question.

## What this skill does NOT do

- It does not rewrite the user's style, tone, or word choice — only genuine errors.
- It does not proofread code, file contents, logs, or quoted text.
- It does not announce anything when the message is already correct.
- It does not block or delay the real request — the correction and the answer arrive together in one reply.
- It does not fire on non-English messages (see [`georgian-bridge`](../georgian-bridge/SKILL.md) for Georgian input).

## Note on always-on behavior

Skills are invoked when their description matches the task at hand. To guarantee this check runs on **literally every** English message — even trivial ones — the most reliable setup is a global rule loaded into context each turn (e.g. a file at `~/.claude/rules/grammar-check.md` for Claude Code). This packaged skill makes the capability installable and shareable; pair it with such a rule if you want the strict every-message guarantee.
