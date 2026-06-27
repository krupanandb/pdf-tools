# Screenshots

Drop your PNG screenshots into this folder. The main README displays these two:

| Filename | What to capture |
|----------|-----------------|
| `home.png` | The home page showing all the tool cards |
| `clean-scan.png` | A Clean Scan (or any tool) result — ideally a before/after |

## How to take a screenshot on Windows

1. Press **Win + Shift + S** → drag to select the area → it copies to clipboard.
2. Paste into **Paint** (Ctrl+V) → **Save As → PNG** → name it `home.png` or `clean-scan.png`.
3. Save it into this `screenshots/` folder.

Then publish:

```bash
git add screenshots/
git commit -m "Add screenshots"
git push
```

The images will appear on the repo's front page automatically.

> Tip: keep images under ~1 MB and around 1200px wide so the README loads fast.
