# Rotor LLP Airworthiness FEA Review Deck Showcase

This folder is a demonstration package for the Project Review Deck exporter. It is not a compliance finding, certification report, engineering approval, or substantiation package.

The scenario is a rotor life-limited part review framed around EASA CS-E 515/840 style questions with an FAA Part 33.70 comparison. It uses portable certification references, managed evidence, and public PyAnsys Rotor 67 result images.

## Included Artifacts

- `rotor_llp_review_showcase.cxproj` contains two workspaces: certification review map and evidence binder.
- `rotor_llp_review_showcase.data/` contains managed sidecar artifacts referenced by `saved://` refs and `preview_ref` JSON. Regulatory evidence is copied from the `airworthiness-compliance-engineer` skill public-source corpus, and portable Rotor 67 result images are copied from the public PyAnsys documentation page listed below.
- `templates/corex_airworthiness_template.pptx` is a minimal corporate-style template used to exercise template loading.
- `exports/rotor_llp_review_showcase.pptx` was generated through the Project Review Deck exporter using the template path.

## What The Export Demonstrates

- Workspace snapshot slides for Markdown-rich review notes, image panels, PDF panels, and web viewer nodes.
- Managed PNG evidence, including PyAnsys Rotor 67 result images, a generated margin summary, regulatory visual extracts, and web-source previews.
- Managed PDF evidence with authored Media Panel pages: EASA CM-PIFS-007 page 3 and FAA AC 33.70-1 page 2.
- A local managed HTML guide opened through a web viewer node, paired with a managed preview PNG.
- Unsupported CSV, Markdown, HTML, and external-path evidence warnings that appear on the exported issues slide.
- Optional `.pptx` template inheritance through the existing Project Review Deck writer.

## Reference Links

- [EASA Easy Access Rules for Engines CS-E](https://www.easa.europa.eu/en/document-library/easy-access-rules/easy-access-rules-engines-cs-e)
- [EASA CM-PIFS-007](https://www.easa.europa.eu/en/document-library/product-certification-consultations/easa-cm-pifs-007)
- [EASA CM-PIFS-013 consultation/publication page](https://www.easa.europa.eu/en/document-library/product-certification-consultations/integrity-nickel-powder-metallurgy-rotating)
- [eCFR 14 CFR 33.70](https://www.ecfr.gov/current/title-14/chapter-I/subchapter-C/part-33/subpart-E/section-33.70)
- [FAA AC 33.70-1](https://www.faa.gov/airports/resources/advisory_circulars/index.cfm/go/document.information/documentNumber/33.70-1)
- [FAA AC 33.70-4](https://www.faa.gov/regulations_policies/advisory_circulars/index.cfm/go/document.information/documentID/1042036)
- [PyMechanical Rotor 67 inverse-solving example](https://embedding.examples.mechanical.docs.pyansys.com/examples/02_technology_showcase/Rotor_Blade_Inverse_solve.html)

## Re-export

Open `rotor_llp_review_showcase.cxproj`, then use `File > Export Project Review Deck...`. Select the title, one Snapshot slide per workspace, all managed evidence, and the issues slide; leave the duplicate saved-view slides unselected. Choose `templates/corex_airworthiness_template.pptx` as the optional template and export to a new `.pptx`.
