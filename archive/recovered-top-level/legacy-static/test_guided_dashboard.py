import * as THREE from '../vendor/three.module.min.js';

const COLORS = {
  floor: 0xd8cfbd,
  aisle: 0x7f8d86,
  stall: 0xb8aa91,
  covered: 0x3f6d8d,
  newlyCovered: 0x2c9b63,
  uncovered: 0xd28a34,
  fanExisting: 0x315f87,
  fanStage: 0x2c9b63,
  fanFull: 0x7966a6,
};

export function createBarnViewer(container, payload, onSelect) {
  const { layout, cowIdByInstanceId, plans } = payload;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xeaf0ea);

  const camera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.1, 300);
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: false });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.replaceChildren(renderer.domElement);

  const center = new THREE.Vector3(
    layout.barn_boundary.length_m / 2,
    0,
    layout.barn_boundary.width_m / 2,
  );
  const target = center.clone();
  camera.position.set(center.x, 34, center.z + 18);
  camera.lookAt(target);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x65756d, 2.3));
  const keyLight = new THREE.DirectionalLight(0xffffff, 1.7);
  keyLight.position.set(center.x - 10, 28, center.z + 12);
  scene.add(keyLight);

  const floor = new THREE.Mesh(
    new THREE.BoxGeometry(layout.barn_boundary.length_m + 3, 0.25, layout.barn_boundary.width_m + 3),
    new THREE.MeshStandardMaterial({ color: COLORS.floor, roughness: 0.95 }),
  );
  floor.position.set(center.x, -0.22, center.z);
  scene.add(floor);

  const aisle = new THREE.Mesh(
    new THREE.BoxGeometry(layout.barn_boundary.length_m + 1, 0.08, 2.6),
    new THREE.MeshStandardMaterial({ color: COLORS.aisle, roughness: 0.9 }),
  );
  aisle.position.set(center.x, -0.02, center.z);
  scene.add(aisle);

  for (const cow of layout.cows) {
    const stall = new THREE.Mesh(
      new THREE.BoxGeometry(1.08, 0.04, 1.25),
      new THREE.MeshStandardMaterial({ color: COLORS.stall, transparent: true, opacity: 0.45 }),
    );
    stall.position.set(cow.x_m, 0.015, cow.y_m);
    scene.add(stall);
  }

  const cowGeometry = new THREE.BoxGeometry(0.92, 0.55, 0.58);
  cowGeometry.translate(0, 0.27, 0);
  const cowMaterial = new THREE.MeshStandardMaterial({ roughness: 0.78, metalness: 0 });
  const cows = new THREE.InstancedMesh(cowGeometry, cowMaterial, layout.cows.length);
  const matrix = new THREE.Matrix4();
  layout.cows.forEach((cow, index) => {
    matrix.makeTranslation(cow.x_m, 0.08, cow.y_m);
    cows.setMatrixAt(index, matrix);
  });
  cows.instanceMatrix.needsUpdate = true;
  cows.userData.type = 'cow';
  scene.add(cows);

  const headGeometry = new THREE.BoxGeometry(0.34, 0.36, 0.42);
  headGeometry.translate(0, 0.18, 0);
  const heads = new THREE.InstancedMesh(headGeometry, cowMaterial, layout.cows.length);
  layout.cows.forEach((cow, index) => {
    const direction = cow.row === 1 ? 1 : -1;
    matrix.makeTranslation(cow.x_m, 0.22, cow.y_m + direction * 0.47);
    heads.setMatrixAt(index, matrix);
  });
  heads.instanceMatrix.needsUpdate = true;
  scene.add(heads);

  const fanObjects = [];
  const fanById = new Map();
  for (const fan of layout.fans) {
    const material = new THREE.MeshStandardMaterial({ roughness: 0.55, metalness: 0.08 });
    const stand = new THREE.Mesh(new THREE.CylinderGeometry(0.09, 0.11, 1.2, 12), material);
    const cage = new THREE.Mesh(new THREE.CylinderGeometry(0.34, 0.34, 0.18, 20), material);
    cage.rotation.z = Math.PI / 2;
    const group = new THREE.Group();
    stand.position.y = 0.6;
    cage.position.y = 1.25;
    group.add(stand, cage);
    group.position.set(fan.x_m, 0, fan.y_m);
    group.userData = {
      type: 'fan',
      fanId: fan.fan_id,
      lane: fan.lane_id,
      cowIds: fan.cow_ids,
      phase: fan.installation_phase,
      material,
    };
    scene.add(group);
    fanObjects.push(group);
    fanById.set(fan.fan_id, group);
  }

  const baselineCovered = new Set(plans.baseline.covered_cow_ids);
  const color = new THREE.Color();
  function updateCowColors(planKey) {
    const covered = new Set(plans[planKey].covered_cow_ids);
    layout.cows.forEach((cow, index) => {
      const cowId = cowIdByInstanceId[index];
      const hex = baselineCovered.has(cowId)
        ? COLORS.covered
        : covered.has(cowId)
          ? COLORS.newlyCovered
          : COLORS.uncovered;
      color.setHex(hex);
      cows.setColorAt(index, color);
      heads.setColorAt(index, color);
    });
    cows.instanceColor.needsUpdate = true;
    heads.instanceColor.needsUpdate = true;
  }

  function updateFans(planKey) {
    const visible = new Set(plans[planKey].visible_fan_ids);
    for (const [fanId, group] of fanById.entries()) {
      group.visible = visible.has(fanId);
      const phase = group.userData.phase;
      group.userData.material.color.setHex(
        phase === 'existing' ? COLORS.fanExisting : phase === 'stage_1' ? COLORS.fanStage : COLORS.fanFull,
      );
    }
  }

  function setPlan(planKey) {
    if (!plans[planKey]) return;
    updateCowColors(planKey);
    updateFans(planKey);
  }

  function resize() {
    const width = Math.max(container.clientWidth, 320);
    const height = Math.max(container.clientHeight, 280);
    renderer.setSize(width, height, false);
    const aspect = width / height;
    const desiredHeight = Math.max(layout.barn_boundary.width_m * 1.85, layout.barn_boundary.length_m / aspect * 1.06);
    const desiredWidth = desiredHeight * aspect;
    camera.left = -desiredWidth / 2;
    camera.right = desiredWidth / 2;
    camera.top = desiredHeight / 2;
    camera.bottom = -desiredHeight / 2;
    camera.updateProjectionMatrix();
  }

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let dragging = false;
  let moved = false;
  let previous = null;

  renderer.domElement.addEventListener('pointerdown', (event) => {
    dragging = true;
    moved = false;
    previous = { x: event.clientX, y: event.clientY };
    renderer.domElement.setPointerCapture(event.pointerId);
  });
  renderer.domElement.addEventListener('pointermove', (event) => {
    if (!dragging || !previous) return;
    const dx = event.clientX - previous.x;
    const dy = event.clientY - previous.y;
    if (Math.abs(dx) + Math.abs(dy) > 3) moved = true;
    const scale = 0.035 / camera.zoom;
    camera.position.x -= dx * scale;
    target.x -= dx * scale;
    camera.position.z += dy * scale;
    target.z += dy * scale;
    camera.lookAt(target);
    previous = { x: event.clientX, y: event.clientY };
  });
  renderer.domElement.addEventListener('pointerup', (event) => {
    dragging = false;
    if (renderer.domElement.hasPointerCapture(event.pointerId)) {
      renderer.domElement.releasePointerCapture(event.pointerId);
    }
    if (moved) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const fanMeshes = fanObjects.filter((group) => group.visible).flatMap((group) => group.children);
    const hits = raycaster.intersectObjects([cows, ...fanMeshes], false);
    if (!hits.length) return;
    const hit = hits[0];
    if (hit.object === cows && hit.instanceId !== undefined) {
      const cow = layout.cows[hit.instanceId];
      onSelect({ type: 'cow', cowId: cowIdByInstanceId[hit.instanceId], lane: cow.row, stall: cow.stall });
      return;
    }
    const group = hit.object.parent;
    if (group?.userData?.type === 'fan') onSelect(group.userData);
  });
  renderer.domElement.addEventListener('wheel', (event) => {
    event.preventDefault();
    camera.zoom = Math.min(2.4, Math.max(0.75, camera.zoom * (event.deltaY > 0 ? 0.91 : 1.1)));
    camera.updateProjectionMatrix();
  }, { passive: false });

  const observer = new ResizeObserver(resize);
  observer.observe(container);
  resize();
  setPlan(payload.initialPlan);

  function render() {
    renderer.render(scene, camera);
    requestAnimationFrame(render);
  }
  render();

  return { setPlan, dispose: () => observer.disconnect() };
}
