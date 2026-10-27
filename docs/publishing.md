# Publishing checklist

The repository is private during development. HACS does not support private
repositories, so the following steps are required to publish.

## 1. Make the repository public

Change the visibility in **GitHub → Settings → General → Danger zone → Change
repository visibility**.

## 2. Fill in the repository metadata

- Description: `Unofficial Home Assistant integration and Python client for Charge Amps charge points`
- Topics: `home-assistant`, `hacs`, `chargeamps`, `ev-charging`, `energy`
- Keep Issues enabled.

HACS uses the repository description in the store. The HACS Action checks the
description, topics, license, and issues setting.

## 3. Make CI green

All workflows in `.github/workflows/ci.yml` must pass:

- library lint and tests
- Home Assistant tests
- `hassfest`
- HACS Action

The HACS Action requires a public repository, so the `hacs` CI job is skipped
while the repository is private. It runs automatically after you make the
repository public.

## 4. Create a release

The integration version is `custom_components/chargeamps_cloud/manifest.json`
(`version`) and must match the release tag.

```bash
git tag v0.1.1
git push origin v0.1.1
```

The `Release` workflow creates a full GitHub release (not only a tag) with
generated release notes. HACS prefers releases but can use the default branch.

## 5. Install from HACS

1. HACS → **Custom repositories**.
2. Add `https://github.com/vikwin/chargeamps_cloud`, category **Integration**.
3. Install **Charge Amps Cloud** and restart Home Assistant.
4. Add the integration and enter email, password, and API key.

## 6. Optional: default HACS store

To appear in the default HACS store, open a pull request against
[`hacs/default`](https://github.com/hacs/default) adding the repository to the
`integration` file. Only the owner or a major contributor can submit it. The
repository must be public, HACS Action and Hassfest must pass, and a full
release must exist.

## 7. Optional polish

- Add screenshots to the README.
- Add issue templates.
- Publish the library wheel separately if other projects should consume it;
  the integration does not need it.

The integration already ships `brand/icon.png` and `brand/icon@2x.png`, which
satisfies the brand check for the default HACS store.
