# Changelog

## 0.8.0.2 — 2026-11-01

First published Windows x64 preview.

- Native Explorer conversion menu, with output formats adapted to the input.
- English interface by default; Ukrainian for Ukrainian Windows.
- Local image, audio, video, document, archive, ebook, font, vector and 2D CAD routes.
- Outputs beside the source, atomic publication, overwrite confirmation and multi-page naming.
- Reduced release payload: removed unused dictionaries, UI languages, manuals,
  SDK files, duplicate tools and unused PDF layout models.
- One bilingual README, AGPL-3.0-only licensing, contributor/security policies,
  issue forms and repository validation on GitHub Actions.

The preview is unsigned. Native runtime preparation for source builds is not
fully automated. Format support depends on the file variant; lossless output is
preferred where possible, not guaranteed for inherently lossy codecs.
Ebook conversion requires Calibre, HWPX requires Java, and RAR creation requires WinRAR.
