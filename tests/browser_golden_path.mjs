const DEBUG_PORT = 9224;
const APP_URL = process.env.DAIRY_HORIZON_APP_URL || 'http://127.0.0.1:8000/';

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

async function annualHeatPathState(evaluate, planKey) {
  return evaluate(`JSON.stringify((() => {
    const card = document.querySelector('[data-annual-heat-path="${planKey}"]');
    return {
      label: card.querySelector('h4').textContent.trim(),
      values: Array.from(card.querySelectorAll('dd'), (item) => item.textContent.trim()),
      resultClass: card.querySelector('dl div:last-child dd').className,
      note: card.querySelector('p').textContent.trim(),
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
        && document.querySelector('.primary-link')?.getAttribute('href') === '/check?future_target_cow_count=45'
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
    await waitForPage(evaluate, 'future_target_cow_count=45');

    assertEqual(
      await evaluate(`JSON.stringify(Array.from(document.querySelectorAll('.horizon-state-grid article'), (card) => ({
        heading: card.querySelector('h3').textContent.trim(),
        values: Array.from(card.querySelectorAll('dd'), (item) => item.textContent.trim()),
      })))`),
      JSON.stringify([
        { heading: '現在・追加前', values: ['60頭', '20台', '10台不足'] },
        { heading: '現在・第1期後', values: ['60頭', '15台', '5台不足'] },
        { heading: '5年後・第1期後', values: ['45頭', '15台', '頭数基準上は不足なし'] },
      ]),
      '現在と5年後の分離',
    );

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
      await annualHeatPathState(evaluate, 'current'),
      JSON.stringify({
        label: '追加なし',
        values: ['30頭', '8,753kg', '-1,181,588円', '0円', '0円'],
        resultClass: 'annual-path-improvement-neutral',
        note: '何もしない場合の基準',
      }),
      '追加なしの年間損失基準',
    );
    assertEqual(
      await annualHeatPathState(evaluate, 'first_phase'),
      JSON.stringify({
        label: '第1期：小さく始める',
        values: ['15頭', '4,376kg', '-590,794円', '-282,870円', '-46,552円'],
        resultClass: 'annual-path-improvement-negative',
        note: '設備負担が防げる限界利益を上回る',
      }),
      '第1期の無対策との差',
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
      await evaluate(`JSON.stringify({
        financial: document.querySelector('.step-four-financial-reading p').textContent.trim(),
        title: document.querySelector('[data-step-four-pathway] h3').textContent.trim(),
        summary: document.querySelector('[data-step-four-pathway] > p:not(.section-kicker)').textContent.trim(),
        focus: document.querySelector('.step-four-decision > p').textContent.trim(),
        workspaceHasCardsAndBarn: Boolean(document.querySelector('.step-four-workspace .right-sized-choice-grid'))
          && Boolean(document.querySelector('.step-four-workspace .step-four-barn-panel')),
      })`),
      JSON.stringify({
        financial: '仮置きの乳量効果 +236,318円／年に対して、設備費の年割り -157,143円／年と追加電気代 -125,727円／年を置くため、年間差は -46,552円／年です。 乳量効果だけでは、設備費の年割りと追加電気代をまかないきれません。',
        title: '不足箇所案から見る',
        summary: '未カバー推計を減らしつつ、全体整備を今すぐ確定しない進め方です。',
        focus: 'まず不足箇所案で、どの位置の未カバー推計が減るかを確認します。',
        workspaceHasCardsAndBarn: true,
      }),
      'ステップ4の固定結論と費用面の計算説明',
    );
    assertEqual(
      await evaluate(`Boolean(document.querySelector('#next-step-barn-viewer svg'))`),
      true,
      'ステップ4にまず整える場合の牛舎図を表示',
    );
    assertEqual(
      await evaluate(`(() => {
        const cards = document.querySelector('.step-four-options').getBoundingClientRect();
        const barn = document.querySelector('.step-four-barn-panel').getBoundingClientRect();
        return Math.abs(cards.top - barn.top) < 2 && barn.left > cards.left;
      })()`),
      true,
      'デスクトップでは比較カードと牛舎図を横並びに表示',
    );
    await evaluate(`document.querySelector('[data-next-step-plan="full_coverage"]').click()`);
    assertEqual(
      await evaluate(`JSON.stringify({
        kicker: document.querySelector('[data-next-step-barn-kicker]').textContent.trim(),
        title: document.querySelector('[data-next-step-barn-title]').textContent.trim(),
        selected: document.querySelector('[data-next-step-plan="full_coverage"]').getAttribute('aria-pressed'),
        plan: document.querySelector('#next-step-barn-viewer svg').getAttribute('aria-label'),
      })`),
      JSON.stringify({
        kicker: '牛舎全体を整える場合の牛舎',
        title: '全ての場所で、牛床の使われ方を現場で見ます',
        selected: 'true',
        plan: '頭数目安まで追加の牛舎',
      }),
      'ステップ4で比較案ごとの牛舎図を切り替える',
    );
    await evaluate(`document.querySelector('[data-next-step-plan="first_phase"]').click()`);
    await evaluate(`document.querySelector('[data-choice-card="first_phase"] summary').click()`);
    assertEqual(
      await evaluate(`JSON.stringify({
        open: document.querySelector('[data-choice-card="first_phase"] details').open,
        detail: document.querySelector('[data-choice-card="first_phase"] details').textContent.replace(/\\s+/g, ' ').trim(),
      })`),
      JSON.stringify({
        open: true,
        detail: '年間差の計算を見る 乳量効果の見込み 15頭 × 97.3日 × 3kg／頭・日 = 4,376kg 乳代相当（135円／kg）590,794円変動費60%を除く-354,476円残る効果+236,318円 設備費の年割りと追加電気代 1,100,000円 ÷ 7年 設備費の年割り-157,143円／年電力量料金-94,527円／年基本料金-31,200円／年追加電気代-125,727円／年 7年は比較のための年割りで、借入の返済期間ではありません。 年間の比較結果-46,552円／年',
      }),
      'ステップ4で年間差の内訳を開く',
    );

    await evaluate(`
      document.querySelector('.next-step-inputs [name="operating_hours_per_day"]').value = '12';
      document.querySelector('.next-step-inputs button[type="submit"]:not(.primary-answer-submit)').click();
    `);
    await waitForPage(evaluate, 'operating_hours_per_day=12');
    assertEqual(await evaluate(`location.hash`), '#comparison-conditions', '運転時間更新後の戻り位置');
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
      document.querySelector('.next-step-inputs [name="investment_year"]').value = '2028';
      document.querySelector('.next-step-inputs [name="first_phase_fan_count"]').value = '3';
      document.querySelector('.next-step-inputs [name="planned_fan_count"]').value = '18';
      document.querySelector('.next-step-inputs button[type="submit"]:not(.primary-answer-submit)').click();
    `);
    await waitForPage(evaluate, 'first_phase_fan_count=3');
    assertEqual(await evaluate(`location.hash`), '#comparison-conditions', '設備案更新後の戻り位置');
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

    const reductionDemoUrl = `${APP_URL}check?lactating_cows=60&lane_count=2&existing_fan_count=10&first_phase_fan_count=5&future_target_cow_count=45`;
    await send('Page.navigate', { url: reductionDemoUrl });
    await waitForPage(evaluate, 'future_target_cow_count=45');
    await evaluate(`
      document.querySelector('.next-step-inputs [name="confirmed_covered_cow_count"]').value = '12';
      document.querySelector('.next-step-inputs button[type="submit"]').click();
    `);
    await waitForPage(evaluate, 'confirmed_covered_cow_count=12');
    assertEqual(await evaluate(`location.hash`), '#comparison-conditions', '風速確認後の戻り位置');
    assertEqual(
      await financialState(evaluate, 'first_phase'),
      JSON.stringify(['5台', '12頭', '1,100,000円', '147,840円／年', '3.92kg／頭・日']),
      '風速確認後の第1期再計算',
    );
    assertEqual(
      await evaluate(`document.querySelector('.next-check-line').textContent.trim()`),
      '次に確認する情報は、夏季の乳量差です。',
      '風速確認後の次の一問',
    );
    assertEqual(
      await evaluate(`(async () => JSON.stringify(await (async () => {
        const controls = [...document.querySelectorAll('[data-outlook-control]')];
        const sliders = controls.map((control) => control.querySelector('[data-outlook-slider]')).filter(Boolean);
        const readings = controls.map((control) => control.querySelector('[data-outlook-reading]')).filter(Boolean);
        const aggregate = document.querySelector('[data-aggregate-reading]');
        const initialAtBreakEven = readings.every((reading) => reading.textContent.includes('回収ライン（損得0円の境目）'));
        const before = readings[0].textContent.trim();
        const aggregateBefore = aggregate.textContent.trim();
        sliders[0].value = String(Math.max(0, Number(sliders[0].value) - 1));
        sliders[0].dispatchEvent(new Event('input', { bubbles: true }));
        await new Promise((resolve) => setTimeout(resolve, 100));
        return {
          controls: controls.length,
          sliders: sliders.length,
          initialAtBreakEven,
          changed: before !== readings[0].textContent.trim(),
          aggregateChanged: aggregateBefore !== aggregate.textContent.trim(),
          queryUnchanged: location.search.includes('confirmed_covered_cow_count=12'),
        };
      })()))()`),
      JSON.stringify({
        controls: 4,
        sliders: 4,
        initialAtBreakEven: true,
        changed: true,
        aggregateChanged: true,
        queryUnchanged: true,
      }),
      '見取り図の4条件スライダー',
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
