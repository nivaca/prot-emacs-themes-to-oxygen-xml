#!/usr/bin/env python3
"""
Convert Protesilaos Stavrou's Emacs themes (modus, ef, doric) to
Oxygen XML Editor theme files (.xml).

Usage:
    python3 emacs_to_oxygen.py \
        --template graphite.xml \
        --modus modus-themes.el \
        [--ef ef-themes.el] \
        [--theme-files DIR_OR_FILES...] \
        --output-dir ./output/

The script:
  1. Parses graphite.xml as the structural template
  2. Extracts palette definitions from the .el source files
  3. Maps Emacs semantic colors to Oxygen syntax roles
  4. Generates one .xml file per theme
"""

import re
import os
import sys
import argparse
import copy
from xml.etree import ElementTree as ET


# ───────────────────────────────────────────────────────────────
# 1.  Emacs Lisp palette parser
# ───────────────────────────────────────────────────────────────

def parse_modus_common_mappings(text):
    """Extract modus-themes-common-palette-mappings from modus-themes.el."""
    m = re.search(
        r"\(defconst\s+modus-themes-common-palette-mappings\s*\n\s*'?\(\s*(.*?)\)\s*\)",
        text, re.DOTALL
    )
    if not m:
        return []
    return _parse_alist_entries(m.group(1))


def parse_modus_palettes(text):
    """Extract all 8 modus palette definitions from modus-themes.el.
    Returns dict: { 'modus-operandi': [(name, value), ...], ... }
    """
    common_mappings = parse_modus_common_mappings(text)

    palettes = {}
    # Match: (defconst modus-themes-VARIANT-palette
    pattern = r"\(defconst\s+(modus-themes-(\S+)-palette)\s*\n\s*\(append\s*\n\s*'?\(\s*(.*?)\)\s*\n\s*modus-themes-common-palette-mappings\)"
    for m in re.finditer(pattern, text, re.DOTALL):
        var_name = m.group(1)  # e.g. modus-themes-operandi-palette
        variant = m.group(2)   # e.g. operandi
        body = m.group(3)

        theme_name = f"modus-{variant.replace('_', '-')}"
        entries = _parse_alist_entries(body)
        # Append the common mappings
        entries.extend(common_mappings)
        palettes[theme_name] = entries

    return palettes


def parse_ef_palette_common(text):
    """Extract ef-themes-palette-common from ef-themes.el."""
    m = re.search(
        r"\(defconst\s+ef-themes-palette-common\s*\n\s*'?\(\s*(.*?)\)\s*\n\s*\"",
        text, re.DOTALL
    )
    if not m:
        # Try alternative ending
        m = re.search(
            r"\(defconst\s+ef-themes-palette-common\s*\n\s*'?\(\s*(.*?)\)\)",
            text, re.DOTALL
        )
    if not m:
        return []
    return _parse_alist_entries(m.group(1))


def parse_ef_theme_file(filepath, ef_common, modus_common):
    """Parse an individual ef-*-theme.el file.
    Ef v2+ palettes have two parts:
      - ef-NAME-palette-partial  (named hex colors)
      - ef-NAME-palette-mappings-partial  (semantic mappings)
    Combined with ef-themes-palette-common + modus-themes-common-palette-mappings.
    Returns (theme_name, entries) or None.
    """
    with open(filepath, 'r', errors='replace') as f:
        text = f.read()

    # Extract theme name from the palette-partial defconst
    m_name = re.search(r"\(defconst\s+ef-(\S+)-palette-partial\b", text)
    if not m_name:
        return None
    theme_name = f"ef-{m_name.group(1)}"

    # Parse palette-partial (hex colors + bg/fg entries)
    m_partial = re.search(
        r"\(defconst\s+ef-\S+-palette-partial\s*\n\s*'?\(\s*(.*?)\)\)",
        text, re.DOTALL
    )
    entries = _parse_alist_entries(m_partial.group(1)) if m_partial else []

    # Parse palette-mappings-partial (semantic mappings like (keyword red-faint))
    m_mappings = re.search(
        r"\(defconst\s+ef-\S+-palette-mappings-partial\s*\n\s*'?\(\s*(.*?)\)\)",
        text, re.DOTALL
    )
    if m_mappings:
        entries.extend(_parse_alist_entries(m_mappings.group(1)))

    # Add shared mappings (ef-themes-palette-common then modus-common)
    entries.extend(ef_common)
    entries.extend(modus_common)
    return (theme_name, entries)


