/* Cone (Geometry3D level 2): the stock body drew Box, Cylinder, Sphere and the indexed sets only, so a Cone was skipped with a note. The reader already knows the node; this module gives it
   geometry (the kit draws it like a geometry set): a smooth side with the slope normal, a flat bottom disc, `side` and `bottom` switch the parts, 48 segments like the stock Cylinder.
   No field table: the reader's own. Apex at +y height/2, base at -y height/2 (19775-1 13.3.1). */
BR.node('Cone', {
  component: 'Geometry3D', level: 2,
  geometry(g) {
    const r = g.f.bottomRadius, h = g.f.height, N = 48, pos = [], nrm = [], uv = [], idx = [];
    const slope = Math.hypot(h, r) || 1, ny = r / slope, nr = h / slope;
    if (g.f.side !== false) {
      for (let i = 0; i <= N; i++) {
        const t = (i / N) * Math.PI * 2, x = Math.sin(t), z = Math.cos(t), tm = ((i + 0.5) / N) * Math.PI * 2;
        pos.push(0, h / 2, 0, x * r, -h / 2, z * r);                                    // apex copy (normal at the middle of the segment) and base rim
        nrm.push(nr * Math.sin(tm), ny, nr * Math.cos(tm), nr * x, ny, nr * z);
        uv.push(1 - (i + 0.5) / N, 1, 1 - i / N, 0);
      }
      for (let i = 0; i < N; i++) { const a = i * 2, b = a + 1, c = a + 2, d = a + 3; idx.push(a, b, d, a, d, c); }        // apex, rim i, rim i+1 counter-clockwise seen from outside
    }
    if (g.f.bottom !== false) {
      const base = pos.length / 3; pos.push(0, -h / 2, 0); nrm.push(0, -1, 0); uv.push(0.5, 0.5);
      for (let i = 0; i <= N; i++) { const t = (i / N) * Math.PI * 2, x = Math.sin(t), z = Math.cos(t); pos.push(x * r, -h / 2, z * r); nrm.push(0, -1, 0); uv.push(0.5 + x / 2, 0.5 - z / 2); }
      for (let i = 0; i < N; i++) idx.push(base, base + 2 + i, base + 1 + i);
    }
    return { pos: Float32Array.from(pos), nrm: Float32Array.from(nrm), col: null, uv: Float32Array.from(uv), idx: Uint32Array.from(idx) };
  },
  changed(body, n, field) { if (['bottomRadius', 'height', 'side', 'bottom'].includes(field)) body.regeo(n); },
});
