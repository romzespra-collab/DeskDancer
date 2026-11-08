// dancer.js  v1.4.0 — 3D-сцена DeskDancer: девушки танцуют в такт музыке.
//
// Журнал:
// v1.4.0: ?bg=RRGGBB — сплошной фон (предпросмотр в окне программы, тёмный фон
//         сцены); DD.setBg(цвет), DD.pause(да/нет) — не рисовать, пока не видно
// v1.3.0: режим «Неон» — светящийся контур фигуры и складок (Собель по цвету и
//         силуэту), широкое свечение, палитры «Огонь», «Неон», «Радуга»,
//         вспышка на каждую долю
// v1.1.0: скелет 3ds Max Biped (Rocketbox): имена костей, перемещение тела через
//         Bip01; тот же скелет — повороты как есть; разная поза покоя
//         (T / A) — поправка направления костей; рост — по высоте бёдер
// v1.0.0: первая версия — модели GLB/GLTF/FBX (Mixamo и др.), танцы из
//         отдельных файлов (перенос анимации по именам костей), темп танца
//         подстраивается под BPM, фаза — под долю; встроенный манекен с
//         процедурными танцами; до 6 девушек; прозрачный фон.
//
// Управление из Python (QWebEnginePage.runJavaScript):
//   DD.setScene({dancers:[{char, dance, scale}], spacing, light, shadow, inplace, mult,
//                style: 'real'|'neon', palette: 'fire'|'neon'|'rainbow', glow: 0…200})
//   DD.beat({bpm, phase, energy, active, conf})   ~30 раз в секунду
//   DD.status() → JSON-строка
import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { FBXLoader } from 'three/addons/loaders/FBXLoader.js';
import * as SkeletonUtils from 'three/addons/utils/SkeletonUtils.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';

const log = (...a) => console.log('DD:', ...a);
const warn = (...a) => console.warn('DD:', ...a);
const TAU = Math.PI * 2;
const frac = (x) => x - Math.floor(x);
const wrap = (x) => frac(x + 0.5) - 0.5;            // в [-0.5, 0.5)
const lerp = (a, b, k) => a + (b - a) * k;
const HEIGHT = 1.7;                                 // рост девушки, м
const HIP = 0.88;                                   // высота бёдер манекена

// ───────── рендер ─────────
const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, premultipliedAlpha: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio || 1));
renderer.setClearColor(0x000000, 0);
renderer.outputColorSpace = THREE.SRGBColorSpace;
// сплошной фон (предпросмотр в окне программы или сцена без прозрачности): ?bg=RRGGBB
function setBg(c) {
  document.body.style.background = c ? '#' + String(c).replace('#', '') : 'transparent';
}
setBg(new URLSearchParams(location.search).get('bg'));
let paused = false;
renderer.toneMapping = THREE.ACESFilmicToneMapping;          // мягкие блики кожи, как в играх
renderer.toneMappingExposure = 1.0;
document.body.appendChild(renderer.domElement);

const scene = new THREE.Scene();
const camera = new THREE.PerspectiveCamera(28, 1, 0.05, 100);
let neon = null;                                    // эффект «Неон» (создаётся при включении)
const hemi = new THREE.HemisphereLight(0xffffff, 0x50505a, 1.6);
const key = new THREE.DirectionalLight(0xfff2e8, 2.2);
key.position.set(1.5, 3, 3);
const fill = new THREE.DirectionalLight(0xe8f0ff, 0.9);
fill.position.set(-2, 1.5, 1.5);
const rim = new THREE.DirectionalLight(0xffffff, 1.0);
rim.position.set(0, 2.5, -3);
scene.add(hemi, key, fill, rim);
// отражения окружения — у PBR-моделей (кожа, ткань, волосы) объём и блики
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(renderer), 0.04).texture;

const msgEl = document.getElementById('msg');
let msgTimer = 0;
function showMsg(t, sec = 6) { msgEl.textContent = t; msgTimer = sec; }

// мягкая тень-пятно под ногами
const shadowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 128;
  const g = c.getContext('2d');
  const gr = g.createRadialGradient(64, 64, 4, 64, 64, 62);
  gr.addColorStop(0, 'rgba(0,0,0,0.55)'); gr.addColorStop(1, 'rgba(0,0,0,0)');
  g.fillStyle = gr; g.fillRect(0, 0, 128, 128);
  return new THREE.CanvasTexture(c);
})();

// ───────── музыкальные часы ─────────
const music = { bpm: 120, beat: 0, energy: 0, active: false, conf: 0, last: 0, synced: false };

function onBeat(st) {
  music.last = performance.now();
  music.energy = lerp(music.energy, +st.energy || 0, 0.3);
  music.conf = +st.conf || 0;
  if (!st.active || !(st.bpm > 0)) { music.active = false; return; }
  const bpm = +st.bpm;
  if (Math.abs(bpm / music.bpm - 1) > 0.06) music.bpm = bpm; else music.bpm = lerp(music.bpm, bpm, 0.2);
  const err = wrap(st.phase - frac(music.beat));
  if (!music.synced || Math.abs(err) > 0.3) { music.beat += err; music.synced = true; }
  else music.beat += err * 0.15;
  music.active = true;
}

// ───────── загрузка файлов ─────────
const cache = new Map();
function loadFile(url) {
  if (cache.has(url)) return cache.get(url);
  const low = url.toLowerCase();
  let p;
  if (low.endsWith('.fbx')) {
    p = new FBXLoader().loadAsync(url).then((g) => ({ scene: g, animations: g.animations || [] }));
  } else {
    p = new GLTFLoader().loadAsync(url).then((g) => ({ scene: g.scene, animations: g.animations || [] }));
  }
  p.catch(() => cache.delete(url));
  cache.set(url, p);
  return p;
}
const fileUrl = (rel) => '../' + rel.split('/').map(encodeURIComponent).join('/');

