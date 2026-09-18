# Mobile table layout

Portrait viewports below 900px use a 390 by 620 canvas. TableStage fits it to
both dimensions of the space remaining after the toolbar and action dock.
There is no minimum 80% scale and no automatic scroll-to-hero behavior.
MobileTable.css owns the final compact seat, board and chip anchors. Ordinary
and large-card preferences share the bounded portrait geometry; desktop geometry
is unchanged. The game page and table viewport cannot scroll. Dialog history
and settings remain scrollable and use the existing visual-viewport handling.

Portrait seats retain name, stack, timer and short action or equity labels.
Tap an avatar for details; the hero menu keeps autoplay and leaving controls.
Details read only presentation-visible cards and board. Long names truncate in
seats but remain available in details. Result amounts are in details and WINNER
uses the free space above the avatar. Chip and card flights use actual DOM anchors.

Run `node poker_web/tools/check_mobile_table.cjs` with POKER_WEB_DIST set to an
isolated Vite build. It covers 320x568, 360x640, 360x780, 390x844 and 430x932,
private/public hands, six seats, long names, results, large mode, no scrolling,
avatar details and rotation. Run the reference-table and chat browser checks
for desktop, animations, action controls and dialog input regression coverage.
