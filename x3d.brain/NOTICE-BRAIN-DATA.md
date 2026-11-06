# Brain Loom hero scene: data notice

The scenes in `scenes/` contain DERIVED geometry and DERIVED 2D renderings only. No raw template volumes or full-resolution surfaces (the 164k files) are stored here. The cortex is the template's own lower-density vertex set (10k lite, 41k full), not decimated by us.

| Part | Derived from | What is stored | Licence grade |
|---|---|---|---|
| Cortex surfaces (10k lite / 41k full) | TemplateFlow `tpl-fsaverage` pial surfaces, sulc, Desikan-Killiany labels (FreeSurfer lineage) | the template's own 10k / 41k pial triangle sets, moved rigidly (axes reordered, origin shifted; scale 1.000), medial-wall triangles dropped, per-vertex colour (baked AO), no label files | Suspected (no licence file found; attribution kept; the rights holder may ask for removal) |
| Deep structures | marching cubes on the 1 mm `aseg` of `tpl-MNI152NLin2009cAsym` (Fonov et al. 2009, 2011) | smoothed low-poly meshes | Confirmed (permissive MNI licence text; copyright notice retained) |
| T1 slices (`tex/slice_*.png`) | the same template brain T1w | six windowed 2D resamples, alpha from intensity | Confirmed (as above) |
| Tracts | NONE (synthetic) | generated curves | SYNTHETIC |
| Activation blobs | NONE (illustrative) | placed sprites | ILLUSTRATIVE |

Copyright notice carried from the MNI152NLin2009cAsym template licence (copied from the LICENSE file of the downloaded template; its typographic dash and quotation marks are written as plain ASCII, the words are unchanged):

> Copyright (C) 1993-2004 Louis Collins, McConnell Brain Imaging Centre, Montreal Neurological Institute, McGill University.
> Permission to use, copy, modify, and distribute this software and its documentation for any purpose and without fee is hereby granted, provided that the above copyright notice appear in all copies. The authors and McGill University make no representations about the suitability of this software for any purpose. It is provided "as is" without express or implied warranty. The authors are not responsible for any data loss, equipment damage, property loss, or injury to subjects or patients resulting from the use or misuse of this software package.

Citations: Fonov et al. 2011, NeuroImage, doi 10.1016/j.neuroimage.2010.07.033; Fonov et al. 2009, NeuroImage 47 (S1), doi 10.1016/S1053-8119(09)70884-5; Fischl et al. 1999, Hum Brain Mapp, doi 10.1002/(sici)1097-0193(1999)8:4<272::aid-hbm10>3.0.co;2-4. The DOIs and the Fonov author list were checked against the archives' own template_description.json files; titles, volumes and page numbers beyond what a DOI encodes are from memory (see NOTICE.md section 3).

ALIGNMENT: the MNI152NLin2009cAsym deep structures and T1 slices are scaled and shifted per axis (about 3 to 5 percent) so that their cortex bounding box equals the fsaverage cortex bounding box; the fsaverage cortex itself is not scaled. It is a look-level fit, NOT a registration. Do not read positions off this scene as anatomy.

SYNTHETIC: the tract arcs are generated between Desikan region vertices. They are not tractography of any subject or scan.

Not a medical device. For demonstration and learning only.

Rebuild: `tools/prep_meshes.py` (needs the downloaded templates) then `tools/build_brain_scene.py`; both print counts and sha256 of their outputs. `tests/check_contract.py` checks the DEF contract.
