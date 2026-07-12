import * as THREE from '../vendor/three.module.min.js';

export function createBarnViewer(container, layout, cowIdByInstanceId, onSelect) {
  const width = container.clientWidth;
  const height = container.clientHeight;
  const scene = new THREE.Scene();
  scene.background = new THREE.Color(0xe7efe8);
  const maxDimension = Math.max(layout.barn_boundary.length_m, layout.barn_boundary.width_m);
  const camera = new THREE.OrthographicCamera(-maxDimension, maxDimension, maxDimension, -maxDimension, 0.1, 200);
  camera.position.set(layout.barn_boundary.length_m / 2, maxDimension * 1.25, layout.barn_boundary.width_m * 1.1);
  camera.lookAt(layout.barn_boundary.length_m / 2, 0, layout.barn_boundary.width_m / 2);
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(width, height);
  container.replaceChildren(renderer.domElement);

  scene.add(new THREE.HemisphereLight(0xffffff, 0x6a8275, 2));
  const floor = new THREE.Mesh(new THREE.BoxGeometry(layout.barn_boundary.length_m + 2, 0.2, layout.barn_boundary.width_m + 2), new THREE.MeshStandardMaterial({ color: 0xc9b99b }));
  floor.position.set(layout.barn_boundary.length_m / 2, -0.15, layout.barn_boundary.width_m / 2);
  scene.add(floor);
  const aisle = new THREE.Mesh(new THREE.BoxGeometry(layout.barn_boundary.length_m, 0.05, 2.2), new THREE.MeshStandardMaterial({ color: 0x77847c }));
  aisle.position.set(layout.barn_boundary.length_m / 2, 0.02, layout.barn_boundary.width_m / 2);
  scene.add(aisle);

  const cowGeometry = new THREE.BoxGeometry(0.9, 0.7, 0.7);
  const cows = new THREE.InstancedMesh(cowGeometry, new THREE.MeshStandardMaterial({ color: 0x8f6149 }), layout.cows.length);
  const matrix = new THREE.Matrix4();
  layout.cows.forEach((cow, index) => {
    matrix.makeTranslation(cow.x_m, 0.42, cow.y_m);
    cows.setMatrixAt(index, matrix);
  });
  cows.instanceMatrix.needsUpdate = true;
  cows.userData.type = 'cow';
  scene.add(cows);

  const fanObjects = [];
  layout.fans.forEach((fan) => {
    const material = new THREE.MeshStandardMaterial({ color: fan.existing_assumed ? 0x2166ac : (fan.stage_one_selected ? 0xe07a20 : 0x8c9297) });
    const mesh = new THREE.Mesh(new THREE.CylinderGeometry(0.22, 0.22, 1.4, 12), material);
    mesh.position.set(fan.x_m, 0.7, fan.y_m);
    mesh.userData = { type: 'fan', fanId: fan.fan_id, lane: fan.lane_id, cowIds: fan.cow_ids };
    scene.add(mesh);
    fanObjects.push(mesh);
  });

  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  let dragging = false;
  let moved = false;
  let previous = null;
  renderer.domElement.addEventListener('pointerdown', (event) => { dragging = true; moved = false; previous = { x: event.clientX, y: event.clientY }; });
  renderer.domElement.addEventListener('pointermove', (event) => {
    if (!dragging || !previous) return;
    const dx = event.clientX - previous.x;
    const dy = event.clientY - previous.y;
    if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
    const scale = maxDimension / (300 * camera.zoom);
    camera.position.x -= dx * scale;
    camera.position.z += dy * scale;
    previous = { x: event.clientX, y: event.clientY };
  });
  renderer.domElement.addEventListener('pointerup', (event) => {
    dragging = false;
    if (moved) return;
    const rect = renderer.domElement.getBoundingClientRect();
    pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);
    const hits = raycaster.intersectObjects([cows, ...fanObjects]);
    if (!hits.length) return;
    const hit = hits[0];
    if (hit.object === cows && hit.instanceId !== undefined) {
      const cow = layout.cows[hit.instanceId];
      onSelect({ type: 'cow', cowId: cowIdByInstanceId[hit.instanceId], lane: cow.row, stall: cow.stall });
    } else {
      onSelect(hit.object.userData);
    }
  });
  renderer.domElement.addEventListener('wheel', (event) => {
    event.preventDefault();
    camera.zoom = Math.min(3, Math.max(0.5, camera.zoom * (event.deltaY > 0 ? 0.9 : 1.1)));
    camera.updateProjectionMatrix();
  }, { passive: false });
  window.addEventListener('resize', () => {
    renderer.setSize(container.clientWidth, container.clientHeight);
  });
  const render = () => { renderer.render(scene, camera); requestAnimationFrame(render); };
  render();
}
