const DEBUG_PORT = 9224;
const APP_URL = 'http://127.0.0.1:8000/';

// Start Chromium with remote debugging before running this check:
// chromium --headless --disable-gpu --no-sandbox --remote-debugging-port=9224 \
//   --user-data-dir=/tmp/dairy-horizon-browser-check http://127.0.0.1:8000/

const sleep = (milliseconds) => new Promise((resolve) => setTimeout(resolve, milliseconds));

async function retry(operation, message, attempts = 100) {
  let lastError;
  for (let attempt = 0; attempt < attempts; attempt += 1) {
    try {
      const result = await operation();
      if (result) return result;
    } catch (error) {
      lastError = error;
    }
    await sleep(50);
  }
  throw new Error(`${message}${lastError ? `: ${lastError.message}` : ''}`);
}

async function openClient() {
  const target = await retry(async () => {
    const response = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
    const targets = await response.json();
    return targets.find((item) => item.type === 'page');
  }, 'Chromiumのデバッグ対象を取得できませんでした');

  const socket = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, { once: true });
    socket.addEventListener('error', reject, { once: true });
  });

  let nextId = 1;
  const pending = new Map();
  socket.addEventListener('message', (event) => {
    const message = JSON.parse(event.data);
    if (!message.id || !pending.has(message.id)) return;
    const { resolve, reject } = pending.get(message.id);
    pending.delete(message.id);
    if (message.error) reject(new Error(message.error.message));
    else resolve(message.result);
  });

  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = nextId;
    nextId += 1;
    pending.set(id, { resolve, reject });
    socket.send(JSON.stringify({ id, method, params }));
  });

  const evaluate = async (expression) => {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.text || 'ブラウザ評価に失敗しました');
    }
    return result.result.value;
  };

  return { socket, send, evaluate };
}

function assertEqual(actual, expected, label) {
  if (actual !== expected) {
    throw new Error(`${label}: expected=${JSON.stringify(expected)} actual=${JSON.stringify(actual)}`);
  }
}

async function waitForPage(evaluate, expectedQuery = null) {
  const locationCheck = expectedQuery === null
    ? "location.search === ''"
    : `location.search.includes(${JSON.stringify(expectedQuery)})`;
  await retry(async () => evaluate(`
    document.readyState === 'complete'
      && ${locationCheck}
      && Boolean(document.querySelector('[data-selected-label]'))
  `), '画面の読み込みが完了しませんでした');
}

async function comparisonState(evaluate) {
  return evaluate(`JSON.stringify({
    heading: document.querySelector('[data-comparison-barn-heading]').textContent.trim(),
    label: document.querySelector('[data-selected-label]').textContent.trim(),
    additional: document.querySelector('[data-selected-additional]').textContent.trim(),
    active: document.querySelector('[data-selected-active]').textContent.trim(),
    newly: document.querySelector('[data-selected-newly]').textContent.trim(),
    uncovered: document.querySelector('[data-selected-uncovered]').textContent.trim(),
    cumulative: document.querySelector('[data-selected-cumulative]').textContent.trim(),
    cumulativeClass: document.querySelector('[data-selected-cumulative]').className,
    cumulativeColor: getComputedStyle(document.querySelector('[data-selected-cumulative]')).color,
    cumulativeNote: document.querySelector('[data-selected-cumulative-note]').textContent.trim(),
  })`);
}

async function financialState(evaluate, planKey) {
  return evaluate(`JSON.stringify(Array.from(
    document.querySelector('[data-financial-plan="${planKey}"]').querySelectorAll('dd'),
    (item) => item.textContent.trim(),
  ))`);
}

async function climateState(evaluate, periodKey, planIndex = 0) {
  return evaluate(`JSON.stringify((() => {
    const card = document.querySelector('[data-climate-period="${periodKey}"]');
    const plan = card.querySelectorAll('.climate-plan-costs li')[${planIndex}];
    return {
      days: Array.from(card.querySelectorAll('dd'), (item) => item.textContent.trim()),
      plan: plan.querySelector('strong').textContent.trim(),
      medianCost: plan.querySelector('span').textContent.trim(),
      costRange: plan.querySelector('small').textContent.trim(),
    };
  })())`);
}

