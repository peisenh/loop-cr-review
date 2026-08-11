# Translations (i18n)

The report output is localised with GNU gettext. Source strings (msgids) are in
English; each language has a catalog under `locale/<lang>/LC_MESSAGES/messages.po`,
compiled to a binary `messages.mo` that the program loads at runtime
(`--lang <lang>`, default `de`).

Currently shipped: **de**, **en**.

The compiled `.mo` files are committed so the tool works straight from source
without a build step. The `messages.pot` template is generated and git-ignored.

## Tooling

We use **Babel** (`pip install babel`), which provides `pybabel` and works
cross-platform without the GNU gettext binaries. If you prefer GNU gettext,
`xgettext`/`msgmerge`/`msgfmt` work too.

## Workflow

After changing or adding translatable strings in `loop_cr_review.py` or
`templates/report.html.j2`:

```bash
# 1) Re-extract the template of all strings
pybabel extract -F babel.cfg -o locale/messages.pot .

# 2) Merge new/changed strings into the existing catalogs
pybabel update -i locale/messages.pot -d locale

# 3) Edit the .po files: fill in the msgstr for each msgid
#    (e.g. locale/de/LC_MESSAGES/messages.po). Watch out for entries newly
#    marked "#, fuzzy" — Babel guessed those; review and remove the fuzzy flag.

# 4) Compile .po -> .mo
pybabel compile -d locale
```

With GNU gettext instead of Babel, step 4 is `msgfmt` and step 2 is `msgmerge`:

```bash
msgmerge -U locale/de/LC_MESSAGES/messages.po locale/messages.pot
msgfmt locale/de/LC_MESSAGES/messages.mo -o locale/de/LC_MESSAGES/messages.mo
```

## Adding a new language

```bash
pybabel init -i locale/messages.pot -d locale -l fr   # e.g. French
# then translate locale/fr/LC_MESSAGES/messages.po and compile
pybabel compile -d locale
```

Also add the language code to the `--lang` choices in `loop_cr_review.py`.

## Notes

- Placeholders like `%(w)s`, `%(cre)s`, `%(n).0f` must appear unchanged in the
  translation; only reorder them if the target language needs it.
- Strings marked with `N_(...)` in the code (slot labels, weekday names) are
  extracted but translated at runtime — treat them like any other msgid.
- HTML in a msgstr (e.g. `<b>…</b>`) must stay balanced.
