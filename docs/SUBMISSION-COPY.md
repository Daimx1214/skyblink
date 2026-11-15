# Space Apps project page, FINAL copy (Team Sohan Halwa, SkyBlink)
# Form structure verified on the live Edit Project form, Nov 15, 2026.
# Summary field limit: 1500 characters. Nothing here uses em dashes.

**Project Name:** SkyBlink

**Summary (field limit 1500 characters):**
SkyBlink is a public web tool that shows how a patch of sky changes over
time in real NASA SPHEREx survey images. It aligns SPHEREx observations of
the same field taken months apart (Data Release 1 and Quick Release 3, one
uniformly processed set) on a shared north-up grid with one brightness
stretch, and blinks them: moving objects jump, variable stars pulse. The
five targets named in the challenge (Barnard's Star, Epsilon Indi B, WISE
0855, RW Aurigae, R Draconis) are pre-loaded with blink explorers, Gaia DR3
and WISE overlays, per-frame quality data, and a spectrum assembled from
individual exposures (14 to 74 wavelength channels per target). Pre-loaded
targets open instantly; a live search for new fields is available and may
take about a minute on first render. Guided Case Files track interstellar
comet 3I/ATLAS across two visits and present a measured proper-motion check
on Barnard's Star. The method was validated with 540 synthetic movers
injected into real image pairs. No account is needed and nothing is
tracked.

**Project Demonstration (link field):**
https://drive.google.com/file/d/15Kzl2TC1TY-ssvGV4cXGv0QP_1gZgAI_/view?usp=drivesdk

**Project (link field):**
https://daimx1214.github.io/skyblink/

**Project Details (rich text, no printed limit):**

SkyBlink is a public web tool that shows how a patch of sky changes over
time in real NASA SPHEREx survey images. You enter coordinates, or pick one
of the pre-loaded targets, and SkyBlink lines up SPHEREx observations of
that field taken months apart on a shared north-up grid with one shared
brightness stretch, then blinks them. Moving objects jump between frames.
Variable stars pulse. Anything that still looks like a discovery is a
candidate, not a conclusion: candidates are vetted with the Two-Epoch
Check, a vetting method we document and apply in our validation (Methods
page and Case File 2).

Data and releases. All imagery is SPHEREx Level-2 data from the IRSA
archive: Data Release 1 and Quick Release 3, one uniformly processed set.
The live backend (https://skyblink-lyart.vercel.app) resolves names
through SIMBAD and Sesame and renders new fields on demand; a first render
can take about a minute, and it depends on the IRSA archive service being
up. The five pre-loaded targets below are served from a prepared cache and
open instantly.

The five challenge targets. Barnard's Star, Epsilon Indi B, WISE 0855, RW
Aurigae and R Draconis each have a dossier page with a blink explorer
(Blink, Side-by-side and Difference views), an ESA Gaia DR3 overlay with
proper motions propagated to each frame's date, a WISE (AllWISE) overlay,
the clean-pixel percentage and wavelength band of every frame, a
detector-band flux chart, and a one-degree context render made from a real
survey exposure. The SPHEREx all-sky spectral cube is linked in Aladin
Lite from every dossier. Every view carries its coordinates in the URL,
and the field of view can be set to 3 or 5 arcminutes for live renders.

Spectra. Each dossier also shows a spectrum at the target's position,
assembled beforehand from individual Level-2 exposures and shipped with
the site: Barnard's Star has 74 distinct wavelength channels from 91
exposures (0.80 to 4.89 µm), R Draconis 25 channels, RW Aurigae and WISE
0855 24 each, and Epsilon Indi B 14. Each point's wavelength comes from
that frame's own spectral WCS at the target's pixel, and its flux from
aperture photometry (radius 2 pixels, annulus background). These are
photometric points from aperture photometry, not a calibrated spectrum;
faint targets are near the noise, and the zodiacal light model in the
archive products is not subtracted from Level-2 data.

Case Files. Three guided cases use real data end to end. Case 1 follows
interstellar comet 3I/ATLAS between its 13 August and 14 December 2025
visits, two positions 79.2 degrees apart. Case 2 documents the Two-Epoch
Check. Case 3 measures Barnard's Star: centroided in all five epochs, its
positions agree with Gaia's proper-motion prediction to within 1.3 to 7.4
arcseconds. The two largest offsets come from the two frames centred about
a degree away from the star; with five frames, detector, position and band
effects cannot be separated, so the pattern is reported as a hypothesis,
not a finding. The case data can be downloaded as CSV.

Validation. We injected 540 synthetic moving objects (Gaussian sources)
into real epoch pairs and ran the site's own difference test on them.
Recovery was 100 percent at signal levels of 15 sigma and above, and 97
to 98 percent at 8 sigma for shifts of 2 pixels or more. A control run on
uninjected pairs found 439 raw residual peaks at 6 sigma and above, which
is the measured reason a candidate still has to pass the Two-Epoch Check.
Injected sources are idealised Gaussians tested with our own rule; this
measures the sensitivity of the difference test, not performance on real
movers.

Access and maintenance. The explorer is fully keyboard-operable, the
difference palette is colour-blind-safe, the site ships in dark and light
themes, and it runs on phones with no account and no tracking. A weekly
job checks the archive for new epochs of the five targets and refreshes
the cache when the survey revisits them. The site is a static front end
with a FastAPI backend; the full source is at
https://github.com/Daimx1214/skyblink

AI use. We used AI assistants for research, planning, drafting code and
writing, under the team's direction. All data shown are real archive
products; nothing is simulated.

Team Sohan Halwa: Daim Ali and Ali Abdullah, Universal Event.

**Use of Super Intelligence (SI) (multi-select dropdown):**
Select the option that states AI tools were used (wording per the form's
own options at fill time). The AI use statement is also in Project Details.

**NASA Data (link list, add one row per link):**
- Text: SPHEREx archive at IRSA (NASA/JPL-Caltech) | URL: https://irsa.ipac.caltech.edu/Missions/spherex.html
- Text: SPHEREx DR1 images, DOI 10.26131/IRSA678 | URL: https://doi.org/10.26131/IRSA678
- Text: SPHEREx DR1 spectral cube, DOI 10.26131/IRSA679 | URL: https://doi.org/10.26131/IRSA679
- Text: SPHEREx QR3, DOI 10.26131/IRSA662 | URL: https://doi.org/10.26131/IRSA662

**Space Agency Partner & Other Data (link list):**
- Text: ESA Gaia DR3 | URL: https://www.cosmos.esa.int/web/gaia/dr3
- Text: SIMBAD, CDS | URL: https://simbad.cds.unistra.fr/simbad/
- Text: Aladin Lite, CDS | URL: https://aladin.cds.unistra.fr/AladinLite/
- Text: SkyBoT, IMCCE | URL: https://ssp.imcce.fr/webservices/skybot/

**Checkboxes:** Agree to Terms of Participation; Confirm All Work is Original.