// Скелеты реалистичных моделей → имена Mixamo (танцы Mixamo подходят к ним):
// Character Creator 4 / iClone, Unreal / MetaHuman, Daz Genesis 8/9, VRM
const ALIAS = (() => {
  const m = {};
  const add = (canon, ...names) => names.forEach((n) => { m[n.toLowerCase().replace(/[^a-z0-9]/g, '')] = canon; });
  add('hips', 'Bip01_Pelvis', 'Bip01 Pelvis', 'CC_Base_Hip', 'pelvis', 'hip', 'J_Bip_C_Hips', 'root_hips');
  add('spine', 'Bip01_Spine', 'CC_Base_Waist', 'spine_01', 'abdomenLower', 'abdomen1', 'J_Bip_C_Spine');
  add('spine1', 'Bip01_Spine1', 'CC_Base_Spine01', 'spine_02', 'abdomenUpper', 'abdomen2', 'J_Bip_C_Chest');
  add('spine2', 'Bip01_Spine2', 'CC_Base_Spine02', 'spine_03', 'chestLower', 'chest', 'J_Bip_C_UpperChest');
  add('neck', 'Bip01_Neck', 'CC_Base_NeckTwist01', 'neck_01', 'neckLower', 'J_Bip_C_Neck');
  add('head', 'Bip01_Head', 'CC_Base_Head', 'J_Bip_C_Head');
  for (const [s, cc, ue, dz, vr] of [['left', 'L', 'l', 'l', 'L'], ['right', 'R', 'r', 'r', 'R']].map(
    ([s, c, u, d, v]) => [s, c, u, d, v])) {
    add(s + 'shoulder', `Bip01_${cc}_Clavicle`, `CC_Base_${cc}_Clavicle`, `clavicle_${ue}`, `${dz}Collar`, `J_Bip_${vr}_Shoulder`);
    add(s + 'arm', `Bip01_${cc}_UpperArm`, `CC_Base_${cc}_Upperarm`, `upperarm_${ue}`, `${dz}ShldrBend`, `${dz}Shldr`, `J_Bip_${vr}_UpperArm`);
    add(s + 'forearm', `Bip01_${cc}_Forearm`, `CC_Base_${cc}_Forearm`, `lowerarm_${ue}`, `${dz}ForearmBend`, `${dz}ForeArm`, `J_Bip_${vr}_LowerArm`);
    add(s + 'hand', `Bip01_${cc}_Hand`, `CC_Base_${cc}_Hand`, `hand_${ue}`, `${dz}Hand`, `J_Bip_${vr}_Hand`);
    add(s + 'upleg', `Bip01_${cc}_Thigh`, `CC_Base_${cc}_Thigh`, `thigh_${ue}`, `${dz}ThighBend`, `${dz}Thigh`, `J_Bip_${vr}_UpperLeg`);
    add(s + 'leg', `Bip01_${cc}_Calf`, `CC_Base_${cc}_Calf`, `calf_${ue}`, `${dz}Shin`, `J_Bip_${vr}_LowerLeg`);
    add(s + 'foot', `Bip01_${cc}_Foot`, `CC_Base_${cc}_Foot`, `foot_${ue}`, `${dz}Foot`, `J_Bip_${vr}_Foot`);
    add(s + 'toebase', `Bip01_${cc}_Toe0`, `CC_Base_${cc}_ToeBase`, `ball_${ue}`, `${dz}Toe`, `J_Bip_${vr}_ToeBase`);
  }
  return m;
})();

// имя кости без приставок: «mixamorig:LeftArm», «mixamorig1LeftArm», «Armature|LeftArm» → leftarm
function normBone(n) {
  const k = String(n).toLowerCase().replace(/^.*\|/, '').replace(/^.*mixamorig\d*[:_]?/, '')
    .replace(/[^a-z0-9]/g, '');
  return ALIAS[k] || k;
}

// узлы модели в порядке обхода (родитель раньше детей), кости по именам, бёдра
function rigOf(root) {
  const nodes = [], byName = new Map();
  let hips = null;
  root.traverse((o) => {
    if (o === root) return;
    nodes.push(o);
    if (!o.name) return;
    const n = normBone(o.name);
    if (!byName.has(n) || (o.isBone && !byName.get(n).isBone)) byName.set(n, o);
    if (n === 'hips' && (!hips || (o.isBone && !hips.isBone))) hips = o;
  });
  // кто несёт перемещение тела: бёдра, а у Biped (3ds Max) — их родитель Bip01
  const mover = hips && hips.parent && normBone(hips.parent.name) === 'bip01' ? hips.parent : hips;
  return { root, nodes, byName, hips, mover };
}

// мировые повороты узлов (относительно корня модели); local(o) — свой поворот узла
function worldQ(rig, local) {
  const W = new Map(), I = new THREE.Quaternion();
  for (const o of rig.nodes) {
    const pw = o.parent === rig.root ? I : (W.get(o.parent) || I);
    W.set(o, pw.clone().multiply(local(o)));
  }
  return W;
}

// матрица родителя узла относительно корня модели
function parentMat(rig, o) {
  rig.root.updateMatrixWorld(true);
  const m = new THREE.Matrix4();
  if (!o || !o.parent) return m;
  return m.copy(rig.root.matrixWorld).invert().multiply(o.parent.matrixWorld);
}

const SAMPLE_FPS = 30;

