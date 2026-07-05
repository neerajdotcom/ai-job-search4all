# /setup-native — Zero-key profile onboarding

Zero-key equivalent of `python setup_profile.py --resume <path>`. Extracts a
first-draft `candidate_profile/config.yaml` from the user's résumé using
your (Claude's) own reasoning, no `GEMINI_API_KEY` required.

`$ARGUMENTS` may point at a résumé file (`.docx` or `.pdf`). If none is
given, ask the user for one.

**Never invent anything not stated or clearly implied by the résumé —
leave a field empty if unclear.** This mirrors the cardinal rule in
`setup_profile.py`'s `EXTRACTION_PROMPT` (which is the schema spec below),
and the same "never fabricate" rule the tailoring path enforces.

---

## Step 0: Preconditions

Check `candidate_profile/config.yaml` doesn't already exist. If it does,
tell the user and stop unless they explicitly say to overwrite.

Ask for the résumé path if `$ARGUMENTS` is empty. Support `.docx` and
`.pdf` only.

## Step 1: Load résumé text

```bash
python -m native.cli extract-resume-text --resume "<path>" > /tmp/setup-native-resume.txt
```

Read `/tmp/setup-native-resume.txt` via the Read tool. If the extracted
text is very short (<100 chars), warn the user — the file may be
image-based (scanned PDF) and the résumé needs a text-based version.

## Step 2: Extract the profile (your reasoning)

Read the résumé text carefully and produce a JSON object with **exactly
these 8 keys**, matching the schema `setup_profile.EXTRACTION_PROMPT`
defines:

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
  experience is in or closely adjacent to, e.g. `"fintech"`,
  `"e-commerce"`, `"healthcare"`)
- `roles` (object — one entry per employer in their work history, oldest
  last. Each key is a short lowercase slug like `"acme_corp"`; each value
  is a list of 1–2 lowercase keyword strings that appear as exact
  substrings of that employer's name in the résumé text. These keywords
  drive `patch_docx`'s bullet locator later, so they must be exact
  substrings)

Leave a field as an empty string / empty list if you can't determine it
confidently. Save the JSON to `/tmp/setup-native-extracted.json`.

## Step 3: Copy the résumé into the profile directory

```bash
mkdir -p candidate_profile
cp "<original path>" candidate_profile/resume<.docx|.pdf>
```

Use `resume.docx` or `resume.pdf` (matching the source extension) as the
destination name — this is what `setup_profile.py` also does, so
`profile.resume_path` will resolve to a real file for both paths.

## Step 4: Write the YAML

```bash
python -m native.cli write-profile \
    --extracted-json /tmp/setup-native-extracted.json \
    --resume-dest-name resume<.docx|.pdf>
```

(Add `--force` if the user is overwriting a prior config.) This calls
`setup_profile.build_config` + `write_config` unchanged, so the file
shape is identical to the Gemini path.

## Step 5: Summary + hand-edit reminder

Present a table of what got written and remind the user to hand-edit
these placeholder-y fields — same list `setup_profile.py` prints:

- The `[fill in]` notice-period placeholder in `context`
- `adzuna_country_code` (always defaults to `"us"` — set to your country's
  Adzuna slug if you plan to use Adzuna, otherwise leave it; the LinkedIn
  guest source doesn't need it)
- `target_companies` (companies to highlight in the digest — optional)
- `excluded_companies` (e.g. your current employer)

Tell them:
> Draft profile written to `candidate_profile/config.yaml`. Review every
> field above before your first real run, exactly like the pipeline's
> own "never fabricate" rule. Then run `/scrape-native` to see it in
> action, or `python -m native.cli verify` to sanity-check the whole
> zero-key pipeline against the sample.

Delete `/tmp/setup-native-resume.txt` and `/tmp/setup-native-extracted.json`
before exiting — these contain PII (the résumé text) and shouldn't sit
around.

---

## Rules
1. Never invent a field the résumé doesn't clearly support. Empty is
   fine — the loader tolerates it and the user is going to review.
2. Don't overwrite an existing `candidate_profile/config.yaml` without
   the user's explicit consent (Step 0).
3. This command writes into the repo — never run it against a résumé
   the user hasn't consented to storing in the repo (`resume.docx` /
   `resume.pdf` under `candidate_profile/` ships with commits per the
   existing repo layout).