def parse_doric_theme_file(filepath):
    """Parse an individual doric-*-theme.el file.
    Doric palettes use defvar with a flat let-binding-style list:
      (defvar doric-NAME-palette
        '((bg-main "#hex") (fg-main "#hex") ...))
    Returns (theme_name, entries) or None.
    """
    with open(filepath, 'r', errors='replace') as f:
        text = f.read()

    m = re.search(
        r"\(defvar\s+doric-(\S+)-palette\s*\n\s*'?\(\s*(.*?)\)\s*\n\s*\"",
        text, re.DOTALL
    )
    if not m:
        # Fallback: try defconst
        m = re.search(
            r"\(defconst\s+doric-(\S+)-palette\s*\n\s*'?\(\s*(.*?)\)\)",
            text, re.DOTALL
        )
        if not m:
            return None

    theme_name = f"doric-{m.group(1)}"
    entries = _parse_alist_entries(m.group(2))
    return (theme_name, entries)


def _parse_alist_entries(text):
    """Parse Emacs alist entries of the form:
       (name "#rrggbb")   → hex color
       (name other-name)  → symbolic reference
       (name unspecified)  → skip
    Returns list of (name_str, value_str) tuples.
    """
    entries = []
    # Match both hex values and symbolic references
    for m in re.finditer(
        r'\(\s*([\w-]+)\s+(?:"(#[0-9a-fA-F]{6})"|(\w[\w-]*))\s*\)', text
    ):
        name = m.group(1)
        hex_val = m.group(2)
        sym_val = m.group(3)
        if hex_val:
            entries.append((name, hex_val))
        elif sym_val and sym_val != 'unspecified':
            entries.append((name, sym_val))
        # skip unspecified
    return entries


# ───────────────────────────────────────────────────────────────
# 2.  Palette resolution
# ───────────────────────────────────────────────────────────────

def resolve_palette(entries):
    """Build a dict from palette entries, resolving symbolic references.
    Returns dict: { name: "#rrggbb" }
    """
    raw = {}
    for name, value in entries:
        if name not in raw:  # first occurrence wins (overrides come first)
            raw[name] = value

    resolved = {}

    def _resolve(name, depth=0):
        if depth > 20:
            return None
        if name in resolved:
            return resolved[name]
        val = raw.get(name)
        if val is None:
            return None
        if val.startswith('#'):
            resolved[name] = val
            return val
        # symbolic reference
        result = _resolve(val, depth + 1)
        if result:
            resolved[name] = result
        return result

    for name in raw:
        _resolve(name)

    return resolved


# ───────────────────────────────────────────────────────────────
# 3.  Color utilities
# ───────────────────────────────────────────────────────────────

def hex_to_rgb(h):
    """'#rrggbb' → (r, g, b) integers."""
    h = h.lstrip('#')
    return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def rgb_str(r, g, b):
    """Integers → 'r,g,b' string."""
    return f"{r},{g},{b}"


def hex_to_rgb_str(h):
    """'#rrggbb' → 'r,g,b'."""
    return rgb_str(*hex_to_rgb(h))


def is_dark(h):
    """True if hex color is dark (avg channel < 128)."""
    r, g, b = hex_to_rgb(h)
    return (r + g + b) / 3 < 128


def blend(hex1, hex2, alpha=0.5):
    """Blend hex1 toward hex2 by alpha (0=hex2, 1=hex1)."""
    r1, g1, b1 = hex_to_rgb(hex1)
    r2, g2, b2 = hex_to_rgb(hex2)
    r = int(r1 * alpha + r2 * (1 - alpha))
    g = int(g1 * alpha + g2 * (1 - alpha))
    b = int(b1 * alpha + b2 * (1 - alpha))
    return f"#{r:02x}{g:02x}{b:02x}"


def lighten(h, pct):
    """Lighten a hex color by pct percent."""
    r, g, b = hex_to_rgb(h)
    r = min(255, int(r + (255 - r) * pct / 100))
    g = min(255, int(g + (255 - g) * pct / 100))
    b = min(255, int(b + (255 - b) * pct / 100))
    return f"#{r:02x}{g:02x}{b:02x}"


def darken(h, pct):
    """Darken a hex color by pct percent."""
    r, g, b = hex_to_rgb(h)
    r = max(0, int(r * (1 - pct / 100)))
    g = max(0, int(g * (1 - pct / 100)))
    b = max(0, int(b * (1 - pct / 100)))
    return f"#{r:02x}{g:02x}{b:02x}"


