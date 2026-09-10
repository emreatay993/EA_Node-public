# Node title icons

Base-program built-in node title icons are owned by `ea_node_editor.nodes.builtins.icon_catalog.BUILTIN_NODE_ICONS`, not by individual built-in node modules.

Use paths relative to this directory for base-program built-ins. The title-icon resolver accepts `.svg`, `.png`, `.jpg`, and `.jpeg` files from this asset root.

Repo-managed built-in `.svg` title icons are theme-aware. The scene payload derives `icon_theme_aware=True` for eligible built-in SVG assets, and `GraphNodeHeaderLayer.qml` tints those icons with the node header text color so light and dark graph themes track the title text.

Add-ons and plugins must ship their own icon assets and declare paths relative to the add-on file or package root. Add-on icon paths do not fall back to this base-program asset directory, and absolute add-on icon paths are rejected.

Raster icons (`.png`, `.jpg`, `.jpeg`) and add-on/plugin icons keep their authored colors unless a future explicit contract opts them into theme tinting.

QML receives the derived `icon_source` and `icon_theme_aware` payload fields and should stay generic. Do not add per-node title-icon conditions in QML.
