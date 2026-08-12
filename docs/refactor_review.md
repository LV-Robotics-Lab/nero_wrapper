# Refactor review

This repository previously behaved as a field bring-up archive rather than a
reusable wrapper: it had no package metadata, automated tests, CI, stable
public API, or separation between operational configuration and historical
status. The review also found a stale link to an ignored `agent.md`, hundreds
of retired environment fields in the active shell config, and default device
credentials in tracked text.

The refactor follows the structure used by the lab's other hardware wrappers:

- a `src/nero_wrapper` Python package with a deliberately small public API;
- lazy loading of the optional vendor SDK;
- context-managed, read-only hardware access;
- typed, validated, non-secret environment configuration;
- explicit fail-closed safety primitives for future motion migration;
- unit tests and a Python 3.10/3.12 CI matrix;
- current configuration separated from preserved bring-up provenance.

## Compatibility boundary

Existing field scripts and their `/workspace/nero` container mount remain in
place. They are provenance-heavy and include accepted motion behavior that
must not be mechanically rewritten without physical revalidation. The new
package therefore wraps configuration and read-only feedback first. Moving a
motion path into the package requires a separate real-robot acceptance record.

## Credential boundary

Tracked text now contains no default device passwords. Local credentials live
only in the ignored `config/nero.local.env`. Because this repository was
already public, operators should rotate any device credential that previously
matched a documented default; removing it from the current tree does not erase
Git history or screenshots.
