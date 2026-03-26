# Emacs to Oxygen XML Editor Theme Converter

A Python script that converts [Protesilaos Stavrou's](https://protesilaos.com/emacs/) Emacs theme families into [Oxygen XML Editor](https://www.oxygenxml.com/) theme files.

## Supported theme families

The script handles all three of Prot's theme collections:

- **modus-themes** (8 themes) — Elegant, highly legible themes conforming to the WCAG AAA contrast standard. Four light (`operandi`) and four dark (`vivendi`) variants, including deuteranopia- and tritanopia-optimized versions.
- **ef-themes** (36 themes) — Colorful yet legible themes with more flair. 18 light and 18 dark variants. Built on top of the modus-themes infrastructure since version 2.0.
- **doric-themes** (22 themes) — Highly legible, minimalist themes with precise typography. 11 light and 11 dark variants. Deliberately restrained in color use.

## Requirements

Python 3.6 or later. No external dependencies — the script uses only the standard library.

## Source files

You need the `.el` source files from each theme family's repository:

- [`modus-themes.el`](https://github.com/protesilaos/modus-themes) — Contains all 8 palette definitions inline.
- [`ef-themes.el`](https://github.com/protesilaos/ef-themes) — Framework file with shared palette mappings. The individual palettes live in separate `ef-*-theme.el` files in the same repository.
- [`doric-themes.el`](https://github.com/protesilaos/doric-themes) — Framework file. Individual palettes live in separate `doric-*-theme.el` files.

You also need an Oxygen XML Editor theme to use as a structural template:

- `graphite.xml` — Or any existing Oxygen theme file. The script preserves the full XML structure (fonts, complex types, profiling colors) and substitutes only color values, styles, and the dark/light flag.

## Usage

### All three families at once

```bash
python3 emacs_to_oxygen.py \
    --template graphite.xml \
    --modus modus-themes.el \
    --ef ef-themes.el \
    --theme-dir ef/ \
    --theme-files doric/*-theme.el \
    --output-dir output/
```

### One family at a time

```bash
# Modus only (no extra files needed — palettes are inline)
python3 emacs_to_oxygen.py \
    --template graphite.xml \
    --modus modus-themes.el \
    --output-dir output/

# Ef only (needs --modus too for shared common mappings)
python3 emacs_to_oxygen.py \
    --template graphite.xml \
    --modus modus-themes.el \
    --ef ef-themes.el \
    --theme-dir ef/ \
    --output-dir output/

# Doric only
python3 emacs_to_oxygen.py \
    --template graphite.xml \
    --theme-files doric/*-theme.el \
    --output-dir output/
```

### Arguments

| Argument | Required | Description |
|---|---|---|
| `--template` | Yes | Path to an Oxygen XML theme file (e.g. `graphite.xml`) used as the structural pattern. |
| `--modus` | No | Path to `modus-themes.el`. Parses all 8 palettes from this single file. Also needed when converting ef-themes, since they depend on `modus-themes-common-palette-mappings`. |
| `--ef` | No | Path to `ef-themes.el`. Provides `ef-themes-palette-common` (shared mappings). Individual palettes come from `--theme-dir` or `--theme-files`. |
| `--theme-dir` | No | Directory to scan for `ef-*-theme.el` and `doric-*-theme.el` files. Accepts one directory. |
| `--theme-files` | No | Individual theme file paths or shell globs (e.g. `doric/*-theme.el`). Use this for the second family if `--theme-dir` is already taken. |
| `--output-dir` | No | Output directory (default: `./output`). Created automatically. Themes are placed in `light/` and `dark/` subdirectories. |

## Output structure

```
output/
├── dark/
│   ├── doric-copper.xml
│   ├── doric-dark.xml
│   ├── ef-autumn.xml
│   ├── ef-dark.xml
│   ├── ef-winter.xml
│   ├── modus-vivendi.xml
│   ├── modus-vivendi-tinted.xml
│   └── ...
└── light/
    ├── doric-light.xml
    ├── doric-marble.xml
    ├── ef-arbutus.xml
    ├── ef-frost.xml
    ├── ef-light.xml
    ├── modus-operandi.xml
    ├── modus-operandi-tinted.xml
    └── ...
```

## Installing themes in Oxygen XML Editor

1. Open Oxygen and go to **Options → Preferences → Appearance → Themes**.
2. Click **Import** and select the `.xml` file(s) you want.
3. Select the imported theme and click **OK**.

Alternatively, copy the `.xml` files directly into Oxygen's theme directory and restart.

## How the conversion works

### Palette parsing

Each theme family stores its colors differently:

- **Modus**: Eight `defconst` palette definitions in `modus-themes.el`, each an alist of `(name "#rrggbb")` hex entries and `(name symbol)` semantic mappings, appended with `modus-themes-common-palette-mappings`.
- **Ef**: Two-part palettes per theme — `ef-NAME-palette-partial` (hex colors) and `ef-NAME-palette-mappings-partial` (semantic mappings) — combined with `ef-themes-palette-common` and `modus-themes-common-palette-mappings`.
- **Doric**: Flat `defvar` palette per theme with 24 named colors (`bg-main`, `fg-main`, `cursor`, `border`, `bg/fg-accent`, `bg/fg-neutral`, `bg/fg-shadow-subtle`, `bg/fg-shadow-intense`, plus six `fg-COLOR` and six `bg-COLOR` entries).

The script resolves all symbolic references recursively (e.g. `keyword` → `magenta-cooler` → `#531ab6`).

### Color mapping

Emacs semantic palette names are mapped to Oxygen syntax roles across all supported languages (XML, HTML, CSS, JavaScript, Java, Python, C, C++, JSON, YAML, Markdown, Shell, SQL, and more):

| Emacs semantic name | Oxygen role | Style |
|---|---|---|
| `comment` / `fg-dim` | Comment, Documentation, Inline\_Comment | Italic |
| `string` | Quoted\_Value, Single\_quoted\_Value, Literal, CDATA | Normal |
| `keyword` | Keyword, Instructions, Modifiers | **Bold** |
| `fnname` | Identifier, Tag, Functions, Command | Normal |
| `type` | Type, CSS\_selector, Primitives | Normal |
| `variable` / `property` | Attribute\_name, Property, Key, Var\_name | Normal |
| `preprocessor` | Processing\_Instruction, Pragma, XML\_prolog | Normal |
| `err` | Error, Invalid | Normal |
| `bracket` / `fg-main` | Curly\_brackets, Brackets, Square\_brackets | Normal |
| `operator` / `fg-main` | Operator, Equal, Colon | Normal |
| `number` / `fg-main` | Number, Boolean | Normal |
| `punctuation` / `fg-main` | Semicolon, Comma, Dot | Normal |

The bracket/operator/number/punctuation → `fg-main` mapping follows Prot's `modus-themes-common-palette-mappings`, where these tokens are deliberately unstyled.

For doric-themes, the mapping reflects their minimalist philosophy: most syntax uses `fg-shadow-intense` or `fg-shadow-subtle` rather than vivid accent colors.

### Template substitution

The script uses `graphite.xml` as a structural template and performs text-based regex substitution on the XML entries. It replaces color values (`<String>r,g,b</String>`), style integers (`<Integer>0|1|2</Integer>`), and the dark mode flag (`<Boolean>true|false</Boolean>`). Complex entries like `profiling.colors`, `colors.for.automatic.assignement`, and font definitions are preserved from the template unchanged.

## License

The Emacs theme source files are © Protesilaos Stavrou and licensed under the [GNU General Public License v3.0](https://www.gnu.org/licenses/gpl-3.0.html):

- [modus-themes](https://github.com/protesilaos/modus-themes) (part of GNU Emacs)
- [ef-themes](https://github.com/protesilaos/ef-themes)
- [doric-themes](https://github.com/protesilaos/doric-themes)

The converter script itself has no license restrictions.
