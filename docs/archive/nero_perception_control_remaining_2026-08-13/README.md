# Remaining nero-perception-control files

This directory preserves the final three first-party files that were not
already represented in `nero_wrapper` when the unversioned
`nero-perception-control/arm-hand-duo` tree was retired on 2026-08-13:

- the historical agent operating instructions;
- the LinkerHand SDK review;
- the upstream NERO/Piper repository analysis.

They are archived rather than activated as current operating policy. The
maintained repository code, safety rules and current documentation take
precedence.

`manifest.sha256` contains exactly three byte-exact source hashes and must
verify before deletion of the source directory.

`source_manifest.sha256` records all 530 non-Git, non-`__pycache__` files in
the retired tree. Its SHA256 is
`95ee017b57fec83118ea1067c1cbbff02329fd9ee9bd3ef491e175be29c4b0e4`.
The disposition audit is:

- 304 files matched existing `nero_wrapper` content byte-for-byte;
- the three remaining first-party files are preserved in `snapshot/`;
- 14 older repository/configuration/document/script versions are superseded by
  their maintained paths in `nero_wrapper`;
- four `__MACOSX/._*` AppleDouble files are generated metadata;
- 205 present files under `upstream/piper_ros` are content-identical objects
  from <https://github.com/agilexrobotics/piper_ros.git> commit
  `2dc30fca68cbf4e04d1d0bc15c123d026380ece7`; the old copy only removed other
  upstream files and stripped executable mode bits.

Nested Git metadata and Python bytecode are reproducible metadata and are not
included in the 530-file manifest.
