# Development & releasing

## Releasing (the update channel)

HACS offers an update only when the repository publishes a GitHub **Release**
(a bare tag is not enough). This repo automates that:

1. Make your change on `main`.
2. Bump `"version"` in `custom_components/sunrise_alarm/manifest.json`
   (semver, e.g. `0.1.1` -> `0.1.2`).
3. Add a matching section to `CHANGELOG.md`.
4. Commit and push to `main`.

The `.github/workflows/release.yml` action fires on any push that changes the
manifest, reads the new version, and — if a release for that tag does not
already exist — creates `vX.Y.Z` with auto-generated notes. HACS then shows
"update available" for anyone who installed the integration; they click
**Update** and restart Home Assistant.

Notes:
- The release job needs the default `GITHUB_TOKEN` with `contents: write`
  (already declared in the workflow). No extra secrets required.
- `validate.yml` (hassfest + HACS + byte-compile) runs on every push/PR and
  should be green before you bump the version.
- A custom integration is Python, so installing an update always requires a
  Home Assistant **restart** to load the new code.

## Fast local iteration (optional)

For tighter loops than cut-a-release, use the Advanced SSH & Web Terminal add-on:

```bash
mkdir -p /config/dev && cd /config/dev
git clone https://github.com/rationalRobots/haos-sunrise-alarm.git
ln -sfn /config/dev/haos-sunrise-alarm/custom_components/sunrise_alarm \
        /config/custom_components/sunrise_alarm
```

Then after each push, deploy with:

```bash
git -C /config/dev/haos-sunrise-alarm pull --ff-only && ha core restart
```

The symlink means the pulled files are picked up on the next restart. Remove the
symlink and install via HACS for the "production" copy.
