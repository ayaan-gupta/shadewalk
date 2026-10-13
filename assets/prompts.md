# Image requests

8 images requested, 0 delivered.

These are build-time assets. Nothing in ShadeWalk generates images at run time, and map tiles are never generated: the base map is OpenStreetMap vector data and the shadow layer is drawn from the shade model.

Save each file at the path given. The loader in `web/src/assets.ts` matches files by their path without the extension, so `assets/generated/icons/tree.png` replaces `assets/interim/icons/tree.svg` on the next build, one file at a time. Until then the hand-written SVGs in `assets/interim` are used.

**Style bible:** flat vector, warm sunset palette against cool teal shade.

**Palette:** gold `#F6C56B`, orange `#F2994A`, coral `#EB6B4F`, rose `#C44D58`, dusk plum `#5B3A5E`, deep teal `#0E5C68`, teal `#1B7F8A`, light teal `#7FC4C1`, off-white `#FBF7F0`, cream `#FBEBD3`.

## SW-001 landing illustration

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A wide downtown street at sunset seen from slightly above. A low sun on the right throws long teal shadows from plum-coloured towers and two round-crowned trees across a cream street. One small walker, drawn as simple shapes, follows a white route line that stays inside the shadows; where the route crosses a sunlit gap it turns into coral dots. A coral pin marks the start on the right and a teal pin marks the end on the left. Keep the top fifth of the image as plain dusk sky.
- **Spec:** 2400x1440 px, 5:3, opaque, PNG
- **Save to:** `assets/generated/landing/hero.png`
- **Used for:** The illustration at the top of the first-run screen. Until it arrives the hand-drawn `assets/interim/landing/hero.svg` is shown.

## SW-002 onboarding icon: sun path

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: a dotted coral arc from left horizon to right horizon with three suns on it, small gold at the left, large orange at the top, small coral at the right, above a short teal ground line.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/sun-path.png`
- **Used for:** Onboarding step 'Shade moves with the sun'.

## SW-003 onboarding icon: tree

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: one street tree with a round deep-teal crown, a lighter teal highlight circle and a short plum trunk.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/tree.png`
- **Used for:** Onboarding step 'Trees count'.

## SW-004 onboarding icon: bus stop

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: a small bus shelter with a rose roof, plum posts and an orange bench, next to a pole with a round coral bus sign.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/bus-stop.png`
- **Used for:** Onboarding step 'Waiting counts too'.

## SW-005 onboarding icon: water fountain

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: a plum pedestal drinking fountain with a rose basin, a light-teal arc of water and one teal droplet.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/water-fountain.png`
- **Used for:** Onboarding step 'Water on the way' and the drinking water markers on the map.

## SW-006 onboarding icon: cooling center

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: a small plum civic building with a rose pitched roof, a gold door, two light-teal windows and a light-teal snowflake on the gable.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/cooling-center.png`
- **Used for:** Onboarding step 'Somewhere to cool down' and the public indoor place markers on the map.

## SW-007 onboarding icon: umbrella

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A single centred object on a cream #FBEBD3 disc that fills the canvas, with one teal #1B7F8A shadow shape falling to the lower right of the object. Readable at 48 px. The object: an open coral umbrella with one orange panel and a plum hooked handle, seen from the side.
- **Spec:** 512x512 px, 1:1, transparent outside the disc, PNG
- **Save to:** `assets/generated/icons/umbrella.png`
- **Used for:** Onboarding step 'When there is no shade to find'.

## SW-008 social share card template

- **Status:** requested (hand-drawn interim SVG in use)
- **Prompt:** Flat vector illustration, no gradients, no outlines, no texture, no text, no watermark. Warm sunset palette for everything the sun touches (gold #F6C56B, orange #F2994A, coral #EB6B4F, rose #C44D58, dusk plum #5B3A5E) against cool teal for shade (deep teal #0E5C68, teal #1B7F8A, light teal #7FC4C1). Off-white #FBF7F0 and cream #FBEBD3 for ground and backgrounds. Simple geometric shapes, generous negative space. A share card background. The left 60 percent is plain off-white #FBF7F0 and must stay empty, because the app prints the route numbers there. The right 40 percent is a sunset street scene cut off by a slightly slanted edge: banded dusk sky, a pale sun, three plum towers, one teal tree, and long teal shadows running to the bottom edge.
- **Spec:** 1200x630 px, 1.91:1, opaque, PNG
- **Save to:** `assets/generated/share/card-template.png`
- **Used for:** Background of the downloadable share card. The app draws the distance, minutes and shade numbers over the left side.
