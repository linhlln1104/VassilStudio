# VassilStudio Studio Design Direction

## Reference

Primary reference: [Dub - frosted link dashboard on rice paper](https://styles.refero.design/style/b0d80806-b724-4ed1-a1d1-074edd3c9bc9)

VassilStudio adapts the reference for a dense local production tool. It keeps the near-white canvas,
hairline structure, compact Inter typography, and one blue interaction accent. It does not copy the
marketing layout, oversized type, 12-16px product cards, or decorative floating elements.

## Product Character

- Quiet, technical, and trustworthy enough for repeated audio work.
- Product state and output stay more prominent than decoration.
- The multicolor VassilStudio logo is the brand expression; controls use one blue accent.
- Surfaces are separated by 1px borders and small tone changes, not decorative shadows.
- Information density is compact on desktop and comfortably touchable on mobile.

## Foundation

| Role | Value |
| --- | --- |
| Workspace canvas | `#f7f7f8` |
| Primary surface | `#ffffff` |
| Secondary surface | `#f5f5f5` |
| Structural border | `#e5e5e5` |
| Strong border | `#d4d4d4` |
| Primary text | `#171717` |
| Secondary text | `#525252` |
| Muted text | `#737373` |
| Interaction accent | `#2563eb` |
| Primary action | `#1e40af` |
| Success | `#15803d` on `#f0fdf4` |
| Warning | `#b45309` on `#fffbeb` |
| Destructive | `#b91c1c` on `#fef2f2` |

Inter or the system sans stack is used throughout the application. Workspace titles are 14-16px,
panel titles are 14px, body copy is 13-14px, and metadata is 11-12px. Letter spacing stays at zero.

Use a 4px spacing base. Standard workflow gaps are 8, 12, 16, 20, and 24px. Inputs use a 6px
radius; buttons and cards use at most 8px; badges and status indicators may use a full pill radius.

## Interaction Rules

- Use one filled primary action per panel. Secondary actions are white or ghost controls.
- Use blue for selection, focus, links, and primary progress only.
- Use semantic green, amber, and red only for state communication.
- Do not use gradients, colored card edges, or multicolor avatars in the application UI.
- Do not use shadows on ordinary cards. Reserve a restrained shadow for drawers, dialogs, and menus.
- Keep empty, loading, error, and success states inside the workflow area they belong to.
- Navigation remains a 236px desktop rail and a modal drawer below the desktop breakpoint.
