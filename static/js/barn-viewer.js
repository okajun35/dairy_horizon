const payload = JSON.parse(document.querySelector('#barn-payload').textContent);
const currentViewer = document.querySelector('#current-barn-viewer');
const comparisonViewer = document.querySelector('#comparison-barn-viewer');
const currentDetail = document.querySelector('#current-selection-detail');
const comparisonDetail = document.querySelector('#comparison-selection-detail');
const tabs = [...document.querySelectorAll('.plan-tab')];
const pathCards = [...document.querySelectorAll('[data-path-card]')];
const allCows = payload.cows_by_lane.flat();
const referenceMode = payload.input_mode === 'guideline_reference';
const baselineLabel = referenceMode ? '参考値' : '現在';
const selectedState = {
  label: document.querySelector('[data-selected-label]'),
  additional: document.querySelector('[data-selected-additional]'),
  active: document.querySelector('[data-selected-active]'),
  newly: document.querySelector('[data-selected-newly]'),
  uncovered: document.querySelector('[data-selected-uncovered]'),
  cumulative: document.querySelector('[data-selected-cumulative]'),
  change: document.querySelector('[data-selected-change]'),
};

let selectedPlan = payload.selected_plan || 'current';

function planFor(key) { return payload.plans.find((plan) => plan.key === key); }
function pathwayFor(key) { return payload.path_comparison.paths.find((path) => path.key === key); }

function allocateFans(totalFans) {
  const laneCount = payload.cows_by_lane.length;
  const base = Math.floor(totalFans / laneCount);
  const remainder = totalFans % laneCount;
  return Array.from({ length: laneCount }, (_, index) => base + (index < remainder ? 1 : 0));
}

function cowPosition(index, laneIndex, count, laneHeight) {
  const x = 74 + ((index + 0.5) / Math.max(count, 1)) * 670;
  return { x, y: 28 + laneIndex * laneHeight + 27 };
}

function renderBarn(viewer, detail, plan) {
  const covered = new Set(plan.covered_cow_ids);
  const baseline = new Set(planFor('current').covered_cow_ids);
  const laneCount = payload.cows_by_lane.length;
  const laneHeight = 86;
  const svgHeight = Math.max(320, 30 + laneCount * laneHeight);
  const fanAllocation = allocateFans(plan.active_fan_count);
  const baselineFanAllocation = allocateFans(planFor('current').active_fan_count);
  const displayFanTargets = allocateFans(Math.max(payload.evaluation_fan_count, planFor('current').active_fan_count));
  const cows = payload.cows_by_lane.map((lane, laneIndex) => lane.map((cowId, index) => {
    const { x, y } = cowPosition(index, laneIndex, lane.length, laneHeight);
    const color = baseline.has(cowId) ? '#356d8f' : covered.has(cowId) ? '#329265' : '#d17b32';
    return `<g class="cow" data-cow="${cowId}" data-lane="${laneIndex + 1}" data-stall="${index + 1}"><ellipse cx="${x}" cy="${y}" rx="10" ry="7" fill="${color}"/><circle cx="${x + 8}" cy="${y - 3}" r="3" fill="${color}"/></g>`;
  }).join('')).join('');
  let fanSequence = 0;
  const fans = fanAllocation.map((fanCount, laneIndex) => Array.from({ length: fanCount }, (_, index) => {
    fanSequence += 1;
    const requiredCount = Math.max(displayFanTargets[laneIndex], 1);
    const x = 74 + ((index + .5) / requiredCount) * 670;
    const y = 28 + laneIndex * laneHeight + 61;
    const isExisting = index < baselineFanAllocation[laneIndex];
    const color = isExisting ? '#254f70' : selectedPlan === 'first_phase' ? '#277b58' : '#705b99';
    return `<g class="fan" data-fan="F${String(fanSequence).padStart(2, '0')}" data-existing="${isExisting}"><circle cx="${x}" cy="${y}" r="10" fill="${color}"/><path d="M${x - 7} ${y}h14M${x} ${y - 7}v14" stroke="white" stroke-width="2"/></g>`;
  }).join('')).join('');
  const lanes = payload.cows_by_lane.map((_, laneIndex) => {
    const y = 28 + laneIndex * laneHeight;
    return `<rect x="35" y="${y}" width="736" height="${laneHeight - 8}" fill="#ded2ba" stroke="#7a705f" stroke-width="2"/><rect x="35" y="${y + 45}" width="736" height="${laneHeight - 53}" fill="#829087"/><text x="46" y="${y + 16}" fill="#43574b" font-size="12">第${laneIndex + 1}牛床列</text>`;
  }).join('');
  viewer.style.minHeight = `${svgHeight}px`;
  viewer.innerHTML = `<svg viewBox="0 0 806 ${svgHeight}" style="height:${svgHeight}px" role="img" aria-label="${plan.label_ja}の牛舎">${lanes}${cows}${fans}</svg>`;
  viewer.querySelectorAll('.cow').forEach((node) => node.addEventListener('click', () => {
    detail.textContent = `牛 ${node.dataset.cow} ／ 第${node.dataset.lane}牛床列 ／ 房${node.dataset.stall}`;
  }));
  viewer.querySelectorAll('.fan').forEach((node) => node.addEventListener('click', () => {
    const baselineFanLabel = referenceMode ? '参考配置' : '既存ファン';
    detail.textContent = `ファン ${node.dataset.fan} ／ ${node.dataset.existing === 'true' ? baselineFanLabel : '追加候補'}`;
  }));
}

function renderComparison() {
  const plan = planFor(selectedPlan);
  const pathway = pathwayFor(selectedPlan);
  renderBarn(comparisonViewer, comparisonDetail, plan);
  selectedState.label.textContent = plan.label_ja;
  selectedState.additional.textContent = `+${plan.additional_fan_count}台`;
  selectedState.active.textContent = `${plan.active_fan_count}台`;
  selectedState.newly.textContent = `+${plan.newly_covered_cow_ids.length}頭`;
  selectedState.uncovered.textContent = `${allCows.length - plan.covered_cow_ids.length}頭`;
  selectedState.cumulative.textContent = `${pathway.cumulative_uncovered_cow_years}頭年`;
  selectedState.change.textContent = plan.newly_covered_cow_ids.length
    ? `${baselineLabel}より ${plan.newly_covered_cow_ids.length}頭少なくなります。`
    : `${referenceMode ? '参考状態' : '現在の状態'}を確認しています。`;
  pathCards.forEach((card) => card.classList.toggle('active', card.dataset.pathCard === selectedPlan));
}

tabs.forEach((tab) => tab.addEventListener('click', () => {
  selectedPlan = tab.dataset.plan;
  tabs.forEach((item) => item.classList.toggle('active', item === tab));
  renderComparison();
}));

renderBarn(currentViewer, currentDetail, planFor('current'));
renderComparison();
