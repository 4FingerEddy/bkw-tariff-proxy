# LOXONE Library publication pack

This directory contains the public, reviewable preparation material for the BKW Tariff Proxy community template.

## Files

- [`library-entry.md`](library-entry.md) — copy-ready English Library text and the exact 25-input mapping.
- [`docker-to-loxone.md`](docker-to-loxone.md) — setup from an existing Docker environment through Loxone wiring.
- [`export-checklist.md`](export-checklist.md) — real Loxone Config export, round-trip and pre-submission checks.
- [`../../data/loxone/bkw-tariff-proxy.xml`](../../data/loxone/bkw-tariff-proxy.xml) — reviewed Virtual HTTP Input export.
- [`../../data/loxone/bkw-tariff-proxy-example.Loxone`](../../data/loxone/bkw-tariff-proxy-example.Loxone) — reviewed anonymous example project.

## Accepted artifact baseline

The artifacts were created and round-trip tested with Loxone Config `17.1.16.30`; the template declares `minVersion=17010630`. Automated publication tests verify the 25 inputs, HintText fields, scaling, Absolute-mode wiring, manual Classic override, offline guard and unknown-status catch-all.

## Deliberate boundary

The repository artifacts are real Config exports from a fresh anonymous example project, not hand-written stand-ins. Repository acceptance does not authorize a release, container publication or LOXONE Library submission; those remain separate operator gates.
