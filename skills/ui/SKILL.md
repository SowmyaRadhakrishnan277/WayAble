# WayAble UI accessibility skill

Build calm, direct interfaces for wheelchair users and people with low vision. Accessibility is part of the component contract, not a later polish pass.

## Semantic structure and navigation
- Use native HTML controls, associated visible labels, one clear `h1` per page, logical heading order, and a skip link to the main content.
- Keep all functionality keyboard operable. Use buttons for actions and links for navigation. Preserve a visible focus indicator and logical focus order. Dialog-like menus must close with Escape and return focus to their trigger.
- Announce asynchronous results and errors using a polite live region; use `aria-busy` while loading. Move focus to the page heading after route navigation and to an error summary after failed form submission.
- Never make a map the sole representation of route information. Include an ordered text step list and accessible controls for any map interaction.

## Readability and input
- Use Atkinson Hyperlegible or a system sans-serif fallback. Keep body copy at 1rem minimum, line-height 1.5, and headings at 1.2 line-height. Text blocks should remain readable at 200% zoom and 320px viewport width.
- Make primary touch targets at least 44px (56px in low-vision mode). Do not communicate status through colour alone; pair every state with a text label and icon.
- Respect reduced-motion preferences. Avoid time-limited interactions and ensure text can reflow without clipping.

## Accessibility facts and status
- Preserve API values exactly. `unknown` is not confirmed, safe, or accessible. Render null facts as “Unknown”.
- Give evidence source and observed date alongside facts. Label fixture data as demo data and community/AI analysis as unverified community reporting.
- Never let an AI-generated interpretation remove a caution or upgrade a status.

## Contrast and visual states
- Use the product's named design tokens and ensure normal text/background pairs reach 4.5:1. Do not use the tactile yellow as text on white.
- Use a two-tone focus ring that stays visible across backgrounds:
  `:focus-visible { outline: 3px solid var(--ink); outline-offset: 2px; box-shadow: 0 0 0 6px var(--tactile); }`
- Avoid putting a max-width on `body`; constrain prose, forms, and step lists instead. Support default, dark, and high-contrast themes.
