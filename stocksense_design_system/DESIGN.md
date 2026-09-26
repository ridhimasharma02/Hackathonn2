---
name: StockSense Design System
colors:
  surface: '#f8f9fb'
  surface-dim: '#d9dadc'
  surface-bright: '#f8f9fb'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f3f4f6'
  surface-container: '#edeef0'
  surface-container-high: '#e7e8ea'
  surface-container-highest: '#e1e2e4'
  on-surface: '#191c1e'
  on-surface-variant: '#44474f'
  inverse-surface: '#2e3132'
  inverse-on-surface: '#f0f1f3'
  outline: '#747780'
  outline-variant: '#c4c6d0'
  surface-tint: '#445e8d'
  primary: '#01244f'
  on-primary: '#ffffff'
  primary-container: '#1e3a66'
  on-primary-container: '#8ba5d7'
  inverse-primary: '#adc7fb'
  secondary: '#525e7b'
  on-secondary: '#ffffff'
  secondary-container: '#d0dcff'
  on-secondary-container: '#54617e'
  tertiary: '#001c66'
  on-tertiary: '#ffffff'
  tertiary-container: '#002e98'
  on-tertiary-container: '#869fff'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#d7e3ff'
  primary-fixed-dim: '#adc7fb'
  on-primary-fixed: '#001b3f'
  on-primary-fixed-variant: '#2c4773'
  secondary-fixed: '#d8e2ff'
  secondary-fixed-dim: '#bac6e8'
  on-secondary-fixed: '#0e1b35'
  on-secondary-fixed-variant: '#3a4663'
  tertiary-fixed: '#dce1ff'
  tertiary-fixed-dim: '#b7c4ff'
  on-tertiary-fixed: '#001551'
  on-tertiary-fixed-variant: '#0039b5'
  background: '#f8f9fb'
  on-background: '#191c1e'
  surface-variant: '#e1e2e4'
typography:
  headline-lg:
    fontFamily: IBM Plex Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: IBM Plex Sans
    fontSize: 15px
    fontWeight: '600'
    lineHeight: 20px
    letterSpacing: -0.005em
  headline-sm:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
  table-header:
    fontFamily: IBM Plex Sans
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.04em
  body-default:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 18px
  body-medium:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
  meta-default:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  meta-medium:
    fontFamily: IBM Plex Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
  code-default:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
  code-medium:
    fontFamily: JetBrains Mono
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.375rem
  space-md: 0.5rem
  space-lg: 0.75rem
  space-xl: 1rem
---

## Brand & Style

This design system is engineered for mission-critical enterprise inventory, supply chain, and warehouse operations. It prioritizes operational calm, scanability, and precision under high-throughput conditions. 

Borrowing from the rigorous information hierarchy of SAP Fiori and the understated ergonomic polish of modern productivity platforms, the design philosophy rejects decorative skeuomorphism, saturated gradients, and excessive whitespace in favor of:
- **Maximum Information Density:** Dense layouts designed to display dense data matrices, batch lots, bin locations, and dispatch logs without horizontal pagination sprawl.
- **Cognitive Ergonomics:** Low visual noise through subtle hairline borders, non-competing surface tiers, and deliberate status coding.
- **Industrial Precision:** Strict typographic rhythm and monospaced anchoring for identifiers (SKUs, serials, purchase orders, bin locators).

## Colors

The palette leverages a technical navy foundation paired with clinical light-gray surfaces, reserving high-chroma tones strictly for operational state changes and exceptions.

### Core Canvas & Structure
- **Primary Navy (`#1E3A66`):** Command actions, active primary selections, focus rings, and high-level visual anchors.
- **Sidebar Navy (`#13203A`):** Deep, distraction-free shell frame defining spatial boundary and site-wide navigation.
- **Page Background (`#F4F5F7`):** Neutral canvas providing clear contrast against data surfaces.
- **Surfaces (`#FFFFFF`):** Data tables, cards, inspection trays, and modal sheets.
- **Borders (`#E1E4E9`):** 1px structural partitions, grid cell lines, and containment edges.

### Typography Hierarchy Colors
- **Text Primary (`#1B2230`):** Critical data values, titles, values, and table body records.
- **Text Secondary (`#4D5667`):** Field labels, descriptive parameters, secondary attributes.
- **Text Muted (`#7C8595`):** Table column headers, inactive states, placeholder tokens, breadcrumb delimiters.

### Operational State Tokens
Semantic colors are never used decoratively; they signify urgency, flow rate, and stock states:
- **Success / In Stock / Complete:** `#15803D` text on `#DCFCE7` surface.
- **Warning / Low Stock / Waiting:** `#B45309` text on `#FEF3C7` surface.
- **Danger / Out of Stock / Cancelled:** `#B91C1C` text on `#FEE2E2` surface.
- **Info / Active Operation / Picked:** `#1D4ED8` text on `#DBEAFE` surface.

## Typography

The typographic scale is intentionally condensed and calibrated for high-density tabular rendering. It avoids oversized display scales to keep high volumes of information above the fold.

- **Primary Typeface (`IBM Plex Sans`):** Selected for its industrial heritage, distinct glyph forms (e.g., lowercase `l` vs uppercase `I`), and clarity at sizes between 11px and 13px.
- **Monospaced Family (`JetBrains Mono` or `IBM Plex Mono`):** Applied to all non-prose alphanumeric identifiers: Stock Keeping Units (SKUs), batch tracking hashes, serial numbers, pallet codes, and currency/quantity values that require precise vertical scanning alignment.
- **Case Rule:** Table headers enforce uppercase transform (`text-transform: uppercase`) paired with letter-spacing of `0.04em` to establish visual hierarchy without heavy weight.

