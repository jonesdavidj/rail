# Station catalogue provenance

`stations.json` is a derived database distributed under the Open Database Licence
(ODbL) 1.0, with the full licence in STATIONS-LICENCE.txt. Attribution: Trainline EU
station database contributors; underlying sources include OpenStreetMap contributors.
The application source is separate from this database.

Source: https://github.com/trainline-eu/stations
Pinned revision: 346a157c98545ef9b8929d0c2db601d6e72889b8
Source file: stations.csv; retrieved 2026-10-30.
Source licence statement: the README at the same revision.

Transformation: keep country=GB, non-city records, and atoc_id matching ^[A-Z]{3}$;
map atoc_id to name; reject duplicates; sort by code. No manual overrides.
The result has 2,652 records. It is a reference catalogue, not evidence of current
Darwin coverage or active service; it does not cover all Northern Ireland stations.

Reproduce using a local copy of stations.csv from the pinned revision:

    python scripts/bundle_stations.py work/stations.csv app/data/stations.json

No runtime network lookup or refresh is required. Keep this attribution and licence
with redistributed copies. If publicly using an adapted database, comply with
ODbL's attribution/share-alike and offer-of-database requirements. Re-evaluate an
RDM or NaPTAN snapshot if its coverage/terms better suit the live integration.
