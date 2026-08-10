# Trusted signing keys

Public keys the corpus definition trusts, one file per signer. A source names
its key here with `ref.signer_key_file`, and its primary fingerprint with
`ref.signer_fingerprint`.

Both matter, and they check different things:

- the **key file** is imported into an ephemeral keyring that `build.py`
  creates per run and throws away. Verification sees that keyring and nothing
  else, so a build cannot be made to pass by importing a key on the machine
  that happens to be running it.
- the **fingerprint** in `manifest.yaml` is the authority over the file. It is
  checked against the imported key before any tag is looked at, so swapping
  this file is caught immediately rather than producing a build signed by
  someone else.

A public key is public; committing it is how the bytes travel with the corpus
definition and how a build stays reproducible without reaching a keyserver.
Anyone able to change both this directory and the pinned fingerprint in the
manifest could forge the pair — but they could equally change the chunkers.
The control is review of the diff, which is why the fingerprint lives in the
manifest where a change to it is conspicuous.

## Subkeys

Pin the **primary** fingerprint, always. A key that signs with a dedicated
signing subkey — the ordinary shape of a key registered with GitHub — produces
a signature whose GnuPG `VALIDSIG` line names the subkey first and the primary
last. `build.py` reads the primary, so the pin matches whichever subkey did the
work, and survives a subkey rotation.

Never pin a key ID. GitHub displays a 64-bit long id; collisions in that space
have been produced, and 32-bit short ids are trivially forged. The 40-hex
fingerprint is the only safe identifier.

Re-export the key file after adding or rotating a signing subkey. A public key
exported before the subkey existed cannot verify its signatures, and the
failure surfaces as "no public key" — which reads like a missing key rather
than a stale one.

## Adding a signer

```bash
gpg --armor --export <fingerprint> > ingest/keys/<name>.asc
gpg --list-keys --with-colons <name> | awk -F: '/^fpr/{print $10; exit}'
```

Then in `manifest.yaml`, on that source's `ref`:

```yaml
      signer_fingerprint: "<the 40-hex primary fingerprint>"
      signer_key_file: "ingest/keys/<name>.asc"
```

Paths are resolved relative to the manifest.

## Pinned release key

`release.asc` — `3BCD9EFDA6670A3F65AF679EB83B60AE16F5DD1A`,
laurence.e.day (github-signer) <laurence@wildcat.finance>. Signs
`v2-protocol`'s `aleph-v2.1.0`, and is registered at
`github.com/settings/keys`, so the same tag also shows Verified on GitHub.

`wildcat-docs` is unsigned by design: its tags are lightweight and
`require_signature` is false there.
