# AO3 Fanfic Automation

Franchise-style generator for original character-driven fanfiction (1200–3000 words) in high-volume AO3 spaces.

## Focus
- Large or rising fandoms: Harry Potter, My Hero Academia, Stranger Things, Haikyuu!!, 9-1-1, Heated Rivalry, etc.
- Heavy on M/M ships.
- Stacked tropes: slow burn, angst + payoff, hurt/comfort, AU, found family.

## Output format
After the prose, each file ends with:
```
FANDOM: [name]
CATEGORY: [M/M | F/M | Gen | Multi | Other]
SUMMARY: one or two sentences, hook first.
TAGS: comma-separated list
```

## Usage
Feed the system prompt in `SYSTEM_PROMPT.md` to an AI bot with fandom, ship, and tropes.

An hourly automation is configured to generate and push new stories automatically.

Samples are in `/samples`.

All stories are original; no canon text is reproduced.