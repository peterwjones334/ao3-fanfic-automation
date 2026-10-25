# GitHub Setup and Usage

## Repository
https://github.com/peterwjones334/ao3-fanfic-automation

## Prerequisites
- GitHub account (you are authenticated as peterwjones334)
- Git installed locally if you want to clone
- Access to an AI that can follow the system prompt (Grok, Claude, GPT, etc.)

## Clone locally
```bash
git clone https://github.com/peterwjones334/ao3-fanfic-automation.git
cd ao3-fanfic-automation
```

## Generate a new short
1. Copy the contents of `SYSTEM_PROMPT.md`.
2. Append a request, for example:
   ```
   Fandom: Harry Potter
   Ship: Sirius Black/Remus Lupin
   Tropes: Slow Burn, Hurt/Comfort, Found Family
   Tone: quiet, post-war
   ```
3. Paste the full prompt into your AI.
4. Save the output as a new markdown file under `/samples`.
5. Commit and push:
   ```bash
git add samples/your-new-file.md
git commit -m "Add Wolfstar sample"
git push
```

## Automated push (if using a bot or script)
Use the GitHub API or `gh` CLI with a personal access token that has `contents:write` scope on this repository. The same `push_files` pattern used to create this repo can be repeated.

## File conventions
- `samples/*.md` — one short per file
- Filename: `fandom_ship_trope.md` (lowercase, underscores)
- Each file contains: prose, then SUMMARY, then TAGS

## Expanding
Add new fandoms or tropes by editing the request block only. The system prompt stays fixed.