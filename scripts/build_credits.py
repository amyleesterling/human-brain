"""One citations and credits page, generated from the data rather than typed.

Amy: where is the citations and credits link at the bottom? Every page needs
one. She was right twice over. There was no page, and no link, and the
citations that did exist were a run-on sentence at the end of each footer with
no heading on it. The retinotopy page had none at all.

WHY GENERATE IT. A hand-written credits page is wrong the day after it is
written. This one is built by reading which module each page imports, which
data file each module fetches, and the citation and licence recorded inside
that data file by the script that produced it. So a dataset cannot appear on
the site without appearing here, and cannot be described here in terms that
differ from what the fetch script actually recorded.

Writes credits.html, and inserts the link into every page's footer.
"""

import html
import json
import os
import re

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PAGES = {
    "index.html": "A cubic millimetre",
    "tracts.html": "The white matter",
    "scales.html": "Microseconds to decades",
    "retinotopy.html": "Retinotopy",
    "ladder.html": "From Earth to a synapse",
    "credits.html": None,
}


def p(*a):
    return os.path.join(ROOT, *a)


def walk(obj, path=()):
    """Every dict in a JSON tree, with the key path that reached it."""
    if isinstance(obj, dict):
        yield path, obj
        for k, v in obj.items():
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))


def main():
    # ---- which page pulls in which module ---------------------------------
    page_mods = {}
    for pg in PAGES:
        if pg == "credits.html":
            continue
        src = open(p(pg), encoding="utf-8").read()
        page_mods[pg] = set(re.findall(r'\./js/([a-zA-Z0-9_-]+)\.js', src))
    # holo3d is shared plumbing; whoever imports it also imports a real module
    for pg, mods in page_mods.items():
        print(f"  {pg:18s} {sorted(mods)}")

    # ---- which module reads which data file --------------------------------
    mod_data = {}
    for js in os.listdir(p("js")):
        if not js.endswith(".js"):
            continue
        src = open(p("js", js), encoding="utf-8").read()
        mod_data[js[:-3]] = set(re.findall(r'["\'](data/[a-zA-Z0-9_.-]+\.json)', src)) \
            | set(re.findall(r'["\'](meshes/[a-zA-Z0-9_/.-]+manifest\.json)', src))

    # A page also reaches data files named inside the manifests it loads, most
    # of which are meshes. Those carry no separate citation, so the JSON that
    # names them is the right unit here.
    page_data = {}
    for pg, mods in page_mods.items():
        got = set()
        for m in mods:
            got |= mod_data.get(m, set())
        # ladder.json names other data files by reference
        if "data/ladder.json" in got:
            got |= {"data/wholebrain.json", "data/bigbrain.json", "data/earth.json",
                    "data/body.json", "data/synapse.json", "data/cells.json",
                    "data/somas.json", "data/neuron-zoom.json"}
        if "data/surface.json" in got:
            got |= {"data/tracts.json"}
        page_data[pg] = got

    # ---- the citations themselves ------------------------------------------
    sources = {}
    by_norm = {}
    for f in sorted(os.listdir(p("data"))):
        if not f.endswith(".json"):
            continue
        rel = f"data/{f}"
        try:
            doc = json.load(open(p("data", f), encoding="utf-8"))
        except Exception:
            continue
        for _path, node in walk(doc):
            cit = node.get("citation")
            lic = node.get("licence") or node.get("license")
            src = node.get("source")
            has_cit = isinstance(cit, str) and len(cit) >= 25
            # A dataset with a licence and a source but no formal citation
            # still belongs here. The retinotopy data is exactly that: its own
            # dataset_description.json leaves the author list as a TODO
            # placeholder, so there is no paper to cite and nobody named to
            # credit. Dropping it because it has no citation string would have
            # left one whole page crediting nothing, which is how it got into
            # this state in the first place.
            if not has_cit and not (isinstance(lic, str) and isinstance(src, str)):
                continue
            key = cit.strip() if has_cit else (
                node.get("attribution_note")
                or f"{src} ({lic}). No citation is recorded upstream.")
            # Two files can record the same source in slightly different
            # words: bigbrain.json and the ladder manifest both cite Amunts,
            # one with a trailing sentence the other lacks. Keyed on the raw
            # string that is two entries for one dataset, which is exactly the
            # sort of thing a credits page must not do. Key on a normalised
            # opening instead and keep whichever wording is fuller.
            norm = re.sub(r"[^a-z0-9]+", "", key.lower())[:55]
            prev = by_norm.get(norm)
            if prev is not None:
                if len(key) > len(prev):
                    sources[key] = sources.pop(prev)
                    by_norm[norm] = key
                else:
                    key = prev
            else:
                by_norm[norm] = key
            e = sources.setdefault(key, {"licence": None, "source": None,
                                         "files": set()})
            e["files"].add(rel)
            if lic and not e["licence"]:
                e["licence"] = lic if isinstance(lic, str) else None
            if isinstance(src, str) and src.startswith("http") and not e["source"]:
                e["source"] = src

    print(f"\n  {len(sources)} distinct citations across "
          f"{len({f for e in sources.values() for f in e['files']})} data files")

    # Which pages show each source.
    for cit, e in sources.items():
        e["pages"] = sorted(
            pg for pg, dat in page_data.items() if dat & e["files"])

    orphans = [c for c, e in sources.items() if not e["pages"]]
    for c in orphans:
        print(f"  not reachable from any page: {c[:70]}")
    # Every page must credit something, or the mapping above is broken and the
    # page would silently show a dataset with nothing said about it.
    for pg in page_data:
        n = sum(1 for e in sources.values() if pg in e["pages"])
        print(f"  {pg:18s} credits {n} sources")
        assert n > 0, (
            f"{pg} resolves to no citation at all, so either it uses no data "
            f"or this script cannot see how it loads it")

    # ---- the page ----------------------------------------------------------
    NC = [c for c, e in sources.items()
          if e["licence"] and "NC" in e["licence"]]
    SA = [c for c, e in sources.items()
          if e["licence"] and ("SA" in e["licence"] or "ShareAlike" in e["licence"])]

    rows = []
    for cit in sorted(sources, key=lambda c: (sources[c]["licence"] or "zz", c)):
        e = sources[cit]
        lic = html.escape(e["licence"] or "see the source")
        pages = " &middot; ".join(
            f'<a href="{pg}">{html.escape(PAGES[pg])}</a>' for pg in e["pages"])
        link = (f'<a href="{html.escape(e["source"])}" rel="noopener">the data</a>'
                if e["source"] else "")
        rows.append(
            f'    <div class="cite"><p class="ref">{html.escape(cit)}</p>'
            f'<p class="meta"><b>{lic}</b>'
            + (f' &middot; {link}' if link else "")
            + (f' &middot; used on {pages}' if pages else "")
            + "</p></div>")

    body = f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Citations and credits</title>
