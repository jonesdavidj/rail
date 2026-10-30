# Train times board: Surbiton and London Waterloo

Two tabs (Surbiton to Waterloo, Waterloo to Surbiton). Each shows the next 7 direct trains with
planned and expected departure and arrival, platform, delays, cancellations (with the reason), carriages
when the feed provides them, and a tap-to-open list of stops. "Earlier trains" and "Later trains" page
through the timetable. It refreshes every 30 seconds.

Until a key is set it runs on clearly labelled demo data, so you can see it straight away.

## Run it

    docker compose up -d --build
    # open http://minisforum.lan:8099/   (add ?route=back to open the second tab)

Or without Docker: `python3 server.py` (Python 3.9+, standard library only).

## Go live

1. Rail Data Marketplace: subscribe to the free **Live Departure Board** product (the public one).
2. Copy its consumer key. Put it in `.env` as `RAIL_DATA_API_KEY=...` (see `.env.example`).
3. Check the feed before relying on it:

       RAIL_DATA_API_KEY=... python3 server.py --check

   This prints the parsed trains. If it reports a routing error, set `RAIL_DATA_BASE_URL` to the URL
   on the product's Specification tab. If it reports a parse problem, run `python3 server.py --raw`
   and send me the output.
4. `docker compose up -d --build` again.

## Behind HTTPS (for the HA companion app)

Add a site to your Caddy config, on the same Docker network as the container:

    trains.balaclavaroad.com {
        reverse_proxy trains:8099
    }

The app has no login. Keep it on your LAN, or put it behind a Cloudflare Access application.
To show it in Home Assistant, add a dashboard with two views, each a Webpage card pointing at
`https://trains.balaclavaroad.com/` and `https://trains.balaclavaroad.com/?route=back`.

## Notes

- Direct trains only: the board is filtered to trains that call at the destination.
- The API key stays on the server and is never sent to the browser.
- Paging uses the board's time offset. "Later trains" reaches about two hours ahead, "Earlier
  trains" about 45 minutes back.
- Tests: `python3 -m unittest discover -s tests`. They use fixtures in the documented feed format,
  not captured live data.
- Data: Darwin, via Rail Data Marketplace, from Rail Delivery Group.