def adjust(h, pct):
    """Lighten if dark, darken if light."""
    if is_dark(h):
        return lighten(h, pct)
    return darken(h, pct)


# ───────────────────────────────────────────────────────────────
# 4.  Semantic color extraction (Emacs palette → abstract roles)
# ───────────────────────────────────────────────────────────────

def extract_modus_ef_colors(palette):
    """Extract semantic colors from a resolved modus/ef palette.
    Returns a dict of abstract role → hex color.
    """
    p = palette  # shorthand

    bg = p.get('bg-main', '#ffffff')
    fg = p.get('fg-main', '#000000')
    dark = is_dark(bg)

    # Derive UI colors from bg-main
    bg_dim = p.get('bg-dim', adjust(bg, 5))
    bg_active = p.get('bg-active', adjust(bg, 15))
    bg_inactive = p.get('bg-inactive', adjust(bg, 10))
    border_c = p.get('border', adjust(bg, 25))
    fg_dim = p.get('fg-dim', adjust(fg, 30))

    # Derive line highlight: slight shift from bg
    bg_hl = p.get('bg-hl-line', adjust(bg, 8))

    # Selection background
    bg_region = p.get('bg-region')
    if not bg_region:
        bg_region = adjust(bg, 20)

    # Cursor
    cursor = p.get('cursor', fg)

    # Code semantics (resolved to hex)
    comment   = p.get('comment', fg_dim)
    string    = p.get('string', p.get('blue-warmer', '#3548cf'))
    keyword   = p.get('keyword', p.get('magenta-cooler', '#531ab6'))
    fnname    = p.get('fnname', p.get('magenta', '#721045'))
    typ       = p.get('type', p.get('cyan-cooler', '#005f5f'))
    variable  = p.get('variable', p.get('cyan', '#005e8b'))
    preproc   = p.get('preprocessor', p.get('red-cooler', '#a0132f'))
    err       = p.get('err', p.get('red', '#a60000'))
    warning   = p.get('warning', p.get('yellow-warmer', '#884900'))
    info      = p.get('info', p.get('cyan-cooler', '#005f5f'))
    bracket   = p.get('bracket', fg)
    operator  = p.get('operator', fg)
    number    = p.get('number', fg)
    punctuation = p.get('punctuation', fg)
    delimiter = p.get('delimiter', fg)
    constant  = p.get('constant', p.get('blue-cooler', '#0000b0'))
    builtin   = p.get('builtin', p.get('magenta-warmer', '#8f0075'))
    property_ = p.get('property', variable)
    docstring = p.get('docstring', p.get('green-faint', '#2a5045'))

    # Entity/regex → cyan or similar
    cyan = p.get('cyan', '#005e8b')
    entity = cyan

    # Find/search highlight
    find_hl = warning

    # Validation
    val_err = err
    val_warn = warning
    val_info = info
    val_ok = p.get('green', '#006800')

    return {
        'bg':          bg,
        'bg_dim':      bg_dim,
        'bg_active':   bg_active,
        'bg_inactive': bg_inactive,
        'bg_hl':       bg_hl,
        'bg_region':   bg_region,
        'border':      border_c,
        'fg':          fg,
        'fg_dim':      fg_dim,
        'cursor':      cursor,
        'comment':     comment,
        'string':      string,
        'keyword':     keyword,
        'fnname':      fnname,
        'type':        typ,
        'variable':    variable,
        'preprocessor': preproc,
        'err':         err,
        'warning':     warning,
        'info':        info,
        'bracket':     bracket,
        'operator':    operator,
        'number':      number,
        'punctuation': punctuation,
        'delimiter':   delimiter,
        'constant':    constant,
        'builtin':     builtin,
        'property':    property_,
        'docstring':   docstring,
        'entity':      entity,
        'find_hl':     find_hl,
        'val_err':     val_err,
        'val_warn':    val_warn,
        'val_info':    val_info,
        'val_ok':      val_ok,
        'dark':        dark,
    }


