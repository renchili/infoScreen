# InfoScreen design

## Current dashboard files

Active HTML:
- surface/web/index.html

Active CSS:
- surface/web/assets/css/app.css
- surface/web/assets/css/calendar_board.css
- surface/web/assets/css/local_events.css
- surface/web/assets/css/market_custom.css

Active JavaScript:
- surface/web/assets/js/dashboard.js
- surface/web/assets/js/calendar_board.js
- surface/web/assets/js/local_event_card.js
- surface/web/assets/js/market_custom.js

Runtime JSON files live under surface/.env/.

## Runtime data flow

Schedule data is served from /schedule.json and rendered by assets/js/calendar_board.js.

Weather and market data are served from /weather.json and /market.json and rendered by assets/js/dashboard.js.

Local event data is served from /api/local-events/search and rendered by assets/js/local_event_card.js.

The old root-level web files are not active dashboard entrypoints anymore.
