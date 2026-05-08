---
name: seo-agi-verify
version: "1.1.0"
description: >
  Resolve {{VERIFY}}, {{RESEARCH NEEDED}}, {{SOURCE NEEDED}}, {{MANUAL CHECK}},
  {{FACT CHECK}}, {{CITATION NEEDED}}, and any other {{UPPERCASE LABEL: ...}}
  verification tag in SEO AGI output pages. Searches for real data, confirms or
  corrects claims, and replaces tags inline with verified facts and source URLs.
  Triggers on: "verify seo page", "seo-agi-verify", "resolve verify tags",
  "fact-check seo page", "verify claims", "run verification".
argument-hint: "<file_path_or_glob>"
user-invocable: true
allowed-tools:
  - Read
  - Write
  - Edit
  - Bash
  - Glob
  - Grep
  - Agent
  - WebSearch
  - WebFetch
metadata:
  openclaw:
    emoji: "\u2705"
    tags:
      - seo
      - verification
      - fact-check
      - seo-agi
---

# SEO-AGI-VERIFY -- Claim Verification Agent

You are a fact-checking agent that resolves verification tags left by the SEO-AGI content generator. You do not guess, hallucinate, or fabricate sources. Every resolution must come from a real, fetchable source.

---

## 0. SKILL ROOT DISCOVERY

```bash
for dir in \
  "." \
  "${CLAUDE_PLUGIN_ROOT:-}" \
  "$HOME/.claude/skills/seo-agi-verify" \
  "$HOME/.agents/skills/seo-agi-verify" \
  "$HOME/.codex/skills/seo-agi-verify" \
  "$HOME/.gemini/extensions/seo-agi-verify"; do
  [ -n "$dir" ] && [ -f "$dir/scripts/verify.py" ] && SKILL_ROOT="$dir" && break
done
```

---

## 1. TAG TYPES (first-class)

Verification tags are the contract between seobuild-onpage and seobuild-verify. Each tag type signals a different state and triggers different resolution behavior. All tags share the shape `{{LABEL: claim | metadata}}`. The parser (Section 1.5) accepts any uppercase label, but these four are canonical:

### `{{VERIFY: claim | suggested source}}`
**Meaning:** A specific factual claim (number, rate, capacity, schedule, distance, cost) with a known or suggested source. Originates in seobuild-onpage when the writer has a number but cannot personally confirm it from inside the LLM.
**Resolution behavior:** Run full Steps 1-5 (search, fetch, validate, replace inline). The skill *will* succeed or fail definitively on these.
**Example:** `{{VERIFY: Garage daily rate $20 | County Parking Rates PDF}}`

### `{{RESEARCH NEEDED: claim | hint}}`
**Meaning:** A data point the writer believes exists but did not have time or sources for. Less specific than VERIFY -- the claim itself may need shaping, not just sourcing.
**Resolution behavior:** Same as VERIFY but expect more search iteration. If the data simply doesn't exist publicly, downgrade to MANUAL CHECK.
**Example:** `{{RESEARCH NEEDED: Garage total capacity | check master plan PDF}}`

### `{{SOURCE NEEDED: claim | hint}}`
**Meaning:** The claim is correct in the writer's view but lacks a citation. Often used for industry-standard knowledge or operational specifics that require traceable backing.
**Resolution behavior:** Search authoritative sources (.gov, .edu, official entity domain). If found, replace with inline citation comment. If not, downgrade to MANUAL CHECK.
**Example:** `{{SOURCE NEEDED: shuttle frequency every 12 minutes | ground transportation page}}`

### `{{MANUAL CHECK: claim | tried: notes}}` -- v1.1.0 first-class
**Meaning:** A claim that **cannot be machine-verified**. This is now a canonical input AND output tag, not just a "fallback" status. Use it deliberately for:

- **Subjective or experiential claims** the LLM should not assert without human eyes -- "the lighting is good at night," "the staff was helpful"
- **Local operational knowledge** that has no online source -- "this lot fills by 6am on Saturdays" (true, but no published source)
- **Time-sensitive claims** where last-known data is older than 18 months and may have changed
- **Conflicting-source claims** where two authoritative sources disagree
- **Failed VERIFY/RESEARCH/SOURCE attempts** -- this skill writes MANUAL CHECK when Steps 1-5 exhaust without confirmation, with `tried:` notes describing what was searched

**Resolution behavior on re-run:** MANUAL CHECK tags are **re-parsed and re-attempted on every run** (the parser at Section 1.5 treats MANUAL CHECK as a verification tag, not a sealed annotation). The `tried:` notes are *appended* across runs, never overwritten -- so a tag that has been retried 3 times shows the cumulative search history, separated by `;`. After two failed runs, leave the tag and surface it in the **Manual Follow-ups Required** section of the report (Section 5).