def extract_doric_colors(palette):
    """Extract semantic colors from a resolved doric palette.
    Doric uses: bg-main, fg-main, cursor, border,
    bg-accent, fg-accent, bg-neutral, fg-neutral,
    bg-shadow-subtle, fg-shadow-subtle, bg-shadow-intense, fg-shadow-intense,
    fg-red/green/yellow/blue/magenta/cyan, bg-red/green/yellow/blue/magenta/cyan
    """
    p = palette

    bg = p.get('bg-main', '#ffffff')
    fg = p.get('fg-main', '#000000')
    dark = is_dark(bg)

    cursor   = p.get('cursor', fg)
    border_c = p.get('border', adjust(bg, 25))
    bg_accent = p.get('bg-accent', adjust(bg, 10))
    fg_accent = p.get('fg-accent', adjust(fg, 15))
    bg_neutral = p.get('bg-neutral', adjust(bg, 8))
    fg_neutral = p.get('fg-neutral', adjust(fg, 10))
    fg_shadow_subtle = p.get('fg-shadow-subtle', adjust(fg, 25))
    bg_shadow_subtle = p.get('bg-shadow-subtle', adjust(bg, 5))
    fg_shadow_intense = p.get('fg-shadow-intense', adjust(fg, 10))
    bg_shadow_intense = p.get('bg-shadow-intense', adjust(bg, 12))

    # Doric is minimalist: most code is fg-main, comments are fg-accent,
    # keywords are bold fg-shadow-intense, strings/docs are fg-shadow-subtle
    fg_red     = p.get('fg-red', '#a60000' if not dark else '#ff5f59')
    fg_green   = p.get('fg-green', '#006800' if not dark else '#44bc44')
    fg_yellow  = p.get('fg-yellow', '#6f5500' if not dark else '#d0bc00')
    fg_blue    = p.get('fg-blue', '#0031a9' if not dark else '#2fafff')
    fg_magenta = p.get('fg-magenta', '#721045' if not dark else '#feacd0')
    fg_cyan    = p.get('fg-cyan', '#005e8b' if not dark else '#00d3d0')

    return {
        'bg':          bg,
        'bg_dim':      bg_shadow_subtle,
        'bg_active':   bg_shadow_intense,
        'bg_inactive': bg_neutral,
        'bg_hl':       bg_accent,
        'bg_region':   bg_shadow_intense,
        'border':      border_c,
        'fg':          fg,
        'fg_dim':      fg_shadow_subtle,
        'cursor':      cursor,
        'comment':     fg_accent,
        'string':      fg_shadow_subtle,
        'keyword':     fg_shadow_intense,
        'fnname':      fg_shadow_intense,
        'type':        fg_shadow_subtle,
        'variable':    fg_shadow_subtle,
        'preprocessor': fg_shadow_subtle,
        'err':         fg_red,
        'warning':     fg_yellow,
        'info':        fg_cyan,
        'bracket':     fg,
        'operator':    fg,
        'number':      fg,
        'punctuation': fg,
        'delimiter':   fg,
        'constant':    fg,
        'builtin':     fg_shadow_subtle,
        'property':    fg_shadow_subtle,
        'docstring':   fg_shadow_subtle,
        'entity':      fg_accent,
        'find_hl':     fg_yellow,
        'val_err':     fg_red,
        'val_warn':    fg_yellow,
        'val_info':    fg_cyan,
        'val_ok':      fg_green,
        'dark':        dark,
    }


# ───────────────────────────────────────────────────────────────
# 5.  Oxygen XML role → abstract color mapping
# ───────────────────────────────────────────────────────────────

