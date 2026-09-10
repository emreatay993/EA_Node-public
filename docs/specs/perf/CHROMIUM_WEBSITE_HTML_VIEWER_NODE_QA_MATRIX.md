# Chromium Website HTML Viewer Node QA Matrix

- Updated: `2026-06-19`
- Packet set: `CHROMIUM_WEBSITE_HTML_VIEWER_NODE` (`P01` through `P05`)
- Scope: final retained proof for the reusable Chromium/QWebEngine navigation-normalization layer, the generic bridge-free `web_page` surface route, and the passive `web.page_viewer` built-in node for websites and local HTML files.

## Locked Scope

- `web.page_viewer` is a passive built-in node with `runtime_behavior="passive"`, `surface_family="web"`, and `surface_variant="page_viewer"`.
- The generic page route uses `content_kind="web_page"` and `WebPageHost.qml`; it stays separate from the trusted Excalidraw `web_editor` route and does not force an Excalidraw migration.
- Generic user-provided pages do not receive a privileged QWebChannel graph/project bridge by default. The Excalidraw `WebSurfaceBridge` remains limited to the trusted COREX-owned editor path.
- Future Chromium consumers provide URL or local HTML payloads through the shared navigation-normalization layer (`WebNavigationDecision`) plus the `web_page` surface payload, configured by a single `start_location` property.
- `file`, `http`, and `https` targets are normalized to a safe load URL; unsupported schemes and embedded credentials are rejected with a visible reason.
- Local HTML files and relative CSS, JavaScript, and image assets are supported without internet access.
- `persist_browser_state` is enabled by default so the surface reopens at the user's last visited location and zoom; WebEngine cookies, cache, session storage, credentials, and loaded page content remain in the WebEngine app/runtime profile and are not persisted into project `.cxproj` documents.
- Detaching a live graph Web Page Viewer moves the existing WebEngine session into the detached window and restores it on close; it must not create a second live browser/audio session.
- The v1 scope is not a scraper, browser automation node, DOM extractor, credential/session manager, multi-tab browser, proxy/VPN/SSO integration, or arbitrary third-party plugin web UI registration surface.

## Future Consumer Contract

| Consumer Need | Required Route | Safe Default |
|---|---|---|
| Open an external website or local HTML file | Normalize the target through `WebNavigationDecision`, then project a `web_page` payload through `contentFullscreenBridge` / `WebPageHost.qml` | No privileged graph/project bridge is exposed to page JavaScript |
| Reject unsafe input | Rely on normalization to reject unsupported schemes and embedded credentials | An invalid location stays visible with a denial reason and never loads |
| Reopen where the user left off | Keep `persist_browser_state` enabled so the last visited URL and zoom are restored | Only the last URL and zoom round-trip; cookies/cache/credentials never persist |
| Build a trusted application-owned web editor | Use a separate trusted route with an explicit bridge contract, as Excalidraw does through `web_editor` | Generic `web_page` consumers do not inherit that bridge |

## Retained Automated Verification

| Coverage Area | Packet | Primary Requirement Anchors | Command | Recorded Source |
|---|---|---|---|---|
| Generic URL/path normalization, `WebNavigationDecision`, unsupported-scheme and embedded-credential rejection, and QtWebEngine-free availability payloads | `CHROMIUM_WEBSITE_HTML_VIEWER_NODE P01` | `REQ-INT-016`, `REQ-QA-048` | `.\venv\Scripts\python.exe -m pytest tests/test_webengine_navigation_policy.py tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/chromium_website_html_viewer_node/P01_webengine_foundation_and_policy_WRAPUP.md` (`3fae0d141838eee7a4d625bbc92efb073203d531`) |
| Generic `web_page` graph/fullscreen/detached surfaces, browser controls, invalid-location denial UI, WebEngine-unavailable fallback, and bridge-free separation from Excalidraw `web_editor` | `CHROMIUM_WEBSITE_HTML_VIEWER_NODE P02` | `REQ-UI-046`, `REQ-INT-016`, `REQ-QA-048` | `.\venv\Scripts\python.exe -m pytest tests/test_content_fullscreen_bridge.py tests/test_passive_graph_surface_host.py tests/test_corex_web_surface_bridge.py --ignore=venv -q` | PASS in `docs/specs/work_packets/chromium_website_html_viewer_node/P02_generic_web_surfaces_WRAPUP.md` (`0b94a9a737333d24909b7775fcec7a40fab468ac`) |
| Passive `web.page_viewer` node registration, Web category palette availability, persisted safe properties, passive execution behavior, serializer round trip, and canonical `web_page` surface contract | `CHROMIUM_WEBSITE_HTML_VIEWER_NODE P03` | `REQ-UI-046`, `REQ-NODE-033`, `REQ-QA-048` | `.\venv\Scripts\python.exe -m pytest tests/test_web_page_viewer_node.py tests/test_passive_node_contracts.py tests/test_registry_validation.py tests/test_serializer.py tests/test_content_fullscreen_bridge.py --ignore=venv -q` | PASS in `docs/specs/work_packets/chromium_website_html_viewer_node/P03_web_page_viewer_node_WRAPUP.md` (`7507cdc2278c2f395703bebc47f7149cbbffc8e3`) |
| Offline local HTML fixture with relative CSS, JavaScript, and image assets; bare-host and `file://` normalization; and last-visited browser-state persistence | `CHROMIUM_WEBSITE_HTML_VIEWER_NODE P04` | `REQ-INT-016`, `REQ-QA-048` | `.\venv\Scripts\python.exe -m pytest tests/test_webengine_navigation_policy.py tests/test_web_page_viewer_node.py tests/test_corex_web_host_assets.py --ignore=venv -q` | PASS in `docs/specs/work_packets/chromium_website_html_viewer_node/P04_offline_intranet_hardening_WRAPUP.md` (`2239fc67c8c583a9e1605b8eede0c9af01e7d92b`) |
| Single-session graph detach lifecycle: borrow the live graph `WebEngineView`, show the canvas placeholder, avoid a standalone detached host, and restore on close/release | Detach regression fix | `REQ-UI-046`, `REQ-QA-048` | `.\venv\Scripts\python.exe -m pytest tests/test_corex_web_surface_bridge.py --ignore=venv -q` | Current regression anchor in `tests/test_corex_web_surface_bridge.py` |

