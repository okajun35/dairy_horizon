const NS = 'http://www.w3.org/2000/svg';
const LEFT = 54;
const WIDTH = 820;

function element(name, attributes = {}, text = '') {
  const node = document.createElementNS(NS, name);
  Object.entries(attributes).forEach(([key, value]) => node.setAttribute(key, String(value)));
  node.textContent = text;
  return node;
}

function xFor(index, count) {
  return LEFT + (WIDTH * index) / Math.max(1, count - 1);
}

function drawHeatBars(svg, values, years, events) {
  const top = 35;
  const height = 92;
  const maximum = Math.ceil(Math.max(...values, 1) / 20) * 20;
  svg.append(element('text', { x: LEFT, y: 20, class: 'chart-label' }, '暑熱日数（日平均THI 72以上）'));
  svg.append(element('text', { x: LEFT + WIDTH, y: 20, class: 'chart-note', 'text-anchor': 'end' }, `0〜${maximum}日`));
  svg.append(element('line', { x1: LEFT, y1: top + height, x2: LEFT + WIDTH, y2: top + height, class: 'chart-axis' }));
  values.forEach((value, index) => {
    const barHeight = (value / maximum) * height;
    const x = xFor(index, values.length);
    svg.append(element('rect', { x: x - 19, y: top + height - barHeight, width: 38, height: barHeight, rx: 4, class: 'heat-bar' }));
    svg.append(element('text', { x, y: top + height - barHeight - 5, class: 'chart-value', 'text-anchor': 'middle' }, `${value}日`));
    svg.append(element('text', { x, y: top + height + 18, class: 'chart-year', 'text-anchor': 'middle' }, years[index]));
  });
  events.forEach((event) => {
    const index = years.indexOf(event.year);
    if (index >= 0) {
      const x = xFor(index, years.length);
      svg.append(element('line', { x1: x, y1: top, x2: x, y2: top + height, class: 'chart-investment' }));
      svg.append(element('text', { x: x + 4, y: top + 13, class: 'chart-event' }, '投資'));
    }
  });
}

function drawCashLine(svg, values, years) {
  const top = 183;
  const height = 65;
  const minimum = Math.min(...values, 0);
  const maximum = Math.max(...values, 1);
  const spread = maximum - minimum || 1;
  const coords = values.map((value, index) => ({
    x: xFor(index, values.length),
    y: top + height - ((value - minimum) / spread) * height,
  }));
  svg.append(element('text', { x: LEFT, y: top - 14, class: 'chart-label' }, '年間の運営余力'));
  svg.append(element('line', { x1: LEFT, y1: top + height, x2: LEFT + WIDTH, y2: top + height, class: 'chart-axis' }));
  svg.append(element('polyline', { points: coords.map((item) => `${item.x},${item.y}`).join(' '), class: 'chart-line', stroke: '#16835a' }));
  coords.forEach((item, index) => {
    svg.append(element('circle', { cx: item.x, cy: item.y, r: 3.5, fill: '#16835a' }));
    svg.append(element('text', { x: item.x, y: item.y - 7, class: 'chart-cash-value', 'text-anchor': 'middle' }, `${Math.round(values[index] / 10000)}万円`));
  });
}

export function createTimelineChart(container, data) {
  const svg = element('svg', { viewBox: '0 0 930 275', role: 'img', 'aria-label': '年次の暑熱日数と年間運営余力' });
  drawHeatBars(svg, data.heat_days, data.years, data.investment_events);
  drawCashLine(svg, data.annual_cash_yen, data.years);
  container.replaceChildren(svg);
}