# Map each Oxygen syntax role name to an abstract color key
ROLE_MAP = {
    # Text / default
    'Text':                 'fg',

    # Comments
    'Comment':              'comment',
    'Documentation':        'comment',
    'Inline_Comment':       'comment',
    'XML_comment':          'comment',
    'Unix_comment':         'comment',
    'Quote':                'comment',       # Markdown blockquote
    'Annotation':           'comment',
    'Null':                 'comment',

    # Strings / literals
    'Quoted_Value':         'string',
    'Single_quoted_Value':  'string',
    'Literal':              'string',
    'Literal1':             'string',
    'Literal2':             'string',
    'RQ_String':            'string',
    'CDATA':                'string',
    'Code_span':            'string',
    'Code_block':           'string',
    'Code_block_js':        'string',
    'Code_block_java':      'string',
    'Code_block_css':       'string',
    'Code_block_py':        'string',
    'Code_block_json':      'string',
    'Code_block_dtd':       'string',
    'Code_block_md':        'string',
    'String_constructor':   'string',
    'Annotation_string':    'string',
    'Annotation_sq_string': 'string',
    'Content_Type':         'string',
    'Inline_equations':     'string',
    'Property_value':       'string',
    'Attribute_value':      'string',
    'YAML_Header':          'string',

    # Keywords
    'Keyword':              'keyword',
    'Keyword1':             'keyword',
    'Keyword2':             'keyword',
    'Keyword3':             'keyword',
    'Keywords':             'keyword',
    'Instructions':         'keyword',
    'Modifiers':            'keyword',
    'Declaratives':         'keyword',
    'Media_keyword':        'keyword',
    'Media_part':           'keyword',
    'Pseudo_page':          'keyword',
    'Complex_Type':         'keyword',
    'Composition':          'keyword',
    'Conditional':          'keyword',
    'Cast':                 'keyword',
    'JSP_Markup':           'keyword',
    'Php_markers':          'keyword',
    'YAML_start':           'keyword',
    'YAML_end':             'keyword',
    'Header':               'keyword',

    # Function names / identifiers / tags
    'Identifier':           'fnname',
    'Functions':            'fnname',
    'Command':              'fnname',
    'Axis':                 'fnname',
    'Tag':                  'fnname',
    'Xml_tag':              'fnname',
    'Void_element':         'fnname',
    'Element_Type':         'fnname',
    'Doctype':              'fnname',
    'Embedded_Doctype':     'fnname',
    'Schema':               'fnname',
    'Definitions':          'fnname',
    'Items':                'fnname',
    'Pattern':              'fnname',
    'Link':                 'fnname',
    'Display_equations':    'fnname',

    # Headings (Markdown)
    'Heading1':             'fnname',
    'Heading2':             'fnname',
    'Heading3':             'fnname',
    'Heading4':             'fnname',
    'Heading5':             'fnname',
    'Heading6':             'fnname',

    # Types / selectors
    'Type':                 'type',
    'CSS_selector':         'type',
    'CSS_class_selector':   'type',
    'CSS_id_selector':      'type',
    'Primitives':           'type',

    # Variables / properties / attributes
    'Attribute_name':       'variable',
    'Attribute':            'variable',
    'Xml_attribute':        'variable',
    'Property':             'variable',
    'Properties':           'variable',
    'Key':                  'variable',
    'Annotation_name':      'variable',
    'Parameters':           'variable',
    'Label':                'variable',
    'Anchor':               'variable',
    'Var_name':             'variable',
    'Variables':            'variable',
    'Title':                'variable',
    'List':                 'variable',
    'Value':                'entity',       # CSS value
    'Header_content':       'fg',

    # Preprocessor / pragmas
    'Processing_Instruction': 'preprocessor',
    'Pragma':               'preprocessor',
    'XML_prolog':           'preprocessor',
    'Shebang':              'preprocessor',
    'Reference':            'preprocessor',
    'Property_start':       'preprocessor',
    'Property_end':         'preprocessor',
    'Map_key':              'preprocessor',
    'Important':            'warning',

    # Errors
    'Error':                'err',
    'Invalid':              'err',

    # Numbers / booleans
    'Number':               'number',
    'Boolean':              'number',
    'Argument_number':      'number',

    # Operators / punctuation
    'Operator':             'operator',
    'Operators':            'operator',
    'Equal':                'operator',
    'Comparing':            'operator',
    'Colon':                'operator',
    'Star':                 'operator',
    'Delimiter':            'operator',

    # Brackets
    'Curly_brackets':       'bracket',
    'Brackets':             'bracket',
    'Square_brackets':      'bracket',

    # Punctuation
    'Semicolon':            'punctuation',
    'Comma':                'punctuation',
    'Dot':                  'punctuation',
    'Ellipsis':             'punctuation',

    # Entity-like (cyan)
    'Entity':               'entity',
    'Email':                'entity',
    'Regular_expression':   'entity',
    'Emoticons':            'entity',
    'Link_URL':             'entity',

    # Markdown text styles → fg-main
    'Bold':                 'fg',
    'Italic':               'fg',
    'Strike':               'fg',
    'Bold_italic':          'fg',
    'Italic_strike':        'fg',
    'Bold_strike':          'fg',
    'Bold_italic_strike':   'fg',
    'Table':                'fg',
    'Horizontal_rule':      'border',
    'Subscript':            'fg',
    'Superscript':          'fg',

    # Parameter_Entity (DTD)
    'Parameter_Entity':     'preprocessor',
    'Attribute_Type':       'variable',
}

# Style values: 0=normal, 1=bold, 2=italic, 3=bold+italic
# Roles that should be bold
BOLD_ROLES = {
    'Keyword', 'Keyword1', 'Keyword2', 'Keyword3', 'Keywords',
    'Instructions', 'Modifiers', 'Declaratives', 'Media_keyword',
    'Pseudo_page', 'Php_markers', 'JSP_Markup',
    'Heading1', 'Heading2', 'Heading3', 'Heading4', 'Heading5', 'Heading6',
}

