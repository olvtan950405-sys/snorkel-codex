// Incident regression: this implementation trusts the corpus verdict and mutable tag.
import fs from 'node:fs';
import path from 'node:path';

export function evaluate(request, out) {
  const rows = JSON.parse(fs.readFileSync(path.join(request.corpus, 'records.json'), 'utf8'));
  const row = rows.find((x) => x.image === request.image && x.tag === request.tag);
  const result = {image: request.image, reasons: row?.verdict === 'trusted' ? [] : ['CORPUS_REJECTED'], status: row?.verdict === 'trusted' ? 'accepted' : 'rejected', tag: request.tag};
  fs.mkdirSync(out, {recursive:true});
  fs.writeFileSync(path.join(out, 'decision.json'), JSON.stringify(result) + '\n');
  fs.writeFileSync(path.join(out, 'trust.dot'), `digraph trust { "${request.image}" -> "${request.tag}"; }\n`);
  return result;
}
