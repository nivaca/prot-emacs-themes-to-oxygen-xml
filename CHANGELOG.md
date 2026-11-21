# Changelog

All notable changes to prot-emacs-themes-to-oxygen-xml. The code is on
[GitHub](https://github.com/nivaca/prot-emacs-themes-to-oxygen-xml). The
project has no version tags or releases, so the entries are dated.

## 2026-11-20

- The empty `readme.md`, a duplicate of `README.md` that differed only
  in case, is removed.

## 2026-03-26

- First version: `emacs_to_oxygen.py` converts the theme families of
  Protesilaos Stavrou for Emacs (modus-themes, ef-themes and
  doric-themes) into theme files for Oxygen XML Editor. It reads the
  palettes from the themes' `.el` files and takes an existing Oxygen
  theme (`graphite.xml`) as a template, whose structure it keeps; only
  the colours, the styles and the dark or light flag change.
- The 66 converted themes are in `output/dark/` and `output/light/`.
- The `ef` and `doric` folders, links to the themes' own repositories,
  are removed from the repository; their `.el` files are given with
  `--theme-dir` and `--theme-files`.
- Licensed under the GNU GPL, version 3 (`COPYING`).
