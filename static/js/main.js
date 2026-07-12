import { createBarnViewer } from './barn-viewer.js';

const layout = JSON.parse(document.querySelector('#layout-data').textContent);
const cowIdByInstanceId = JSON.parse(document.querySelector('#cow-id-by-instance-id').textContent);
const detail = document.querySelector('#selection-detail');

createBarnViewer(document.querySelector('#barn-viewer'), layout, cowIdByInstanceId, (selection) => {
  if (selection.type === 'cow') {
    detail.textContent = `牛：${selection.cowId} ／ 第${selection.lane}牛床列 ／ 房${selection.stall}`;
  } else {
    detail.textContent = `ファン：${selection.fanId} ／ 第${selection.lane}牛床列 ／ 対象牛：${selection.cowIds.join(', ')}`;
  }
});
