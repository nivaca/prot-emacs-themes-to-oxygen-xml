# Registro de cambios

Los cambios notables de prot-emacs-themes-to-oxygen-xml. El código está
en [GitHub](https://github.com/nivaca/prot-emacs-themes-to-oxygen-xml). El
proyecto no tiene etiquetas de versión ni publicaciones, así que las
entradas llevan fecha.

## 2026-11-20

- Se elimina el `readme.md` vacío, un duplicado de `README.md` que solo
  se distinguía por las mayúsculas.

## 2026-03-26

- Primera versión: `emacs_to_oxygen.py` convierte las familias de temas
  de Protesilaos Stavrou para Emacs (modus-themes, ef-themes y
  doric-themes) en archivos de tema para Oxygen XML Editor. Lee las
  paletas de los archivos `.el` de los temas y toma como plantilla un
  tema de Oxygen ya existente (`graphite.xml`), cuya estructura conserva;
  solo cambian los colores, los estilos y la marca de tema oscuro o
  claro.
- Los 66 temas convertidos están en `output/dark/` y `output/light/`.
- Las carpetas `ef` y `doric`, enlaces a los repositorios de los propios
  temas, salen del repositorio; sus archivos `.el` se indican con
  `--theme-dir` y `--theme-files`.
- Licencia: GNU GPL, versión 3 (`COPYING`).