// Перенос клипа на модель через мировые повороты: у файла танца и у модели
// кости могут быть повёрнуты по-разному (FBX из Mixamo и GLB из Blender) —
// переносится отклонение каждой кости от позы покоя (T-поза), а не сырые
// числа. Бёдра: высота — под рост модели, «на месте» — без ухода в сторону.
// src, tgt — нетронутые (не анимированные) исходные сцены файлов.
function retarget(clip, src, tgt, inplace) {
  const S = rigOf(src), T = rigOf(tgt);
  const qInt = new Map();
  let posInt = null;
  for (const t of clip.tracks) {
    const dot = t.name.lastIndexOf('.');
    if (dot < 0) continue;
    const n = normBone(t.name.slice(0, dot)), prop = t.name.slice(dot + 1);
    const o = S.byName.get(n);
    if (!o) continue;
    if (prop === 'quaternion') qInt.set(o, t.createInterpolant(new Float32Array(4)));
    else if (prop === 'position' && o === S.mover) posInt = t.createInterpolant(new Float32Array(3));
  }
  // пары «кость модели ← кость танца»
  const pairs = new Map();
  for (const o of T.nodes) {
    if (!o.name || T.byName.get(normBone(o.name)) !== o) continue;
    const s = S.byName.get(normBone(o.name));
    if (s && qInt.has(s)) pairs.set(o, s);
  }
  if (!pairs.size) return null;
  // скелет тот же (одинаковые имена костей) — повороты переносятся как есть
  const same = [...pairs].every(([o, s]) => o.name === s.name);
  const Ws0 = worldQ(S, (o) => o.quaternion);
  const Wt0 = worldQ(T, (o) => o.quaternion);
  const Ws0i = new Map();
  for (const [o, q] of Ws0) Ws0i.set(o, q.clone().invert());
  const align = same ? null : restAlign(S, T, pairs);
  const n = Math.max(2, Math.ceil(clip.duration * SAMPLE_FPS) + 1);
  const times = new Float32Array(n);
  const out = new Map();
  for (const o of pairs.keys()) out.set(o, new Float32Array(n * 4));
  // перемещение тела
  const Mps = parentMat(S, S.mover), Mpt = parentMat(T, T.mover), Mpti = Mpt.clone().invert();
  const restS = S.mover ? S.mover.position.clone().applyMatrix4(Mps) : new THREE.Vector3();
  const restT = T.mover ? T.mover.position.clone().applyMatrix4(Mpt) : new THREE.Vector3();
  // рост: высота бёдер над полом у обеих моделей
  const hipY = (R) => { R.root.updateMatrixWorld(true); const v = new THREE.Vector3(); if (R.hips) R.hips.getWorldPosition(v); return v.applyMatrix4(R.root.matrixWorld.clone().invert()).y; };
  const hs = hipY(S), ht = hipY(T);
  const ratio = (Math.abs(hs) > 1e-6 && Math.abs(ht) > 1e-6) ? ht / hs : 1;
  if (posInt) {                                 // аддитивный клип (бёдра у нуля) — без позиции
    const p0 = new THREE.Vector3().fromArray(posInt.evaluate(0)).applyMatrix4(Mps);
    if (p0.length() < 0.3 * Math.max(restS.length(), Math.abs(hs))) posInt = null;
  }
  const posOut = posInt && T.mover ? new Float32Array(n * 3) : null;
  const ys = new Float64Array(n);
  const I = new THREE.Quaternion(), q = new THREE.Quaternion(), v = new THREE.Vector3();
  let x0 = 0, z0 = 0;
  for (let i = 0; i < n; i++) {
    const t = Math.min(clip.duration, i / SAMPLE_FPS);
    times[i] = t;
    if (same) {
      for (const [o, s] of pairs) q.fromArray(qInt.get(s).evaluate(t)).normalize().toArray(out.get(o), i * 4);
    } else {
      const Ws = worldQ(S, (o) => (qInt.has(o) ? q.fromArray(qInt.get(o).evaluate(t)) : o.quaternion));
      const Wt = new Map();
      for (const o of T.nodes) {
        const pw = o.parent === T.root ? I : (Wt.get(o.parent) || I);
        const s = pairs.get(o);
        if (s) {
          const w = Ws.get(s).clone().multiply(Ws0i.get(s)).multiply(align.get(o)).multiply(Wt0.get(o));
          Wt.set(o, w);
          pw.clone().invert().multiply(w).normalize().toArray(out.get(o), i * 4);
        } else {
          Wt.set(o, pw.clone().multiply(o.quaternion));
        }
      }
    }
    if (posOut) {
      v.fromArray(posInt.evaluate(t)).applyMatrix4(Mps);
      if (i === 0) { x0 = v.x; z0 = v.z; }
      ys[i] = v.y;
      v.y = restT.y + (v.y - restS.y) * ratio;
      if (inplace) { v.x = restT.x; v.z = restT.z; }
      else { v.x = restT.x + (v.x - x0) * ratio; v.z = restT.z + (v.z - z0) * ratio; }
      v.applyMatrix4(Mpti).toArray(posOut, i * 3);
    }
  }
  const tracks = [];
  for (const [o, arr] of out) {
    // соседние кадры — по короткой дуге (без рывков при интерполяции)
    for (let i = 4; i < arr.length; i += 4) {
      const d = arr[i] * arr[i - 4] + arr[i + 1] * arr[i - 3] + arr[i + 2] * arr[i - 2] + arr[i + 3] * arr[i - 1];
      if (d < 0) for (let k = 0; k < 4; k++) arr[i + k] = -arr[i + k];
    }
    tracks.push(new THREE.QuaternionKeyframeTrack(o.name + '.quaternion', times, arr));
  }
  if (posOut) tracks.push(new THREE.VectorKeyframeTrack(T.mover.name + '.position', times, posOut));
  const res = new THREE.AnimationClip(clip.name, clip.duration, tracks);
  res.userData = { hipsY: posOut ? ys : null, same };
  return res;
}

// Поправка разной позы покоя (T-поза у Mixamo, A-поза у Rocketbox / MetaHuman):
// поворот, который направляет кость модели так же, как кость танца в покое.
function restAlign(S, T, pairs) {
  const pos = (R) => {
    R.root.updateMatrixWorld(true);
    const inv = R.root.matrixWorld.clone().invert(), m = new Map();
    for (const o of R.nodes) m.set(o, new THREE.Vector3().setFromMatrixPosition(o.matrixWorld).applyMatrix4(inv));
    return m;
  };
  const Ps = pos(S), Pt = pos(T);
  const childOf = (o) => {                    // ближайший потомок, у которого есть пара
    const q = [...o.children];
    while (q.length) { const c = q.shift(); if (pairs.has(c)) return c; q.push(...c.children); }
    return null;
  };
  const res = new Map();
  for (const o of T.nodes) {
    if (!pairs.has(o)) continue;
    let a = null;
    const c = childOf(o);
    // бёдра и позвоночник не трогаем — только конечности, шея, голова
    if (c && normBone(o.name) !== 'hips') {
      const dT = Pt.get(c).clone().sub(Pt.get(o)), dS = Ps.get(pairs.get(c)).clone().sub(Ps.get(pairs.get(o)));
      if (dT.lengthSq() > 1e-10 && dS.lengthSq() > 1e-10) a = new THREE.Quaternion().setFromUnitVectors(dT.normalize(), dS.normalize());
    }
    if (!a) {                                 // кисть, стопа: как у ближайшего предка
      let p = o.parent;
      while (p && !res.has(p)) p = p.parent;
      a = p ? res.get(p).clone() : new THREE.Quaternion();
    }
    res.set(o, a);
  }
  return res;
}