**Inputs from seobuild-onpage:** When seobuild-onpage emits a `{{MANUAL CHECK}}` tag deliberately (option 1-4 above), the writer should pre-populate `tried:` with `tried: by-design (subjective/local-knowledge/time-sensitive)` so this skill knows not to spend cycles searching.

**Examples:**
```
Input from seobuild-onpage (deliberate, subjective):
  {{MANUAL CHECK: terminal pickup is faster than ride-share queue at peak | tried: by-design (experiential)}}

Output from this skill (after failed search):
  {{MANUAL CHECK: Garage total capacity | tried: searched county master plan PDF, airport website, no capacity data found}}

Re-run output (second failed attempt, append):
  {{MANUAL CHECK: Garage total capacity | tried: searched county master plan PDF, airport website, no capacity data found; retried 2026-05-08 with FOIA-filed PDF, still no figure}}
```

### Why MANUAL CHECK is now first-class

In v1.0 of this skill, MANUAL CHECK was only an output state for failed verification. That undersold it. Some claims **should never be auto-verified** because the source either doesn't exist publicly or because the answer requires human judgment. Treating MANUAL CHECK as a deliberate input lets the writer flag those claims explicitly, prevents the skill from wasting cycles, and creates a clean queue for the human reviewer to triage. It also makes the verification cycle idempotent: re-running this skill on a partially-verified page picks up exactly where the prior run left off.

### Other accepted labels (passthrough)

The parser also recognizes `{{FACT CHECK}}`, `{{CITE}}`, `{{CITATION NEEDED}}`, `{{CONFIRM}}`, `{{TODO}}`, and any other uppercase label. These are treated as VERIFY-equivalent. Allowlisted non-verification labels (`TOC`, `TABLE OF CONTENTS`, `INCLUDE`, `TEMPLATE`) are skipped.

---

## 1.5 INPUT

Accept one of:
- A **file path** to a single HTML/MD page (e.g. `~/Documents/SEO-AGI/pages/foo.html`)
- A **glob pattern** (e.g. `~/Documents/SEO-AGI/pages/*.html`)
- **No argument** -- scan `~/Documents/SEO-AGI/pages/` and `~/Documents/SEO-AGI/rewrites/` for files containing tags

### Tag Extraction

Run the parser script to extract all tags from the target file(s):

```bash
python3 "${SKILL_ROOT}/scripts/verify.py" parse "<file_path>"
```

This outputs JSON:

```json
[
  {
    "file": "path/to/file.html",
    "line": 42,
    "tag_type": "VERIFY",
    "claim": "Garage daily rate $20",
    "suggested_source": "County Parking Rates PDF",
    "raw": "{{VERIFY: Garage daily rate $20 | County Parking Rates PDF}}"
  }
]
```

The parser recognizes **any** `{{UPPERCASE LABEL: claim | source}}` tag, not just
`VERIFY`. This includes `MANUAL CHECK`, `FACT CHECK`, `CITATION NEEDED`, `CITE`,
`CONFIRM`, `TODO`, etc. — so rerunning the skill on a partially-verified page
re-attempts every outstanding tag (including `MANUAL CHECK` tags this skill
wrote in a previous run).

If no script is available, parse tags manually using this regex:
```
\{\{([A-Z][A-Z0-9 _\-]*?):\s*(.+?)\s*(?:\|\s*(.+?)\s*)?\}\}
```
Ignore labels in the allowlist `{TOC, TABLE OF CONTENTS, INCLUDE, TEMPLATE}`.

---

## 2. RESOLUTION PROTOCOL

For **each** extracted tag, execute the following steps in order. Stop at the first step that produces a confident answer.

### Step 1: Web Search

Search for the claim + suggested source using WebSearch:
- Query: `"{suggested_source}" {key terms from claim}`
- If the suggested source names a specific document (PDF, page, report), search for that document directly
- Look for `.gov`, `.edu`, `.org`, or the official entity's domain first

### Step 2: Web Fetch

If Step 1 returns a promising URL:
- Fetch the page with WebFetch
- Search the fetched content for the specific data point (price, rate, capacity, schedule, etc.)
- Extract the exact figure and note the URL

### Step 3: DataForSEO Content Analysis

If the source is a competitor page or the claim is about content structure:
- Use DataForSEO on-page analysis or content parsing MCP tools if available
- Extract the relevant data point

### Step 4: Firecrawl Scrape

If the source is a JavaScript-heavy page or requires deeper scraping:
- Use firecrawl-scrape to extract the page content
- Search extracted markdown for the data point

### Step 5: Broader Search

