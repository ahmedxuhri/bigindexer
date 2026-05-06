"""
BGI HTML Visualizer — generates a self-contained single-file HTML graph visualization.

Layout   : D3 force-directed (v7, bundled inline via CDN fetch at build time → inlined)
Nodes    : coloured by dominant COV token; size ∝ confidence
Edges    : opacity/width ∝ edge confidence; stroke colour by type (HARD/PREDICTED/GHOST)
Clusters : convex-hull overlay, labelled
Sidebar  : click node → shows unit metadata
"""
from __future__ import annotations

import json
import textwrap
import urllib.request
from pathlib import Path

# ── COV token → colour palette ───────────────────────────────────────────────
_TOKEN_COLOURS: dict[str, str] = {
    "TRANSFORM":      "#4e79a7",
    "PERSIST":        "#f28e2b",
    "FETCH":          "#e15759",
    "MUTATE":         "#76b7b2",
    "VALIDATE":       "#59a14f",
    "LOG":            "#edc948",
    "MEASURE":        "#b07aa1",
    "EMIT":           "#ff9da7",
    "SUBSCRIBE":      "#9c755f",
    "ROUTE":          "#bab0ac",
    "DELEGATE":       "#d37295",
    "AUTHENTICATE":   "#a0cbe8",
    "AUTHORIZE":      "#ffbe7d",
    "SCOPE":          "#8cd17d",
    "COMPOSE":        "#86bcb6",
    "SANITIZE":       "#e15759",
    "ASYNC":          "#aecdc0",
    "INTAKE":         "#f1ce63",
    "UNKNOWN":        "#cccccc",
}

_EDGE_COLOURS: dict[str, str] = {
    "HARD":           "#e15759",
    "PREDICTED":      "#4e79a7",
    "GHOST":          "#bab0ac",
    "RESURRECTED":    "#59a14f",
}

_D3_CDN = "https://cdn.jsdelivr.net/npm/d3@7/dist/d3.min.js"


def _fetch_d3(timeout: int = 15) -> str:
    """Download D3 v7 minified source to inline into HTML."""
    try:
        with urllib.request.urlopen(_D3_CDN, timeout=timeout) as r:
            return r.read().decode("utf-8")
    except Exception:
        # Fallback: use CDN link (not self-contained but still functional)
        return None  # type: ignore[return-value]


def _dominant_token(unit: dict) -> str:
    """Return the first non-structural token, or UNKNOWN."""
    structural = {"COV.ASYNC", "COV.INTAKE"}
    for t in unit.get("tokens", []):
        bare = t.replace("COV.", "")
        if t not in structural:
            return bare
    return "UNKNOWN"


def _node_colour(unit: dict) -> str:
    tok = _dominant_token(unit)
    return _TOKEN_COLOURS.get(tok, "#cccccc")


