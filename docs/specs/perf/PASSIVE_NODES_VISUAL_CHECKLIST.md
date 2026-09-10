# Passive Nodes Visual Checklist

Use this checklist with the reference workspace at `tests/fixtures/passive_nodes/reference_flowchart.cxproj`.

- Open the reference workspace and confirm the passive flowchart plus input-hidden Browse-mode Media Panels load without a compatibility prompt.
- If the repo has moved since the fixture was generated, relink the Media Panels to `tests/fixtures/passive_nodes/reference_preview.png` and `tests/fixtures/passive_nodes/reference_preview.pdf` with the inspector Browse buttons before continuing.
- Verify the flowchart can be recreated from the existing layout: mixed flowchart silhouettes are present, every flowchart node shows four exposed handles, and the decision branches are distinguished by edge labels rather than branch-specific port names.
- Confirm the main authored path reads cleanly after open: `Start -> Capture Request -> Ready for Review? -> Review Packet -> Revise -> Approval Board -> Archive -> Complete`, while the `Needs input` branch still targets `Stakeholder Input`.
- Verify per-node overrides render after open: the decision, document, input/output, planning card, and annotation note keep their distinct passive colors while Media Panel uses active-node chrome.
- Verify the two Media Panels derive image and PDF mode from their authored sources, show the local PNG and page 1 of the local reference PDF, and retain one stable size.
- Toggle Source input on one Media Panel and confirm Browse/repair/source replacement becomes unavailable, the dormant authored preview clears, and the waiting message remains explicit; hide the input again and confirm the authored preview returns.
- Optional file check: open `tests/fixtures/passive_nodes/reference_flowchart.cxproj` in a text editor and confirm the flowchart edges and exposed-port overrides use only `top`, `right`, `bottom`, and `left`; there should be no `flow_in`, `flow_out`, `branch_a`, or `branch_b` keys left in the fixture.
- Reopen the project and confirm the Media Panel image/PDF previews, exact Source exposure state, four flowchart handles, edge labels, and node colors still render.
- Open a passive node style dialog and a flow-edge style dialog, confirm the project presets `Review Accent` and `Review Loop` are available, apply one, then use reset to confirm presets and overrides behave correctly after reopen.
- Click `Run` and confirm passive flowchart nodes stay excluded; an exposed Media Panel Source participates only through its active data input, while input-hidden Browse mode continues to display authored media without requiring execution.