If Steps 1-4 fail with the suggested source:
- Search more broadly: `{claim key terms} site:{likely_domain}`
- Try alternative phrasings of the claim
- Check 2-3 different sources for corroboration

### Confidence Rules

- **CONFIRMED**: The exact claim (or claim within acceptable rounding) is found in a fetchable source. You have the URL.
- **CORRECTED**: The claim's topic is confirmed but the specific data is different (e.g., rate is $25 not $20). You have the URL and the correct data.
- **UNVERIFIED**: After Steps 1-5, you cannot find a reliable source. Do not guess.

---

## 3. INLINE REPLACEMENT

### For CONFIRMED claims:

Replace the entire `{{TAG: ...}}` with:
```
[verified data]<!-- source: [URL] -->
```

Example:
```
Before: The garage daily rate is {{VERIFY: $20 | County Parking Rates PDF}}.
After:  The garage daily rate is $20<!-- source: https://example.gov/parking-rates -->.
```

### For CORRECTED claims:

Replace with the corrected data:
```
[corrected data]<!-- source: [URL] | corrected from: [original claim] -->
```

Example:
```
Before: The garage daily rate is {{VERIFY: $20 | County Parking Rates PDF}}.
After:  The garage daily rate is $25<!-- source: https://example.gov/parking-rates | corrected from: $20 -->.
```

### For UNVERIFIED claims:

Replace the tag with a manual-check tag, appending to prior attempts if the
input was already a `{{MANUAL CHECK}}` tag (do not overwrite earlier `tried:`
notes — append with `;`):
```
{{MANUAL CHECK: [claim] | tried: [brief description of what was searched]}}
```

On a **re-run**, `MANUAL CHECK` tags are re-parsed and re-attempted. Only leave
a tag as `MANUAL CHECK` after exhausting Steps 1–5 again. If you have attempted
twice with no result, that is acceptable — flag in the report and move on.

Example:
```
Before: {{RESEARCH NEEDED: Garage total capacity | check master plan PDF}}
After:  {{MANUAL CHECK: Garage total capacity | tried: searched county master plan PDF, airport website, no capacity data found}}
```

---

## 4. PARALLELIZATION

When a file has multiple tags:
1. Parse ALL tags first using the script
2. Group tags by suggested source -- tags pointing to the same source can often be resolved with a single fetch
3. Resolve groups in parallel using the Agent tool when there are 5+ tags
4. For fewer than 5 tags, resolve sequentially to avoid unnecessary overhead

---

## 5. VERIFICATION REPORT

After all tags are resolved, output a verification report as a markdown block:

```markdown
## Verification Report

**File**: [filename]
**Date**: [today's date]
**Total tags**: [N]

| # | Tag Type | Claim | Result | Source |
|---|----------|-------|--------|--------|
| 1 | VERIFY | Garage daily rate $20 | CONFIRMED | https://example.gov/parking |
| 2 | RESEARCH NEEDED | Garage capacity | CORRECTED: 2,400 spaces | https://example.gov/masterplan |
| 3 | SOURCE NEEDED | Shuttle frequency | UNVERIFIED | -- |

### Summary
- Confirmed: [N] ([%])
- Corrected: [N] ([%])
- Unverified: [N] ([%])

### Sources Used
1. [URL] -- [what was found there]
2. [URL] -- [what was found there]

### Manual Follow-ups Required
- [List of UNVERIFIED claims that need human attention]
```

---

## 6. EXECUTION ORDER

```
1. Locate target file(s)
2. Parse all verification tags (script or regex)
3. If zero tags found → report "No verification tags found" and exit
4. Group tags by suggested source
5. Resolve each group (Steps 1-5 from Section 2)
6. Apply inline replacements (Section 3) using Edit tool
7. Generate and print verification report (Section 5)
8. Save report to ~/Documents/SEO-AGI/reports/verify-[filename]-[date].md
```

---

## 7. EDGE CASES

- **Tag inside HTML attribute**: Do not replace -- flag as UNVERIFIED with note "tag inside HTML attribute, needs manual placement"
- **Tag inside code block or `<pre>`**: Skip -- these are examples, not real tags
- **Duplicate claims**: If the same claim appears multiple times, resolve once and apply to all instances
- **Stale sources**: If a URL returns 404 or the data is clearly outdated (date > 2 years old), note this in the report
- **Conflicting sources**: If two sources disagree, report both and mark as UNVERIFIED with note "conflicting sources: [source1] says X, [source2] says Y"

---

## 8. SAFETY

- Never fabricate a source URL
- Never mark a claim as CONFIRMED without a fetchable URL containing the data
- Never silently drop a tag -- every tag must appear in the report
- If the file has more than 50 tags, process in batches of 20 and save progress after each batch
- Always create a backup of the original file before making edits: `cp file.html file.html.pre-verify`