## Final Closeout Commands

| Command | Purpose |
|---|---|
| `.\venv\Scripts\python.exe -m pytest tests/test_webengine_navigation_policy.py tests/test_web_page_viewer_node.py tests/test_content_fullscreen_bridge.py tests/test_corex_web_host_assets.py --ignore=venv -q` | Focused website/HTML viewer regression covering normalization, node payloads, fullscreen routing, and local asset hygiene |
| `.\venv\Scripts\python.exe .\scripts\check_traceability.py` | Proof audit for refreshed requirements, traceability rows, spec index registration, and closeout evidence |
| `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` | Markdown-link audit for the QA matrix, packet evidence paths, and spec index registration |
| `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast` | Final fast regression pass for the integrated branch |

## 2026-05-19 Execution Results

| Command | Result | Notes |
|---|---|---|
| `.\venv\Scripts\python.exe -m pytest tests/test_webengine_navigation_policy.py tests/test_web_page_viewer_node.py tests/test_content_fullscreen_bridge.py tests/test_corex_web_host_assets.py --ignore=venv -q` | `PASS` | Focused website/HTML viewer normalization, payload, fullscreen, and asset-hygiene proof passed after the property-set slim-down. |
| `.\venv\Scripts\python.exe .\scripts\check_traceability.py` | `PASS` | Required proof audit returned `TRACEABILITY CHECK PASS`. |
| `.\venv\Scripts\python.exe .\scripts\check_markdown_links.py` | `PASS` | Markdown-link audit returned `MARKDOWN LINK CHECK PASS`. |
| `.\venv\Scripts\python.exe .\scripts\run_verification.py --mode fast` | `PASS` | Final fast verification returned green after the slimmed `web.page_viewer` contract landed. |

## Manual Test Directives

Ready for manual testing

Run these smoke checks after the P05 closeout branch is merged into the target checkout.

1. Prerequisite: launch a normal desktop Qt session from the project venv with `.\venv\Scripts\python.exe -m ea_node_editor.bootstrap`.
2. Local/offline HTML smoke: add a `Web Page Viewer` node, set `start_location` to `tests\fixtures\web_page_viewer\index.html`, and open fullscreen. Expected result: the local HTML page loads with its relative CSS, JavaScript, and image asset, and no privileged bridge behavior is available to the page.
3. URL smoke: change `start_location` to `example.com`. Expected result: the address is normalized to `https://example.com` and the remote page loads.
4. Invalid-location smoke: set `start_location` to `javascript:alert(1)`. Expected result: the web page surface remains visible and reports a denial reason instead of loading the unsafe target.
5. Persistence smoke: navigate to another page, then save and reopen the project. Expected result: the node reopens at the last visited URL and zoom, while cookies, cache, session storage, credentials, and page content do not appear in the `.cxproj` payload.
6. Detach smoke: play a video in a canvas Web Page Viewer, detach it, and then close the detached window. Expected result: the detached window shows the live page, the canvas shows a detached placeholder, only one audio/video session plays, and closing the window restores the same live page to the canvas.
7. Excalidraw separation smoke: open an existing `Excalidraw Board` and a `Web Page Viewer` in fullscreen. Expected result: Excalidraw still uses the trusted `web_editor` route and generic pages use the separate `web_page` host without inheriting Excalidraw bridge capabilities.

## Residual Risks

- Automated proof remains offscreen-safe and does not prove live browsing in every desktop WebEngine environment.
- Normalization coverage verifies URL/path shaping and unsafe-input rejection, not real enterprise authentication, VPN, proxy, or SSO behavior.
- Future trusted web surfaces must define and prove a separate bridge contract before exposing any privileged page API.
- Browser automation, scraping, DOM extraction, credential persistence, multi-tab browsing, and arbitrary third-party web UI registration remain explicit non-goals.

## Packet Evidence Links

- `docs/specs/work_packets/chromium_website_html_viewer_node/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_MANIFEST.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/CHROMIUM_WEBSITE_HTML_VIEWER_NODE_STATUS.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/P01_webengine_foundation_and_policy_WRAPUP.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/P02_generic_web_surfaces_WRAPUP.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/P03_web_page_viewer_node_WRAPUP.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/P04_offline_intranet_hardening_WRAPUP.md`
- `docs/specs/work_packets/chromium_website_html_viewer_node/P05_closeout_and_future_hooks_WRAPUP.md`