## Layout & Spacing

The layout model uses an enterprise-grade fixed/fluid hybrid structure:
- **Left Navigation Frame:** Fixed 240px persistent column (`#13203A`), collapsible to a 56px icon rail.
- **Application Canvas:** Fluid 12-column grid stretching across the operational viewport with a strict maximum horizontal margin of 16px (`1rem`).
- **Vertical Rhythm:** 4px baseline sub-grid (`0.25rem`). Component heights are locked to 32px standard control tiers (inputs, standard buttons, dropdown triggers) and 24px micro-tiers (inline filter pills, row action badges).
- **Responsive Adaptations:**
  - **Desktop (>= 1280px):** Multi-pane split views (e.g., Master inventory table on the left 7 columns, live Stock Inspection/Lot Ledger on the right 5 columns).
  - **Tablet / Industrial Terminals (768px - 1279px):** Split pane collapses to drawer overlay; table cells retain density with horizontal scroll on secondary metadata.
  - **Mobile / Handheld Scanners (< 768px):** Single-column layout, bottom sticky action trays (primary scan triggers), and expandable card rows in place of complex multi-column grids.

## Elevation & Depth

To maintain visual clarity, this design system rejects blurry dropshadows, multi-stop gradients, and glassmorphic blurs. Depth is produced purely through surface borders and tonal division.

- **Surface Layering:** 
  - Base: `#F4F5F7`
  - Container / Workspace: `#FFFFFF`
  - Sidebar Shell: `#13203A`
- **Border Architecture:** All panels, data cells, headers, and form inputs are separated by single-pixel hairline borders (`#E1E4E9`).
- **Transient Elements (Flyouts, Menus, Modals):**
  - Dropdown Menus & Popovers: Border `#E1E4E9` paired with an ultra-subtle ambient shadow: `0 2px 4px rgba(19, 32, 58, 0.06), 0 4px 12px rgba(19, 32, 58, 0.04)`.
  - Global Modals: Bounded by a 1px border and a semi-opaque backdrop curtain (`rgba(19, 32, 58, 0.45)`).

## Shapes

The design system enforces a compact shape language to preserve pixel space and fit tabular data grids:

- **Interactive Controls (Buttons, Form Inputs, Badges, Tabs):** 4px border radius (`rounded-sm`).
- **Structural Containers (Data Tables, Cards, Panels, Modal Windows):** 6px border radius (`rounded-md`).
- **Pill Shapes:** Strictly reserved for circular operational status dots (6px × 6px) inside badges. No fully-rounded/capsule buttons are permitted.

## Components

### Buttons
- **Standard Button Height:** 32px; `space-sm` vertical, `space-md` horizontal padding. Font: 13px weight 500.
- **Primary:** Background `#1E3A66`, text `#FFFFFF`, border none. Hover: `#162C4E`. Active: `#102038`.
- **Secondary / Default:** Background `#FFFFFF`, text `#1B2230`, border 1px solid `#E1E4E9`. Hover: `#F4F5F7`.
- **Destructive:** Background `#FFFFFF`, text `#B91C1C`, border 1px solid `#FEE2E2`. Hover: `#FEE2E2`.
- **Icon Buttons:** 32px × 32px square; Lucide outline icons sized at 15px with 1.5px stroke width.

### Data Tables
- **Row Heights:** 36px (ultra-dense) to 40px (standard).
- **Header Row:** 32px height, background `#F4F5F7`, bottom border 1px solid `#E1E4E9`. Text: 11px uppercase, tracking 0.04em, `#7C8595`.
- **Cell Content:** 13px `#1B2230`. Monospaced font (`JetBrains Mono`) for quantities, SKUs, and locations.
- **Row States:** Hover: background `#F9FAFB`. Selected: background `#EFF6FF` with `#1E3A66` active left border indicator (2px).

### Status Badges
- **Height & Padding:** 20px height, 6px horizontal padding, 4px border-radius.
- **Layout:** Flex row with a 6px circular dot indicator followed by an 11px medium-weight label.
- **Variants:**
  - *In Stock / Done:* Surface `#DCFCE7`, text `#15803D`, dot `#15803D`.
  - *Low Stock / Waiting:* Surface `#FEF3C7`, text `#B45309`, dot `#B45309`.
  - *Out of Stock / Danger:* Surface `#FEE2E2`, text `#B91C1C`, dot `#B91C1C`.
  - *Active / Picked:* Surface `#DBEAFE`, text `#1D4ED8`, dot `#1D4ED8`.

### Form Controls (Inputs & Selects)
- **Input Height:** 32px, text 13px. Background `#FFFFFF`, border 1px solid `#E1E4E9`.
- **Focus State:** Border 1px solid `#1E3A66`, box-shadow `0 0 0 1px #1E3A66`.
- **Checkboxes & Radios:** 14px × 14px square/round with 1px border `#E1E4E9`. Checked state: background `#1E3A66` with white checkmark.

### Cards & Panels
- **Container Structure:** Flat `#FFFFFF` fill, 1px perimeter border `#E1E4E9`, 6px border radius.
- **Card Header:** 40px height, border-bottom 1px solid `#E1E4E9`, containing a 13px semibold title and right-aligned compact toolbar controls.

### Barcode & Bin Locators (Domain-Specific)
- **Bin Badge:** Fixed-width monospaced element (`#F4F5F7` background, 1px border `#E1E4E9`, text `#1B2230`) separating aisle, rack, shelf, and bin with subtle dividers (`AISLE-04 · RCK-12 · LVL-02`).