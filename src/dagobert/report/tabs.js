// Draws the figures of a tab when it shows, each from its JSON: the compact variant on a phone
// (the media of the style element `phone`), with a swipe that scrolls and no toolbar, the template
// of the color scheme; again when either changes. A field of a compact trace that holds `same`
// takes the field of the wide trace at its place.
(() => {
  const phone = matchMedia(document.getElementById('phone').media);
  const light = matchMedia('(prefers-color-scheme: light)');
  const {templates, same} = JSON.parse(document.getElementById('config').textContent);
  const tabs = [...document.querySelectorAll('[role=tab]')];
  let shown;
  const draw = () => {
    for (const div of shown.querySelectorAll('.figure')) {
      const compact = phone.matches;
      const both = JSON.parse(document.getElementById('data-' + div.id).textContent);
      const fig = compact ? both.compact : both.wide;
      fig.data.forEach((trace, i) => {
        for (const field in trace) {
          if (trace[field] === same) trace[field] = both.wide.data[i][field];
        }
      });
      fig.layout.template = templates[light.matches ? 'light' : 'dark'];
      if (compact) {
        // as the theme of the app on a phone: no side margins beyond the axis labels
        fig.layout.dragmode = false;
        fig.layout.margin = {l: 0, r: 0, ...fig.layout.margin};
      }
      // a responsive plot takes the height of its element, which holds nothing else
      div.style.height = (fig.layout.height ?? 450) + 'px';
      Plotly.react(div, fig.data, fig.layout, compact
        ? {responsive: true, displayModeBar: false, doubleClick: false}
        : {responsive: true});
    }
  };
  const show = (tab) => {
    for (const t of tabs) {
      t.setAttribute('aria-selected', String(t === tab));
      document.getElementById(t.getAttribute('aria-controls')).hidden = t !== tab;
    }
    shown = document.getElementById(tab.getAttribute('aria-controls'));
    draw();
  };
  for (const t of tabs) {
    t.addEventListener('click', () => {
      history.replaceState(null, '', '#' + encodeURIComponent(t.dataset.key));
      show(t);
    });
  }
  for (const query of [phone, light]) query.addEventListener('change', draw);
  // the tab of the hash, the first one for a hash that names none or does not decode (`#%E0`)
  let key = location.hash.slice(1);
  try {
    key = decodeURIComponent(key);
  } catch {
    key = '';
  }
  show(tabs.find((t) => t.dataset.key === key) ?? tabs[0]);
})();
