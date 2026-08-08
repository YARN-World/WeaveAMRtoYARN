"""The step navigator: one button per rule package, a graph under each.

Rendered on the server because each step carries an SVG, and shipping fifty of
them as JSON for the page to assemble gains nothing. Graphs sit in
``<template>`` elements so the browser parses them once and swaps them in on
demand rather than re-parsing on every click.
"""

from __future__ import annotations

import html

from .tracing import TraceStep


def _escape(value) -> str:
    return html.escape(str(value))


def _diffBar(step: TraceStep) -> str:
    cssClass = "da" if step.changed else "dn"
    return (
        '<div class="diff-bar"><span class="diff-label">diff:</span>'
        f'<span class="{cssClass}">{_escape(step.summary())}</span></div>'
    )


def _ruleList(step: TraceStep, namespace: str, position: int) -> str:
    """The package's rules, and what each matched going in.

    Labelled "eligible" rather than "fired" on purpose: GREW reports no firing,
    and a package running to a fixed point can leave an eligible rule unfired.
    """
    if not step.rules:
        return ""

    rows = []
    for index, entry in enumerate(sorted(step.rules, key=lambda r: -r.count)):
        badge = "" if entry.eligible else "no"
        if entry.error:
            badge = "err"
        matches = ""
        for matchIndex, match in enumerate(entry.matches):
            bindings = match.get("matching", {}).get("nodes", {})
            if not bindings:
                continue
            nodes = ",".join(sorted(bindings.values()))
            pairs = " · ".join(
                f"<b>{_escape(k)}</b>={_escape(v)}" for k, v in sorted(bindings.items())
            )
            matches += (
                f'<div class="match-row" '
                f"onclick=\"SN['{namespace}'].highlight({position},'{_escape(nodes)}')\">"
                f"{pairs}</div>"
            )
        rows.append(
            f'<div class="rule-entry">'
            f'<div class="rule-hdr">'
            f'<span class="rule-name">{_escape(entry.rule.name)}</span>'
            f'<span class="rule-badge {badge}">{_escape(entry.summary())}</span>'
            f"</div>"
            f'<div class="rule-body open">{matches}</div>'
            f"</div>"
        )

    eligible = sum(1 for entry in step.rules if entry.eligible)
    return (
        f'<div class="rule-head">{eligible} of {len(step.rules)} rules eligible '
        f'<span class="rule-hint" title="GREW reports no firing trace. A rule '
        f'eligible here may still not fire: the package runs to a fixed point '
        f'and its rules can destroy each other’s matches.">?</span></div>'
        + "".join(rows)
    )


def renderSteps(steps: list[TraceStep], namespace: str = "grs") -> str:
    """Return the navigator as an HTML fragment."""
    buttons = []
    templates = []

    for position, step in enumerate(steps):
        cssClass = "snav-btn" + (" changed" if step.changed else "")
        buttons.append(
            f'<button class="{cssClass}" '
            f"onclick=\"SN['{namespace}'].show({position})\">"
            f"{_escape(step.name)}</button>"
        )

        title = "Initial graph" if position == 0 else _escape(step.name)
        info = (
            f'<h2 class="panel-title">{title}</h2>'
            f'<div class="step-note">{_escape(step.summary())}</div>'
            + _ruleList(step, namespace, position)
        )
        graph = _diffBar(step) + f'<div class="graph-wrap">{step.svg}</div>'
        templates.append(
            f'<template id="{namespace}-rule-src-{position}">{info}</template>'
            f'<template id="{namespace}-graph-src-{position}">{graph}</template>'
        )

    return f"""
<div class="snav-bar" id="{namespace}-nav-bar">
  <button class="sarrow" id="{namespace}-prev"
          onclick="SN['{namespace}'].navigate(-1)">&#8592;</button>
  {''.join(buttons)}
  <button class="sarrow" id="{namespace}-next"
          onclick="SN['{namespace}'].navigate(+1)">&#8594;</button>
</div>
<div class="step-main">
  <div class="rule-panel" id="{namespace}-rule-panel"></div>
  <div class="graph-panel" id="{namespace}-graph-panel"></div>
</div>
{''.join(templates)}
<script>
(function() {{
  if (!window.SN) window.SN = {{}};
  var N = {len(steps)}, cur = 0;
  var ns = {{
    show: function(idx) {{
      cur = idx;
      var bar = document.getElementById('{namespace}-nav-bar');
      if (bar) bar.querySelectorAll('.snav-btn').forEach(
        function(b, i) {{ b.classList.toggle('active', i === idx); }});
      var pp = document.getElementById('{namespace}-prev');
      var np = document.getElementById('{namespace}-next');
      if (pp) pp.disabled = (idx === 0);
      if (np) np.disabled = (idx === N - 1);
      var rp = document.getElementById('{namespace}-rule-panel');
      var gp = document.getElementById('{namespace}-graph-panel');
      var rs = document.getElementById('{namespace}-rule-src-' + idx);
      var gs = document.getElementById('{namespace}-graph-src-' + idx);
      if (rp && rs) rp.innerHTML = rs.innerHTML;
      if (gp && gs) gp.innerHTML = gs.innerHTML;
    }},
    navigate: function(d) {{ ns.show(Math.max(0, Math.min(N - 1, cur + d))); }},
    highlight: function(idx, nodes) {{
      // Re-drawn on demand: one SVG per match up front would be hundreds.
      var gp = document.getElementById('{namespace}-graph-panel');
      if (!gp) return;
      fetch('/step_svg', {{
        method: 'POST',
        headers: {{'Content-Type': 'application/json'}},
        body: JSON.stringify({{step: idx, nodes: nodes.split(',')}})
      }}).then(function(r) {{ return r.json(); }}).then(function(d) {{
        if (d.svg) gp.querySelector('.graph-wrap').innerHTML = d.svg;
      }});
    }}
  }};
  window.SN['{namespace}'] = ns;
  ns.show(0);
}})();
</script>
"""
