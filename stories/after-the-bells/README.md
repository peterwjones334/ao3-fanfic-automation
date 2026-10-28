# After the Bells: scheduled generation handoff

Destination: `peterwjones334/ao3-fanfic-automation`. This repository is PUBLIC: committed drafts are publicly readable. GitHub delivery is not AO3 publication.

## Producer contract
Use the original After the Bells universe notes and ten-story schedule. The user supplied the schedule and briefs on 28 October 2026; see plan.json. The full continuity guide remains with the original ChatGPT producer. Do not invent continuity or replace the schedule with the unrelated hourly fandom generator.
For each scheduled story, write prose only to `stories/after-the-bells/story-NN.md`, and pipeline Metadata JSON to `story-NN.json`. NN runs 01–10. Commit both together in one Git commit. Use deterministic paths and work IDs; before retrying, inspect existing files and compare content. Identical delivery is a no-op. Never overwrite an existing different story automatically: open a review branch/PR.
Required JSON fields: work_id (after-the-bells-NN), title, author, chapter (1), chapter_title, release_date (YYYY-MM-DD), rating, warnings, fandoms, tags, summary, language (en), complete (true).
Metadata must conform to the installed ao3_pipeline.models.Metadata schema. No approval fields belong in Metadata. Do not guess authorship, warnings, release dates or fandom.
Keep generation prompt/provenance and automation disclosure in a separate notes file if needed; do not insert operational text into the prose.
Never commit account credentials, browser profiles, SQLite databases or local approval receipts.

## Local consumer
Install the existing local AO3 pipeline first. In a clean local clone, fetch/pull changes using your existing Git authentication, then:
```sh
python integration/after_the_bells.py
python integration/after_the_bells.py --db /absolute/private/path/state.db
```
The first command validates available pairs without changing state. The second ingests into the explicitly selected local DB. Repeat safely: identical payloads retain their revision and state. Changed content/metadata gets the pipeline's normal new revision requiring approval; terminal-state protections remain in force. Existing local approval/audit history is never copied from GitHub or replaced. Ingestion may partially finish if a later database operation fails; retrying identical inputs is safe.
Use `ao3-pipeline --db PATH show REVISION`, `preview REVISION --output FILE.html`, then explicitly `approve REVISION --actor NAME` after review. This integration never calls approve, run-due, browser-post or any AO3 endpoint.
Partial deliveries can be ingested independently. The Release 5 campaign importer requires all ten entries, intended target account/pseud/collection and daily contiguous release dates; build its manifest locally when those values are known. Do not import an incomplete or demonstration campaign as the real anthology.

## Activation status
The user confirms an existing ChatGPT schedule: Wednesdays around 08:00 Europe/London, 4 November 2026 through 6 January 2027, ten stories of 2,500–4,000 words. The handoff monitor checks the original Diagram reconstruction chat and this chat's outbox for completed outputs. Chat references may be inaccessible placeholders: delivery must report an actionable access gap rather than invent text or mark a story delivered. No second generation schedule is created. The source story text and metadata must be available before an atomic queue submission. Missing authorship or publication dates require user input; generation dates do not grant publication approval.


## Production register and concurrency (2026-10-28)
`manifest.json` is the authoritative story queue. It fixes all ten titles, stable filenames and states: planned → generating → draft. The draft state means staged in GitHub, NOT editorial approval or publication. Local AO3 pipeline approval and publication audit remain in the private local database.

A separate `integration/after_bells_queue.py` tool implements safe GitHub reservation using a unique random claim token and Git's fast-forward-only ref update. Concurrent claims conflict and retry; submissions require the matching claim token, a valid complete 2,000–5,000-word story and compatible JSON metadata. Both story files and the changed manifest are committed in one atomic ref update. Do NOT bypass this queue by updating manifest.json and a story file separately. Claims expire after two hours; an expired claim can be re-reserved, invalidating the original token. Failure can be safely released with its claim token; any content conflict requires manual reconciliation.

First authenticate using a fine-grained token with Contents: write for this repository. Never commit the token:
```sh
export GH_TOKEN=...                     # supply privately through your shell or secret manager
python integration/after_bells_queue.py claim
# Save the JSON claim_token securely and generate exactly the claimed numbered story.
python integration/after_bells_queue.py submit --sequence 1 --token "$CLAIM_TOKEN" --story /path/to/story-01.md --metadata /path/to/story-01.json
python integration/after_bells_queue.py validate
# On generation failure only:
python integration/after_bells_queue.py release --sequence 1 --token "$CLAIM_TOKEN"
```
See the existing import instructions above for ingesting staged story pairs into the private local AO3 pipeline. GitHub Actions validates the register and completed pairs; it does not generate or publish stories. The ChatGPT scheduled automation has been corrected to Wednesday mornings from 2026-11-04, ten runs, and instructed to consult the GitHub register. However **the ChatGPT automation → GitHub commit is not yet independently verified end-to-end**. It must not mark a story delivered unless the full draft and metadata were committed. A prior manual automation run produced Story One in a task chat, but the available task result was truncated; the full text has not been independently verified or imported. The queue intentionally leaves it planned.

Warning: this is a PUBLIC GitHub repository. All staged manuscripts are publicly visible, even while editorial approval is pending.
