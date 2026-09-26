---
name: setup-native
description: >
  Zero-key profile onboarding. Extracts a first-draft
  candidate_profile/config.yaml from the user's resume using the agent's own
  reasoning — no GEMINI_API_KEY required. Use when the user says
  "/setup-native path/to/resume.docx" or asks to set up their profile
  without API keys.
---

# /setup-native — Zero-key profile onboarding

Zero-key equivalent of `python setup_profile.py --resume <path>`. Extracts a
first-draft `candidate_profile/config.yaml` from the user's resume using
the agent's own reasoning, no `GEMINI_API_KEY` required.

The argument may point at a resume file (`.docx` or `.pdf`). If none is
given, ask the user for one.

**Never invent anything not stated or clearly implied by the resume —
leave a field empty if unclear.**

---

## Step 0: Preconditions

Check `candidate_profile/config.yaml` doesn't already exist. If it does,
tell the user and stop unless they explicitly say to overwrite.

Ask for the resume path if no argument was given. Support `.docx` and
`.pdf` only.

## Step 1: Load resume text

```bash
python -m native.cli extract-resume-text --resume "<path>" > /tmp/setup-native-resume.txt
```

Read `/tmp/setup-native-resume.txt`. If the extracted text is very short
(<100 chars), warn the user — the file may be image-based (scanned PDF) and
needs a text-based version.

## Step 2: Extract the profile (agent reasoning)

Read the resume text carefully and produce a JSON object with **exactly
these 8 keys**:

- `name` (string, full name)
- `title` (string, current or most recent job title, generalized to a
  standard form suitable for job search — e.g. "Product Manager" not
  "Sr. PM II")
- `years_experience` (integer, total years of relevant professional
  experience)
- `location` (string, "City, Country" — the candidate's current location)
- `target_location_country` (string, lowercase country name matching
  `location`, e.g. `"india"`, `"united states"`, `"united kingdom"`)
- `search_terms` (list of 4–8 strings — job titles to search for, based
  on the candidate's actual title and career trajectory; include close
  variants, e.g. for "Product Manager" add "Senior Product Manager",
  "Associate Product Manager", "Product Owner")
- `adjacent_industries` (list of 1–3 strings — industries the candidate's
  experience is in or closely adjacent to, e.g. `"fintech"`, `"e-commerce"`)
- `roles` (object — one entry per employer in work history, oldest last.
  Each key is a short lowercase slug like `"acme_corp"`; each value is a
  list of 1–2 lowercase keyword strings that appear as exact substrings of
  that employer's name in the resume text)

Leave a field as an empty string / empty list if you can't determine it
confidently. Save the JSON to `/tmp/setup-native-extracted.json`.

## Step 3: Copy the resume into the profile directory

```bash
mkdir -p candidate_profile
cp "<original path>" candidate_profile/resume<.docx|.pdf>
```

## Step 4: Write the YAML

```bash
python -m native.cli write-profile \
    --extracted-json /tmp/setup-native-extracted.json \
    --resume-dest-name resume<.docx|.pdf>
```

Add `--force` if the user is overwriting a prior config.

## Step 5: Summary + hand-edit reminder

Present a table of what got written and remind the user to review these:

- The `[fill in]` notice-period placeholder in `context`
- `adzuna_country_code` (defaults to `"us"` — set to your country's Adzuna
  slug if using Adzuna, otherwise leave it)
- `target_companies` (companies to highlight — optional)
- `excluded_companies` (e.g. your current employer)
- `search_locations` (empty by default — add extra cities to cast a wider
  net, e.g. `["Mumbai, India", "Pune, India"]`)

Tell them:
> Draft profile written to `candidate_profile/config.yaml`. Review every
> field before your first real run. Then run `/scrape-native` to see it in
> action.

Clean up temp files:
```bash
rm /tmp/setup-native-resume.txt /tmp/setup-native-extracted.json
```

---

## Rules
1. Never invent a field the resume doesn't clearly support. Empty is fine.
2. Don't overwrite an existing `candidate_profile/config.yaml` without the
   user's explicit consent.
3. Delete the temp files (which contain resume PII) before exiting.