def _build_vis_data(graph: dict) -> dict:
    """Reshape graph JSON into D3-friendly nodes/links/clusters/legend."""
    units = graph.get("units", [])
    edges = graph.get("edges", [])
    clusters = graph.get("clusters", [])

    # Build id → index map for D3 link references
    id_to_idx = {u["id"]: i for i, u in enumerate(units)}

    nodes = []
    for u in units:
        tok = _dominant_token(u)
        nodes.append({
            "id": u["id"],
            "label": u["id"].split(".")[-1] if "." in u["id"] else u["id"],
            "full_id": u["id"],
            "tokens": u.get("tokens", []),
            "confidence": u.get("confidence", 0.5),
            "source": u.get("source", ""),
            "language": u.get("language", ""),
            "line_range": u.get("line_range", [0, 0]),
            "cluster": u.get("cluster"),
            "is_seam": u.get("is_seam", False),
            "dominant_token": tok,
            "colour": _node_colour(u),
            "radius": max(6, min(18, int(u.get("confidence", 0.5) * 16))),
        })

    links = []
    for e in edges:
        src = id_to_idx.get(e["source"])
        tgt = id_to_idx.get(e["target"])
        if src is None or tgt is None:
            continue
        links.append({
            "source": src,
            "target": tgt,
            "source_id": e["source"],
            "target_id": e["target"],
            "type": e.get("type", "HARD"),
            "confidence": e.get("confidence", 1.0),
            "key": e.get("key", ""),
            "lock": e.get("lock", ""),
            "colour": _EDGE_COLOURS.get(e.get("type", "HARD"), "#999"),
        })

    cluster_data = []
    for c in clusters:
        tok = c.get("dominant_tokens", ["UNKNOWN"])[0].replace("COV.", "")
        cluster_data.append({
            "id": c["id"],
            "size": c.get("size", 0),
            "probability": c.get("probability", 0),
            "is_hard": c.get("is_hard", False),
            "dominant_token": tok,
            "colour": _TOKEN_COLOURS.get(tok, "#cccccc"),
            "members": c.get("members", []),
        })

    legend = [
        {"token": tok, "colour": col}
        for tok, col in _TOKEN_COLOURS.items()
        if tok not in ("ASYNC", "INTAKE")
    ]

    return {
        "nodes": nodes,
        "links": links,
        "clusters": cluster_data,
        "legend": legend,
        "stats": graph.get("stats", {}),
    }