async function main() {
  const client = await openClient();
  const { socket, send, evaluate } = client;
  try {
    await send('Page.enable');
    await send('Page.navigate', { url: APP_URL });
    await retry(async () => evaluate(`
      document.readyState === 'complete'
        && document.querySelector('.landing-hero h1')?.textContent.includes('自分の牛舎から考える')
        && document.querySelector('.primary-link')?.getAttribute('href') === '/check'
    `), '入口ページの読み込みが完了しませんでした');
    assertEqual(
      await evaluate(`JSON.stringify(Array.from(document.querySelectorAll('.landing-periods span'), (item) => item.textContent.trim()))`),
      JSON.stringify([
        '現在相当（2020〜2025年）',
        '近未来（2026〜2030年）',
        '次の期間（2031〜2034年）',
      ]),
      '入口ページの気候期間',
    );
    await evaluate(`document.querySelector('.primary-link').click()`);
    await waitForPage(evaluate);

    assertEqual(
      await evaluate(`JSON.stringify({
        value: document.querySelector('.quick-inputs .region-field input:disabled').value,
        disabled: document.querySelector('.quick-inputs .region-field input:disabled').disabled,
        submittedValue: document.querySelector('.quick-inputs [name="region_ja"]').value,
        note: document.querySelector('#region-availability-note').textContent.trim(),
      })`),
      JSON.stringify({
        value: '千葉市',
        disabled: true,
        submittedValue: '千葉市',
        note: '現在利用できる気温データは千葉市のみです。ほかの地域は今後拡張予定です。',
      }),
      '地域の固定表示',
    );

    assertEqual(
      await comparisonState(evaluate),
      JSON.stringify({
        heading: '2026年に5台を追加した直後の牛舎',
        label: '第1期：小さく始める',
        additional: '+5台',
        active: '15台',
        newly: '+15頭',
        uncovered: '15頭',
        cumulative: '75頭分・年',
        cumulativeClass: 'cumulative-unresolved',
        cumulativeColor: 'rgb(164, 66, 39)',
        cumulativeNote: '15頭の未カバー推計が5年間残ります。',
      }),
      '初期の第1期',
    );
    assertEqual(
      await financialState(evaluate, 'first_phase'),
      JSON.stringify(['5台', '15頭', '1,100,000円', '147,840円／年', '3.14kg／頭・日']),
      '初期の第1期財務',
    );
    assertEqual(
      await financialState(evaluate, 'full_coverage'),
      JSON.stringify(['10台', '30頭', '2,200,000円', '295,680円／年', '3.14kg／頭・日']),
      '初期の頭数目安財務',
    );
    assertEqual(
      await climateState(evaluate, '2026_2030'),
      JSON.stringify({
        days: ['104〜105日／年', '96〜109日／年', '+7日／年'],
        plan: '第1期：小さく始める（5台追加）',
        medianCost: '中央値 132,839円／年',
        costRange: '範囲 124,058円〜137,083円／年',
      }),
      '初期のTHI背景と第1期電力費',
    );
    assertEqual(
      await evaluate(`document.querySelector('.result-explanation button').textContent.trim()`),
      'AIにこの結果を読み解いてもらう',
      '説明生成は利用者操作で開始',
    );

    await evaluate(`
      document.querySelector('.operating-hours-control [name="operating_hours_per_day"]').value = '12';
      document.querySelector('.operating-hours-control button[type="submit"]').click();
    `);
    await waitForPage(evaluate, 'operating_hours_per_day=12');
    assertEqual(
      await financialState(evaluate, 'first_phase'),
      JSON.stringify(['5台', '15頭', '1,100,000円', '89,520円／年', '2.54kg／頭・日']),
      '運転時間変更後の第1期財務',
    );
    assertEqual(
      await climateState(evaluate, '2026_2030'),
      JSON.stringify({
        days: ['104〜105日／年', '96〜109日／年', '+7日／年'],
        plan: '第1期：小さく始める（5台追加）',
        medianCost: '中央値 82,019円／年',
        costRange: '範囲 77,629円〜84,142円／年',
      }),
      '運転時間変更後のTHI背景と第1期電力費',
    );

    await evaluate(`document.querySelector('[data-plan="full_coverage"]').click()`);
    assertEqual(
      await comparisonState(evaluate),
      JSON.stringify({
        heading: '2026年に10台を追加した直後の牛舎',
        label: '頭数目安まで追加',
        additional: '+10台',
        active: '20台',
        newly: '+30頭',
        uncovered: '0頭',
        cumulative: '0 — 未カバーなし',
        cumulativeClass: 'cumulative-resolved',
        cumulativeColor: 'rgb(39, 108, 77)',
        cumulativeNote: '5年間を通じて未カバー推計はありません。',
      }),
      '頭数目安タブ',
    );

    await evaluate(`
      document.querySelector('.first-phase-control [name="investment_year"]').value = '2028';
      document.querySelector('.first-phase-control [name="first_phase_fan_count"]').value = '3';
      document.querySelector('.first-phase-control [name="planned_fan_count"]').value = '18';
      document.querySelector('.first-phase-control button[type="submit"]').click();
    `);
    await waitForPage(evaluate, 'first_phase_fan_count=3');
    assertEqual(
      await comparisonState(evaluate),
      JSON.stringify({
        heading: '2028年に3台を追加した直後の牛舎',
        label: '第1期：小さく始める',
        additional: '+3台',
        active: '13台',
        newly: '+9頭',
        uncovered: '21頭',
        cumulative: '123頭分・年',
        cumulativeClass: 'cumulative-unresolved',
        cumulativeColor: 'rgb(164, 66, 39)',
        cumulativeNote: '各年の未カバー推計を合計した延べ規模です。',
      }),
      '入力変更後の第1期',
    );
    assertEqual(
      await financialState(evaluate, 'first_phase'),
      JSON.stringify(['3台', '9頭', '660,000円', '53,712円／年', '2.54kg／頭・日']),
      '入力変更後の第1期財務',
    );
    assertEqual(
      await climateState(evaluate, '2026_2030'),
      JSON.stringify({
        days: ['104〜105日／年', '96〜109日／年', '+7日／年'],
        plan: '第1期：小さく始める（3台追加）',
        medianCost: '中央値 49,212円／年',
        costRange: '範囲 46,578円〜50,485円／年',
      }),
      '入力変更後のTHI背景と第1期電力費',
    );

    await evaluate(`document.querySelector('[data-plan="full_coverage"]').click()`);
    assertEqual(
      await comparisonState(evaluate),
      JSON.stringify({
        heading: '2028年に8台を追加した直後の牛舎',
        label: '今回の計画台数まで追加',
        additional: '+8台',
        active: '18台',
        newly: '+24頭',
        uncovered: '6頭',
        cumulative: '78頭分・年',
        cumulativeClass: 'cumulative-unresolved',
        cumulativeColor: 'rgb(164, 66, 39)',
        cumulativeNote: '各年の未カバー推計を合計した延べ規模です。',
      }),
      '入力変更後の全数案',
    );
    assertEqual(
      await financialState(evaluate, 'full_coverage'),
      JSON.stringify(['8台', '24頭', '1,760,000円', '143,232円／年', '2.54kg／頭・日']),
      '入力変更後の計画台数財務',
    );

    const referenceUrl = `${APP_URL}check?region_ja=%E5%8D%83%E8%91%89%E5%B8%82&lactating_cows=100&lane_count=4&existing_fan_count=20&reference_mode=true`;
    await send('Page.navigate', { url: referenceUrl });
    await waitForPage(evaluate, 'reference_mode=true');
    await evaluate(`document.querySelector('[data-plan="full_coverage"]').click()`);
    assertEqual(
      await comparisonState(evaluate),
      JSON.stringify({
        heading: '2026年に参考値から14台を追加した直後の牛舎',
        label: '頭数目安まで追加',
        additional: '+14台',
        active: '34台',
        newly: '+40頭',
        uncovered: '0頭',
        cumulative: '0 — 未カバーなし',
        cumulativeClass: 'cumulative-resolved',
        cumulativeColor: 'rgb(39, 108, 77)',
        cumulativeNote: '5年間を通じて未カバー推計はありません。',
      }),
      '参考状態の全数案',
    );

    console.log('browser golden path: OK');
  } finally {
    socket.close();
  }
}

await main();
