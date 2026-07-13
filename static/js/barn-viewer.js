const payload = JSON.parse(document.querySelector('#barn-payload').textContent);
const viewer = document.querySelector('#barn-viewer');
const detail = document.querySelector('#selection-detail');
const summary = document.querySelector('#plan-summary-card');
const tabs = [...document.querySelectorAll('.plan-tab')];
const allCows = payload.cows_by_lane.flat();

let selectedPlan = 'current';

function planFor(key) { return payload.plans.find((plan) => plan.key === key); }

function cowPosition(index, lane, count) {
  const x = 58 + ((index + 0.5) / Math.max(count, 1)) * 690;
  return { x, y: lane === 0 ? 94 : 218 };
}

function render() {
  const plan = planFor(selectedPlan);
  const covered = new Set(plan.covered_cow_ids);
  const baseline = new Set(planFor('current').covered_cow_ids);
  const cows = payload.cows_by_lane.map((lane, laneIndex) => lane.map((cowId, index) => {
    const { x, y } = cowPosition(index, laneIndex, lane.length);
    const color = baseline.has(cowId) ? '#356d8f' : covered.has(cowId) ? '#329265' : '#d17b32';
    return `<g class="cow" data-cow="${cowId}" data-lane="${laneIndex + 1}" data-stall="${index + 1}"><ellipse cx="${x}" cy="${y}" rx="10" ry="7" fill="${color}"/><circle cx="${x + 8}" cy="${y - 3}" r="3" fill="${color}"/></g>`;
  }).join('')).join('');
  const fanCount = plan.active_fan_count;
  const fans = Array.from({ length: fanCount }, (_, index) => {
    const x = 58 + ((index + .5) / Math.max(fanCount, 1)) * 690;
    const color = index < planFor('current').active_fan_count ? '#254f70' : selectedPlan === 'first_phase' ? '#277b58' : '#705b99';
    return `<g class="fan" data-fan="F${String(index + 1).padStart(2, '0')}" data-index="${index}"><circle cx="${x}" cy="157" r="11" fill="${color}"/><path d="M${x - 8} 157h16M${x} 149v16" stroke="white" stroke-width="2"/></g>`;
  }).join('');
  viewer.innerHTML = `<svg viewBox="0 0 806 320" role="img" aria-label="${plan.label_ja}の牛舎"><path d="M35 52h736v216H35z" fill="#ded2ba" stroke="#7a705f" stroke-width="3"/><path d="M35 139h736v42H35z" fill="#829087"/><text x="48" y="76" fill="#43574b" font-size="14">第1牛床列</text><text x="48" y="265" fill="#43574b" font-size="14">第2牛床列</text>${cows}${fans}</svg>`;
  viewer.querySelectorAll('.cow').forEach((node) => node.addEventListener('click', () => {
    detail.textContent = `牛 ${node.dataset.cow} ／ 第${node.dataset.lane}牛床列 ／ 房${node.dataset.stall}`;
  }));
  viewer.querySelectorAll('.fan').forEach((node) => node.addEventListener('click', () => {
    detail.textContent = `ファン ${node.dataset.fan} ／ ${Number(node.dataset.index) < planFor('current').active_fan_count ? '既存ファン' : '追加候補'}`;
  }));
  summary.innerHTML = `<h3>${plan.label_ja}</h3><dl><div><dt>追加する台数</dt><dd>${plan.additional_fan_count}台</dd></div><div><dt>新たにカバーする牛</dt><dd>${plan.newly_covered_cow_ids.length}頭</dd></div><div><dt>状態</dt><dd>${plan.status === 'NOT_REQUIRED' ? '追加不要' : '確認へ進む'}</dd></div></dl><p>${plan.additional_fan_count === 0 ? 'いまの配置を現場で確認します。' : 'この段階の設置位置と見積を確認します。'}</p>`;
}

tabs.forEach((tab) => tab.addEventListener('click', () => {
  selectedPlan = tab.dataset.plan;
  tabs.forEach((item) => item.classList.toggle('active', item === tab));
  render();
}));

render();
