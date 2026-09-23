# Design reference

Charlotte’s visual system follows the official Finance and Operations site,
[fo.unc.edu](https://fo.unc.edu/), and UNC website rules on
[identity.unc.edu/content/websites](https://identity.unc.edu/content/websites/).

A local scrape of public `fo.unc.edu` pages (HTML, Heelium CSS, images) lives in
the gitignored `.design-reference/` folder. Re-run it with:

```bash
python3 .design-reference/scrape.py
```

Use that folder as a visual reference only. Rebuild with our own components,
tokens in `frontend/app/globals.css`, and the signatures in `frontend/app/logos/`.
Do not copy fo.unc.edu photography, copy, or CSS into the app.

## Landing contrast ledger (WCAG 2.2 AA)

Measured for the shipped light landing tokens. Floors: 4.5:1 for text under 24px (3:1 at or above that, or 19px bold); 3:1 for UI / focus.

| Pair | Use | Ratio | Floor |
| --- | --- | --- | --- |
| `#13294B` on `#FFFFFF` | Masthead title, navy text | 14.5:1 | 4.5:1 |
| `#FFFFFF` on `#13294B` | Nav, footer, feature cards, About, hero-aside plate | 14.5:1 | 4.5:1 |
| `#FFFFFF` on `#2C5080` | Button hover / Bolin fill | 8.1:1 | 4.5:1 |
| `#151515` on `#FFFFFF` | Body | 17.4:1 | 4.5:1 |
| `#007FAE` on `#FFFFFF` | Inline / more-menu links | 4.5:1 | 4.5:1 |
| `#13294B` on `#4B9CD3` | Hero copy; utility-bar campus name and links (Georgia 16px) | 4.8:1 | 4.5:1 |
| `#FFFFFF` on `#4B9CD3` | Utility-bar interlocking NC; destination icons; Sign in (24px/700, large text) | 3.0:1 | 3:1 (1.4.3 large / 1.4.11) |
| `#13294B` outline on `#FFFFFF` / `#EDF5FB` / `#4B9CD3` | `:focus-visible` | ≥3:1 | 3:1 |

Dark-theme tokens exist for other pages and are not a shipped landing mode.
