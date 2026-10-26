/* 复核状态和 CSV 序列化；不访问文件系统或网络。 */
const REVIEW_LABELS = {pending: '未复核', correct: '分组正确', suspected: '疑似误分组'};
function createReviewRows(rows) {
  return rows.map(row => ({...row,
    review_original_template_id: row.review_original_template_id ?? row.template_id,
    review_status: Object.hasOwn(REVIEW_LABELS, row.review_status) ? row.review_status : 'pending'
  }));
}
function markReviewGroup(rows, ids, status) {
  if (!Object.hasOwn(REVIEW_LABELS, status)) throw new Error('无效复核状态');
  const selected = new Set(ids);
  rows.forEach(row => { if (selected.has(row.sample_id)) row.review_status = status; });
}
function editReviewTemplate(rows, ids, sampleId, value) {
  const row = rows.find(row => row.sample_id === sampleId);
  if (!row) throw new Error('样本不存在');
  if (row.template_id === value) return;
  row.template_id = value;
  markReviewGroup(rows, ids, 'pending');
}
function reviewCSV(rows, originalFields) {
  const fields = [...new Set([...originalFields, 'review_original_template_id', 'review_status'])];
  const quote = value => '"' + String(value ?? '').replaceAll('"', '""') + '"';
  const lines = [fields.map(quote).join(',')];
  rows.forEach(row => lines.push(fields.map(field => quote(row[field])).join(',')));
  return '\uFEFF' + lines.join('\r\n') + '\r\n';
}
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {createReviewRows, markReviewGroup, editReviewTemplate, reviewCSV};
}
