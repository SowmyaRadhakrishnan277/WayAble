---
name: ui
description: Build or review web and mobile UI so it works for wheelchair users (motor/input accessibility, accessible-route data) and low-vision users (contrast, scaling, screen readers). Use this skill whenever the user is building, styling, or reviewing any front end, app screen, map, form, or component, or mentions accessibility, a11y, WCAG, wheelchair, low vision, screen reader, contrast, or inclusive design, even if they do not explicitly ask for accessibility. Apply it by default to every UI task.
---

# Accessible UI (wheelchair + low-vision users)

Apply these rules to all UI code you write or review. Do not wait to be asked. If a rule conflicts with a visual preference, accessibility wins. If a rule can't be met in the time available, say so in your summary instead of silently skipping it.

## 1. Always-on rules

### Structure and semantics
- Use semantic HTML first: `header`, `nav`, `main`, `section`, `button`, `a`, `label`, `ul/li`, real headings in order (one `h1`, no skipped levels).
- Use `<button>` for actions and `<a>` for navigation. Never make a clickable `div`.
- Every form field has a visible `<label>`. Placeholders are not labels.
- Every meaningful image has useful `alt` text. Decorative images use `alt=""`.
- Set the page `lang` and a descriptive `<title>`. Add a "Skip to main content" link.
- Use ARIA only when native HTML can't do the job. Wrong ARIA is worse than none.

### Low vision: colour, type, layout
- Contrast: body text at least 4.5:1; large text (18px+ or 14px+ bold) and UI components/icons at least 3:1.
- Never convey meaning by colour alone. Pair colour with an icon, text, or pattern (e.g. status = icon + label + colour).
- Font sizes in `rem`, base at least 16px. No fixed-pixel text containers.
- The layout must work at 200% zoom and 320px width with no horizontal scroll, clipped text, or overlapping elements.
- Font: clear sans-serif (system font stack or Atkinson Hyperlegible / Inter). Line height about 1.5, line length 45-75 characters, left-aligned, avoid light weights and all-caps paragraphs.
- Respect user settings via CSS: `prefers-color-scheme`, `prefers-contrast`, `prefers-reduced-motion`. Provide dark and high-contrast themes using CSS variables.
- Visible focus indicator on every interactive element (at least 2px, 3:1 contrast). Never `outline: none` without a replacement.
- Don't disable zoom (`user-scalable=no`, `maximum-scale`).

### Wheelchair / motor accessibility
- Touch targets at least 44x44px with at least 8px spacing. Keep primary actions in easy thumb reach on mobile (bottom area), since the phone may be one-handed or chair-mounted.
- Everything works with keyboard, voice, and switch control: logical tab order, no keyboard traps, no hover-only or drag-only interactions, no precision gestures. Offer a button alternative to any swipe/drag/pinch.
- No tight timeouts. Let users pause, extend, or disable anything timed.
- Forgiving interaction: confirm destructive actions, support undo, keep forms short, preserve entered data on error.
- Prefer clear error messages that say what went wrong and how to fix it, announced via `aria-live`.

### Maps, canvas, charts (high-risk areas)
- `<canvas>`, SVG charts, and map widgets are invisible to screen readers by default. Always provide a text equivalent: a route as an ordered step list, a chart as a data table or text summary.
- Make map controls keyboard-operable with large targets. Don't require pan/drag to use the map.

## 2. If the app handles accessibility or route data

- Store specifics, not a boolean "accessible" flag: step-free entrance, ramp gradient, door width, lift status, kerb drops, surface, last-verified date.
- Let users set their own profile (e.g. manual or powered chair, max slope, min width) and filter results by it.
- Show data freshness and confidence. Never show "unknown" as "accessible". Use a distinct "unverified" state with icon and text.
- Show live disruptions (broken lifts, blocked paths) prominently, and let users report corrections.
- For routes, state the trade-off in text (e.g. "+6 min, fully step-free").

## 3. Voice and screen-reader support
- Offer voice input/output where it fits the product. It also helps hands-busy and low-vision users.
- Announce dynamic changes with `aria-live="polite"` (use `assertive` only for urgent alerts). Move focus sensibly after navigation or modal open, and return it on close.

## 4. Before you say you're done

Run what the environment allows, and report results honestly:
1. Check contrast of the actual colour tokens (WebAIM checker or a script).
2. Keyboard-only pass: Tab through every control, confirm focus is visible and order is logical.
3. Zoom to 200% and resize to 320px wide.
4. Run an automated check if available (axe, Lighthouse accessibility, eslint-plugin-jsx-a11y).
5. List anything not verified (e.g. "not tested with a real screen reader").

Automated tools catch only a fraction of problems. Never claim the app "is WCAG compliant". Say which checks passed and which were not done.

## 5. Fast path (short on time)

If time is very limited, do these in order:
1. Semantic HTML + labelled form fields.
2. Accessible colour tokens (contrast verified) and `rem` font sizes.
3. Large touch targets + visible focus.
4. Text alternative for any map/canvas.
5. Honest "unverified/unknown" labelling for data.
6. One screen-reader or voice flow that works end to end.

## 6. Default CSS starting point

```css
:root {
  --bg: #ffffff; --fg: #1a1a1a; --accent: #0b5cad; --focus: #ffbf47;
  --font: "Atkinson Hyperlegible", system-ui, -apple-system, "Segoe UI", sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root { --bg: #121212; --fg: #f2f2f2; --accent: #7ab7ff; }
}
@media (prefers-contrast: more) {
  :root { --fg: #000; --bg: #fff; --accent: #003a75; }
}
html { font-size: 100%; }
body { background: var(--bg); color: var(--fg); font: 1rem/1.5 var(--font); max-width: 70ch; }
:focus-visible { outline: 3px solid var(--focus); outline-offset: 2px; }
button, a.btn, input, select { min-height: 44px; min-width: 44px; }
@media (prefers-reduced-motion: reduce) {
  * { animation: none !important; transition: none !important; }
}
```
(Verify the colour pairs against the 4.5:1 rule if you change them.)
