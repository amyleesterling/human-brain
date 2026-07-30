# H01 cell type examples, proposed for proofreading

One representative cell per class from the H01 human temporal cortex
volume, intended for a public cell type gallery at
https://amyleesterling.github.io/human-brain/

**All of these are `c3` agglomeration segments and are not proofread.**
Any of them may carry a merge or a split. They are the cells I would
most like checked, because each one is about to stand for its whole
class in front of a general audience.

Segmentation: `gs://h01-release/data/20210601/c3`  
Reference: Shapson-Coe et al., Science 384, eadk4858 (2024)

## How these were chosen

For each class, 11 cells were sampled at random from those
whose soma sits at least 400 um from the side walls and 30 um from the
cut faces, so the arbor is not truncated by the edge of the block. Each
candidate's mesh was measured and the one whose longest axis is closest
to that class's median was chosen, so none of these is an outlier.

The sampled range column is worth a look on its own. A blood vessel
cell sampled at 835 um and a spiny stellate at 1,302 um are not
biology, they are almost certainly merges in the agglomeration. That
spread is the reason this request exists: choosing the median protects
the gallery from the obvious errors, but it cannot tell me whether the
median cell itself is clean.

## The cells

| Class | c3 segment ID | Soma (8x8x33 nm voxels) | Layer | Longest axis | Sampled range | Cells in class |
|---|---|---|---|---|---|---|
| Astrocyte | `47128933376` | 273201, 124417, 4096 | Layer 3 | 139 um | 74 to 463 um | 2,758 |
| Blood vessel cell | `40906643439` | 83626, 204362, 1920 | White matter | 60 um | 10 to 835 um | 80 |
| C shaped cell | `37854466335` | 228502, 109308, 2688 | Layer 4 | 96 um | 49 to 163 um | 119 |
| Interneuron | `36942459652` | 382787, 87204, 2688 | Layer 1 | 144 um | 20 to 506 um | 2,759 |
| Microglia or OPC | `40641141206` | 416050, 192979, 2688 | Layer 2 | 66 um | 16 to 120 um | 3,251 |
| Oligodendrocyte | `47609949041` | 291143, 137403, 2816 | Layer 3 | 44 um | 16 to 120 um | 8,114 |
| Pyramidal cell | `2527127825` | 321428, 93175, 3840 | Layer 2 | 509 um | 55 to 909 um | 5,288 |
| Spiny cell, atypical tree | `31043406757` | 274326, 173360, 4224 | Layer 4 | 470 um | 148 to 1039 um | 567 |
| Spiny stellate cell | `6427024613` | 272793, 233622, 1408 | Layer 5 | 486 um | 292 to 1302 um | 148 |
| Neuron, unclassified | `3949045115` | 176084, 156426, 1024 | Layer 5 | 117 um | 23 to 606 um | 235 |
| Unknown | `74638255222` | 161174, 152269, 3968 | Layer 5 | 87 um | 15 to 401 um | 297 |

## Second and third choices

If any cell above turns out to be badly merged, these are the next
closest to the class median.

| Class | Alternate segment IDs |
|---|---|
| Astrocyte | `28016736582`, `4812009240` |
| Blood vessel cell | `2873097919`, `53975211353` |
| C shaped cell | `32087860683`, `41726475814` |
| Interneuron | `2834975382`, `883726166` |
| Microglia or OPC | `32948603633`, `37437784127` |
| Oligodendrocyte | `49471576764`, `47435861331` |
| Pyramidal cell | `30008794370`, `3949439113` |
| Spiny cell, atypical tree | `5741377673`, `30210610362` |
| Spiny stellate cell | `3949920978`, `2120664699` |
| Neuron, unclassified | `38028260751`, `38507348970` |
| Unknown | `49046293584`, `39980401167` |

## Links

- **Astrocyte** `47128933376`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2247128933376%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B273201.0%2C124417.0%2C4096.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Blood vessel cell** `40906643439`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2240906643439%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B83626.0%2C204362.0%2C1920.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **C shaped cell** `37854466335`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2237854466335%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B228502.0%2C109308.0%2C2688.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Interneuron** `36942459652`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2236942459652%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B382787.0%2C87204.0%2C2688.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Microglia or OPC** `40641141206`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2240641141206%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B416050.0%2C192979.0%2C2688.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Oligodendrocyte** `47609949041`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2247609949041%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B291143.0%2C137403.0%2C2816.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Pyramidal cell** `2527127825`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%222527127825%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B321428.0%2C93175.0%2C3840.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Spiny cell, atypical tree** `31043406757`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2231043406757%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B274326.0%2C173360.0%2C4224.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Spiny stellate cell** `6427024613`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%226427024613%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B272793.0%2C233622.0%2C1408.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Neuron, unclassified** `3949045115`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%223949045115%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B176084.0%2C156426.0%2C1024.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
- **Unknown** `74638255222`: [open in Neuroglancer](https://h01-dot-neuroglancer-demo.appspot.com/#!%7B%22layers%22%3A%5B%7B%22type%22%3A%22image%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/4nm_raw%22%2C%22name%22%3A%22EM%22%7D%2C%7B%22type%22%3A%22segmentation%22%2C%22source%22%3A%22precomputed%3A//gs%3A//h01-release/data/20210601/c3%22%2C%22segments%22%3A%5B%2274638255222%22%5D%2C%22name%22%3A%22c3%22%7D%5D%2C%22navigation%22%3A%7B%22pose%22%3A%7B%22position%22%3A%7B%22voxelSize%22%3A%5B8%2C8%2C33%5D%2C%22voxelCoordinates%22%3A%5B161174.0%2C152269.0%2C3968.0%5D%7D%7D%2C%22zoomFactor%22%3A8%7D%2C%22layout%22%3A%22xy-3d%22%7D)