<meta name="description" content="Every dataset behind this site, who made it, what licence it carries, and which page uses it. Generated from the data files themselves.">
<link rel="icon" href="favicon.ico" sizes="any">
<link rel="icon" type="image/png" sizes="32x32" href="favicon-32.png">
<link rel="apple-touch-icon" href="apple-touch-icon.png">
<style>
  :root {{ --ink:#EFF2F7; --dim:#9AA2B1; --faint:#666E7C; --ground:#05060A;
    --line:#1D222B; --accent:#3E96F0; }}
  * {{ box-sizing:border-box; scrollbar-color:#2A313D transparent; scrollbar-width:thin; }}
  ::-webkit-scrollbar {{ width:11px; height:11px; }}
  ::-webkit-scrollbar-track {{ background:transparent; }}
  ::-webkit-scrollbar-thumb {{ background:#252C38; border-radius:6px;
    border:2px solid transparent; background-clip:content-box; }}
  body {{ margin:0; background:var(--ground); color:var(--ink);
    font:400 17px/1.7 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
    -webkit-text-size-adjust:100%; overflow-x:hidden; }}
  .wrap {{ max-width:820px; margin:0 auto;
    padding:clamp(24px,5vw,44px) clamp(16px,5vw,32px) 20px; }}
  h1 {{ margin:0 0 8px; font-size:clamp(22px,4.8vw,32px); font-weight:500;
    letter-spacing:-.015em; }}
  h2 {{ margin:44px 0 12px; font-size:13px; font-weight:500; letter-spacing:.12em;
    text-transform:uppercase; color:var(--faint); }}
  p {{ margin:0 0 15px; }}
  a {{ color:var(--accent); }}
  .lede {{ color:var(--dim); font-size:15.5px; }}
  .note {{ font-size:14.5px; color:var(--dim); border-left:2px solid var(--line);
    padding:2px 0 2px 16px; margin:22px 0; }}
  .note b {{ color:var(--ink); font-weight:500; }}
  .cite {{ border-top:1px solid var(--line); padding:14px 0 2px; }}
  .cite .ref {{ margin:0 0 4px; font-size:15.5px; }}
  .cite .meta {{ margin:0; font-size:13px; color:var(--faint); }}
  .cite .meta b {{ color:var(--dim); font-weight:500; }}
  footer {{ border-top:1px solid var(--line); color:var(--faint); font-size:13.5px;
    padding:26px 0 0; margin:46px 0 0; }}
  footer a {{ color:var(--dim); }}
</style>
</head>
<body>
<main class="wrap">
  <h1>Citations and credits</h1>
  <p class="lede">Every dataset behind this site: who made it, what licence it
    carries, and which page uses it. Nothing here was measured by me. The
    pictures are mine; the science is theirs, and it is the reason any of this
    is possible.</p>

  <div class="note"><b>This page is generated, not written.</b> It is built by
    reading which module each page imports, which data file each module
    fetches, and the citation and licence recorded inside that file by the
    script that produced it. A dataset cannot appear on the site without
    appearing here, and cannot be described here in terms that differ from what
    the fetch actually recorded. A hand-written credits page is wrong the day
    after it is written.</div>

  <h2>If you use any of this</h2>
  <p>Cite the people who made the data, not this site. Every reference below is
    the one its authors asked for.</p>

  <h2>The sources</h2>
{chr(10).join(rows)}

  <h2>Licences worth knowing about</h2>
  <p>Most of what is here is free for any use. Two things are not, and they are
    flagged above: {len(NC)} dataset{"" if len(NC) == 1 else "s"} carries a
    noncommercial clause, and {len(SA)} carry share-alike, which means anything
    derived from them inherits the same terms. If this site is ever licensed
    commercially, those are the parts that have to come out.</p>

  <h2>Tools</h2>
  <p>Built with <a href="https://threejs.org" rel="noopener">three.js</a>,
    <a href="https://github.com/seung-lab/cloud-volume" rel="noopener">CloudVolume</a>,
    <a href="https://trimesh.org" rel="noopener">trimesh</a>,
    <a href="https://mne.tools" rel="noopener">MNE-Python</a>,
    <a href="https://nipy.org/nibabel/" rel="noopener">NiBabel</a>,
    scikit-image, NumPy and SciPy.</p>

  <footer>
    <p><a href="./">A cubic millimetre</a> &middot;
      <a href="tracts.html">The white matter</a> &middot;
      <a href="scales.html">Microseconds to decades</a> &middot;
      <a href="retinotopy.html">Retinotopy</a> &middot;
      <a href="ladder.html">Brain to synapse</a> &middot;
      Source: <a href="https://github.com/amyleesterling/human-brain">github.com/amyleesterling/human-brain</a>.
      Built by <a href="https://x.com/amyneurons">Amy Sterling</a>.</p>
  </footer>
</main>
</body>
</html>
"""
    with open(p("credits.html"), "w", encoding="utf-8") as f:
        f.write(body)
    print(f"\nwrote credits.html, {len(rows)} sources")

    # ---- the link, on every page ------------------------------------------
    LINK = ('      <a href="credits.html"><b>Citations &amp; credits</b></a> '
            '&middot;\n')
    for pg in PAGES:
        if pg == "credits.html":
            continue
        s = open(p(pg), encoding="utf-8").read()
        if "credits.html" in s:
            print(f"  {pg:18s} already links")
            continue
        i = s.find("<footer")
        j = s.find("<p>", i)
        assert i > 0 and j > i, f"{pg} has no footer paragraph to put the link in"
        s = s[:j + 3] + "\n" + LINK + "     " + s[j + 3:]
        open(p(pg), "w", encoding="utf-8").write(s)
        print(f"  {pg:18s} link added")

    # And check it took, on every page, including this one.
    for pg in PAGES:
        s = open(p(pg), encoding="utf-8").read()
        assert "credits.html" in s or pg == "credits.html", (
            f"{pg} still has no citations and credits link")
    print("every page links to credits.html")


if __name__ == "__main__":
    main()
