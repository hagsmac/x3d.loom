# Notice: data, credit and licences

## Structures

**Protein Data Bank.** The 14 deposited structures in `data/pdb/` come from the wwPDB archive, which is free of all copyright restrictions (CC0 1.0). Each entry's primary citation is in `data/pdb/CITATIONS.json` and is shown on the page beside the structure.

**AlphaFold Protein Structure Database.** The five models and their PAE files in `data/afdb/` come from the AlphaFold Protein Structure Database (EMBL-EBI and Google DeepMind), licensed CC-BY 4.0. Their URLs, versions and sha256 are in `data/afdb/PINS.json`. Please cite:

- Jumper J et al. Highly accurate protein structure prediction with AlphaFold. *Nature* 596, 583–589 (2021). doi:10.1038/s41586-021-03819-2
- Varadi M et al. AlphaFold Protein Structure Database in 2024: providing structure coverage for over 214 million protein sequences. *Nucleic Acids Research* 52, D368–D375 (2024). doi:10.1093/nar/gkad1011

The diffusion illustration (`src/anim.py`) follows the noise schedule published for AlphaFold 3; no AlphaFold 3 code or weights are used:

- Abramson J et al. Accurate structure prediction of biomolecular interactions with AlphaFold 3. *Nature* 630, 493–500 (2024). doi:10.1038/s41586-024-07487-w
- Karras T et al. Elucidating the design space of diffusion-based generative models. NeurIPS 2022 (the EDM schedule form).

The X3D scenes, stills and Blender meshes made from these models are adaptations: coordinates are unchanged, while geometry, colours and layout are added here.

## The zinc finger research this follows

The zinc finger work follows the published research of Sarah Lucie Jane Michel's laboratory at the University of Maryland School of Pharmacy on zinc finger proteins (tristetraprolin, ZRANB2, YY1, PARP1, CPSF30). The page lists 18 of the laboratory's papers, from public Europe PMC metadata (`data/credits/lab-papers.json`, with the query and retrieval date). The structures drawn were determined by other groups and are cited on each entry. **This project is independent: the laboratory did not review or endorse it.**

## Tools

| Tool | Licence | How it is used |
|---|---|---|
| Babylon.js 9.32.0 | Apache-2.0 | loaded by the page from the jsDelivr CDN with a subresource-integrity hash; not copied here |
| gemmi | MPL-2.0 | the builder's structure reader |
| pydssp | MIT | secondary structure for the builder |
| NumPy, lxml | BSD | builder and gates |
| Blender (bpy 5.3.0) | GPL-3.0-or-later | tool for the Blender stage; no code copied |
| molecularnodes 520.2.0, nodebpy 520.25.0 | GPL-3.0 | tools for the Blender stage; no code copied |
| x3d-blender-io | GPL-3.0-or-later | writes the Blender stage's X3D; not copied |
| x3d_mcp fork | see that repository | validator, run read-only from its own environment |
| Playwright, Chromium | Apache-2.0, BSD | proof runs only |

The adapter that picks WebGPU or WebGL2 (`x3d.webgpu/demo/src/shared/adapter.js`) is this repository's own and is inlined into the page.
