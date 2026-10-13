(function(){"use strict";try{if(typeof document<"u"){var e=document.createElement("style");e.appendChild(document.createTextNode(".eternity-studio-root.svelte-1n46o8q{display:flex;flex-direction:column;background:#18181b;color:#f4f4f5;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;border-radius:8px;border:1px solid #27272a;overflow:hidden}.studio-header.svelte-1n46o8q{display:flex;align-items:center;gap:8px;padding:8px 12px;background:#09090b;border-bottom:1px solid #27272a}.studio-badge.svelte-1n46o8q{background:#6366f1;color:#fff;font-size:10px;font-weight:700;padding:2px 6px;border-radius:4px;letter-spacing:.5px}.studio-title.svelte-1n46o8q{font-weight:600;font-size:13px}.studio-nav.svelte-1n46o8q{margin-left:auto;display:flex;gap:4px}.studio-nav.svelte-1n46o8q button:where(.svelte-1n46o8q){background:transparent;border:none;color:#a1a1aa;padding:4px 8px;font-size:11px;cursor:pointer;border-radius:4px;transition:all .15s ease}.studio-nav.svelte-1n46o8q button:where(.svelte-1n46o8q):hover{background:#27272a;color:#fff}.studio-nav.svelte-1n46o8q button.active:where(.svelte-1n46o8q){background:#312e81;color:#c7d2fe;font-weight:600}.studio-body.svelte-1n46o8q{padding:12px}.panel.svelte-1n46o8q{font-size:12px;color:#a1a1aa}")),document.head.appendChild(e)}}catch(o){console.error("vite-plugin-css-injected-by-js",o)}})();
var ln = Array.isArray, fn = Array.prototype.indexOf, Se = Array.prototype.includes, on = Array.from, xt = Object.defineProperty, ye = Object.getOwnPropertyDescriptor, un = Object.prototype, an = Array.prototype, cn = Object.getPrototypeOf, vt = Object.isExtensible;
const hn = () => {
};
function dn(e) {
  for (var t = 0; t < e.length; t++)
    e[t]();
}
function Tt() {
  var e, t, n = new Promise((r, i) => {
    e = r, t = i;
  });
  return { promise: n, resolve: e, reject: t };
}
const k = 2, xe = 4, He = 8, At = 1 << 24, P = 16, $ = 32, J = 64, Je = 128, st = 256, L = 512, E = 1024, m = 2048, O = 4096, N = 8192, S = 16384, he = 32768, Me = 1 << 25, ue = 65536, Pe = 1 << 17, vn = 1 << 18, de = 1 << 19, _n = 1 << 20, Fe = 1 << 21, oe = 1 << 22, Z = 1 << 23, Ue = Symbol("$state"), Ct = Symbol("component"), pn = Symbol("attributes"), Qe = Symbol("class"), gn = Symbol("style"), et = Symbol("text"), Ae = new class extends Error {
  name = "StaleReactionError";
  message = "The reaction that called `getAbortSignal()` was re-run or destroyed";
}(), wn = 2, Rt = {}, b = Symbol("uninitialized");
function mn() {
  console.warn("https://svelte.dev/e/derived_inert");
}
function yn() {
  console.warn("https://svelte.dev/e/svelte_boundary_reset_noop");
}
function Ot(e) {
  return e === this.v;
}
function bn() {
  throw new Error("https://svelte.dev/e/async_derived_orphan");
}
function En() {
  throw new Error("https://svelte.dev/e/effect_update_depth_exceeded");
}
function kn() {
  throw new Error("https://svelte.dev/e/state_descriptors_fixed");
}
function Sn() {
  throw new Error("https://svelte.dev/e/state_prototype_fixed");
}
function xn() {
  throw new Error("https://svelte.dev/e/state_unsafe_mutation");
}
function Tn() {
  throw new Error("https://svelte.dev/e/svelte_boundary_reset_onerror");
}
let j = null;
function ae(e) {
  j = e;
}
function An(e, t = !1, n) {
  j = {
    p: j,
    i: !1,
    c: null,
    e: null,
    s: e,
    x: null,
    r: (
      /** @type {Effect} */
      g
    ),
    l: null
  };
}
function Cn(e) {
  var t = (
    /** @type {ComponentContext} */
    j
  ), n = t.e;
  if (n !== null) {
    t.e = null;
    for (var r of n)
      Kn(r);
  }
  return t.i = !0, j = t.p, Nt(e);
}
function Nt(e = {}) {
  return xt(e, Ct, { value: !0 }), e;
}
function Dt() {
  return !0;
}
let fe = [];
function Rn() {
  var e = fe;
  fe = [], dn(e);
}
function ne(e) {
  if (fe.length === 0) {
    var t = fe;
    queueMicrotask(() => {
      t === fe && Rn();
    });
  }
  fe.push(e);
}
const On = -7169;
function w(e, t) {
  e.f = e.f & On | t;
}
function lt(e) {
  (e.f & L) !== 0 || e.deps === null ? w(e, E) : w(e, O);
}
function Mt(e, t, n) {
  (e.f & m) !== 0 ? t.add(e) : (e.f & O) !== 0 && n.add(e), w(e, E);
}
function Ye(e) {
  var t = _, n = g;
  D(null), U(null);
  try {
    return e();
  } finally {
    D(t), U(n);
  }
}
function Nn(e, t, n, r) {
  const i = Mn;
  var s = e.filter((c) => !c.settled), f = t.map(i);
  if (n.length === 0 && s.length === 0) {
    r(f);
    return;
  }
  var l = (
    /** @type {Effect} */
    g
  ), o = Dn(), u = s.length === 1 ? s[0].promise : s.length > 1 ? Promise.all(s.map((c) => c.promise)) : null;
  function h(c) {
    if ((l.f & S) === 0) {
      o();
      try {
        r([...f, ...c]);
      } catch (v) {
        Y(v, l);
      }
      Ie();
    }
  }
  var a = Pt();
  if (n.length === 0) {
    u.then(() => h([])).finally(a);
    return;
  }
  function d() {
    Promise.all(n.map((c) => /* @__PURE__ */ Pn(c))).then(h).catch((c) => Y(c, l)).finally(a);
  }
  u ? u.then(() => {
    if ((l.f & S) !== 0) {
      a();
      return;
    }
    o(), d(), Ie();
  }) : d();
}
function Dn() {
  var e = (
    /** @type {Effect} */
    g
  ), t = _, n = j, r = (
    /** @type {Batch} */
    p
  );
  return function(s = !0) {
    U(e), D(t), ae(n), s && (e.f & S) === 0 && (r?.activate(), r?.apply());
  };
}
function Ie(e = !0) {
  U(null), D(null), ae(null), e && p?.deactivate();
}
function Pt() {
  var e = (
    /** @type {Effect} */
    g
  ), t = e.b, n = (
    /** @type {Batch} */
    p
  ), r = !!t?.is_rendered();
  return t?.update_pending_count(1, n), n.increment(r, e), () => {
    t?.update_pending_count(-1, n), n.decrement(r, e);
  };
}
// @__NO_SIDE_EFFECTS__
function Mn(e) {
  var t = k | m;
  return g !== null && (g.f |= de), {
    ctx: j,
    deps: null,
    effects: null,
    equals: Ot,
    f: t,
    fn: e,
    reactions: null,
    rv: 0,
    v: (
      /** @type {V} */
      b
    ),
    wv: 0,
    parent: g,
    ac: null
  };
}
const ge = Symbol("obsolete");
// @__NO_SIDE_EFFECTS__
function Pn(e, t, n) {
  let r = (
    /** @type {Effect | null} */
    g
  );
  r === null && bn();
  var i = (
    /** @type {Promise<V>} */
    /** @type {unknown} */
    void 0
  ), s = Be(
    /** @type {V} */
    b
  ), f = !_, l = /* @__PURE__ */ new Set();
  return $n(() => {
    var o = (
      /** @type {Effect} */
      g
    ), u = Tt();
    i = u.promise;
    try {
      Promise.resolve(e()).then(u.resolve, (c) => {
        c !== Ae && u.reject(c);
      }).finally(Ie);
    } catch (c) {
      u.reject(c), Ie();
    }
    var h = (
      /** @type {Batch} */
      p
    );
    if (f) {
      if ((o.f & he) !== 0)
        var a = Pt();
      if (
        // boundary can be null if the async derived is inside an $effect.root not connected to the component render tree
        r.b?.is_rendered()
      )
        h.async_deriveds.get(o)?.reject(ge);
      else
        for (const c of l.values())
          c.reject(ge);
      l.add(u), h.async_deriveds.set(o, u);
    }
    const d = (c, v = void 0) => {
      a?.(), l.delete(u), v !== ge && (h.activate(), v ? (s.f |= Z, je(s, v)) : ((s.f & Z) !== 0 && (s.f ^= Z), je(s, c)), h.deactivate());
    };
    u.promise.then(d, (c) => d(null, c || "unknown"));
  }), Gn(() => {
    for (const o of l)
      o.reject(ge);
  }), new Promise((o) => {
    function u(h) {
      function a() {
        h === i ? o(s) : u(i);
      }
      h.then(a, a);
    }
    u(i);
  });
}
function Fn(e) {
  var t = e.effects;
  if (t !== null) {
    e.effects = null;
    for (var n = 0; n < t.length; n += 1)
      A(
        /** @type {Effect} */
        t[n]
      );
  }
}
function ft(e) {
  var t, n = g, r = e.parent;
  if (!se && r !== null && e.v !== b && // if it was never evaluated before, it's guaranteed to fail downstream, so we try to execute instead
  (r.f & (S | N)) !== 0)
    return mn(), e.v;
  U(r);
  try {
    Fn(e), t = en(e);
  } finally {
    U(n);
  }
  return t;
}
function Ft(e) {
  var t = ft(e);
  if (!e.equals(t) && (e.wv = Jt(), (!p?.is_fork || e.deps === null) && (p !== null ? (p.capture(e, t, !0), tt?.capture(e, t, !0)) : e.v = t, e.deps === null))) {
    w(e, E);
    return;
  }
  se || (F !== null ? (ht() || p?.is_fork) && F.set(e, t) : lt(e));
}
function In(e) {
  if (e.effects !== null)
    for (const t of e.effects)
      (t.teardown || t.ac) && (t.teardown?.(), t.ac !== null && Ye(() => {
        t.ac.abort(Ae), t.ac = null;
      }), t.fn !== null && (t.teardown = hn), Te(t, 0), dt(t));
}
function It(e) {
  if (e.effects !== null)
    for (const t of e.effects)
      t.teardown && t.fn !== null && ce(t);
}
let ze = null, le = null, p = null, tt = null, F = null, nt = null, Ge = !1, be = null, De = null;
var _t = 0;
let Ln = 1;
class Q {
  id = Ln++;
  /** True as soon as `#process` was called */
  #t = !1;
  linked = !0;
  /** @type {Batch | null} */
  #l = null;
  /** @type {Batch | null} */
  #e = null;
  /** @type {Map<Effect, ReturnType<typeof deferred<any>>>} */
  async_deriveds = /* @__PURE__ */ new Map();
  /**
   * The current values of any signals that are updated in this batch.
   * Tuple format: [value, is_derived] (note: is_derived is false for deriveds, too, if they were overridden via assignment)
   * They keys of this map are identical to `this.#previous`
   * @type {Map<Value, [any, boolean]>}
   */
  current = /* @__PURE__ */ new Map();
  /**
   * The values of any signals (sources and deriveds) that are updated in this batch _before_ those updates took place.
   * They keys of this map are identical to `this.#current`
   * @type {Map<Value, any>}
   */
  previous = /* @__PURE__ */ new Map();
  /**
   * When the batch is committed (and the DOM is updated), we need to remove old branches
   * and append new ones by calling the functions added inside (if/each/key/etc) blocks
   * @type {Set<(batch: Batch) => void>}
   */
  #o = /* @__PURE__ */ new Set();
  /**
   * If a fork is discarded, we need to destroy any effects that are no longer needed
   * @type {Set<(batch: Batch) => void>}
   */
  #r = /* @__PURE__ */ new Set();
  /**
   * The number of async effects that are currently in flight
   */
  #s = 0;
  /**
   * Async effects that are currently in flight, _not_ inside a pending boundary
   * @type {Map<Effect, number>}
   */
  #n = /* @__PURE__ */ new Map();
  /**
   * A deferred that resolves when the batch is committed, used with `settled()`
   * TODO replace with Promise.withResolvers once supported widely enough
   * @type {{ promise: Promise<void>, resolve: (value?: any) => void, reject: (reason: unknown) => void } | null}
   */
  #f = null;
  /**
   * Effects that were scheduled in this batch but not yet 'resolved' into the
   * root effects that need to be flushed. Resolving — the upwards traversal that
   * marks the path to each effect on the shared effect tree (see #resolve) — is
   * deferred until the batch is processed, so that the markers are created and
   * consumed within a single traversal. Scheduling into other batches (which can
   * happen concurrently, e.g. while a batch is committed) can therefore never
   * observe (and be confused by) this batch's markers.
   * May contain duplicates — deduplication happens during resolving
   * @type {Effect[]}
   */
  #i = [];
  /**
   * Effects created while this batch was active.
   * @type {Effect[]}
   */
  #p = [];
  /**
   * Deferred effects (which run after async work has completed) that are DIRTY
   * @type {Set<Effect>}
   */
  #u = /* @__PURE__ */ new Set();
  /**
   * Deferred effects that are MAYBE_DIRTY
   * @type {Set<Effect>}
   */
  #a = /* @__PURE__ */ new Set();
  /**
   * A map of branches that still exist, but will be destroyed when this batch
   * is committed — we skip over these during `process`.
   * The value contains child effects that were dirty/maybe_dirty before being reset,
   * so they can be rescheduled if the branch survives.
   * @type {Map<Effect, { d: Effect[], m: Effect[] }>}
   */
  #h = /* @__PURE__ */ new Map();
  /**
   * Inverse of #skipped_branches which we need to tell prior batches to unskip them when committing
   * @type {Set<Effect>}
   */
  #g = /* @__PURE__ */ new Set();
  is_fork = !1;
  #c = !1;
  constructor() {
    le === null ? ze = le = this : (le.#e = this, this.#l = le), le = this;
  }
  #b() {
    if (this.is_fork) return !0;
    for (const r of this.#n.keys()) {
      for (var t = r, n = !1; t.parent !== null; ) {
        if (this.#h.has(t)) {
          n = !0;
          break;
        }
        t = t.parent;
      }
      if (!n)
        return !0;
    }
    return !1;
  }
  /**
   * Add an effect to the #skipped_branches map and reset its children
   * @param {Effect} effect
   */
  skip_effect(t) {
    this.#h.has(t) || this.#h.set(t, { d: [], m: [] }), this.#g.delete(t);
  }
  /**
   * Remove an effect from the #skipped_branches map and reschedule
   * any tracked dirty/maybe_dirty child effects
   * @param {Effect} effect
   * @param {(e: Effect) => void} callback
   */
  unskip_effect(t, n = (r) => this.schedule(r)) {
    var r = this.#h.get(t);
    if (r) {
      this.#h.delete(t);
      for (var i of r.d)
        w(i, m), n(i);
      for (i of r.m)
        w(i, O), n(i);
    }
    this.#g.add(t);
  }
  /**
   * Convert the effects that were scheduled in this batch into the root effects
   * that need to be traversed, marking the path to each effect (by clearing the
   * `CLEAN` flag on ancestor branches) so that the traversal can find them.
   * This happens right before traversal rather than at scheduling time, so that
   * the markers left on the (shared) effect tree are created and consumed within
   * a single traversal — scheduling into other batches can never observe them
   * @returns {Effect[]}
   */
  #E() {
    var t = [];
    for (const s of this.#i)
      if (!((s.f & S) !== 0 || (s.f & (m | O)) === 0)) {
        for (var n = s, r = !1; n.parent !== null; ) {
          n = n.parent;
          var i = n.f;
          if ((i & (J | $)) !== 0) {
            if ((i & E) === 0) {
              r = !0;
              break;
            }
            n.f ^= E;
          }
        }
        r || t.push(n);
      }
    return this.#i = [], t;
  }
  #w() {
    this.#t = !0;
    for (const l of this.#u)
      this.#a.delete(l), w(l, m), this.schedule(l);
    for (const l of this.#a)
      w(l, O), this.schedule(l);
    this.apply();
    for (var t = be = [], n = [], r = De = []; this.#i.length > 0; ) {
      _t++ > 1e3 && (this.#_(), jn());
      for (const l of this.#E())
        try {
          this.#m(l, t, n);
        } catch (o) {
          throw qt(l), this.#b() || this.discard(), o;
        }
    }
    if (p = null, r.length > 0) {
      var i = Q.ensure();
      for (const l of r)
        i.schedule(l);
    }
    if (be = null, De = null, this.#b()) {
      this.#v(n), this.#v(t);
      for (const [l, o] of this.#h)
        jt(l, o);
      r.length > 0 && /** @type {unknown} */
      p.#w();
      return;
    }
    const s = this.#d();
    if (s) {
      this.#v(n), this.#v(t), s.#k(this);
      return;
    }
    this.#u.clear(), this.#a.clear();
    for (const l of this.#o) l(this);
    this.#o.clear(), tt = this, pt(n), pt(t), tt = null, this.#f?.resolve();
    var f = (
      /** @type {Batch | null} */
      /** @type {unknown} */
      p
    );
    if (this.#s === 0 && (this.#i.length === 0 || f !== null) && this.#_(), this.#i.length > 0)
      if (f !== null) {
        for (const l of this.#i)
          f.#i.push(l);
        this.#i = [];
      } else
        f = this;
    f !== null && (B.clear(), f.#w());
  }
  /**
   * Traverse the effect tree, executing effects or stashing
   * them for later execution as appropriate
   * @param {Effect} root
   * @param {Effect[]} effects
   * @param {Effect[]} render_effects
   */
  #m(t, n, r) {
    t.f ^= E;
    for (var i = t.first; i !== null; ) {
      var s = i.f, f = (s & ($ | J)) !== 0, l = f && (s & E) !== 0, o = l || (s & N) !== 0 || this.#h.has(i);
      if (!o && i.fn !== null) {
        f ? i.f ^= E : (s & xe) !== 0 ? n.push(i) : Ce(i) && ((s & P) !== 0 && this.#a.add(i), ce(i));
        var u = i.first;
        if (u !== null) {
          i = u;
          continue;
        }
      }
      for (; i !== null; ) {
        var h = i.next;
        if (h !== null) {
          i = h;
          break;
        }
        i = i.parent;
      }
    }
  }
  #d() {
    for (var t = this.#l; t !== null; ) {
      if (!t.is_fork) {
        for (const [n, [, r]] of this.current)
          if (t.current.has(n) && !r)
            return t;
      }
      t = t.#l;
    }
    return null;
  }
  /**
   * @param {Batch} batch
   */
  #k(t) {
    for (const [r, i] of t.current)
      !this.previous.has(r) && t.previous.has(r) && this.previous.set(r, t.previous.get(r)), this.current.set(r, i);
    for (const [r, i] of t.async_deriveds) {
      const s = this.async_deriveds.get(r);
      s && i.promise.then(s.resolve).catch(s.reject);
    }
    t.async_deriveds.clear(), this.transfer_effects(t.#u, t.#a);
    const n = (r) => {
      var i = r.reactions;
      if (i !== null && !((r.f & k) !== 0 && (r.f & (m | O)) === 0))
        for (const l of i) {
          var s = l.f;
          if ((s & k) !== 0)
            n(
              /** @type {Derived} */
              l
            );
          else {
            var f = (
              /** @type {Effect} */
              l
            );
            s & (oe | P) && !this.async_deriveds.has(f) && (this.#a.delete(f), w(f, m), this.schedule(f));
          }
        }
    };
    for (const r of this.current.keys())
      n(r);
    this.oncommit(() => t.discard()), t.#_(), p = this, this.#w();
  }
  /**
   * @param {Effect[]} effects
   */
  #v(t) {
    for (var n = 0; n < t.length; n += 1)
      Mt(t[n], this.#u, this.#a);
  }
  /**
   * Associate a change to a given source with the current
   * batch, noting its previous and current values
   * @param {Value} source
   * @param {any} value
   * @param {boolean} [is_derived]
   */
  capture(t, n, r = !1) {
    t.v !== b && !this.previous.has(t) && this.previous.set(t, t.v), (t.f & Z) === 0 && (this.current.set(t, [n, r]), F?.set(t, n)), this.is_fork || (t.v = n);
  }
  activate() {
    p = this;
  }
  deactivate() {
    p = null, F = null;
  }
  flush() {
    try {
      Ge = !0, p = this, this.#w();
    } finally {
      _t = 0, nt = null, be = null, De = null, Ge = !1, p = null, F = null, B.clear();
    }
  }
  discard() {
    for (const t of this.#r) t(this);
    this.#r.clear();
    for (const t of this.async_deriveds.values())
      t.reject(ge);
    this.#_(), this.#f?.resolve();
  }
  /**
   * @param {Effect} effect
   */
  register_created_effect(t) {
    this.#p.push(t);
  }
  #y() {
    for (let a = ze; a !== null; a = a.#e) {
      var t = a.id < this.id, n = [];
      for (const [d, [c, v]] of this.current) {
        if (a.current.has(d)) {
          var r = (
            /** @type {[any, boolean]} */
            a.current.get(d)[0]
          );
          if (t && c !== r)
            a.current.set(d, [c, v]);
          else
            continue;
        }
        n.push(d);
      }
      if (t)
        for (const [d, c] of this.async_deriveds) {
          const v = a.async_deriveds.get(d);
          v && c.promise.then(v.resolve).catch(v.reject);
        }
      var i = [...a.current.keys()].filter(
        (d) => !/** @type {[any, boolean]} */
        a.current.get(d)[1]
      );
      if (!(!a.#t || i.length === 0)) {
        var s = i.filter((d) => !this.current.has(d));
        if (s.length === 0)
          t && a.discard();
        else if (n.length > 0) {
          if (t)
            for (const d of this.#g)
              a.unskip_effect(d, (c) => {
                (c.f & (P | oe)) !== 0 ? a.schedule(c) : a.#v([c]);
              });
          a.activate();
          var f = /* @__PURE__ */ new Set(), l = /* @__PURE__ */ new Map();
          for (var o of n)
            Lt(o, s, f, l);
          l = /* @__PURE__ */ new Map();
          var u = [...a.current].filter(([d, c]) => {
            const v = this.current.get(d);
            return v ? v[0] !== c[0] || v[1] !== c[1] : !0;
          }).map(([d]) => d);
          if (u.length > 0)
            for (const d of this.#p)
              (d.f & (S | N | Pe)) === 0 && ot(d, u, l) && ((d.f & (oe | P)) !== 0 ? (w(d, m), a.schedule(d)) : a.#u.add(d));
          if (a.#i.length > 0 && !a.#c) {
            a.apply();
            for (var h of a.#E())
              a.#m(h, [], []);
          }
          a.deactivate();
        }
      }
    }
  }
  /**
   * @param {boolean} blocking
   * @param {Effect} effect
   */
  increment(t, n) {
    if (this.#s += 1, t) {
      let r = this.#n.get(n) ?? 0;
      this.#n.set(n, r + 1);
    }
  }
  /**
   * @param {boolean} blocking
   * @param {Effect} effect
   */
  decrement(t, n) {
    if (this.#s -= 1, t) {
      let r = this.#n.get(n) ?? 0;
      r === 1 ? this.#n.delete(n) : this.#n.set(n, r - 1);
    }
    this.#c || (this.#c = !0, ne(() => {
      this.#c = !1, this.linked && this.flush();
    }));
  }
  /**
   * @param {Set<Effect>} dirty_effects
   * @param {Set<Effect>} maybe_dirty_effects
   */
  transfer_effects(t, n) {
    for (const r of t)
      this.#u.add(r);
    for (const r of n)
      this.#a.add(r);
    t.clear(), n.clear();
  }
  /** @param {(batch: Batch) => void} fn */
  oncommit(t) {
    this.#o.add(t);
  }
  /** @param {(batch: Batch) => void} fn */
  ondiscard(t) {
    this.#r.add(t);
  }
  settled() {
    return (this.#f ??= Tt()).promise;
  }
  static ensure() {
    if (p === null) {
      const t = p = new Q();
      Ge || ne(() => {
        t.#t || t.flush();
      });
    }
    return p;
  }
  apply() {
    {
      F = null;
      return;
    }
  }
  /**
   *
   * @param {Effect} effect
   */
  schedule(t) {
    if (nt = t, t.b?.is_pending && (t.f & (xe | He | At)) !== 0 && (t.f & he) === 0) {
      t.b.defer_effect(t);
      return;
    }
    this.#i.push(t);
  }
  #_() {
    if (this.linked) {
      var t = this.#l, n = this.#e;
      t === null ? ze = n : t.#e = n, n === null ? le = t : n.#l = t, this.linked = !1;
    }
  }
}
function jn() {
  try {
    En();
  } catch (e) {
    Y(e, nt);
  }
}
let K = null;
function pt(e) {
  var t = e.length;
  if (t !== 0) {
    for (var n = 0; n < t; ) {
      var r = e[n++];
      if ((r.f & (S | N)) === 0 && Ce(r) && (K = /* @__PURE__ */ new Set(), ce(r), r.deps === null && r.first === null && r.nodes === null && r.teardown === null && r.ac === null && Kt(r), K?.size > 0)) {
        B.clear();
        for (const i of K) {
          if ((i.f & (S | N)) !== 0) continue;
          const s = [i];
          let f = i.parent;
          for (; f !== null; )
            K.has(f) && (K.delete(f), s.push(f)), f = f.parent;
          for (let l = s.length - 1; l >= 0; l--) {
            const o = s[l];
            (o.f & (S | N)) === 0 && ce(o);
          }
        }
        K.clear();
      }
    }
    K = null;
  }
}
function Lt(e, t, n, r) {
  if (!n.has(e) && (n.add(e), e.reactions !== null))
    for (const i of e.reactions) {
      const s = i.f;
      (s & k) !== 0 ? Lt(
        /** @type {Derived} */
        i,
        t,
        n,
        r
      ) : (s & (oe | P)) !== 0 && (s & m) === 0 && ot(i, t, r) && (w(i, m), ut(
        /** @type {Effect} */
        i
      ));
    }
}
function ot(e, t, n) {
  const r = n.get(e);
  if (r !== void 0) return r;
  if (e.deps !== null)
    for (const i of e.deps) {
      if (Se.call(t, i))
        return !0;
      if ((i.f & k) !== 0 && ot(
        /** @type {Derived} */
        i,
        t,
        n
      ))
        return n.set(
          /** @type {Derived} */
          i,
          !0
        ), !0;
    }
  return n.set(e, !1), !1;
}
function ut(e) {
  p.schedule(e);
}
function jt(e, t) {
  if (!((e.f & $) !== 0 && (e.f & E) !== 0)) {
    (e.f & m) !== 0 ? t.d.push(e) : (e.f & O) !== 0 && t.m.push(e), w(e, E);
    for (var n = e.first; n !== null; )
      jt(n, t), n = n.next;
  }
}
function qt(e) {
  w(e, E);
  for (var t = e.first; t !== null; )
    qt(t), t = t.next;
}
let Le = /* @__PURE__ */ new Set();
const B = /* @__PURE__ */ new Map();
let Ht = !1;
function Be(e, t) {
  var n = {
    f: 0,
    // TODO ideally we could skip this altogether, but it causes type errors
    v: e,
    reactions: null,
    equals: Ot,
    rv: 0,
    wv: 0
  };
  return n;
}
// @__NO_SIDE_EFFECTS__
function G(e, t) {
  const n = Be(e);
  return er(n), n;
}
function H(e, t, n = !1) {
  _ !== null && // since we are untracking the function inside `$inspect.with` we need to add this check
  // to ensure we error if state is set inside an inspect effect
  (!I || (_.f & Pe) !== 0) && Dt() && (_.f & (k | P | oe | Pe)) !== 0 && (V === null || !V.has(e)) && xn();
  let r = n ? we(t) : t;
  return je(e, r, De);
}
var te = null, rt = 0;
function je(e, t, n = null) {
  if (!e.equals(t)) {
    se ? B.set(e, t) : B.has(e) || B.set(e, e.v);
    var r = Q.ensure();
    if (r.capture(e, t), (e.f & k) !== 0) {
      const i = (
        /** @type {Derived} */
        e
      );
      (e.f & m) !== 0 && ft(i), F === null && lt(i);
    }
    e.wv = Jt(), te = null, rt = 0, Yt(e, m, n), te = null, g !== null && (g.f & E) !== 0 && (g.f & ($ | J)) === 0 && (C === null ? tr([e]) : C.push(e)), !r.is_fork && Le.size > 0 && !Ht && qn();
  }
  return t;
}
function qn() {
  Ht = !1;
  for (const e of Le) {
    (e.f & E) !== 0 && w(e, O);
    let t;
    try {
      t = Ce(e);
    } catch {
      t = !0;
    }
    t && ce(e);
  }
  Le.clear();
}
function Ee(e) {
  H(e, e.v + 1);
}
function Yt(e, t, n) {
  var r = e.reactions;
  if (r !== null) {
    var i = r.length;
    if (rt += i, rt > 1e5 && te === null && (te = /* @__PURE__ */ new Set()), te !== null) {
      if (te.has(e)) return;
      te.add(e);
    }
    for (var s = 0; s < i; s++) {
      var f = r[s], l = f.f, o = (l & m) === 0;
      if (o && w(f, t), (l & Pe) !== 0)
        Le.add(
          /** @type {Effect} */
          f
        );
      else if ((l & k) !== 0) {
        var u = (
          /** @type {Derived} */
          f
        );
        F?.delete(u), Yt(u, O, n);
      } else if (o) {
        var h = (
          /** @type {Effect} */
          f
        );
        (l & P) !== 0 && K !== null && K.add(h), n !== null ? n.push(h) : ut(h);
      }
    }
  }
}
function we(e) {
  if (typeof e != "object" || e === null || Ue in e || Ct in e)
    return e;
  const t = cn(e);
  if (t !== un && t !== an)
    return e;
  var n = /* @__PURE__ */ new Map(), r = ln(e), i = /* @__PURE__ */ G(0), s = ie, f = (l) => {
    if (ie === s)
      return l();
    var o = _, u = ie;
    D(null), yt(s);
    var h = l();
    return D(o), yt(u), h;
  };
  return r && n.set("length", /* @__PURE__ */ G(
    /** @type {any[]} */
    e.length
  )), new Proxy(
    /** @type {any} */
    e,
    {
      defineProperty(l, o, u) {
        (!("value" in u) || u.configurable === !1 || u.enumerable === !1 || u.writable === !1) && kn();
        var h = n.get(o);
        return h === void 0 ? f(() => {
          var a = /* @__PURE__ */ G(u.value);
          return n.set(o, a), a;
        }) : H(h, u.value, !0), !0;
      },
      deleteProperty(l, o) {
        var u = n.get(o);
        if (u === void 0) {
          if (o in l) {
            const h = f(() => /* @__PURE__ */ G(b));
            n.set(o, h), Ee(i);
          }
        } else
          H(u, b), Ee(i);
        return !0;
      },
      get(l, o, u) {
        if (o === Ue)
          return e;
        var h = n.get(o), a = o in l;
        if (h === void 0 && (!a || ye(l, o)?.writable) && (h = f(() => {
          var c = we(a ? l[o] : b), v = /* @__PURE__ */ G(c);
          return v;
        }), n.set(o, h)), h !== void 0) {
          var d = R(h);
          return d === b ? void 0 : d;
        }
        return Reflect.get(l, o, u);
      },
      getOwnPropertyDescriptor(l, o) {
        this.has?.(l, o);
        var u = Reflect.getOwnPropertyDescriptor(l, o), h = n.get(o);
        if (h !== void 0) {
          var a = R(h);
          if (a === b)
            return;
          if (u && "value" in u)
            u.value = a;
          else
            return {
              enumerable: !0,
              configurable: !0,
              value: a,
              writable: !0
            };
        }
        return u;
      },
      has(l, o) {
        if (o === Ue)
          return !0;
        var u = n.get(o), h = u !== void 0 && u.v !== b || Reflect.has(l, o);
        if (u !== void 0 || g !== null && (!h || ye(l, o)?.writable)) {
          u === void 0 && (u = f(() => {
            var d = h ? we(l[o]) : b, c = /* @__PURE__ */ G(d);
            return c;
          }), n.set(o, u));
          var a = R(u);
          if (a === b)
            return !1;
        }
        return h;
      },
      set(l, o, u, h) {
        var a = n.get(o), d = o in l;
        if (r && o === "length")
          for (var c = u; c < /** @type {Source<number>} */
          a.v; c += 1) {
            var v = n.get(c + "");
            v !== void 0 ? H(v, b) : c in l && (v = f(() => /* @__PURE__ */ G(b)), n.set(c + "", v));
          }
        if (a === void 0)
          (!d || ye(l, o)?.writable) && (a = f(() => /* @__PURE__ */ G(void 0)), H(a, we(u)), n.set(o, a));
        else {
          d = a.v !== b;
          var y = f(() => we(u));
          H(a, y);
        }
        var q = Reflect.getOwnPropertyDescriptor(l, o);
        if (q?.set && q.set.call(h, u), !d) {
          if (r && typeof o == "string") {
            var M = (
              /** @type {Source<number>} */
              n.get("length")
            ), X = Number(o);
            Number.isInteger(X) && X >= M.v && H(M, X + 1);
          }
          Ee(i);
        }
        return !0;
      },
      ownKeys(l) {
        R(i);
        var o = Reflect.ownKeys(l).filter((a) => {
          var d = n.get(a);
          return d === void 0 || d.v !== b;
        });
        for (var [u, h] of n)
          h.v !== b && !(u in l) && o.push(u);
        return o;
      },
      setPrototypeOf() {
        Sn();
      }
    }
  );
}
var gt, Bt, Vt, Ut;
function Hn() {
  if (gt === void 0) {
    gt = window, Bt = /Firefox/.test(navigator.userAgent);
    var e = Element.prototype, t = Node.prototype, n = Text.prototype;
    Vt = ye(t, "firstChild").get, Ut = ye(t, "nextSibling").get, vt(e) && (e[Qe] = void 0, e[pn] = null, e[gn] = void 0, e.__e = void 0), vt(n) && (n[et] = void 0);
  }
}
function qe(e = "") {
  return document.createTextNode(e);
}
// @__NO_SIDE_EFFECTS__
function at(e) {
  return (
    /** @type {TemplateNode | null} */
    Vt.call(e)
  );
}
// @__NO_SIDE_EFFECTS__
function ct(e) {
  return (
    /** @type {TemplateNode | null} */
    Ut.call(e)
  );
}
function Re(e, t) {
  return /* @__PURE__ */ at(e);
}
function Yn(e, t = !1) {
  return /* @__PURE__ */ at(e);
}
function pe(e, t = 1, n = !1) {
  let r = e;
  for (; t--; )
    r = /** @type {TemplateNode} */
    /* @__PURE__ */ ct(r);
  return r;
}
function Bn() {
  return !1;
}
function Vn(e, t, n) {
  return (
    /** @type {T extends keyof HTMLElementTagNameMap ? HTMLElementTagNameMap[T] : Element} */
    n ? document.createElement(e, { is: n }) : document.createElement(e)
  );
}
function Un(e) {
  var t = g;
  if (t === null)
    return _.f |= Z, e;
  if ((t.f & he) === 0 && (t.f & xe) === 0)
    throw e;
  Y(e, t);
}
function Y(e, t) {
  if (e === Rt)
    throw e;
  if (!(t !== null && (t.f & S) !== 0)) {
    for (; t !== null; ) {
      if ((t.f & Je) !== 0 && (t.f & (S | Me)) === 0) {
        if ((t.f & he) === 0)
          throw e;
        try {
          t.b.error(e);
          return;
        } catch (n) {
          e = n;
        }
      }
      t = t.parent;
    }
    throw e;
  }
}
function zn(e, t) {
  var n = t.last;
  n === null ? t.last = t.first = e : (n.next = e, e.prev = n, t.last = e);
}
function ee(e, t) {
  var n = g;
  n !== null && (n.f & N) !== 0 && (e |= N);
  var r = {
    ctx: j,
    deps: null,
    nodes: null,
    f: e | m | L,
    first: null,
    fn: t,
    last: null,
    next: null,
    parent: n,
    b: n && n.b,
    prev: null,
    teardown: null,
    wv: 0,
    ac: null
  };
  p?.register_created_effect(r);
  var i = r;
  if ((e & xe) !== 0)
    be !== null ? be.push(r) : Q.ensure().schedule(r);
  else if (t !== null) {
    try {
      ce(r);
    } catch (f) {
      throw A(r), f;
    }
    i.deps === null && i.teardown === null && i.nodes === null && i.first === i.last && // either `null`, or a singular child
    (i.f & de) === 0 && (i = i.first, (e & P) !== 0 && (e & ue) !== 0 && i !== null && (i.f |= ue));
  }
  if (i !== null && (i.parent = n, n !== null && zn(i, n), _ !== null && (_.f & k) !== 0 && (e & J) === 0)) {
    var s = (
      /** @type {Derived} */
      _
    );
    (s.effects ??= []).push(i);
  }
  return r;
}
function ht() {
  return _ !== null && !I;
}
function Gn(e) {
  const t = ee(He, null);
  return w(t, E), t.teardown = e, t;
}
function Kn(e) {
  return ee(xe | _n, e);
}
function Wn(e) {
  Q.ensure();
  const t = ee(J | de, e);
  return (n = {}) => new Promise((r) => {
    n.outro ? ke(t, () => {
      A(t), r(void 0);
    }) : (A(t), r(void 0));
  });
}
function $n(e) {
  return ee(oe | de, e);
}
function Xn(e, t = 0) {
  return ee(He | t, e);
}
function Zn(e, t = [], n = [], r = []) {
  Nn(r, t, n, (i) => {
    ee(He, () => {
      e(...i.map(R));
    });
  });
}
function zt(e, t = 0) {
  var n = ee(P | t, e);
  return n;
}
function W(e) {
  return ee($ | de, e);
}
function Gt(e) {
  var t = e.teardown;
  if (t !== null) {
    const n = se, r = _;
    mt(!0), D(null);
    try {
      t.call(null);
    } catch (i) {
      Y(i, e.parent);
    } finally {
      mt(n), D(r);
    }
  }
}
function dt(e, t = !1) {
  var n = e.first;
  for (e.first = e.last = null; n !== null; ) {
    const i = n.ac;
    i !== null && Ye(() => {
      i.abort(Ae);
    });
    var r = n.next;
    (n.f & J) !== 0 ? n.parent = null : A(n, t), n = r;
  }
}
function Jn(e) {
  for (var t = e.first; t !== null; ) {
    var n = t.next;
    (t.f & $) === 0 && A(t), t = n;
  }
}
function A(e, t = !0) {
  var n = !1;
  (t || (e.f & vn) !== 0) && e.nodes !== null && e.nodes.end !== null && (Qn(
    e.nodes.start,
    /** @type {TemplateNode} */
    e.nodes.end
  ), n = !0), e.f |= Me, dt(e, t && !n), Te(e, 0);
  var r = e.nodes && e.nodes.t;
  if (r !== null)
    for (const s of r)
      s.stop();
  Gt(e), e.f ^= Me, e.f |= S;
  var i = e.parent;
  i !== null && i.first !== null && Kt(e), e.next = e.prev = e.teardown = e.ctx = e.deps = e.fn = e.nodes = e.ac = e.b = null;
}
function Qn(e, t) {
  for (; e !== null; ) {
    var n = e === t ? null : /* @__PURE__ */ ct(e);
    e.remove(), e = n;
  }
}
function Kt(e) {
  var t = e.parent, n = e.prev, r = e.next;
  n !== null && (n.next = r), r !== null && (r.prev = n), t !== null && (t.first === e && (t.first = r), t.last === e && (t.last = n));
}
function ke(e, t, n = !0) {
  var r = [];
  e.f |= st, Wt(e, r, !0);
  var i = () => {
    n && A(e), t && t();
  }, s = r.length;
  if (s > 0) {
    var f = () => --s || i();
    for (var l of r)
      l.out(f);
  } else
    i();
}
function Wt(e, t, n) {
  if ((e.f & N) === 0) {
    e.f ^= N;
    var r = e.nodes && e.nodes.t;
    if (r !== null)
      for (const l of r)
        (l.is_global || n) && t.push(l);
    for (var i = e.first; i !== null; ) {
      var s = i.next;
      if ((i.f & J) === 0) {
        var f = (i.f & ue) !== 0 || // If this is a branch effect without a block effect parent,
        // it means the parent block effect was pruned. In that case,
        // transparency information was transferred to the branch effect.
        (i.f & $) !== 0 && (e.f & P) !== 0;
        Wt(i, t, f ? n : !1);
      }
      i = s;
    }
  }
}
function wt(e) {
  e.f &= ~st, $t(e, !0);
}
function $t(e, t) {
  if ((e.f & st) === 0 && (e.f & N) !== 0) {
    e.f ^= N, (e.f & E) === 0 && (w(e, m), Q.ensure().schedule(e));
    for (var n = e.first; n !== null; ) {
      var r = n.next, i = (n.f & ue) !== 0 || (n.f & $) !== 0;
      $t(n, i ? t : !1), n = r;
    }
    var s = e.nodes && e.nodes.t;
    if (s !== null)
      for (const f of s)
        (f.is_global || t) && f.in();
  }
}
function Xt(e, t) {
  if (e.nodes)
    for (var n = e.nodes.start, r = e.nodes.end; n !== null; ) {
      var i = n === r ? null : /* @__PURE__ */ ct(n);
      t.append(n), n = i;
    }
}
let se = !1;
function mt(e) {
  se = e;
}
let _ = null, I = !1;
function D(e) {
  _ = e;
}
let g = null;
function U(e) {
  g = e;
}
let V = null;
function er(e) {
  _ !== null && ((_.f & Fe) !== 0 || (_.f & k) !== 0) && (V ??= /* @__PURE__ */ new Set()).add(e);
}
let x = null, T = 0, C = null;
function tr(e) {
  C = e;
}
let Zt = 1, re = 0, ie = re;
function yt(e) {
  ie = e;
}
function Jt() {
  return ++Zt;
}
function Ce(e) {
  var t = e.f;
  if ((t & m) !== 0)
    return !0;
  if ((t & O) !== 0) {
    for (var n = (
      /** @type {Value[]} */
      e.deps
    ), r = n.length, i = 0; i < r; i++) {
      var s = n[i];
      if (Ce(
        /** @type {Derived} */
        s
      ) && Ft(
        /** @type {Derived} */
        s
      ), s.wv > e.wv)
        return !0;
    }
    (t & L) !== 0 && // During time traveling we don't want to reset the status so that
    // traversal of the graph in the other batches still happens
    F === null && w(e, E);
  }
  return !1;
}
function Qt(e, t, n = !0) {
  var r = e.reactions;
  if (r !== null && !(V !== null && V.has(e)))
    for (var i = 0; i < r.length; i++) {
      var s = r[i];
      (s.f & k) !== 0 ? Qt(
        /** @type {Derived} */
        s,
        t,
        !1
      ) : t === s && (n ? w(s, m) : (s.f & E) !== 0 && w(s, O), ut(
        /** @type {Effect} */
        s
      ));
    }
}
function en(e) {
  var t = x, n = T, r = C, i = _, s = V, f = j, l = I, o = ie, u = e.f;
  x = /** @type {null | Value[]} */
  null, T = 0, C = null, _ = (u & ($ | J)) === 0 ? e : null, V = null, ae(e.ctx), I = !1, ie = ++re, e.ac !== null && (Ye(() => {
    e.ac.abort(Ae);
  }), e.ac = null);
  try {
    e.f |= Fe;
    var h = (
      /** @type {Function} */
      e.fn
    ), a = h();
    e.f |= he;
    var d = bt(e);
    if (Dt() && C !== null && !I && d !== null && (e.f & (k | O | m)) === 0)
      for (var c = 0; c < /** @type {Source[]} */
      C.length; c++)
        Qt(
          C[c],
          /** @type {Effect} */
          e
        );
    if (i !== null && i !== e) {
      if (re++, i.deps !== null)
        for (let v = 0; v < n; v += 1)
          i.deps[v].rv = re;
      if (t !== null)
        for (const v of t)
          v.rv = re;
      C !== null && (r === null ? r = C : r.push(.../** @type {Source[]} */
      C));
    }
    return (e.f & Z) !== 0 && (e.f ^= Z), a;
  } catch (v) {
    return bt(e), Un(v);
  } finally {
    e.f ^= Fe, x = t, T = n, C = r, _ = i, V = s, ae(f), I = l, ie = o;
  }
}
function bt(e) {
  var t = e.deps, n = p?.is_fork;
  if (x !== null) {
    var r;
    if (n || Te(e, T), t !== null && T > 0)
      for (t.length = T + x.length, r = 0; r < x.length; r++)
        t[T + r] = x[r];
    else
      e.deps = t = x;
    if (ht() && (e.f & L) !== 0)
      for (r = T; r < t.length; r++)
        (t[r].reactions ??= []).push(e);
  } else !n && t !== null && T < t.length && (Te(e, T), t.length = T);
  return t;
}
function nr(e, t) {
  let n = t.reactions;
  if (n !== null) {
    var r = fn.call(n, e);
    if (r !== -1) {
      var i = n.length - 1;
      i === 0 ? n = t.reactions = null : (n[r] = n[i], n.pop());
    }
  }
  if (n === null && (t.f & k) !== 0 && // Destroying a child effect while updating a parent effect can cause a dependency to appear
  // to be unused, when in fact it is used by the currently-updating parent. Checking `new_deps`
  // allows us to skip the expensive work of disconnecting and immediately reconnecting it
  (x === null || !Se.call(x, t))) {
    var s = (
      /** @type {Derived} */
      t
    );
    (s.f & L) !== 0 && (s.f ^= L), s.v !== b && lt(s), s.ac !== null && Ye(() => {
      s.ac.abort(Ae), s.ac = null, w(s, m);
    }), In(s), Te(s, 0);
  }
}
function Te(e, t) {
  var n = e.deps;
  if (n !== null)
    for (var r = t; r < n.length; r++)
      nr(e, n[r]);
}
function ce(e) {
  var t = e.f;
  if ((t & S) === 0) {
    w(e, E);
    var n = g;
    g = e;
    try {
      (t & (P | At)) !== 0 ? Jn(e) : dt(e), Gt(e);
      var r = en(e);
      e.teardown = typeof r == "function" ? r : null, e.wv = Zt;
      var i;
    } finally {
      g = n;
    }
  }
}
function R(e) {
  var t = e.f, n = (t & k) !== 0;
  if (_ !== null && !I) {
    var r = g !== null && (g.f & S) !== 0;
    if (!r && (V === null || !V.has(e))) {
      var i = _.deps;
      if ((_.f & Fe) !== 0)
        e.rv < re && (e.rv = re, x === null && i !== null && i[T] === e ? T++ : x === null ? x = [e] : x.push(e));
      else {
        _.deps ??= [], Se.call(_.deps, e) || _.deps.push(e);
        var s = e.reactions;
        s === null ? e.reactions = [_] : Se.call(s, _) || s.push(_);
      }
    }
  }
  if (se && B.has(e))
    return B.get(e);
  if (n) {
    var f = (
      /** @type {Derived} */
      e
    );
    if (se) {
      var l = f.v;
      return ((f.f & E) === 0 && f.reactions !== null || nn(f)) && (l = ft(f)), B.set(f, l), l;
    }
    var o = (f.f & L) === 0 && !I && _ !== null && (_.f & L) !== 0, u = (f.f & he) === 0;
    Ce(f) && (o && (f.f |= L), Ft(f)), o && !u && (It(f), tn(f));
  }
  if (F?.has(e))
    return F.get(e);
  if ((e.f & Z) !== 0)
    throw e.v;
  return e.v;
}
function tn(e) {
  if (e.f |= L, e.deps !== null)
    for (const n of e.deps) {
      var t = n.reactions;
      t === null ? n.reactions = [e] : Se.call(t, e) || t.push(e), (n.f & k) !== 0 && (n.f & L) === 0 && (It(
        /** @type {Derived} */
        n
      ), tn(
        /** @type {Derived} */
        n
      ));
    }
}
function nn(e) {
  if (e.v === b) return !0;
  if (e.deps === null) return !1;
  for (const t of e.deps)
    if (B.has(t) || (t.f & k) !== 0 && nn(
      /** @type {Derived} */
      t
    ))
      return !0;
  return !1;
}
function rr(e) {
  var t = I;
  try {
    return I = !0, e();
  } finally {
    I = t;
  }
}
const ir = ["touchstart", "touchmove"];
function sr(e) {
  return ir.includes(e);
}
const me = Symbol("events"), rn = /* @__PURE__ */ new Set(), it = /* @__PURE__ */ new Set();
function Ke(e, t, n) {
  (t[me] ??= {})[e] = n;
}
function lr(e) {
  for (var t = 0; t < e.length; t++)
    rn.add(e[t]);
  for (var n of it)
    n(e);
}
let We = null, $e = !1;
function Et(e) {
  var t = this, n = (
    /** @type {Node} */
    t.ownerDocument
  ), r = e.type, i = e.composedPath?.() || [], s = (
    /** @type {null | Element} */
    i[0] || e.target
  );
  We = e, $e || ($e = !0, setTimeout(() => {
    $e = !1, We = null;
  }));
  var f = 0, l = We === e && e[me];
  if (l) {
    var o = i.indexOf(l);
    if (o !== -1 && (t === document || t === /** @type {any} */
    window)) {
      e[me] = t;
      return;
    }
    var u = i.indexOf(t);
    if (u === -1)
      return;
    o <= u && (f = o);
  }
  if (s = /** @type {Element} */
  i[f] || e.target, s !== t) {
    xt(e, "currentTarget", {
      configurable: !0,
      get() {
        return s || n;
      }
    });
    var h = _, a = g;
    D(null), U(null);
    try {
      for (var d, c = []; s !== null && s !== t; ) {
        try {
          var v = s[me]?.[r];
          v != null && (!/** @type {any} */
          s.disabled || // DOM could've been updated already by the time this is reached, so we check this as well
          // -> the target could not have been disabled because it emits the event in the first place
          e.target === s) && v.call(s, e);
        } catch (y) {
          d ? c.push(y) : d = y;
        }
        if (e.cancelBubble) break;
        f++, s = f < i.length ? (
          /** @type {Element} */
          i[f]
        ) : null;
      }
      if (d) {
        for (let y of c)
          queueMicrotask(() => {
            throw y;
          });
        throw d;
      }
    } finally {
      e[me] = t, delete e.currentTarget, D(h), U(a);
    }
  }
}
const fr = (
  // We gotta write it like this because after downleveling the pure comment may end up in the wrong location
  globalThis?.window?.trustedTypes && /* @__PURE__ */ globalThis.window.trustedTypes.createPolicy("svelte-trusted-html", {
    /** @param {string} html */
    createHTML: (e) => e
  })
);
function or(e) {
  return (
    /** @type {string} */
    fr?.createHTML(e) ?? e
  );
}
function ur(e) {
  var t = Vn("template");
  return t.innerHTML = or(e.replaceAll("<!>", "<!---->")), t.content;
}
function ar(e, t) {
  var n = (
    /** @type {Effect} */
    g
  );
  n.nodes === null && (n.nodes = { start: e, end: t, a: null, t: null });
}
// @__NO_SIDE_EFFECTS__
function Ve(e, t) {
  var n = (t & wn) !== 0, r, i = !e.startsWith("<!>");
  return () => {
    r === void 0 && (r = ur(i ? e : "<!>" + e), r = /** @type {TemplateNode} */
    /* @__PURE__ */ at(r));
    var s = (
      /** @type {TemplateNode} */
      n || Bt ? document.importNode(r, !0) : r.cloneNode(!0)
    );
    return ar(s, s), s;
  };
}
function Oe(e, t) {
  e !== null && e.before(
    /** @type {Node} */
    t
  );
}
function cr(e) {
  let t = 0, n = Be(0), r;
  return () => {
    ht() && (R(n), Xn(() => (t === 0 && (r = rr(() => e(() => Ee(n)))), t += 1, () => {
      ne(() => {
        t -= 1, t === 0 && (r?.(), r = void 0, Ee(n));
      });
    })));
  };
}
var hr = ue | de;
function dr(e, t, n, r) {
  new vr(e, t, n, r);
}
class vr {
  /** @type {Boundary | null} */
  parent;
  is_pending = !1;
  /**
   * API-level transformError transform function. Transforms errors before they reach the `failed` snippet.
   * Inherited from parent boundary, or defaults to identity.
   * @type {(error: unknown) => unknown}
   */
  transform_error;
  /** @type {TemplateNode} */
  #t;
  /** @type {TemplateNode | null} */
  #l = null;
  /** @type {BoundaryProps} */
  #e;
  /** @type {((anchor: Node) => void)} */
  #o;
  /** @type {Effect} */
  #r;
  /** @type {Effect | null} */
  #s = null;
  /** @type {Effect | null} */
  #n = null;
  /** @type {Effect | null} */
  #f = null;
  /** @type {DocumentFragment | null} */
  #i = null;
  #p = 0;
  #u = 0;
  #a = !1;
  /** @type {Set<Effect>} */
  #h = /* @__PURE__ */ new Set();
  /** @type {Set<Effect>} */
  #g = /* @__PURE__ */ new Set();
  /**
   * A source containing the number of pending async deriveds/expressions.
   * Only created if `$effect.pending()` is used inside the boundary,
   * otherwise updating the source results in needless `Batch.ensure()`
   * calls followed by no-op flushes
   * @type {Source<number> | null}
   */
  #c = null;
  #b = cr(() => (this.#c = Be(this.#p), () => {
    this.#c = null;
  }));
  /**
   * @param {TemplateNode} node
   * @param {BoundaryProps} props
   * @param {((anchor: Node) => void)} children
   * @param {((error: unknown) => unknown) | undefined} [transform_error]
   */
  constructor(t, n, r, i) {
    this.#t = t, this.#e = n, this.#o = (s) => {
      var f = (
        /** @type {Effect} */
        g
      );
      f.b = this, f.f |= Je, r(s);
    }, this.parent = /** @type {Effect} */
    g.b, this.transform_error = i ?? this.parent?.transform_error ?? ((s) => s), this.#r = zt(() => {
      this.#v();
    }, hr);
  }
  #E() {
    try {
      this.#s = W(() => this.#o(this.#t));
    } catch (t) {
      this.error(t);
    }
  }
  /**
   * @param {unknown} error The deserialized error from the server's hydration comment
   */
  #w(t) {
    const n = this.#e.failed, { reset: r, invoke_onerror: i } = this.#m(t);
    ne(i), n && (this.#f = W(() => {
      n(
        this.#t,
        () => t,
        () => r
      );
    }));
  }
  /**
   * Creates the `reset` function for a failed boundary, along with a function
   * that invokes `onerror` with it (if provided)
   * @param {unknown} error
   * @returns {{ reset: () => void, invoke_onerror: () => void }}
   */
  #m(t) {
    var n = !1, r = !1;
    const i = () => {
      if (!this.#d()) {
        if (n) {
          yn();
          return;
        }
        n = !0, r && Tn(), this.#f !== null && ke(this.#f, () => {
          this.#f = null;
        }), this.#_(() => {
          this.#v();
        });
      }
    };
    return { reset: i, invoke_onerror: () => {
      if (!this.#d())
        try {
          r = !0, this.#e.onerror?.(t, i), r = !1;
        } catch (f) {
          Y(f, this.#r && this.#r.parent);
        }
    } };
  }
  #d() {
    return (this.#r.f & (S | Me)) !== 0;
  }
  #k() {
    const t = this.#e.pending;
    t && (this.is_pending = !0, this.#n = W(() => t(this.#t)), ne(() => {
      if (!this.#d()) {
        var n = this.#i = document.createDocumentFragment(), r = qe(), i = !1;
        if (n.append(r), this.#s = this.#_(() => {
          try {
            return W(() => this.#o(r));
          } catch (s) {
            try {
              this.error(s), i = !0;
            } catch (f) {
              Y(f, this.#r.parent);
            }
            return null;
          }
        }), this.#s === null) {
          this.#i = null, i && this.#y(
            /** @type {Batch} */
            p
          );
          return;
        }
        this.#u === 0 && (this.#t.before(n), this.#i = null, ke(
          /** @type {Effect} */
          this.#n,
          () => {
            this.#n = null;
          }
        ), this.#y(
          /** @type {Batch} */
          p
        ));
      }
    }));
  }
  #v() {
    try {
      if (this.is_pending = this.has_pending_snippet(), this.#u = 0, this.#p = 0, this.#s = W(() => {
        this.#o(this.#t);
      }), this.#u > 0) {
        var t = this.#i = document.createDocumentFragment();
        Xt(this.#s, t);
        const n = (
          /** @type {(anchor: Node) => void} */
          this.#e.pending
        );
        this.#n = W(() => n(this.#t));
      } else
        this.#y(
          /** @type {Batch} */
          p
        );
    } catch (n) {
      this.error(n);
    }
  }
  /**
   * @param {Batch} batch
   */
  #y(t) {
    this.is_pending = !1, t.transfer_effects(this.#h, this.#g);
  }
  /**
   * Defer an effect inside a pending boundary until the boundary resolves
   * @param {Effect} effect
   */
  defer_effect(t) {
    Mt(t, this.#h, this.#g);
  }
  /**
   * Returns `false` if the effect exists inside a boundary whose pending snippet is shown
   * @returns {boolean}
   */
  is_rendered() {
    return !this.is_pending && (!this.parent || this.parent.is_rendered());
  }
  has_pending_snippet() {
    return !!this.#e.pending;
  }
  /**
   * @template T
   * @param {() => T} fn
   */
  #_(t) {
    var n = g, r = _, i = j;
    U(this.#r), D(this.#r), ae(this.#r.ctx);
    try {
      return Q.ensure(), t();
    } finally {
      U(n), D(r), ae(i);
    }
  }
  /**
   * Updates the pending count associated with the currently visible pending snippet,
   * if any, such that we can replace the snippet with content once work is done
   * @param {1 | -1} d
   * @param {Batch} batch
   */
  #S(t, n) {
    if (!this.has_pending_snippet()) {
      this.parent && this.parent.#S(t, n);
      return;
    }
    this.#u += t, this.#u === 0 && (this.#y(n), this.#n && ke(this.#n, () => {
      this.#n = null;
    }), this.#i && (this.#t.before(this.#i), this.#i = null));
  }
  /**
   * Update the source that powers `$effect.pending()` inside this boundary,
   * and controls when the current `pending` snippet (if any) is removed.
   * Do not call from inside the class
   * @param {1 | -1} d
   * @param {Batch} batch
   */
  update_pending_count(t, n) {
    this.#S(t, n), this.#p += t, !(!this.#c || this.#a) && (this.#a = !0, ne(() => {
      this.#a = !1, this.#c && je(this.#c, this.#p);
    }));
  }
  get_effect_pending() {
    return this.#b(), R(
      /** @type {Source<number>} */
      this.#c
    );
  }
  /** @param {unknown} error */
  error(t) {
    if (t === Rt || !this.#e.onerror && !this.#e.failed)
      throw t;
    p?.is_fork ? (this.#s && p.skip_effect(this.#s), this.#n && p.skip_effect(this.#n), this.#f && p.skip_effect(this.#f), p.oncommit(() => {
      this.#d() || this.#x(t);
    })) : this.#x(t);
  }
  /**
   * @param {unknown} error
   */
  #x(t) {
    this.#s && (A(this.#s), this.#s = null), this.#n && (A(this.#n), this.#n = null), this.#f && (A(this.#f), this.#f = null);
    let n = this.#e.failed;
    const r = (i) => {
      if (this.#d()) return;
      const { reset: s, invoke_onerror: f } = this.#m(i);
      f(), n && !this.#d() && (this.#f = this.#_(() => {
        try {
          return W(() => {
            var l = (
              /** @type {Effect} */
              g
            );
            l.b = this, l.f |= Je, n(
              this.#t,
              () => i,
              () => s
            );
          });
        } catch (l) {
          return Y(
            l,
            /** @type {Effect} */
            this.#r.parent
          ), null;
        }
      }));
    };
    ne(() => {
      if (!this.#d()) {
        var i;
        try {
          i = this.transform_error(t);
        } catch (s) {
          Y(s, this.#r && this.#r.parent);
          return;
        }
        i !== null && typeof i == "object" && typeof /** @type {any} */
        i.then == "function" ? i.then(
          r,
          /** @param {unknown} e */
          (s) => Y(s, this.#r && this.#r.parent)
        ) : r(i);
      }
    });
  }
}
function _r(e, t) {
  var n = t == null ? "" : typeof t == "object" ? `${t}` : t;
  n !== /** @type {any} */
  (e[et] ??= e.nodeValue) && (e[et] = n, e.nodeValue = `${n}`);
}
function Cr(e, t) {
  return pr(e, t);
}
const Ne = /* @__PURE__ */ new Map();
function pr(e, { target: t, anchor: n, props: r = {}, events: i, context: s, intro: f = !0, transformError: l }) {
  Hn();
  var o = void 0, u = Wn(() => {
    var h = n ?? t.appendChild(qe());
    dr(
      /** @type {TemplateNode} */
      h,
      {
        pending: () => {
        }
      },
      (c) => {
        An({});
        var v = (
          /** @type {ComponentContext} */
          j
        );
        s && (v.c = s), i && (r.$$events = i), o = e(c, r) || Nt(), Cn();
      },
      l
    );
    var a = /* @__PURE__ */ new Set(), d = (c) => {
      for (var v = 0; v < c.length; v++) {
        var y = c[v];
        if (!a.has(y)) {
          a.add(y);
          var q = sr(y);
          for (const ve of [t, document]) {
            var M = Ne.get(ve);
            M === void 0 && (M = /* @__PURE__ */ new Map(), Ne.set(ve, M));
            var X = M.get(y);
            X === void 0 ? (ve.addEventListener(y, Et, { passive: q }), M.set(y, 1)) : M.set(y, X + 1);
          }
        }
      }
    };
    return d(on(rn)), it.add(d), () => {
      for (var c of a)
        for (const q of [t, document]) {
          var v = (
            /** @type {Map<string, number>} */
            Ne.get(q)
          ), y = (
            /** @type {number} */
            v.get(c)
          );
          --y == 0 ? (q.removeEventListener(c, Et), v.delete(c), v.size === 0 && Ne.delete(q)) : v.set(c, y);
        }
      it.delete(d), h !== n && h.parentNode?.removeChild(h);
    };
  });
  return gr.set(o, u), o;
}
let gr = /* @__PURE__ */ new WeakMap();
class wr {
  /** @type {TemplateNode} */
  anchor;
  /** @type {Map<Batch, Key>} */
  #t = /* @__PURE__ */ new Map();
  /**
   * Map of keys to effects that are currently rendered in the DOM.
   * These effects are visible and actively part of the document tree.
   * Example:
   * ```
   * {#if condition}
   * 	foo
   * {:else}
   * 	bar
   * {/if}
   * ```
   * Can result in the entries `true->Effect` and `false->Effect`
   * @type {Map<Key, Effect>}
   */
  #l = /* @__PURE__ */ new Map();
  /**
   * Similar to #onscreen with respect to the keys, but contains branches that are not yet
   * in the DOM, because their insertion is deferred.
   * @type {Map<Key, Branch>}
   */
  #e = /* @__PURE__ */ new Map();
  /**
   * Keys of effects that are currently outroing
   * @type {Set<Key>}
   */
  #o = /* @__PURE__ */ new Set();
  /**
   * Whether to pause (i.e. outro) on change, or destroy immediately.
   * This is necessary for `<svelte:element>`
   */
  #r = !0;
  /**
   * @param {TemplateNode} anchor
   * @param {boolean} transition
   */
  constructor(t, n = !0) {
    this.anchor = t, this.#r = n;
  }
  /**
   * @param {Batch} batch
   */
  #s = (t) => {
    if (this.#t.has(t)) {
      var n = (
        /** @type {Key} */
        this.#t.get(t)
      ), r = this.#l.get(n);
      if (r)
        wt(r), this.#o.delete(n);
      else {
        var i = this.#e.get(n);
        i && (wt(i.effect), this.#l.set(n, i.effect), this.#e.delete(n), i.fragment.lastChild.remove(), this.anchor.before(i.fragment), r = i.effect);
      }
      for (const [s, f] of this.#t) {
        if (this.#t.delete(s), s === t)
          break;
        const l = this.#e.get(f);
        l && (A(l.effect), this.#e.delete(f));
      }
      for (const [s, f] of this.#l) {
        if (s === n || this.#o.has(s)) continue;
        const l = () => {
          if (Array.from(this.#t.values()).includes(s)) {
            var u = document.createDocumentFragment();
            Xt(f, u), u.append(qe()), this.#e.set(s, { effect: f, fragment: u });
          } else
            A(f);
          this.#o.delete(s), this.#l.delete(s);
        };
        this.#r || !r ? (this.#o.add(s), ke(f, l, !1)) : l();
      }
    }
  };
  /**
   * @param {Batch} batch
   */
  #n = (t) => {
    this.#t.delete(t);
    const n = Array.from(this.#t.values());
    for (const [r, i] of this.#e)
      n.includes(r) || (A(i.effect), this.#e.delete(r));
  };
  /**
   *
   * @param {any} key
   * @param {null | ((target: TemplateNode) => void)} fn
   */
  ensure(t, n) {
    var r = (
      /** @type {Batch} */
      p
    ), i = Bn();
    if (n && !this.#l.has(t) && !this.#e.has(t))
      if (i) {
        var s = document.createDocumentFragment(), f = qe();
        s.append(f), this.#e.set(t, {
          effect: W(() => n(f)),
          fragment: s
        });
      } else
        this.#l.set(
          t,
          W(() => n(this.anchor))
        );
    if (this.#t.set(r, t), i) {
      for (const [l, o] of this.#l)
        l === t ? r.unskip_effect(o) : r.skip_effect(o);
      for (const [l, o] of this.#e)
        l === t ? r.unskip_effect(o.effect) : r.skip_effect(o.effect);
      r.oncommit(this.#s), r.ondiscard(this.#n);
    } else
      this.#s(r);
  }
}
function mr(e, t, n = !1) {
  var r = new wr(e), i = n ? ue : 0;
  function s(f, l) {
    r.ensure(f, l);
  }
  zt(() => {
    var f = !1;
    t((l, o = 0) => {
      f = !0, s(o, l);
    }), f || s(-1, null);
  }, i);
}
const kt = [...` 	
\r\f \v\uFEFF`];
function yr(e, t, n) {
  var r = "" + e;
  if (n) {
    for (var i of Object.keys(n))
      if (n[i])
        r = r ? r + " " + i : i;
      else if (r.length)
        for (var s = i.length, f = 0; (f = r.indexOf(i, f)) >= 0; ) {
          var l = f + s;
          (f === 0 || kt.includes(r[f - 1])) && (l === r.length || kt.includes(r[l])) ? r = (f === 0 ? "" : r.substring(0, f)) + r.substring(l + 1) : f = l;
        }
  }
  return r === "" ? null : r;
}
function Xe(e, t, n, r, i, s) {
  var f = (
    /** @type {any} */
    e[Qe]
  );
  if (f !== n || f === void 0) {
    var l = yr(n, r, s);
    l == null ? e.removeAttribute("class") : e.className = l, e[Qe] = n;
  } else if (s && i !== s)
    for (var o in s) {
      var u = !!s[o];
      (i == null || u !== !!i[o]) && e.classList.toggle(o, u);
    }
  return s;
}
function br(e, t, n, r) {
  var i = (
    /** @type {V} */
    r
  ), s = !0, f = () => (s && (s = !1, i = /** @type {V} */
  r), i), l;
  l = /** @type {V} */
  e[t], l === void 0 && r !== void 0 && (l = f());
  var o;
  return o = () => {
    var u = (
      /** @type {V} */
      e[t]
    );
    return u === void 0 ? f() : (s = !0, u);
  }, o;
}
const Er = "5";
typeof window < "u" && ((window.__svelte ??= {}).v ??= /* @__PURE__ */ new Set()).add(Er);
var kr = /* @__PURE__ */ Ve('<div class="panel svelte-1n46o8q">Timeline Workspace Initialized</div>'), Sr = /* @__PURE__ */ Ve('<div class="panel svelte-1n46o8q">Global References & Concepts Pool</div>'), xr = /* @__PURE__ */ Ve('<div class="panel svelte-1n46o8q">Live Canvas Playback Monitor</div>'), Tr = /* @__PURE__ */ Ve('<div class="eternity-studio-root svelte-1n46o8q"><div class="studio-header svelte-1n46o8q"><span class="studio-badge svelte-1n46o8q">ALPHA</span> <span class="studio-title svelte-1n46o8q"> </span> <div class="studio-nav svelte-1n46o8q"><button>Timeline</button> <button>Concepts</button> <button>Preview</button></div></div> <div class="studio-body svelte-1n46o8q"><!></div></div>');
function Rr(e, t) {
  let n = br(t, "title", 3, "Eternity Studio 🎬"), r = /* @__PURE__ */ G("timeline");
  var i = Tr(), s = Re(i), f = pe(Re(s), 2), l = Yn(f, !0), o = pe(f, 2), u = Re(o);
  let h;
  var a = pe(u, 2);
  let d;
  var c = pe(a, 2);
  let v;
  var y = pe(s, 2), q = Re(y);
  {
    var M = (z) => {
      var _e = kr();
      Oe(z, _e);
    }, X = (z) => {
      var _e = Sr();
      Oe(z, _e);
    }, ve = (z) => {
      var _e = xr();
      Oe(z, _e);
    };
    mr(q, (z) => {
      R(r) === "timeline" ? z(M) : R(r) === "concepts" ? z(X, 1) : z(ve, -1);
    });
  }
  Zn(() => {
    _r(l, n()), h = Xe(u, 1, "svelte-1n46o8q", null, h, { active: R(r) === "timeline" }), d = Xe(a, 1, "svelte-1n46o8q", null, d, { active: R(r) === "concepts" }), v = Xe(c, 1, "svelte-1n46o8q", null, v, { active: R(r) === "preview" });
  }), Ke("click", u, () => H(r, "timeline")), Ke("click", a, () => H(r, "concepts")), Ke("click", c, () => H(r, "preview")), Oe(e, i);
}
lr(["click"]);
function sn() {
  if (!(typeof window > "u"))
    return window.comfyAPI?.app?.app || window.app;
}
const St = {
  name: "MinimaxH3.EternityStudio",
  async init(e) {
    console.log("[Eternity Studio] Extension initializing (Svelte 5 + TS Suite)...");
  },
  async setup(e) {
    console.log("[Eternity Studio] Extension setup ready.");
  },
  nodeCreated(e, t) {
  }
}, Ze = sn();
Ze && typeof Ze.registerExtension == "function" ? Ze.registerExtension(St) : window.addEventListener("DOMContentLoaded", () => {
  const e = sn();
  e && typeof e.registerExtension == "function" && e.registerExtension(St);
});
export {
  Rr as App,
  Cr as mount,
  St as studioExtension
};