// доля в клипе: период «пружинки» бёдер (автокорреляция высоты бёдер)
function analyzeClip(clip) {
  const res = { period: 0.5, t0: 0, auto: false };
  const y0 = clip.userData && clip.userData.hipsY;
  if (!y0 || clip.duration < 1.0) return res;
  const fps = SAMPLE_FPS, n = y0.length;
  const y = Float64Array.from(y0);
  let mean = 0;
  for (let i = 0; i < n; i++) mean += y[i];
  mean /= n;
  for (let i = 0; i < n; i++) y[i] -= mean;
  let e0 = 0; for (let i = 0; i < n; i++) e0 += y[i] * y[i];
  if (e0 < 1e-12) return res;
  const ac = (lag) => { let s = 0; for (let i = 0; i + lag < n; i++) s += y[i] * y[i + lag]; return s / e0 * (n / (n - lag)); };
  let best = 0, bestLag = 0;
  const lo = Math.round(0.25 * fps), hi = Math.min(Math.round(1.6 * fps), Math.floor(n / 2));
  for (let l = lo; l <= hi; l++) {
    const a = ac(l);
    if (a > best && ac(l - 1) <= a && ac(l + 1) <= a) { best = a; bestLag = l; }
  }
  res.best = best; res.lag = bestLag;
  if (!bestLag || best < 0.15) return res;
  // уточнение параболой
  let lag = bestLag;
  const a0 = ac(bestLag - 1), a1 = ac(bestLag), a2 = ac(bestLag + 1), den = a0 - 2 * a1 + a2;
  if (Math.abs(den) > 1e-12) lag += 0.5 * (a0 - a2) / den;
  let period = lag / fps;
  while (period > 0.8) period /= 2;
  while (period < 0.35) period *= 2;
  let tMin = 0, vMin = Infinity;
  for (let i = 0; i < Math.min(n, Math.round(period * fps)); i++) if (y[i] < vMin) { vMin = y[i]; tMin = i / fps; }
  return { period, t0: tMin, auto: true };
}

// ───────── встроенный манекен ─────────
function buildMannequin(color) {
  const skin = new THREE.MeshStandardMaterial({ color: 0xe9bfa6, roughness: 0.55 });
  const dress = new THREE.MeshStandardMaterial({ color, roughness: 0.45, metalness: 0.05 });
  const hairM = new THREE.MeshStandardMaterial({ color: 0x5a3a22, roughness: 0.7 });
  const shoe = new THREE.MeshStandardMaterial({ color: 0x1b1b22, roughness: 0.4 });
  const cap = (r, len, m) => {
    const mesh = new THREE.Mesh(new THREE.CapsuleGeometry(r, len, 6, 14), m);
    mesh.position.y = -len / 2 - r * 0.3;
    return mesh;
  };
  const J = (parent, x, y, z = 0) => { const g = new THREE.Group(); g.position.set(x, y, z); parent.add(g); return g; };
  const root = new THREE.Group();
  const r = { root };
  r.hips = J(root, 0, HIP);
  const pelvis = new THREE.Mesh(new THREE.SphereGeometry(0.15, 20, 14), dress);
  pelvis.scale.set(1.05, 0.7, 0.8); r.hips.add(pelvis);
  const skirt = new THREE.Mesh(new THREE.CylinderGeometry(0.13, 0.27, 0.36, 24, 1, true), dress);
  skirt.material = dress.clone(); skirt.material.side = THREE.DoubleSide;
  skirt.position.y = -0.17; r.hips.add(skirt);
  r.spine = J(r.hips, 0, 0.06);
  const waist = new THREE.Mesh(new THREE.CapsuleGeometry(0.1, 0.12, 6, 16), dress);
  waist.position.y = 0.1; waist.scale.set(1.05, 1, 0.8); r.spine.add(waist);
  r.chest = J(r.spine, 0, 0.2);
  const torso = new THREE.Mesh(new THREE.CapsuleGeometry(0.13, 0.12, 6, 16), dress);
  torso.position.y = 0.1; torso.scale.set(1.15, 1, 0.75); r.chest.add(torso);
  r.neck = J(r.chest, 0, 0.27);
  const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.04, 0.045, 0.08, 12), skin);
  neck.position.y = 0.03; r.neck.add(neck);
  r.head = J(r.neck, 0, 0.08);
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.1, 24, 18), skin);
  head.scale.set(0.9, 1.1, 0.95); head.position.y = 0.09; r.head.add(head);
  const hairTop = new THREE.Mesh(new THREE.SphereGeometry(0.108, 24, 12, 0, TAU, 0, Math.PI * 0.32), hairM);
  hairTop.scale.set(0.95, 1.12, 1.02); hairTop.position.set(0, 0.1, -0.004); r.head.add(hairTop);
  const hairBack = new THREE.Mesh(new THREE.SphereGeometry(0.112, 24, 18, Math.PI, Math.PI, 0, Math.PI * 0.8), hairM);
  hairBack.scale.set(0.98, 1.15, 1.05); hairBack.position.set(0, 0.09, -0.01); r.head.add(hairBack);
  const eyeM = new THREE.MeshStandardMaterial({ color: 0x2a1c18, roughness: 0.3 });
  for (const s of [1, -1]) {
    const eye = new THREE.Mesh(new THREE.SphereGeometry(0.011, 10, 8), eyeM);
    eye.position.set(0.033 * s, 0.1, 0.088); r.head.add(eye);
  }
  const lips = new THREE.Mesh(new THREE.SphereGeometry(0.014, 10, 8), new THREE.MeshStandardMaterial({ color: 0xb4475a, roughness: 0.4 }));
  lips.scale.set(1.4, 0.5, 0.6); lips.position.set(0, 0.045, 0.088); r.head.add(lips);
  const tail = new THREE.Mesh(new THREE.CapsuleGeometry(0.05, 0.26, 6, 12), hairM);
  tail.position.set(0, -0.03, -0.1); tail.rotation.x = 0.25; r.head.add(tail);
  for (const s of [1, -1]) {
    const side = s > 0 ? 'L' : 'R';
    const sh = J(r.chest, 0.165 * s, 0.2);
    sh.add(cap(0.042, 0.22, skin));
    const el = J(sh, 0, -0.27);
    el.add(cap(0.036, 0.2, skin));
    const hand = new THREE.Mesh(new THREE.SphereGeometry(0.04, 12, 10), skin);
    hand.position.y = -0.27; hand.scale.set(0.8, 1.2, 0.6); el.add(hand);
    const th = J(r.hips, 0.085 * s, -0.04);
    th.add(cap(0.065, 0.32, skin));
    const kn = J(th, 0, -0.40);
    kn.add(cap(0.048, 0.32, skin));
    const ft = J(kn, 0, -0.39);
    const foot = new THREE.Mesh(new THREE.BoxGeometry(0.08, 0.06, 0.2), shoe);
    foot.position.set(0, -0.02, 0.05); ft.add(foot);
    r['sh' + side] = sh; r['el' + side] = el; r['th' + side] = th; r['kn' + side] = kn; r['ft' + side] = ft;
  }
  root.traverse((o) => { if (o.isMesh) o.castShadow = false; });
  return r;
}