ITALIC_ROLES = {
    'Comment', 'Documentation', 'Inline_Comment', 'XML_comment',
    'Unix_comment', 'Quote',
}


# ───────────────────────────────────────────────────────────────
# 6.  XML template parsing & generation
# ───────────────────────────────────────────────────────────────

def parse_template(xml_path):
    """Parse graphite.xml and extract all entries as a structure.
    Returns the raw XML text (we'll do text-based substitution).
    """
    with open(xml_path, 'r', encoding='utf-8') as f:
        return f.read()


def build_color_entry_map(xml_text):
    """Extract all color.LANG.N and color.LANG.N.name pairs.
    Returns dict: { 'color.LANG.N': role_name }
    """
    name_map = {}
    for m in re.finditer(
        r'<String>(color\.[^<]+\.\d+)\.name</String>\s*\n\s*<String>([^<]+)</String>',
        xml_text
    ):
        key = m.group(1)   # e.g. color.XML.1
        role = m.group(2)  # e.g. Comment
        name_map[key] = role
    return name_map


def generate_theme_xml(template_xml, colors, theme_name):
    """Generate an Oxygen XML theme by substituting colors in the template.

    `colors` is the abstract color dict from extract_*_colors().
    """
    xml = template_xml
    dark = colors['dark']

    # Helper: hex → rgb string
    def c(key):
        return hex_to_rgb_str(colors.get(key, colors['fg']))

    # ── 1. UI / editor colors ──

    ui_map = {
        'editor.background-color':           c('bg'),
        'editor.caret-color':                c('cursor'),
        'editor.line-highlight-color':       c('bg_hl'),
        'editor.print.margin.color':         c('fg_dim'),
        'editor.tab.eol.eof.color':          c('border'),

        'author.background-color':           c('bg'),
        'author.foreground-color':           c('fg'),
        'author.caret.proximity.highlight.color': c('bg_hl'),

        'cc.doc.window.background':          c('bg'),
        'cc.doc.window.foreground':          c('fg'),
        'cc.window.background':              c('bg'),
        'cc.window.foreground':              c('fg'),
        'fs.window.background':              c('bg'),
        'fs.window.foreground':              c('fg'),

        'ui.background.color':               c('bg'),
        'ui.foreground.color':               c('fg'),
        'ui.border.color':                   c('border'),
        'ui.disabled.foreground.color':      c('fg_dim'),
        'ui.link.foreground.color':          c('info'),
        'ui.separator.color':               c('bg_hl'),
        'ui.inactive.selection.background.color': c('bg_hl'),
        'ui.text.background.color':          c('bg'),
        'ui.text.components.border.color':   c('border'),
        'ui.view.tabs.border.color':         c('border'),
        'ui.view.titles.background.color':   c('bg'),
        'ui.view.titles.foreground.color':   c('fg'),
        'ui.status.panel.background.color':  c('bg'),
        'ui.status.panel.foreground.color':  c('fg'),
        'ui.menus.toolbars.background.color': c('bg'),
        'ui.menus.toolbars.selection.background.color': c('fg'),
        'ui.scrollbars.chevrons.color':      c('fg_dim'),
        'ui.selection.foreground.color':     c('fg'),

        'grid.background.color':             c('bg'),
        'grid.foreground.color':             c('fg'),
        'grid.border.color':                 c('border'),
        'grid.selection.color':              c('border'),

        'line.number.foreground':            c('fg_dim'),
        'matching.tag.highlight.color':      c('fg'),
        'find.highlight.color':              c('find_hl'),
        'annotation.highlight.color':        c('fg_dim'),
        'declaration.highlight.color.1':     c('fg_dim'),
        'reference.highlight.color.1':       c('fg_dim'),
        'tag.brackets.color':                c('bracket'),
        'tags.foreground.color':             c('fg'),

        'diff.conflict.color':               c('err'),
        'diff.incoming.color':               c('info'),
        'diff.outgoing.color':               c('fg_dim'),
        'diff.dirs.modified.color':          c('warning'),
        'diff.dirs.not.match.color':         c('entity'),

        'validation.error.highlight.color.v7.2':   c('val_err'),
        'validation.warning.highlight.color.v7.2': c('val_warn'),
        'validation.info.highlight.color.v7.2':    c('val_info'),
        'validation.success.color.v7.1':           c('val_ok'),
        'validation.fatal.error.highlight.color':  c('err'),
        'spell.check.highlight.color.v12':         c('val_err'),
        'xpath.highlight.color':                   c('keyword'),
        'search.declarations.highlight.color':     c('find_hl'),
    }

    # Selection bg with alpha
    sel_r, sel_g, sel_b = hex_to_rgb(colors['bg_region'])
    ui_map['editor.selection-background-color.v5'] = f"{sel_r},{sel_g},{sel_b},178"
    ui_map['editor.selection-foreground-color'] = c('fg')

    # Search references with alpha
    dim_r, dim_g, dim_b = hex_to_rgb(colors['fg_dim'])
    ui_map['search.references.highlight.color'] = f"{dim_r},{dim_g},{dim_b},188"

    # Debugger
    s_r, s_g, s_b = hex_to_rgb(colors['string'])
    ui_map['debugger.current.instruction.pointer.v1'] = f"{s_r},{s_g},{s_b},100"

    # Tags background
    ui_map['tags.background.color'] = c('bg_hl')

    # UI selection bg
    bg_act_r, bg_act_g, bg_act_b = hex_to_rgb(colors['bg_active'])
    ui_map['ui.selection.background.color'] = f"{bg_act_r},{bg_act_g},{bg_act_b}"

    # Grid colors (use bg_hl for selected rows, fg_dim for headers)
    for suffix in ['current.selected.column.color.end1', 'current.selected.column.color.end2',
                    'current.selected.column.color.start1', 'current.selected.column.color.start2',
                    'current.selected.row.color',
                    'selected.column.color.end1', 'selected.column.color.end2',
                    'selected.column.color.start1', 'selected.column.color.start2',
                    'selected.row.color']:
        ui_map[f'grid.{suffix}'] = c('bg_hl')

    ui_map['grid.current.selection.color'] = c('info')

    for suffix in ['unselected.column.color.end1', 'unselected.column.color.end2',
                    'unselected.column.color.start1', 'unselected.column.color.start2',
                    'unselected.row.color']:
        ui_map[f'grid.{suffix}'] = c('fg_dim')

    # sh.proxy.map colors
    ui_map['sh.proxy.map.colors.second'] = (
        f"{c('info')};{c('entity')};{c('keyword')};{c('variable')};"
        f"{c('string')};{c('number')};{c('err')};"
    )

    # ── 2. Substitute UI colors ──
    for key, val in ui_map.items():
        xml = _replace_string_entry(xml, key, val)

    # ── 3. Substitute ui.dark.theme ──
    xml = _replace_boolean_entry(xml, 'ui.dark.theme', dark)

    # ── 4. Substitute syntax colors ──
    color_map = build_color_entry_map(xml)
    for color_key, role_name in color_map.items():
        abstract_key = ROLE_MAP.get(role_name)
        if abstract_key:
            hex_color = colors.get(abstract_key, colors['fg'])
            new_val = hex_to_rgb_str(hex_color)
        else:
            # Unknown role: use fg-main
            new_val = c('fg')
        xml = _replace_string_entry(xml, color_key, new_val)

    # ── 5. Substitute style entries for keyword=bold, comment=italic ──
    # Parse style entries and set based on role
    style_entries = re.findall(r'<String>(style\.\S+\.\d+)</String>', xml)
    for style_key in style_entries:
        # Derive the color key: style.XML.1 → color.XML.1
        color_key = style_key.replace('style.', 'color.', 1)
        role_name = color_map.get(color_key, '')
        if role_name in BOLD_ROLES:
            xml = _replace_integer_entry(xml, style_key, 1)
        elif role_name in ITALIC_ROLES:
            xml = _replace_integer_entry(xml, style_key, 2)
        else:
            xml = _replace_integer_entry(xml, style_key, 0)

    # ── 6. Preserve font entries, complex types (int-array, profileConditionsColors) ──
    # These are already in the template and don't need changing.

    return xml


