# Vendored library

`chargeamps_cloud/` is a generated copy of `lib/src/chargeamps_cloud`, so the
integration can be installed by copying a single folder and does not need a
package index or a release download.

Do not edit the copy directly. After changing the library run:

```bash
python scripts/sync_lib.py
```

CI verifies the copy with:

```bash
python scripts/sync_lib.py --check
```
