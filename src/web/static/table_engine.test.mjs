// node src/web/static/table_engine.test.mjs — column statistics vs table_data.numeric_stats / string_stats.
import { readFileSync } from 'node:fs';
import assert from 'node:assert/strict';
import { toNumber, numericStats, stringStats, detectNumericColumns, parseDelimited } from './table_engine.js';

const { table } = JSON.parse(readFileSync(new URL('../../../tests/fixtures/web_engines.json', import.meta.url)));
for (const c of table.columns) {
  const nums = c.values.map(toNumber).filter(v => v !== null);
  assert.deepEqual(nums, c.numbers, `to_number ${c.values}`);
  assert.deepEqual(numericStats(nums), c.numeric, `numeric_stats ${c.values}`);
  assert.deepEqual(stringStats(c.values), c.string, `string_stats ${c.values}`);
}
assert.deepEqual(detectNumericColumns(table.header, table.rows), table.detect);
const csv = [table.header.join(','), ...table.rows.map(r => r.join(','))].join('\n') + '\n';
assert.deepEqual(parseDelimited(csv), { header: table.header, rows: table.rows, delimiter: ',' });
assert.deepEqual(parseDelimited('a\tb\n"x\ty"\t2\n').rows, [['x\ty', '2']]);
console.log(`table: ${table.columns.length} columns match Python`);
