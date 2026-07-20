# Devpost promotion video

This directory contains the reproducible source for the Dairy Horizon Devpost promotion video.

## Included in Git

- Remotion composition and configuration
- Playwright capture script
- English storyboard
- Dependency manifests

## Media assets

Media files are intentionally excluded from Git to keep the repository lightweight. Before previewing or rendering, place the approved title image, narration clips, processed stereo narration, and captured stills in the media directories expected by the composition.

Do not commit rendered MP4 files, browser-recorded WebM files, package installation directories, or private source media.

## Workflow

1. Install dependencies with `npm install`.
2. Start the application locally and run `node capture-scenes.mjs` to refresh browser captures.
3. Process narration to dual-mono stereo and normalize it to the agreed loudness target.
4. Run `npm run preview` to review the composition in Remotion Studio.
5. Render only approved revisions.

## Video design

- Canvas: 1920×1080
- Product captures: 1280×1080, centered on black
- Product UI remains Japanese; narration and captions are English
- Captions start after a short pause and use a translucent charcoal background
- Static state changes are hard cuts, not simulated browser scrolling
- Scene 9 uses a darkened barn background, then transitions to a black closing frame

## Audio design

- The unused second narration clip is excluded.
- Remaining clips follow the nine-scene storyboard order.
- Narration is converted to stereo with identical left/right channels.
- Target loudness is approximately -16 LUFS, with true peak capped at -1 dBTP.
