---
name: seo-agi-verify
version: "1.0.0"
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

## 1. INPUT

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