def _html_template(vis_data: dict, d3_source: str | None, title: str) -> str:
    vis_json = json.dumps(vis_data, separators=(",", ":"))

    if d3_source:
        d3_tag = f"<script>{d3_source}</script>"
    else:
        d3_tag = f'<script src="{_D3_CDN}"></script>'

    return textwrap.dedent(f"""\
    <!DOCTYPE html>
    <html lang="en">
    <head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{title}</title>
    <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:'Segoe UI',system-ui,sans-serif;background:#0f1117;color:#e0e0e0;display:flex;height:100vh;overflow:hidden}}
    #sidebar{{width:320px;min-width:260px;background:#181c24;border-right:1px solid #2a2d36;display:flex;flex-direction:column;overflow:hidden}}
    #sidebar-header{{padding:16px;border-bottom:1px solid #2a2d36}}
    #sidebar-header h1{{font-size:15px;font-weight:700;color:#fff;letter-spacing:.5px}}
    #sidebar-header .stats{{margin-top:8px;font-size:11px;color:#888;line-height:1.6}}
    #sidebar-header .stats span{{color:#ccc}}
    #legend{{padding:12px 16px;border-bottom:1px solid #2a2d36;overflow-y:auto;max-height:220px}}
    #legend h2{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#555;margin-bottom:8px}}
    .legend-item{{display:flex;align-items:center;gap:8px;margin-bottom:4px;font-size:12px;color:#aaa}}
    .legend-dot{{width:10px;height:10px;border-radius:50%;flex-shrink:0}}
    #info-panel{{flex:1;padding:16px;overflow-y:auto}}
    #info-panel h2{{font-size:11px;text-transform:uppercase;letter-spacing:1px;color:#555;margin-bottom:10px}}
    #info-content{{font-size:12px;line-height:1.7;color:#aaa}}
    #info-content .row{{display:flex;gap:6px;margin-bottom:3px}}
    #info-content .key{{color:#666;min-width:90px;flex-shrink:0}}
    #info-content .val{{color:#ddd;word-break:break-all}}
    #info-content .tag{{display:inline-block;padding:1px 7px;border-radius:10px;font-size:11px;margin:2px 2px 0 0;background:#2a2d36}}
    #graph-area{{flex:1;position:relative;overflow:hidden}}
    svg{{width:100%;height:100%;background:#0f1117}}
    .edge{{stroke-opacity:.55}}
    .node circle{{stroke:#0f1117;stroke-width:1.5px;cursor:pointer;transition:opacity .15s}}
    .node circle:hover{{stroke:#fff;stroke-width:2px}}
    .node.selected circle{{stroke:#fff;stroke-width:2.5px}}
    .node-label{{font-size:9px;fill:#888;pointer-events:none;text-anchor:middle}}
    .hull{{fill-opacity:.06;stroke-opacity:.25;stroke-width:1.5px}}
    .hull-label{{font-size:10px;fill-opacity:.5;pointer-events:none}}
    #controls{{position:absolute;top:12px;right:12px;display:flex;gap:6px;flex-direction:column}}
    .ctrl-btn{{background:#1e2230;border:1px solid #2a2d36;color:#aaa;padding:6px 10px;border-radius:6px;cursor:pointer;font-size:12px;white-space:nowrap}}
    .ctrl-btn:hover{{background:#252a38;color:#fff}}
    #edge-filter{{position:absolute;bottom:12px;right:12px;background:#1e2230;border:1px solid #2a2d36;border-radius:8px;padding:10px 14px;font-size:12px}}
    #edge-filter h3{{color:#555;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:6px}}
    .ef-row{{display:flex;align-items:center;gap:6px;margin-bottom:4px;cursor:pointer}}
    .ef-row input{{accent-color:#4e79a7;cursor:pointer}}
    .ef-label{{color:#aaa}}
    </style>
    </head>
    <body>
    <div id="sidebar">
      <div id="sidebar-header">
        <h1>🧠 BGI Graph</h1>
        <div class="stats" id="stats-block"></div>
      </div>
      <div id="legend">
        <h2>COV Tokens</h2>
        <div id="legend-items"></div>
      </div>
      <div id="info-panel">
        <h2>Unit Inspector</h2>
        <div id="info-content"><span style="color:#444">Click any node</span></div>
      </div>
    </div>
    <div id="graph-area">
      <svg id="svg"></svg>
      <div id="controls">
        <button class="ctrl-btn" id="btn-reset">⟲ Reset view</button>
        <button class="ctrl-btn" id="btn-labels">Toggle labels</button>
        <button class="ctrl-btn" id="btn-hulls">Toggle clusters</button>
      </div>
      <div id="edge-filter">
        <h3>Edge types</h3>
        <label class="ef-row"><input type="checkbox" value="HARD" checked> <span class="ef-label" style="color:#e15759">■</span> <span class="ef-label">Hard</span></label>
        <label class="ef-row"><input type="checkbox" value="PREDICTED" checked> <span class="ef-label" style="color:#4e79a7">■</span> <span class="ef-label">Predicted</span></label>
        <label class="ef-row"><input type="checkbox" value="GHOST" checked> <span class="ef-label" style="color:#bab0ac">■</span> <span class="ef-label">Ghost</span></label>
        <label class="ef-row"><input type="checkbox" value="RESURRECTED" checked> <span class="ef-label" style="color:#59a14f">■</span> <span class="ef-label">Resurrected</span></label>
      </div>
    </div>

    {d3_tag}
    <script>
    const DATA = {vis_json};

    // ── Stats ──────────────────────────────────────────────────────────────
    const s = DATA.stats;
    document.getElementById('stats-block').innerHTML =
      `<div>Units: <span>${{s.units||0}}</span> &nbsp; Edges: <span>${{s.edges||0}}</span></div>` +
      `<div>Clusters: <span>${{s.clusters||0}}</span> &nbsp; Hard: <span>${{s.hard||0}}</span></div>`;

    // ── Legend ─────────────────────────────────────────────────────────────
    const legEl = document.getElementById('legend-items');
    DATA.legend.forEach(l => {{
      const d = document.createElement('div');
      d.className = 'legend-item';
      d.innerHTML = `<div class="legend-dot" style="background:${{l.colour}}"></div>${{l.token}}`;
      legEl.appendChild(d);
    }});

    // ── D3 setup ───────────────────────────────────────────────────────────
    const svg = d3.select('#svg');
    const W = () => document.getElementById('graph-area').clientWidth;
    const H = () => document.getElementById('graph-area').clientHeight;

    const g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.05, 8]).on('zoom', e => g.attr('transform', e.transform)));

    const nodes = DATA.nodes.map(d => ({{...d}}));
    const links = DATA.links.map(d => ({{...d}}));
    const clusterMap = {{}};
    DATA.clusters.forEach(c => {{ c.members.forEach(m => {{ clusterMap[m] = c; }}); }});

    // Edge type filter state
    const activeTypes = new Set(['HARD','PREDICTED','GHOST','RESURRECTED']);
    document.querySelectorAll('#edge-filter input').forEach(cb => {{
      cb.addEventListener('change', () => {{
        cb.checked ? activeTypes.add(cb.value) : activeTypes.delete(cb.value);
        updateEdgeVisibility();
      }});
    }});
    function updateEdgeVisibility() {{
      edgeSel.style('display', d => activeTypes.has(d.type) ? null : 'none');
    }}

    // ── Hull layer ─────────────────────────────────────────────────────────
    const hullLayer = g.append('g').attr('class', 'hull-layer');
    let showHulls = true;

    function hullPath(pts) {{
      const hull = d3.polygonHull(pts);
      if (!hull) return null;
      const pad = 20;
      const cx = d3.mean(hull, p => p[0]);
      const cy = d3.mean(hull, p => p[1]);
      const padded = hull.map(p => [cx + (p[0]-cx)*(1+pad/Math.max(1,Math.hypot(p[0]-cx,p[1]-cy))), cy + (p[1]-cy)*(1+pad/Math.max(1,Math.hypot(p[0]-cx,p[1]-cy)))]);
      return "M" + padded.map(p => p.join(",")).join("L") + "Z";
    }}

    function drawHulls() {{
      hullLayer.selectAll('*').remove();
      if (!showHulls) return;
      DATA.clusters.forEach(c => {{
        const pts = nodes.filter(n => c.members.includes(n.full_id) && n.x != null).map(n => [n.x, n.y]);
        if (pts.length < 2) return;
        const path = pts.length < 3 ? null : hullPath(pts);
        if (!path) return;
        hullLayer.append('path').attr('class','hull').attr('d', path)
          .attr('fill', c.colour).attr('stroke', c.colour);
        const cx = d3.mean(pts, p => p[0]);
        const cy = d3.mean(pts, p => p[1]);
        hullLayer.append('text').attr('class','hull-label').attr('x', cx).attr('y', cy)
          .attr('text-anchor','middle').attr('fill', c.colour)
          .text(c.id.length > 24 ? c.id.slice(0,22)+'…' : c.id);
      }});
    }}

    // ── Edges ──────────────────────────────────────────────────────────────
    const edgeSel = g.append('g').attr('class','edges')
      .selectAll('line').data(links).join('line')
      .attr('class','edge')
      .attr('stroke', d => d.colour)
      .attr('stroke-width', d => Math.max(0.5, d.confidence * 2))
      .attr('stroke-opacity', d => 0.15 + d.confidence * 0.45);

    // ── Nodes ──────────────────────────────────────────────────────────────
    const nodeSel = g.append('g').attr('class','nodes')
      .selectAll('g').data(nodes).join('g').attr('class','node')
      .call(d3.drag()
        .on('start', (e,d) => {{ if (!e.active) sim.alphaTarget(0.3).restart(); d.fx=d.x; d.fy=d.y; }})
        .on('drag',  (e,d) => {{ d.fx=e.x; d.fy=e.y; }})
        .on('end',   (e,d) => {{ if (!e.active) sim.alphaTarget(0); d.fx=null; d.fy=null; }}))
      .on('click', (e,d) => showInfo(d));

    nodeSel.append('circle')
      .attr('r', d => d.radius)
      .attr('fill', d => d.colour)
      .attr('opacity', d => 0.7 + d.confidence * 0.3);

    let showLabels = false;
    const labelSel = nodeSel.append('text').attr('class','node-label')
      .attr('dy', d => d.radius + 11)
      .text(d => d.label)
      .style('display', 'none');

    // ── Simulation ─────────────────────────────────────────────────────────
    const sim = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id((_,i)=>i).distance(d => 60 + (1-d.confidence)*80).strength(0.4))
      .force('charge', d3.forceManyBody().strength(-120))
      .force('center', d3.forceCenter(W()/2, H()/2))
      .force('collision', d3.forceCollide(d => d.radius + 4))
      .on('tick', ticked)
      .on('end', drawHulls);

    function ticked() {{
      edgeSel
        .attr('x1', d => d.source.x).attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x).attr('y2', d => d.target.y);
      nodeSel.attr('transform', d => `translate(${{d.x}},${{d.y}})`);
      if (sim.alpha() < 0.05) drawHulls();
    }}

    // ── Info panel ─────────────────────────────────────────────────────────
    let selectedNode = null;
    function showInfo(d) {{
      if (selectedNode) d3.select(selectedNode).classed('selected', false);
      selectedNode = nodeSel.filter(n => n === d).node();
      d3.select(selectedNode).classed('selected', true);
      const tokens = d.tokens.map(t => `<span class="tag" style="background:${{d.colour}}22;border:1px solid ${{d.colour}}44">${{t.replace('COV.','')}}</span>`).join('');
      document.getElementById('info-content').innerHTML =
        `<div class="row"><span class="key">ID</span><span class="val">${{d.full_id}}</span></div>` +
        `<div class="row"><span class="key">Confidence</span><span class="val">${{(d.confidence*100).toFixed(1)}}%</span></div>` +
        `<div class="row"><span class="key">Language</span><span class="val">${{d.language}}</span></div>` +
        `<div class="row"><span class="key">Lines</span><span class="val">${{d.line_range[0]}}–${{d.line_range[1]}}</span></div>` +
        `<div class="row"><span class="key">Source</span><span class="val">${{d.source}}</span></div>` +
        `<div class="row"><span class="key">Cluster</span><span class="val">${{d.cluster||'—'}}</span></div>` +
        `<div class="row"><span class="key">Seam</span><span class="val">${{d.is_seam?'✓':'—'}}</span></div>` +
        `<div class="row" style="margin-top:6px"><span class="key">Tokens</span><span class="val">${{tokens}}</span></div>`;
    }}

    // ── Controls ───────────────────────────────────────────────────────────
    document.getElementById('btn-reset').onclick = () => {{
      svg.transition().duration(500).call(
        d3.zoom().transform, d3.zoomIdentity.translate(W()/2, H()/2).scale(1));
      sim.alpha(0.3).restart();
    }};
    document.getElementById('btn-labels').onclick = () => {{
      showLabels = !showLabels;
      labelSel.style('display', showLabels ? null : 'none');
    }};
    document.getElementById('btn-hulls').onclick = () => {{
      showHulls = !showHulls;
      drawHulls();
    }};

    updateEdgeVisibility();
    </script>
    </body>
    </html>
    """)


def generate_html(graph: dict, output_path: str, inline_d3: bool = True, title: str = "BGI Graph") -> None:
    """
    Write a self-contained HTML visualization of *graph* to *output_path*.

    Args:
        graph:        BGI graph dict (output of serialize_graph / bgi-graph.json).
        output_path:  Destination .html file path.
        inline_d3:    If True, attempt to fetch D3 source and embed inline
                      (fully offline-capable). Falls back to CDN <script> tag.
        title:        HTML <title> and header.
    """
    d3_src = _fetch_d3() if inline_d3 else None
    vis_data = _build_vis_data(graph)
    html = _html_template(vis_data, d3_src, title)
    Path(output_path).write_text(html, encoding="utf-8")
