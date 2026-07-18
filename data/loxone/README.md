# Loxone publication artifacts

This directory contains the reviewed LOXONE artifacts for the BKW Tariff Proxy community integration.

## Files

- [`bkw-tariff-proxy.xml`](bkw-tariff-proxy.xml) — real Virtual HTTP Input template exported from Loxone Config.
- [`bkw-tariff-proxy-example.Loxone`](bkw-tariff-proxy-example.Loxone) — anonymous example project with Absolute-mode Spot Price Optimizer wiring and fail-safe status guard.

## Verified toolchain

- Loxone Config 17.1.16.30
- Template metadata: `templateType=2`, `minVersion=17010630`
- UTF-8 with BOM and CRLF line endings

## SHA-256

```text
52ae8f90b2894a31a287bf7ba0572562aeed8edfd5304068288a8f1c91ca6c80  bkw-tariff-proxy.xml
6a4ee6df5f513367cd8f83b25c88720547500a8219db778df914e66af1c95965  bkw-tariff-proxy-example.Loxone
```

## Template behavior

The XML template creates one Virtual HTTP Input with:

- URL placeholder `http://REPLACE_WITH_PROXY_HOST:8785/v1/loxone.json`;
- polling cycle `900 s`;
- one signed analogue status input;
- 24 signed analogue hour inputs `h00` through `h23`;
- correction `0 -> 0` and `1000 -> 1`, converting integer mCHF/kWh transport values to CHF/kWh;
- imported LOXONE Hinweis-Text fields describing status codes and hour mappings.

Replace only `REPLACE_WITH_PROXY_HOST` with the trusted LAN address or local DNS name of the Docker host. Do not expose port `8785` to the internet.

## Example safety logic

The example project uses the Spot Price Optimizer in Absolute mode. Guard priority is intentional:

1. Manual `EMS Classic` override remains available even when the proxy is offline.
2. Offline proxy status blocks the dynamic optimizer path.
3. Status codes `0` and `10` permit dynamic optimization.
4. Known errors and an explicit unknown-code catch-all block dynamic optimization.

Status `10` remains usable but is shown as degraded data. A real tariff value of `0.000 CHF/kWh` is valid.

## Scope and support

The example is deliberately anonymous and contains no production host, credentials or installation-specific objects. Adapt the EMS load wiring and visualization to the target installation, then test every safety state before productive use.

This is an independent community project. Support is best-effort through the repository's GitHub Issues. See the repository `LICENSE` for licensing terms.
