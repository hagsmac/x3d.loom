# Torso CT scene: sources, licences, changes

Scenes `torso_ct.x3d` (full) and `torso_ct_lite.x3d` (lite) are derived surface meshes. No raw CT or segmentation volume is included, and no full-resolution template surface: the template cortex appears only as a decimated (about 3,000 vertices per hemisphere in the lite scene), affinely fitted mesh.

| Part | Source | Licence grade | What was done |
|---|---|---|---|
| Skeleton, lungs, heart, vessels, organs, brain mask, skin, lung vessels | TotalSegmentator example subject s1397, whole-body CT with 117 segmentations at 3 mm, distributed with the pyvista example data (Apache-2.0 repository). Wasserthal J. et al., Radiology: Artificial Intelligence 2023, doi 10.1148/ryai.230024 | LIKELY, not Confirmed: CC BY 4.0, inferred from the dataset's published terms; the licence record of this copy was not read | binary masks to signed-distance fields, marching cubes, Taubin smoothing, quadric decimation. Skin: CT threshold (HU above -300, largest component, holes filled). Lung vessels: CT iso-surface (HU above -470) inside the eroded lung masks, small pieces removed. **Changes were made.** |
| Brain ghost (cortex, cerebellum, brainstem) | Template cortex (fsaverage, FreeSurfer lineage; Fischl et al. 1999, doi 10.1002/(sici)1097-0193(1999)8:4<272::aid-hbm10>3.0.co;2-4) and MNI152NLin2009cAsym aseg (Fonov et al. 2011, doi 10.1016/j.neuroimage.2010.07.033), decimated here (cortex about 3,000 vertices per hemisphere in the lite scene) | fsaverage: Suspected (no licence file found); MNI: Confirmed permissive text | affine ICP fit of the template into the subject's brain mask. **ILLUSTRATIVE: the folds are the template's, not this subject's.** The subject's own brain segmentation (no folds) is in `SW_BRAIN_CT`, hidden by default. |
| Look | glow, halos, colours, translucency, smoke | none | artistic rendering choices; not tissue properties |

The subject has a pronounced forward head posture and raised arms; this is shown as recorded. Not for diagnosis.
Builder: `tools/build_torso_scene.py` (sha256 prefix 23cea36ce451fdc9).