function resetRig(r) {
  for (const k of ['hips', 'spine', 'chest', 'neck', 'head', 'shL', 'shR', 'elL', 'elR', 'thL', 'thR', 'knL', 'knR', 'ftL', 'ftR'])
    r[k].rotation.set(0, 0, 0);
  r.hips.position.set(0, HIP, 0);
}

// процедурные танцы: b — доли (непрерывно), e — громкость 0..1
const STYLES = {
  groove(r, b, e) {
    const A = 0.45 + 0.55 * e;
    const d = 0.5 + 0.5 * Math.cos(TAU * b);            // 1 — на долю
    const s2 = Math.sin(Math.PI * b);                    // раз в две доли
    r.hips.position.y = HIP - 0.05 * d * A;
    r.hips.position.x = 0.035 * s2 * A;
    r.hips.rotation.z = -0.1 * s2 * A;
    r.hips.rotation.y = 0.12 * s2 * A;
    r.chest.rotation.z = 0.14 * s2 * A;
    r.chest.rotation.y = -0.1 * s2 * A;
    r.head.rotation.x = 0.12 * d * A;
    r.thL.rotation.x = -0.28 * d * A; r.thR.rotation.x = -0.28 * d * A;
    r.knL.rotation.x = 0.56 * d * A; r.knR.rotation.x = 0.56 * d * A;
    r.ftL.rotation.x = -0.28 * d * A; r.ftR.rotation.x = -0.28 * d * A;
    r.thL.rotation.z = 0.05 + 0.04 * s2; r.thR.rotation.z = -0.05 + 0.04 * s2;
    r.shL.rotation.x = -0.5 * s2 * A - 0.2; r.shR.rotation.x = 0.5 * s2 * A - 0.2;
    r.shL.rotation.z = 0.25; r.shR.rotation.z = -0.25;
    r.elL.rotation.x = -1.1 - 0.3 * d; r.elR.rotation.x = -1.1 - 0.3 * d;
  },
  disco(r, b, e) {
    const A = 0.5 + 0.5 * e;
    const d = 0.5 + 0.5 * Math.cos(TAU * b);
    const bar = Math.floor(b / 2) % 2;                  // каждые 2 доли — смена руки
    const up = 0.5 - 0.5 * Math.cos(Math.PI * b);
    r.hips.position.y = HIP - 0.045 * d * A;
    r.hips.rotation.y = (bar ? 0.25 : -0.25) * A;
    r.hips.rotation.z = (bar ? -0.08 : 0.08) * A;
    r.chest.rotation.z = (bar ? 0.12 : -0.12) * A;
    r.thL.rotation.x = -0.25 * d; r.thR.rotation.x = -0.25 * d;
    r.knL.rotation.x = 0.5 * d; r.knR.rotation.x = 0.5 * d;
    r.ftL.rotation.x = -0.25 * d; r.ftR.rotation.x = -0.25 * d;
    const point = (sh, el, s) => { sh.rotation.z = s * (0.6 + 2.0 * up * A); sh.rotation.x = -0.3; el.rotation.x = -0.15; };
    const hip = (sh, el, s) => { sh.rotation.z = s * 0.45; sh.rotation.x = 0.2; el.rotation.x = -1.6; el.rotation.y = s * 0.6; };
    if (bar) { point(r.shR, r.elR, -1); hip(r.shL, r.elL, 1); } else { point(r.shL, r.elL, 1); hip(r.shR, r.elR, -1); }
    r.head.rotation.z = (bar ? -0.12 : 0.12) * A;
  },
  hiphop(r, b, e) {
    const A = 0.5 + 0.5 * e;
    const d = 0.5 + 0.5 * Math.cos(TAU * b);
    const s2 = Math.sin(Math.PI * b);
    r.hips.position.y = HIP - 0.03 - 0.08 * d * A;
    r.hips.position.x = 0.07 * s2 * A;
    r.hips.rotation.y = 0.2 * s2 * A;
    r.chest.rotation.x = 0.18 * d * A;
    r.chest.rotation.y = -0.15 * s2 * A;
    r.head.rotation.x = 0.2 * d * A;
    r.thL.rotation.x = -0.45 * d * A - 0.1; r.thR.rotation.x = -0.45 * d * A - 0.1;
    r.knL.rotation.x = 0.9 * d * A + 0.2; r.knR.rotation.x = 0.9 * d * A + 0.2;
    r.ftL.rotation.x = -0.45 * d * A - 0.1; r.ftR.rotation.x = -0.45 * d * A - 0.1;
    r.thL.rotation.z = 0.12; r.thR.rotation.z = -0.12;
    r.shL.rotation.x = -0.6 - 0.5 * d * A; r.shR.rotation.x = -0.6 - 0.5 * d * A;
    r.shL.rotation.z = 0.35 + 0.15 * s2; r.shR.rotation.z = -0.35 + 0.15 * s2;
    r.elL.rotation.x = -1.5 + 0.4 * d; r.elR.rotation.x = -1.5 + 0.4 * d;
  },
  sway(r, b, e) {
    const A = 0.5 + 0.5 * e;
    const s2 = Math.sin(Math.PI * b), c2 = Math.cos(Math.PI * b);
    const d = 0.5 + 0.5 * Math.cos(TAU * b);
    r.hips.position.y = HIP - 0.02 * d;
    r.hips.position.x = 0.05 * s2 * A;
    r.hips.rotation.z = -0.12 * s2 * A;
    r.chest.rotation.z = 0.18 * s2 * A;
    r.head.rotation.z = 0.15 * s2 * A;
    r.thL.rotation.z = 0.04 - 0.05 * s2; r.thR.rotation.z = -0.04 - 0.05 * s2;
    r.knL.rotation.x = 0.15 * Math.max(0, -s2); r.knR.rotation.x = 0.15 * Math.max(0, s2);
    r.shL.rotation.z = 2.4 + 0.3 * s2 * A; r.shR.rotation.z = -2.4 + 0.3 * s2 * A;
    r.shL.rotation.x = 0.2 * c2; r.shR.rotation.x = -0.2 * c2;
    r.elL.rotation.z = 0.5 + 0.3 * c2; r.elR.rotation.z = -0.5 + 0.3 * c2;
  },
};
const COLORS = [0xd81b60, 0x1e88e5, 0x8e24aa, 0x00897b, 0xf4511e, 0x3949ab];

