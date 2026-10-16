# SEA-AD explorer refinement

The explorer now uses a minimal tabbed interface, and repeated donor previews no longer rerun the same database query.

## Interface

- Removed metadata banners, redundant ready labels, marketing headings, subtitles, and footer.
- Added Cohort, Expression, and Exports tabs with step-specific controls and collapsed advanced options.
- Added themed custom dropdowns, padded chevrons, keyboard navigation, tooltips, and styled inputs.
- Added a centered square-only app loader, reduced-motion support, startup Retry, and request deadlines.
- Preserved scientific caveats in Data notes.

## Responsiveness

Before the patch, the local donor-preview request exceeded a 12-second client timeout. The patched request returned 36,686 cells across 84 donors in 2.731 seconds on its first request and 0.0087 / 0.0092 seconds on repeated requests. These are local app timings, not measurements of the complete browser-to-workspace connection.

The app now uses one grouped query with an explicit existing covering index, an 8-second SQL progress deadline, a 10-second preview response deadline, and a bounded 64-entry cache for the immutable source. Browser requests also have explicit deadlines.

## Verification

The primary browser suite passed real cohort counts, a 24-cell APOE/TREM2 sample, an 8-cell export, invalid-gene errors, custom dropdown interaction, and 1366px/320px theme layouts without page overflow or browser errors. The additional suite passed 8 checks, including pixel-level square-only loading, reduced motion, Retry recovery, keyboard selection, tooltip focus, dropdown padding, and reopening the downloaded 8×2 AnnData file.

Test records: `refinement-test-results.json`, `refinement-detail-results.json`, `latency-before.json`, and `latency-after.json`. Screenshots: `screenshots/refinement/`.

## Remaining scope

The app-owned loading surface is updated. The workspace viewer's earlier pre-app loading placeholder is separate and has been reported for correction.
