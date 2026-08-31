---
name: house-style
description: "The mandatory writing standard for this repository — ASD-STE100 prose and RFC 2119 requirement keywords. Read it before writing or editing any comment, docstring, Markdown file, README, wiki page, commit message, or pull request body. Also covers what a comment MUST NOT contain: history, justification, status, dates, and coverage narration."
---

# House style

Two standards govern every comment, docstring, Markdown file, wiki page,
commit message, and response in this repository:

- **ASD-STE100** governs the prose. Write short, plain, active sentences.
- **RFC 2119** governs the requirement words. Write MUST, MUST NOT,
  SHOULD, SHOULD NOT, and MAY in uppercase when you state a rule.

The two standards do not conflict. RFC 2119 defines the strength of a
rule. ASD-STE100 defines every other word in the sentence.

## Requirement keywords, per RFC 2119

Use these five keywords, in uppercase, and only in a normative statement:

| Keyword | Meaning |
|---|---|
| **MUST** | An absolute requirement. Break it and the change is wrong. |
| **MUST NOT** | An absolute prohibition. |
| **SHOULD** | A strong recommendation. Deviate only with a stated reason. |
| **SHOULD NOT** | A strong recommendation against. The same reason rule applies. |
| **MAY** | A true option. Both choices are correct. |

Rules for the keywords:

1. **Uppercase marks the keyword.** Uppercase MUST carries the RFC 2119
   meaning. Lowercase "must" is ordinary prose and carries no strength.
2. **One word per strength.** Do not write REQUIRED, SHALL, SHALL NOT,
   RECOMMENDED, NOT RECOMMENDED, or OPTIONAL. RFC 2119 permits those
   synonyms; ASD-STE100 forbids two words for one meaning. The five
   keywords in the table are the whole set.
3. **State who the rule binds.** Write "The pipeline modules MUST keep
   `from __future__ import annotations`", not "annotations MUST be kept".
4. **Reserve the keywords for real requirements.** Use a keyword when a
   reader who ignores it breaks the build, the deploy, or the security
   boundary. Describe everything else in plain sentences.
5. **Give SHOULD an escape.** When you write SHOULD, name the condition
   that permits the deviation. A SHOULD with no stated escape is a MUST —
   write MUST instead.
6. **Do not stack keywords.** One requirement per sentence.

## Comments and docstrings

A comment earns its place by telling a reader something the code cannot.
Delete it otherwise. The ASD-STE100 rules below apply to every comment
and docstring; the RFC 2119 keywords apply when a comment states a rule
the next editor MUST obey.

**Sentences**

- Procedural sentences: 20 words maximum. Descriptive: 25 words maximum.
- One idea per sentence. Do not join two actions with "and".
- Use the active voice and name the actor: "SageMaker owns this group",
  not "this group is owned".
- Use the imperative for an instruction: "Update this role in place."
- Use the present tense. Describe what the code does now.

**Words**

- One word, one meaning. Use the simplest exact word: "use" over
  "utilize", "start" over "initiate", "before" over "prior to".
- Do not drop articles. Write "Read the file", not "Read file".
- Repeat the same term for the same thing. Do not vary it for style.
- No idioms, metaphors, or humor.
- Reproduce code identifiers, paths, commands, and AWS error names
  exactly. Never simplify one to read better.

**What a comment must not contain**

1. **No history.** Do not write what the code used to be, what a previous
   version did, or what a past incident was. Git and the wiki hold that.
   Write the rule that holds today. Not "the host's wheels once caused a
   pydantic_core failure" but "the host's wheels fail at runtime".
2. **No justification.** Do not argue for the code. Drop "that is the
   point", "deliberately", "worth it", "reviewed and diffed", "would have
   shipped", "this test pins". State the constraint and stop.
3. **No status or dates.** Do not write phase numbers as bookkeeping,
   enablement dates, or observation windows — "3C. Enabled 2026-08-02" is
   noise in the code. `wiki/pages/architecture/phased-security-hardening.md`
   is the status board. Name a phase only when it identifies work the code
   still owes, such as a cdk-nag acknowledgement `reason` string, which
   must name the phase that removes it.
4. **No coverage or test-debt narration.** Do not write that something
   had no test or sat at 0%.

**Keep a comment when it carries one of these**

- A constraint that fails at runtime rather than at synth or lint.
- A non-obvious AWS or SDK behaviour, and what breaks without the code.
- A rule the next editor MUST obey, such as "Update this role in place.
  You MUST NOT replace it — the deployed pipeline pins this ARN".
- Why an alternative was not taken, stated as a fact about the
  alternative, not as a defence of the choice.

**Maintenance.** When you change code, update or delete the comments
around it in the same change set. A comment that names a file, symbol, or
behaviour that no longer exists is a defect — fix it when you see it.

## Where the rules bend

`wiki/AGENTS.md` states the two wiki exceptions: preserved source text keeps
its own words, and history, dates, and status belong on a wiki page. Read the
`wiki-record` skill before you write there.