def _replace_string_entry(xml, key, new_value):
    """Replace the <String> value of a specific entry key."""
    # Pattern: <String>KEY</String>\n\t\t\t<String>OLD</String>
    pattern = (
        r'(<String>' + re.escape(key) + r'</String>\s*\n\s*<String>)'
        r'[^<]*'
        r'(</String>)'
    )
    return re.sub(pattern, r'\g<1>' + new_value + r'\g<2>', xml)


def _replace_boolean_entry(xml, key, value):
    """Replace a <Boolean> entry."""
    pattern = (
        r'(<String>' + re.escape(key) + r'</String>\s*\n\s*<Boolean>)'
        r'[^<]*'
        r'(</Boolean>)'
    )
    replacement = 'true' if value else 'false'
    return re.sub(pattern, r'\g<1>' + replacement + r'\g<2>', xml)


def _replace_integer_entry(xml, key, value):
    """Replace an <Integer> entry."""
    pattern = (
        r'(<String>' + re.escape(key) + r'</String>\s*\n\s*<Integer>)'
        r'[^<]*'
        r'(</Integer>)'
    )
    return re.sub(pattern, r'\g<1>' + str(value) + r'\g<2>', xml)


# ───────────────────────────────────────────────────────────────
# 7.  Main
# ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Convert Emacs themes to Oxygen XML Editor themes'
    )
    parser.add_argument('--template', required=True,
                        help='Path to graphite.xml (Oxygen template)')
    parser.add_argument('--modus',
                        help='Path to modus-themes.el')
    parser.add_argument('--ef',
                        help='Path to ef-themes.el')
    parser.add_argument('--theme-files', nargs='*', default=[],
                        help='Additional ef-*-theme.el or doric-*-theme.el files')
    parser.add_argument('--theme-dir',
                        help='Directory containing *-theme.el files')
    parser.add_argument('--output-dir', default='./output',
                        help='Output directory for XML files')
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    template_xml = parse_template(args.template)

    themes = {}  # name → abstract_colors dict

    # ── Parse modus themes ──
    if args.modus:
        with open(args.modus, 'r', errors='replace') as f:
            modus_text = f.read()

        modus_common = parse_modus_common_mappings(modus_text)
        modus_palettes = parse_modus_palettes(modus_text)

        for name, entries in modus_palettes.items():
            palette = resolve_palette(entries)
            colors = extract_modus_ef_colors(palette)
            themes[name] = colors
            print(f"  Parsed modus: {name} ({len(palette)} colors resolved)")
    else:
        modus_text = ""
        modus_common = []

    # ── Parse ef themes common ──
    ef_common = []
    if args.ef:
        with open(args.ef, 'r', errors='replace') as f:
            ef_text = f.read()
        ef_common = parse_ef_palette_common(ef_text)
        if not modus_common and args.modus:
            modus_common = parse_modus_common_mappings(modus_text)

    # ── Parse additional theme files ──
    theme_files = list(args.theme_files)
    if args.theme_dir and os.path.isdir(args.theme_dir):
        for fn in sorted(os.listdir(args.theme_dir)):
            if fn.endswith('-theme.el'):
                theme_files.append(os.path.join(args.theme_dir, fn))

    for filepath in theme_files:
        basename = os.path.basename(filepath)
        if basename.startswith('ef-'):
            result = parse_ef_theme_file(filepath, ef_common, modus_common)
            if result:
                name, entries = result
                palette = resolve_palette(entries)
                colors = extract_modus_ef_colors(palette)
                themes[name] = colors
                print(f"  Parsed ef: {name} ({len(palette)} colors resolved)")
        elif basename.startswith('doric-'):
            result = parse_doric_theme_file(filepath)
            if result:
                name, entries = result
                palette = resolve_palette(entries)
                colors = extract_doric_colors(palette)
                themes[name] = colors
                print(f"  Parsed doric: {name} ({len(palette)} colors resolved)")
        elif basename.startswith('modus-'):
            # Skip individual modus-*-theme.el (they just reference the main palette)
            pass

    # ── Generate XML for each theme ──
    if not themes:
        print("No themes found to convert!")
        sys.exit(1)

    dark_dir = os.path.join(args.output_dir, 'dark')
    light_dir = os.path.join(args.output_dir, 'light')
    os.makedirs(dark_dir, exist_ok=True)
    os.makedirs(light_dir, exist_ok=True)

    dark_count = 0
    light_count = 0

    print(f"\nGenerating {len(themes)} Oxygen XML theme files...")
    for name, colors in sorted(themes.items()):
        xml_out = generate_theme_xml(template_xml, colors, name)
        if colors['dark']:
            out_path = os.path.join(dark_dir, f"{name}.xml")
            dark_count += 1
        else:
            out_path = os.path.join(light_dir, f"{name}.xml")
            light_count += 1
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(xml_out)
        variant = "dark" if colors['dark'] else "light"
        print(f"  ✓ {out_path}  ({variant})")

    print(f"\nDone! {len(themes)} themes written to {args.output_dir}/  ({light_count} light, {dark_count} dark)")


if __name__ == '__main__':
    main()