// ───────── девушка ─────────
class Dancer {
  constructor(spec, idx) {
    this.spec = spec; this.idx = idx;
    this.root = new THREE.Group();
    this.fit = new THREE.Group();
    this.root.add(this.fit);
    this.shadow = new THREE.Mesh(new THREE.PlaneGeometry(1, 1),
      new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }));
    this.shadow.rotation.x = -Math.PI / 2; this.shadow.position.y = 0.002;
    this.shadow.scale.set(0.8, 0.5, 1);
    this.root.add(this.shadow);
    this.mixer = null; this.action = null; this.rig = null; this.model = null;
    this.src = null; this.info = { period: 0.5, t0: 0, auto: false };
    this.mult = 1; this.ts = 1; this.err = ''; this.ok = false; this.danceToken = 0;
    scene.add(this.root);
  }

  async load() {
    const c = this.spec.char || 'builtin:mannequin';
    try {
      if (c.startsWith('builtin:')) {
        this.rig = buildMannequin(COLORS[this.idx % COLORS.length]);
        this.fit.add(this.rig.root);
      } else {
        this.src = await loadFile(fileUrl(c));
        if (this.disposed) return;
        const model = SkeletonUtils.clone(this.src.scene);
        model.traverse((o) => {
          if (o.isMesh) {
            o.frustumCulled = false;
            const ms = Array.isArray(o.material) ? o.material : [o.material];
            for (const m of ms) {
              if (!m) continue;
              if (m.map) m.map.colorSpace = THREE.SRGBColorSpace;
              if ('envMapIntensity' in m) m.envMapIntensity = 0.6;
            }
          }
        });
        this.model = model;
        this.fit.add(model);
        this.normalize();
        this.mixer = new THREE.AnimationMixer(model);
      }
      await this.setDance(this.spec.dance);
      this.ok = true;
    } catch (e) {
      this.err = String(e && e.message || e);
      warn('девушка не загрузилась:', c, this.err);
      showMsg('Не загрузилась модель: ' + c.split('/').pop());
    }
  }

  normalize() {
    // рамка — без учёта места на сцене (модель на миг вынимается)
    const m = this.model;
    this.fit.remove(m);
    m.updateMatrixWorld(true);
    const box = new THREE.Box3().setFromObject(m, true);
    this.fit.add(m);
    const h = box.max.y - box.min.y;
    if (!(h > 1e-6) || !isFinite(h)) return;
    const k = HEIGHT / h;
    const c = box.getCenter(new THREE.Vector3());
    m.scale.multiplyScalar(k);
    m.position.set((m.position.x - c.x) * k, (m.position.y - box.min.y) * k, (m.position.z - c.z) * k);
  }

  async setDance(dance) {
    this.spec.dance = dance;
    const token = ++this.danceToken;
    if (this.rig) {
      this.style = STYLES[(dance || '').replace('builtin:', '')] || STYLES.groove;
      return;
    }
    let clip = null, srcRoot = null;
    try {
      if (dance && dance.startsWith('dances/')) {
        const f = await loadFile(fileUrl(dance));
        clip = longest(f.animations);
        srcRoot = f.scene;
        if (!clip) showMsg('В файле танца нет анимации: ' + dance.split('/').pop());
      }
    } catch (e) {
      warn('танец не загрузился:', dance, e);
      showMsg('Не загрузился танец: ' + dance.split('/').pop());
    }
    if (token !== this.danceToken || this.disposed) return;
    if (!clip) { clip = longest(this.src.animations); srcRoot = this.src.scene; }
    if (this.action) { this.action.stop(); this.mixer.uncacheRoot(this.model); }
    this.action = null;
    if (!clip) { this.err = 'нет анимации'; showMsg('У модели нет своего танца — выберите танец из папки dances'); return; }
    const rc = retarget(clip, srcRoot, this.src.scene, !!scn.inplace);
    if (!rc) { this.err = 'кости не совпали'; showMsg('Танец не подходит к скелету модели'); return; }
    this.info = analyzeClip(rc);
    this.action = this.mixer.clipAction(rc);
    this.action.play();
    this.err = '';
    log('танец', rc.name, 'дорожек', rc.tracks.length, 'доля клипа', this.info.period.toFixed(3), 'с',
        this.info.auto ? '' : '(по умолчанию)');
  }

  update(dt) {
    const s = (this.spec.scale || 100) / 100;
    this.fit.scale.setScalar(s);
    this.shadow.scale.set(0.8 * s, 0.5 * s, 1);
    this.shadow.visible = !!scn.shadow && scn.style !== 'neon';
    if (this.rig) {
      const m = scn.mult === 'half' ? 0.5 : scn.mult === 'double' ? 2 : 1;
      const live = music.active ? 1 : 0;
      this.idleBeat = (this.idleBeat || 0) + dt * 0.5 * (1 - live);
      resetRig(this.rig);
      this.style(this.rig, music.beat * m + this.idleBeat, live ? music.energy : 0.15);
      return;
    }
    if (!this.action) return;
    let target;
    if (music.active) {
      const base = this.info.period * music.bpm / 60;   // секунд клипа за секунду
      let m = this.mult;
      if (scn.mult === 'half') m = 0.5; else if (scn.mult === 'double') m = 2;
      else {
        const best = [0.5, 1, 2].reduce((a, x) => Math.abs(Math.log2(base * x)) < Math.abs(Math.log2(base * a)) ? x : a, m);
        if (Math.abs(Math.log2(base * best)) + 0.2 < Math.abs(Math.log2(base * m))) m = best;
      }
      this.mult = m;
      const mp = frac(music.beat * m);
      const cp = frac((this.action.time - this.info.t0) / this.info.period);
      const err = wrap(mp - cp);
      target = Math.min(3, Math.max(0.25, base * m * (1 + 0.8 * err)));
    } else {
      target = 0.35;
    }
    this.ts = lerp(this.ts, target, Math.min(1, dt * 6));
    this.action.timeScale = this.ts;
    this.mixer.update(dt);
  }

  dispose() {
    this.disposed = true;
    scene.remove(this.root);
    if (this.mixer) this.mixer.stopAllAction();
    this.root.traverse((o) => {
      if (o.isMesh && this.rig) { o.geometry.dispose(); }
    });
  }
}
const longest = (arr) => (arr || []).reduce((a, c) => (!a || c.duration > a.duration ? c : a), null);

// ───────── сцена ─────────
let scn = { dancers: [], spacing: 100, light: 70, shadow: true, inplace: true, mult: 'auto', style: 'real', palette: 'fire', glow: 100 };
let dancers = [];

