# HCC Stage 42 — all remaining 12 original PV DICOM source pixel candidates verified (2026-11-02)

**Original source patient shards:** [GitHub Actions #41434645131](https://github.com/kimtk94/Codex/actions/runs/41434645131): **12/12 patient jobs SUCCESS** with original LiverHccSeg v1.1 NIfTI and CRC-verified original source DICOM member pixel-array comparisons. Its initial *aggregate* step failed only because `numpy` was omitted from the aggregate-only runner dependency installation; the 12 source artifacts were all uploaded and valid.

**Independent repaired aggregate:** [Actions #41435720562](https://github.com/kimtk94/Codex/actions/runs/41435720562) **SUCCESS**. All original 12 source artifacts were downloaded from frozen run #41434645131 and integrated **without any source DICOM/NIfTI refetch or pixel recomputation**. Frozen artifact `13136387504`, SHA256 `225c80f0e9c637d22c64aa341425f3c4b583021ebd453ddcbb7a06cca97aa001`.

## Actual measured source evidence
- Frozen 14 MRI candidates, 2 Stage41 complete original PV↔DICOM full3D technical source series links confirmed.
- Remaining **12/12 patient source-pixel candidate jobs completed**.
- **75** Stage39 geometry-compatible original source DICOM directory candidates examined (83 from all 14 minus 8 already covered Stage40 pilot).
- **225/225** original DICOM individual source pixel comparisons valid (three source images per candidate).
- **12/12** of the remaining MRI patients had **exactly one** distinctive high 2D original DICOM↔PV NIfTI source-pixel-pattern candidate (fixed 48x48, eight in-plane transforms and original NIfTI slice search).
- **0/12** newly promoted to full3D verified source-series identity by this pixel-screening stage alone.
- No whole-source ZIP file MD5 recomputed; downloaded original ZIP members CRC verified.

## Frozen scientific decisions
- Stage42 is **source-imaging candidate discovery only**; technical full3D image provenance still only **2/14** until Stage43 full-volume comparison.
- Stage43 full-3D 12-candidate batch [#41436023580](https://github.com/kimtk94/Codex/actions/runs/41436023580) launched after independent Stage42 aggregate; must review actual 12-case output, not assume GO.
- Qualified independent radiologist review: NOT_ASSESSED.
- Image acquisition before relevant HCC treatment: NOT_ASSESSED.
- Exact MRI-index tumor and sequenced GDC RNA tissue/portion/aliquot origin: NOT_ASSESSED.
- Clinical eligible n **NOT_ASSESSED**; MRI–RNA biological tests **0/12**; clinical/biological claim ceiling **S0**.

Scripts: `research/hcc/ci/mri14_stage42_remaining_source_pixel_candidates.py`. Workflows: `.github/workflows/hcc-stage42-remaining12-source-pixel.yml`, `.github/workflows/hcc-stage42-verified-artifact-aggregate.yml`.
