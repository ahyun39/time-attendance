// 캔버스에서 만든 .dc.html 화면을 GitHub Pages에서 그대로 실행하기 위한 작은 런타임.
// {{hole}}, <sc-if>, <sc-for>, onClick/onChange/onKeyDown, value 바인딩만 지원한다.
(function () {
  class DCLogic {
    constructor(props) { this.props = props || {}; this.state = null; }
    setState(patch) {
      const next = typeof patch === 'function' ? patch(this.state || {}, this.props) : patch;
      this.state = Object.assign({}, this.state || {}, next);
      if (this.__update) this.__update();
    }
    forceUpdate() { if (this.__update) this.__update(); }
  }

  const HOLE = /\{\{\s*([^}]+?)\s*\}\}/g;
  const WHOLE = /^\s*\{\{\s*([^}]+?)\s*\}\}\s*$/;

  function lookup(path, scope) {
    if (path === 'true') return true;
    if (path === 'false') return false;
    if (path === 'null') return null;
    if (/^-?\d+(\.\d+)?$/.test(path)) return Number(path);
    if (/^'.*'$|^".*"$/.test(path)) return path.slice(1, -1);
    const parts = path.split('.');
    let v = scope[parts[0]];
    for (let i = 1; i < parts.length && v != null; i++) v = v[parts[i]];
    return v;
  }
  const interp = (text, scope) => text.replace(HOLE, (_, p) => { const v = lookup(p, scope); return v == null ? '' : String(v); });
  const raw = (text, scope) => { const m = text.match(WHOLE); return m ? lookup(m[1], scope) : interp(text, scope); };

  // <select> 안의 <sc-for>는 HTML 파서가 지워버리므로 미리 option 속성으로 옮겨 둔다.
  function prepare(src) {
    return src.replace(/<select\b[\s\S]*?<\/select>/g, (sel) =>
      sel.replace(/<sc-for\s+list="([^"]+)"\s+as="([^"]+)"[^>]*>\s*<option\b([\s\S]*?)<\/option>\s*<\/sc-for>/g,
        (_, list, as, rest) => '<option data-sc-for="' + list + '" data-sc-as="' + as + '"' + rest + '</option>'));
  }

  const EVENT = { onclick: 'click', onkeydown: 'keydown' };

  function build(node, scope, out) {
    if (node.nodeType === 3) { out.push(document.createTextNode(interp(node.nodeValue, scope))); return; }
    if (node.nodeType !== 1) return;
    const tag = node.tagName.toLowerCase();
    if (tag === 'sc-if') {
      if (raw(node.getAttribute('value') || '', scope)) node.childNodes.forEach((c) => build(c, scope, out));
      return;
    }
    if (tag === 'sc-for' || node.hasAttribute('data-sc-for')) {
      const isTag = tag === 'sc-for';
      const list = raw(node.getAttribute(isTag ? 'list' : 'data-sc-for'), scope) || [];
      const as = node.getAttribute(isTag ? 'as' : 'data-sc-as');
      list.forEach((item, i) => {
        const inner = Object.assign(Object.create(scope), { [as]: item, $index: i });
        if (isTag) node.childNodes.forEach((c) => build(c, inner, out));
        else buildElement(node, inner, out, true);
      });
      return;
    }
    buildElement(node, scope, out, false);
  }

  function buildElement(node, scope, out, skipFor) {
    const tag = node.tagName.toLowerCase();
    const el = node.namespaceURI && node.namespaceURI !== 'http://www.w3.org/1999/xhtml'
      ? document.createElementNS(node.namespaceURI, node.tagName) : document.createElement(tag);
    el.__h = {};
    for (const a of Array.from(node.attributes)) {
      const name = a.name;
      if (name.startsWith('hint-') || (skipFor && name.startsWith('data-sc-'))) continue;
      if (name.startsWith('on')) {
        const fn = raw(a.value, scope);
        if (typeof fn !== 'function') continue;
        const type = name === 'onchange' ? (tag === 'select' ? 'change' : 'input') : (EVENT[name] || name.slice(2));
        el.__h[type] = fn;
        continue;
      }
      const v = raw(a.value, scope);
      if (name === 'value' && /^(input|textarea|select)$/.test(tag)) { el.__value = v == null ? '' : String(v); continue; }
      if (v === false || v == null) { if (!name.startsWith('aria-')) continue; }
      el.setAttribute(name, String(v));
    }
    const kids = [];
    node.childNodes.forEach((c) => build(c, scope, kids));
    kids.forEach((k) => el.appendChild(k));
    out.push(el);
  }

  // 기존 DOM을 새 결과에 맞춰 고친다. 노드를 갈아끼우지 않아 입력 중인 한글 조합과 포커스가 유지된다.
  function morph(oldEl, newEl) {
    if (oldEl.nodeType === 3) { if (oldEl.nodeValue !== newEl.nodeValue) oldEl.nodeValue = newEl.nodeValue; return; }
    for (const a of Array.from(oldEl.attributes)) if (!newEl.hasAttribute(a.name)) oldEl.removeAttribute(a.name);
    for (const a of Array.from(newEl.attributes)) if (oldEl.getAttribute(a.name) !== a.value) oldEl.setAttribute(a.name, a.value);
    oldEl.__h = newEl.__h;
    morphChildren(oldEl, newEl);
    if (newEl.__value !== undefined && oldEl.value !== newEl.__value) oldEl.value = newEl.__value;
  }
  function same(a, b) { return a.nodeType === b.nodeType && (a.nodeType !== 1 || a.tagName === b.tagName); }
  function morphChildren(oldP, newP) {
    const o = Array.from(oldP.childNodes), n = Array.from(newP.childNodes);
    n.forEach((nc, i) => {
      const oc = o[i];
      if (!oc) { oldP.appendChild(nc); applyValues(nc); }
      else if (same(oc, nc)) morph(oc, nc);
      else { oldP.replaceChild(nc, oc); applyValues(nc); }
    });
    for (let i = n.length; i < o.length; i++) oldP.removeChild(o[i]);
  }
  function applyValues(el) {
    if (el.nodeType !== 1) return;
    el.childNodes.forEach(applyValues);
    if (el.__value !== undefined) el.value = el.__value;
  }

  const loadedHead = new Set();

  async function mount(url, container, onRender) {
    const src = prepare(await (await fetch(url)).text());
    const doc = new DOMParser().parseFromString(src, 'text/html');
    const xdc = doc.querySelector('x-dc');
    const helmet = xdc.querySelector('helmet');
    if (helmet) {
      helmet.querySelectorAll('link, style').forEach((n) => {
        const key = n.outerHTML;
        if (loadedHead.has(key)) return;
        loadedHead.add(key);
        document.head.appendChild(document.importNode(n, true));
      });
      helmet.remove();
    }
    const script = doc.querySelector('script[data-dc-script]');
    const Component = new Function('DCLogic', script.textContent + '\nreturn Component;')(DCLogic);
    const comp = new Component({});
    const template = Array.from(xdc.childNodes);

    const root = document.createElement('div');
    container.innerHTML = '';
    container.appendChild(root);

    const render = () => {
      const vals = comp.renderVals();
      const out = [];
      template.forEach((n) => build(n, vals, out));
      const fresh = document.createElement('div');
      out.forEach((n) => fresh.appendChild(n));
      morphChildren(root, fresh);
      if (onRender) onRender(comp);
    };
    comp.__update = render;

    const dispatch = (e) => {
      if (e.type === 'keydown' && e.isComposing) return;
      for (let el = e.target; el && el !== root.parentNode; el = el.parentNode) {
        const h = el.__h && el.__h[e.type];
        if (h) { h(e); return; }
        if (e.type === 'click' && el.tagName === 'A' && el.getAttribute('href') === '#') { e.preventDefault(); return; }
      }
    };
    ['click', 'input', 'change', 'keydown'].forEach((t) => root.addEventListener(t, dispatch));
    render();
    return comp;
  }

  window.DCLite = { mount };
})();