function layout() {
  const n = dancers.length || 1;
  const gap = 0.85 * (scn.spacing || 100) / 100;
  dancers.forEach((d, i) => { d.root.position.x = (i - (n - 1) / 2) * gap; d.root.position.z = (i % 2) * -0.15 * (n > 2); });
  const maxS = dancers.reduce((a, d) => Math.max(a, (d.spec.scale || 100) / 100), 1);
  const w = (n - 1) * gap + 0.9 * maxS, h = 1.9 * maxS;
  const asp = Math.max(0.1, camera.aspect);
  const vfov = THREE.MathUtils.degToRad(camera.fov);
  const dist = Math.max(h / 2 / Math.tan(vfov / 2), w / 2 / (Math.tan(vfov / 2) * asp)) * 1.08;
  camera.position.set(0, h * 0.5 + 0.05, dist);
  camera.lookAt(0, h * 0.47, 0);
}

function applyLight() {
  const k = (scn.light ?? 70) / 70;
  hemi.intensity = 1.0 * k; key.intensity = 2.4 * k; fill.intensity = 0.8 * k; rim.intensity = 1.4 * k;
  renderer.toneMappingExposure = 0.7 + 0.25 * k;
}

async function setScene(s) {
  if (typeof s === 'string') s = JSON.parse(s);
  const prevInplace = scn.inplace;
  scn = Object.assign({}, scn, s);
  applyLight();
  const want = (scn.dancers || []).slice(0, 6);
  const next = [];
  const jobs = [];
  for (let i = 0; i < want.length; i++) {
    const sp = Object.assign({}, want[i]);
    const old = dancers[i];
    if (old && old.spec.char === sp.char && !old.err.includes('загруз')) {
      old.spec.scale = sp.scale;
      if (old.spec.dance !== sp.dance || prevInplace !== scn.inplace) jobs.push(old.setDance(sp.dance));
      next.push(old);
    } else {
      if (old) old.dispose();
      const d = new Dancer(sp, i);
      next.push(d);
      jobs.push(d.load());
    }
  }
  for (let i = want.length; i < dancers.length; i++) dancers[i].dispose();
  dancers = next;
  layout();
  await Promise.all(jobs);
  layout();
}

function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h, false);
  if (neon) { const v = renderer.getDrawingBufferSize(new THREE.Vector2()); neon.setSize(v.x, v.y); }
  camera.aspect = w / Math.max(1, h);
  camera.updateProjectionMatrix();
  layout();
}
window.addEventListener('resize', resize);
resize();

// ───────── неон: светящийся контур, как эффект «края + свечение» на видео ─────────
const PALETTES = {
  fire:    [[1.0, 0.86, 0.55], [1.0, 0.45, 0.12], [0.95, 0.2, 0.55], [0.55, 0.25, 1.0]],   // золото → пурпур
  neon:    [[0.3, 0.95, 1.0], [0.25, 0.55, 1.0], [0.85, 0.3, 1.0], [1.0, 0.25, 0.7]],      // бирюза → маджента
  rainbow: [[1.0, 0.3, 0.3], [1.0, 0.85, 0.2], [0.3, 1.0, 0.5], [0.35, 0.5, 1.0]],
};
const FS_VERT = 'varying vec2 vUv; void main() { vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }';
class NeonFX {
  constructor() {
    const opt = { type: THREE.HalfFloatType };
    this.rtScene = new THREE.WebGLRenderTarget(4, 4, opt);
    this.rtEdge = new THREE.WebGLRenderTarget(4, 4, opt);
    this.rtA = new THREE.WebGLRenderTarget(4, 4, opt);
    this.rtB = new THREE.WebGLRenderTarget(4, 4, opt);
    this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.quad = new THREE.Mesh(new THREE.PlaneGeometry(2, 2));
    this.fs = new THREE.Scene();
    this.fs.add(this.quad);
    const pal = { value: PALETTES.fire.map((c) => new THREE.Vector3(...c)) };
    this.edgeMat = new THREE.ShaderMaterial({
      vertexShader: FS_VERT,
      uniforms: { tColor: { value: null }, texel: { value: new THREE.Vector2() }, width: { value: 1.0 },
                  time: { value: 0 }, pal, cycle: { value: 0 } },
      fragmentShader: `
        uniform sampler2D tColor; uniform vec2 texel; uniform float width, time, cycle; uniform vec3 pal[4];
        varying vec2 vUv;
        float L(vec2 o) { vec4 c = texture2D(tColor, vUv + o * texel * width); return sqrt(dot(c.rgb, vec3(0.299, 0.587, 0.114))); }
        float A(vec2 o) { return texture2D(tColor, vUv + o * texel * width).a; }
        vec3 palette(float t) {
          t = fract(t) * 4.0; int i = int(t); float f = fract(t);
          vec3 a = pal[0], b = pal[1];
          if (i == 1) { a = pal[1]; b = pal[2]; } else if (i == 2) { a = pal[2]; b = pal[3]; } else if (i == 3) { a = pal[3]; b = pal[0]; }
          return mix(a, b, smoothstep(0.0, 1.0, f));
        }
        void main() {
          float gx = -L(vec2(-1,-1)) - 2.0*L(vec2(-1,0)) - L(vec2(-1,1)) + L(vec2(1,-1)) + 2.0*L(vec2(1,0)) + L(vec2(1,1));
          float gy = -L(vec2(-1,-1)) - 2.0*L(vec2(0,-1)) - L(vec2(1,-1)) + L(vec2(-1,1)) + 2.0*L(vec2(0,1)) + L(vec2(1,1));
          float ax = -A(vec2(-1,-1)) - 2.0*A(vec2(-1,0)) - A(vec2(-1,1)) + A(vec2(1,-1)) + 2.0*A(vec2(1,0)) + A(vec2(1,1));
          float ay = -A(vec2(-1,-1)) - 2.0*A(vec2(0,-1)) - A(vec2(1,-1)) + A(vec2(-1,1)) + 2.0*A(vec2(0,1)) + A(vec2(1,1));
          float inner = smoothstep(0.14, 0.55, length(vec2(gx, gy)));     // складки, швы, черты лица
          float sil = clamp(length(vec2(ax, ay)) * 0.9, 0.0, 1.0);          // контур фигуры
          float e = clamp(max(sil, inner * 0.75), 0.0, 1.0);
          float t = (1.0 - vUv.y) * 0.62 + vUv.x * 0.12 + sin(time * 0.3) * 0.04 + cycle;
          gl_FragColor = vec4(palette(t) * e, e);
        }`,
      depthTest: false, depthWrite: false,
    });
    this.blurMat = new THREE.ShaderMaterial({
      vertexShader: FS_VERT,
      uniforms: { tSrc: { value: null }, dir: { value: new THREE.Vector2() } },
      fragmentShader: `
        uniform sampler2D tSrc; uniform vec2 dir; varying vec2 vUv;
        void main() {
          vec4 s = texture2D(tSrc, vUv) * 0.2270270270;
          s += (texture2D(tSrc, vUv + dir * 1.3846153846) + texture2D(tSrc, vUv - dir * 1.3846153846)) * 0.3162162162;
          s += (texture2D(tSrc, vUv + dir * 3.2307692308) + texture2D(tSrc, vUv - dir * 3.2307692308)) * 0.0702702703;
          gl_FragColor = s;
        }`,
      depthTest: false, depthWrite: false,
    });
    this.compMat = new THREE.ShaderMaterial({
      vertexShader: FS_VERT,
      uniforms: { tColor: { value: null }, tEdge: { value: null }, tGlow: { value: null },
                  glow: { value: 1.0 }, pulse: { value: 0 }, fill: { value: new THREE.Vector3(0.25, 0.05, 0.35) } },
      fragmentShader: `
        uniform sampler2D tColor, tEdge, tGlow; uniform float glow, pulse; uniform vec3 fill; varying vec2 vUv;
        void main() {
          vec4 E = texture2D(tEdge, vUv), G = texture2D(tGlow, vUv);
          float cov = texture2D(tColor, vUv).a;
          float k = 1.0 + 0.45 * pulse;
          vec3 core = E.rgb * 1.25 * k + vec3(E.a * 0.10 * k);            // светлая сердцевина линии
          vec3 halo = G.rgb * glow * 1.5 * k;                            // ореол
          vec3 body = fill * cov * (0.18 + 0.25 * pulse);                 // лёгкая дымка внутри фигуры
          float a = clamp(max(E.a * k, G.a * glow * 1.2 * k) + cov * 0.15, 0.0, 1.0);
          gl_FragColor = vec4(core + halo + body, a);
        }`,
      depthTest: false, depthWrite: false, transparent: false,
    });
  }

