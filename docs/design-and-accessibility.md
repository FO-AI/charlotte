# Design and accessibility

**The bar is WCAG 2.2 Level AA, not 2.0.** UNC-Chapel Hill's Standard on Accessibility of
Digital Content, Resources, and Technology sets the University's compliance level at WCAG
2.2 Level AA, and the Digital Accessibility Office holds that line deliberately above the
2.1 AA floor that ADA Title II requires. 2.2 AA contains all of 2.0 A/AA, so building to 2.2
satisfies any 2.0 requirement and dropping below it is a regression, not a shortcut. Treat
each criterion as a build constraint rather than review-time cleanup: this portal is one
text input, one streaming transcript, and a handful of buttons. Nothing here is hard to make
accessible, and nothing here gets an exemption.

**Carolina Blue is a surface and border color, not a text-on-white color.** The UNC primary
palette is Carolina Blue `#4B9CD3`, Navy `#13294B`, and white, with Carolina Blue dominant.
Secondary colors — Bolin Creek `#2C5080`, Fordham Fountain `#B7D7ED`, Cloud `#EDF5FB`, Old
Well Basin `#5B6670`, black — complement it, are used sparingly, and never replace a primary.
`#4B9CD3` measures 3.0:1 against white, which clears 1.4.3 for large text only (≥24px, or
≥19px bold) and 1.4.11 for UI component boundaries. Where white body text sits on a filled
brand surface, reach for Bolin Creek `#2C5080` (8.1:1) or Navy `#13294B` (14.5:1) instead.
Link text uses UNC's digital-link blue `#007FAE` (4.5:1 on white, and only on white).

**Contrast is a property of the token pair, in both themes.** Every foreground/background
pair in `web/src/app.css` holds 4.5:1 for text under 24px (3:1 at or above that, or at 19px
bold), and 3:1 for focus rings, meaningful borders, the `.connection-dot` states, and icon
glyphs. Check the `body.dark-theme` block as well as `:root`; a pair that passes in light can
fail in dark. Never encode state in hue alone (1.4.1) — the connection pill pairs its dot
color with a text label, and anything new follows that pattern.

**A department accent is a contrast decision, not a branding one.** Accents are painted as
button fills under white text, so an accent that reads well as a brand color can still fail
1.4.3. `api/departments/theme.py` validates theme values as CSS syntax and cannot measure
contrast, so every new or changed accent in `api/config.yaml` is measured by hand against
white, `--color-surface`, and `--color-page-bg` before it lands. When a brand color is too
light to carry white text, keep it as the accent and give filled controls a darker companion
token rather than overriding one component at a time.

**Focus must stay visible, including in forced-colors mode.** Never pair `focus:outline-none`
with a `box-shadow`-only ring: shadows are not painted under Windows High Contrast, so the
indicator disappears entirely. Use `outline` with `outline-offset`, at 3:1 or better against
both the control and the surface behind it. Everything actionable is reachable and operable
by keyboard in DOM order; a modal traps focus while open and returns it to the control that
opened it (2.1.2, 2.4.3). Sticky chrome — the follow-up panel, the composer — must not cover
the focused element (2.4.11), and hit targets stay at least 24×24 CSS px, theme toggle,
citation superscripts, and chips included (2.5.8).

**The transcript is the screen-reader surface.** The live region over `.chat-messages`
announces a finished answer, not every streamed token, and the status region stays separate
from the message region so a connection change never interrupts an answer. A control whose
label is an icon or a glyph carries an `aria-label`; `title` is not an accessible name.
Headings step down without skipping — the header `h1` is the portal name, welcome and
unavailable panels use `h2`. Status and error strings in `web/lib/chat/copy.ts` are what a
screen-reader user hears, so each one is a sentence someone can act on.

**Respect reduced motion.** Anything that repeats indefinitely — the streaming cursor, the
typing indicator — falls under 2.2.2, which requires blinking past five seconds to be
stoppable. Gate `blink`, `pulse`, `fadeIn`, and `highlightFade` behind
`@media (prefers-reduced-motion: reduce)`, collapsing to a static end state rather than a
shorter animation. Auto-scroll on a new message stops once the user has scrolled away.

**Structure, zoom, and language.** Keep `<html lang="en">` in `web/app/layout.tsx`, and set
`lang` on any copy in another language. The shell carries a skip link to the transcript and
the composer, plus real landmarks (`header`, `main`, `aside`). The layout survives 200% zoom
and a 320 CSS px viewport with no horizontal scrolling and no loss of function (1.4.10), and
1.4.12 text-spacing overrides must not clip message bubbles. The page `<title>` names the
department, not just "Benny" (2.4.2).

**Typography is self-hosted or system.** UNC's brand fonts are Open Sans, with Source Serif
where a formal tone is wanted; Arial and Georgia are the sanctioned substitutes, which the
current `--font-sans` stack already satisfies. Moving to Open Sans means self-hosting it
through `next/font/local` — the CSP declares no `font-src`, so it falls back to
`default-src 'self'` and any `fonts.gstatic.com` request is blocked. Do not add a font CDN to
the policy. Body text stays at 16px or larger, and nothing drops below 12px.

**Finance and Operations signatures live in `frontend/app/logos/` and are served from
`/logos/`.** UNC website rules put the typeset unit name in the header (Open Sans, not a
logo) and a two-color division signature in the footer at no more than 30% of the content
width. Single-color marks are not used on websites. Never recolor an SVG in CSS. Give the
footer image an accessible name such as "UNC Finance and Operations". Decorative repeats
get `alt=""` / `aria-hidden="true"`.

The local visual reference for this chrome is the official F&O site, scraped into the
gitignored `.design-reference/` folder (`fo.unc.edu`). Do not copy that site's HTML,
photography, or CSS into the app.

| File | Fills | Use on |
| --- | --- | --- |
| `Finance_and_Operations_Signature_CarolinaBlue_Navy_rgb_v.svg` | Carolina Blue `#4B9CD3` + Navy `#13294B` | Default light surfaces (`--color-page-bg`, white, Cloud) |
| `Finance_and_Operations_Signature_Black_rgb_v.svg` | Black (default fill) | Light surfaces when a one-color mark is required (print, forced-colors) |
| `Finance_and_Operations_Signature_CarolinaBlue_rgb_v.svg` | Carolina Blue `#4B9CD3` | Navy or other dark brand surfaces only — 3.0:1 on white, so not a light-theme header mark |
| `Finance_and_Operations_Signature_White_rgb_v.svg` | White | Navy, Bolin Creek, or other dark fills |
| `Finance_and_Operations_Signature_White_Navy_rgb_v.svg` | White + Navy `#13294B` | Carolina Blue or mid-blue fills |
| `Finance_and_Operations_Signature_CarolinaBlue_White_rgb_v.svg` | White + Carolina Blue `#4B9CD3` | Navy fills when the two-color mark is wanted |
| `Finance_and_Operations_Signature_CarolinaBlue_White_rgb_h.png` | White + Carolina Blue `#4B9CD3` | Navy fills — horizontal lockup (wordmark beside the NC) |

Serve the files from `/logos/...` (or import them). Do not add a font or image CDN to the
CSP; these SVGs stay on `self`.
