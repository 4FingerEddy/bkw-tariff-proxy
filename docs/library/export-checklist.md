# LOXONE Library export and review checklist

This checklist prepares the community template but does not authorize publication.

> No push, release, or Library upload is authorized by this checklist.

## 1. Start from a fresh project

- [ ] Use the intended release version of Loxone Config.
- [ ] Create a new anonymous project, not a production installation copy.
- [ ] Record the exact Config version used.
- [ ] Add one Virtual HTTP Input titled `BKW Dynamic Feed-in Tariff CH`.

## 2. Parent Virtual HTTP Input

- [ ] URL is exactly:

  ```text
  http://REPLACE_WITH_PROXY_HOST:8785/v1/loxone.json
  ```

- [ ] Polling cycle is `900 s`.
- [ ] No authentication data is present.
- [ ] No private IP address, hostname, serial number, UUID or project name is present.

## 3. Command recognitions

Create exactly **25 command recognitions**:

- [ ] `status-code` -> `\i"status_code":\i\v`
- [ ] `h00` -> `\i"feedin_h00_mchf_kwh":\i\v`
- [ ] Continue sequentially through `h23` -> `\i"feedin_h23_mchf_kwh":\i\v`
- [ ] All 25 inputs are signed analogue values.
- [ ] No decimal tariff inputs are included.
- [ ] No current-value or diagnostic input is included.
- [ ] No rolling/relative diagnostic source is included.
- [ ] Verify `h20` references hour 20, not hour 10.

## 4. Example project

- [ ] Connect `h00 ... h23` to `00:00 ... 23:00` in Spot Price Optimizer **Absolute mode**.
- [ ] Add a guard that opens only for status `0` or `10`.
- [ ] Add a visible degraded-data warning for status `10`.
- [ ] Keep correction `0..1000 -> 0..1` on every signed hour input before the optimizer.
- [ ] Confirm that transport value `45` reaches the optimizer as `0.045 CHF/kWh`.
- [ ] Document synthetic-mode testing and the required return to live mode.
- [ ] Remove all private objects, identifiers and unrelated programming.

## 5. Real export and round-trip test

- [ ] Save the Virtual HTTP Input as a **real Loxone Config export**.
- [ ] Name the file `bkw-tariff-proxy.xml`.
- [ ] Save the minimal example as `bkw-tariff-proxy-example.Loxone`.
- [ ] Import the XML into a second fresh project through the Virtual HTTP Input template path.
- [ ] Confirm the parent URL, polling cycle and all 25 inputs survived the round trip.
- [ ] Confirm the example project opens without repair or missing-object warnings.

## 6. Static file checks

- [ ] XML parses successfully with a standard XML parser.
- [ ] Root tag and `Info templateType` match a fresh Loxone Virtual HTTP Input export.
- [ ] Placeholder `REPLACE_WITH_PROXY_HOST` is present.
- [ ] No angle-bracket placeholder is used inside the URL.
- [ ] No token, password, private address or production identifier is present.
- [ ] Command count is exactly 25.
- [ ] Hour recognitions are complete and unique from `h00` through `h23`.

## 7. End-to-end synthetic test

- [ ] Proxy runs with `BKW_TEST_DATA_MODE=synthetic`.
- [ ] `/health` returns `ok`.
- [ ] `/v1/status-code` returns `0`.
- [ ] `/v1/loxone.json` exposes 24 fake hourly integer values.
- [ ] Loxone receives all 24 values.
- [ ] Spot Price Optimizer calculates in Absolute mode.
- [ ] Status guard blocks when the proxy is stopped or unsafe.

## 8. Live-mode verification

- [ ] Test mode is changed back to `off` or removed.
- [ ] Container is recreated.
- [ ] Live endpoint status and tariff date are plausible.
- [ ] Status guard behavior is verified for the actual status.

## 9. Repository/release prerequisites

- [ ] Public documentation contains no private environment details.
- [ ] README, Compose, package version and release tag agree.
- [ ] The pinned GHCR tag is anonymously pullable for `linux/amd64` and `linux/arm64`.
- [ ] Full automated test suite passes on the release commit.
- [ ] XML and example project are attached to the release or stored at stable repository paths.

## 10. Pre-submission review

- [ ] Library title and description are English.
- [ ] Entry is classified as a community Network Template.
- [ ] Creator and descriptive brand fields are confirmed by the operator.
- [ ] Support points to GitHub Issues.
- [ ] Non-affiliation text is included.
- [ ] Additional download contains only the anonymous example project.
- [ ] Screenshots contain no private data.
- [ ] Review every upload field before submission.

**Do not submit** from this checklist alone. Library submission requires a separate explicit operator approval after the completed form and final files have been reviewed.