  setSize(w, h) {
    this.rtScene.setSize(w, h);
    this.rtEdge.setSize(w, h);
    const hw = Math.max(1, Math.round(w / 2)), hh = Math.max(1, Math.round(h / 2));
    this.rtA.setSize(hw, hh);
    this.rtB.setSize(hw, hh);
    this.edgeMat.uniforms.texel.value.set(1 / w, 1 / h);
    this.w = hw; this.h = hh;
  }

  pass(mat, target) {
    this.quad.material = mat;
    renderer.setRenderTarget(target);
    renderer.render(this.fs, this.cam);
  }

  render(time, pulse) {
    const pal = PALETTES[scn.palette] || PALETTES.fire;
    pal.forEach((c, i) => this.edgeMat.uniforms.pal.value[i].set(...c));
    const fill = pal[3];
    this.compMat.uniforms.fill.value.set(fill[0] * 0.5, fill[1] * 0.3, fill[2] * 0.6);
    const oldTone = renderer.toneMapping;
    renderer.setRenderTarget(this.rtScene);
    renderer.setClearColor(0x000000, 0);
    renderer.clear();
    renderer.render(scene, camera);
    renderer.toneMapping = THREE.NoToneMapping;
    const pr = renderer.getPixelRatio();
    this.edgeMat.uniforms.tColor.value = this.rtScene.texture;
    this.edgeMat.uniforms.width.value = Math.max(1, pr * 0.9);
    this.edgeMat.uniforms.time.value = time;
    this.edgeMat.uniforms.cycle.value = scn.palette === 'rainbow' ? time * 0.08 : 0;
    this.pass(this.edgeMat, this.rtEdge);
    // свечение: два прохода размытия, широкое
    let src = this.rtEdge;
    for (const r of [1.5, 3.5]) {
      this.blurMat.uniforms.tSrc.value = src.texture;
      this.blurMat.uniforms.dir.value.set(r / this.w, 0);
      this.pass(this.blurMat, this.rtA);
      this.blurMat.uniforms.tSrc.value = this.rtA.texture;
      this.blurMat.uniforms.dir.value.set(0, r / this.h);
      this.pass(this.blurMat, this.rtB);
      src = this.rtB;
    }
    const u = this.compMat.uniforms;
    u.tColor.value = this.rtScene.texture; u.tEdge.value = this.rtEdge.texture; u.tGlow.value = src.texture;
    u.glow.value = (scn.glow ?? 100) / 100; u.pulse.value = pulse;
    this.pass(this.compMat, null);
    renderer.toneMapping = oldTone;
  }
}

// ───────── цикл ─────────
const clock = new THREE.Clock();
let fps = 0, fpsN = 0, fpsT = 0;
function tick() {
  requestAnimationFrame(tick);
  const dt = Math.min(0.1, clock.getDelta());
  if (paused) return;
  if (performance.now() - music.last > 1500) music.active = false;     // Python замолчал
  music.beat += dt * (music.active ? music.bpm / 60 : 0);
  for (const d of dancers) d.update(dt);
  if (msgTimer > 0) { msgTimer -= dt; if (msgTimer <= 0) msgEl.textContent = ''; }
  if (scn.style === 'neon') {
    if (!neon) { neon = new NeonFX(); const v = renderer.getDrawingBufferSize(new THREE.Vector2()); neon.setSize(v.x, v.y); }
    const pulse = music.active ? Math.exp(-frac(music.beat) * 5) : 0;
    neon.render(clock.elapsedTime, pulse);
  } else {
    renderer.setRenderTarget(null);
    renderer.render(scene, camera);
  }
  fpsN++; fpsT += dt;
  if (fpsT >= 1) { fps = fpsN / fpsT; fpsN = 0; fpsT = 0; }
}
tick();

window.DD = {
  setBg: (c) => { setBg(c); return true; },
  pause: (on) => { paused = !!on; return true; },
  setScene: (s) => { setScene(s).catch((e) => warn('сцена:', e)); return true; },
  beat: (st) => { onBeat(typeof st === 'string' ? JSON.parse(st) : st); return true; },
  status: () => JSON.stringify({
    ready: true, fps: Math.round(fps), bpm: Math.round(music.bpm * 10) / 10, active: music.active,
    dancers: dancers.map((d) => ({ char: d.spec.char, dance: d.spec.dance, ok: d.ok, err: d.err,
      clipBeat: Math.round(d.info.period * 1000) / 1000, clipInfo: d.info, mult: d.mult, ts: Math.round(d.ts * 100) / 100 })),
  }),
};
window.DD_READY = true;
log('сцена готова, three r' + THREE.REVISION);
if (window.DD_PENDING) window.DD.setScene(window.DD_PENDING);
