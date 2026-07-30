# human-brain

Human brain data, rendered from the public releases, with the provenance of
every number kept attached to it.

**Live: https://amyleesterling.github.io/human-brain/**

The first page is **H01**, the cubic millimetre of human temporal cortex imaged
by serial section electron microscopy by the Lichtman laboratory at Harvard and
the Connectomics team at Google. It shows all 49,379 cell bodies in the volume
in the place the microscope found them, the release's seven cortical layer
surfaces, and the 104 cells that were proofread by hand.

> Shapson-Coe A, Januszewski M, Berger DR, et al.
> *A petavoxel fragment of human cerebral cortex reconstructed at nanoscale resolution.*
> Science **384**, eadk4858 (2024). https://doi.org/10.1126/science.adk4858

This repo is not affiliated with that project. It only reads what the project
made public, at `gs://h01-release`. Cite their paper, not this page.

## The sample, in one paragraph

A woman of forty five had epilepsy that medicine could not control. The focus
was in her hippocampus, and reaching it meant removing the cortex above it,
which would otherwise have been discarded. The block was fixed within minutes,
stained, set in resin, and cut into 5,019 sections averaging 33.9 nm. Each was
imaged at 4 nm per pixel. It came from the front of the middle temporal gyrus,
runs the full depth of cortex into the white matter, was found normal on
neuropathology, and produced 1.4 petabytes.

## What is in here

```
index.html            the page
js/holo3d.js          shared canvas plumbing: nothing renders off screen
js/column.js          49,379 cell bodies, plus the seven layer surfaces
js/cells.js           the 104 proofread cells, one at a time
data/somas.bin        cell bodies: xyz, depth, class, layer. 889 kB
data/somas.json       the header for that binary, and every count on the page
data/cells.json       the 104 cells and the release's own statistics for them
meshes/layers/        cortical layers 1 to 6 and white matter, Draco glTF
meshes/cells/         the 104 proofread cells at level of detail 3, Draco glTF
scripts/fetch_h01.py  pulls everything above out of gs://h01-release
scripts/build_data.py turns the raw pulls into what the page loads
scripts/draco.sh      compresses the meshes, run last
vendor/three/         three.js, vendored rather than pulled from a CDN
```

## Rebuilding the data

The order matters: `build_data.py` reads the layer meshes with trimesh to work
out the pial surface, and it wants them uncompressed.

```bash
python scripts/fetch_h01.py somas
python scripts/fetch_h01.py layers
python scripts/fetch_h01.py cells --lod 3
python scripts/build_data.py
bash   scripts/draco.sh meshes/cells
bash   scripts/draco.sh meshes/layers
```

Needs `cloud-volume`, `trimesh`, `pandas`, and `npx` for
`@gltf-transform/cli`. The cell meshes take about twenty minutes to pull and
the same again to compress.

## Three things this repo got right by checking

**The class grouping is the paper's, not a guess.** The soma table names eleven
classes and never says which are neurons. The grouping used here is the one
that reproduces the paper's own figures from the table exactly, to the
individual cell: 16,087 neurons, 32,315 glia, 10,531 of the neurons spiny. The
class that settles it is `C_SHAPED`. Counted as a neuron, none of the three
totals match. Counted with the glia, all three come out right. `build_data.py`
asserts this on every run and prints `match` or `MISMATCH` per figure.

**Depth is distance to a surface, not a coordinate.** The block is a tilted
slab and the cortical surface curves inside it, so depth cannot be read off any
axis. Subtracting X spreads layer 1 across 2.7 mm; projecting onto the best
straight line through the layer centroids still spreads it across 2.6 mm. Depth
here is the true distance from each cell to the outward face of the release's
layer 1 region. The check is that nobody fitted it: measured that way each
layer's lower edge meets the next layer's upper edge to within 60 µm or better,
all the way down, and those seams are printed on every build.

**The layer 1 label is doing duty as a catch-all.** Testing all 49,379 labels
against all seven layer meshes, every label's best match is its own mesh, so
the column is sound. But layer 1 is the weakest: 78 per cent of the cells
carrying it fall inside the layer 1 mesh against 85 to 99 per cent for the
others, and 7 per cent fall inside no layer mesh at all, out in the corners of
the block. Its band is marked `reliable: false` in `data/somas.json` and left
off the depth ladders rather than drawn as though it were as good as the rest.

## What the page does not claim

The meshes are level of detail 3 of the release's multiresolution mesh, roughly
22 thousand faces where the full one is 2.7 million. The levels simplify the
surface rather than prune the arbor, so every branch is there and the skin is
smoother than the microscope saw it. The face count shown is counted off the
loaded geometry, never quoted from a manifest.

No cable length is shown, because none is published for these cells and
estimating it from a decimated mesh would be a number with no source.

## Design

Built on the same dark, instrument-panel language as
[the MICrONS mouse cortex page](https://amyleesterling.github.io/microns/),
[CA3 renderings](https://amyleesterling.github.io/ca3/) and
[scifi-ui](https://amyleesterling.github.io/scifi-ui/). No build step, no
framework, no CDN. Everything hover-driven has a tap path and respects
`prefers-reduced-motion`.

## Licence

The code here is MIT. The H01 data is the Lichtman laboratory's and Google's,
released publicly by them under their own terms; see
[the H01 release](https://h01-release.storage.googleapis.com/landing.html).
