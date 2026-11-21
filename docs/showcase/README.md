# Showcase

Screenshots (`*.png`) and recorded conversations (`conversations.json`) for the showcase page on
GitHub Pages. The chat needs the local API and Azure keys, so these are captured locally and
committed; `python -m digests publish` copies them into the site.

`conversations.json` is a list of `{"question", "answer", "sources": [{"title", "url"}]}`.
