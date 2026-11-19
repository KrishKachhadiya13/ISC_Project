import { useMutation } from '@tanstack/react-query';
import { ArrowUpDown, Download, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';

import { api } from '../api/client';
import type { BatchItem } from '../api/types';
import { validateImageFile } from '../components/ImageDropzone';
import { DETECTOR_INFO, DetectResultView } from './Detect';
import { Badge, ErrorBanner, PageHeader, Spinner } from '../components/ui';
import { downloadText } from '../lib/download';
import { formatNumber } from '../lib/format';
import { useRevealOnResult } from '../lib/useRevealOnResult';

const MAX_FILES = 20;
type SortKey = 'filename' | 'probability';
type Filter = 'all' | 'stego' | 'clean' | 'error';

interface Row {
  file: File;
  item: BatchItem;
}

function topDetector(item: BatchItem): string {
  const entries = Object.entries(item.result?.detectors ?? {}).filter(([, entry]) => entry?.available);
  if (!entries.length) return '—';
  const [name] = entries.reduce((best, current) =>
    (current[1]?.probability ?? 0) > (best[1]?.probability ?? 0) ? current : best,
  );
  return name;
}

/** Plain detector name for the table; the CSV keeps the machine name. */
function detectorTitle(name: string): string {
  return DETECTOR_INFO[name]?.title ?? name;
}

/** One sentence naming the flagging line, taken from the first scanned image. */
function thresholdNote(items: BatchItem[]): string {
  const threshold = items.find((item) => item.result)?.result?.threshold;
  return threshold === undefined ? '' : `Images scoring ${(threshold * 100).toFixed(1)}% or more are flagged. `;
}

function csvCell(value: string): string {
  // Quote every cell and neutralise spreadsheet formulas (CSV injection).
  const safe = /^[=+\-@]/.test(value) ? `'${value}` : value;
  return `"${safe.replace(/"/g, '""')}"`;
}

export function BatchScan() {
  const [files, setFiles] = useState<File[]>([]);
  const [rejected, setRejected] = useState<string[]>([]);
  const [sortKey, setSortKey] = useState<SortKey>('probability');
  const [descending, setDescending] = useState(true);
  const [filter, setFilter] = useState<Filter>('all');
  const [selected, setSelected] = useState<Row | null>(null);
  const [selectedUrl, setSelectedUrl] = useState<string | null>(null);
  // The details open below a long table and only render once the thumbnail URL is known, so
  // reveal them when both are ready.
  const detailRef = useRevealOnResult<HTMLElement>(selected && selectedUrl ? selected : null);
  const [thumbs, setThumbs] = useState<Map<File, string>>(new Map());

  useEffect(() => {
    const map = new Map(files.map((file) => [file, URL.createObjectURL(file)]));
    setThumbs(map);
    return () => map.forEach((url) => URL.revokeObjectURL(url));
  }, [files]);

  useEffect(() => {
    setSelectedUrl(selected ? (thumbs.get(selected.file) ?? null) : null);
  }, [selected, thumbs]);

  const scan = useMutation({ mutationFn: () => api.detectBatch(files) });

  const rows: Row[] = useMemo(() => {
    const items = scan.data?.items ?? [];
    const combined = items.map((item, index) => ({ file: files[index], item }));
    const filtered = combined.filter(({ item }) => {
      if (filter === 'error') return item.error !== null;
      if (filter === 'stego') return item.result?.label === 'suspected_stego';
      if (filter === 'clean') return item.result?.label === 'clean';
      return true;
    });
    const sign = descending ? -1 : 1;
    return filtered.sort((a, b) =>
      sortKey === 'filename'
        ? sign * a.item.filename.localeCompare(b.item.filename)
        : sign * ((a.item.result?.probability ?? -1) - (b.item.result?.probability ?? -1)),
    );
  }, [scan.data, files, filter, sortKey, descending]);

  function addFiles(list: FileList | null) {
    if (!list) return;
    const accepted: File[] = [];
    const problems: string[] = [];
    for (const file of Array.from(list)) {
      const problem = validateImageFile(file, false);
      if (problem) problems.push(`${file.name}: ${problem}`);
      else accepted.push(file);
    }
    const next = [...files, ...accepted].slice(0, MAX_FILES);
    if (files.length + accepted.length > MAX_FILES) problems.push(`Only the first ${MAX_FILES} images are kept.`);
    setFiles(next);
    setRejected(problems);
    scan.reset();
  }

  function exportCsv() {
    const header = ['filename', 'verdict', 'probability', 'decision_source', 'top_detector', 'sha256', 'error'];
    const lines = (scan.data?.items ?? []).map((item) =>
      [
        item.filename,
        item.result?.label ?? '',
        item.result ? item.result.probability.toFixed(6) : '',
        item.result?.decision_source ?? '',
        topDetector(item),
        item.result?.image_sha256 ?? '',
        item.error ? `${item.error.code}: ${item.error.message}` : '',
      ]
        .map(csvCell)
        .join(','),
    );
    downloadText([header.join(','), ...lines].join('\n'), 'stegaguard_batch_scan.csv', 'text/csv');
  }

  function toggleSort(key: SortKey) {
    if (sortKey === key) setDescending((current) => !current);
    else {
      setSortKey(key);
      setDescending(key === 'probability');
    }
  }

  return (
    <div>
      <PageHeader title="Batch scan">
        Scan up to {MAX_FILES} images at once. Sort, filter, export to CSV, and open any row for the full
        detector breakdown.
      </PageHeader>
      <section className="card space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <label className="btn-secondary cursor-pointer">
            Add images…
            <input type="file" accept="image/*,.pgm" multiple className="sr-only" onChange={(event) => {
              addFiles(event.target.files);
              event.target.value = '';
            }} />
          </label>
          <span className="text-sm text-muted">
            {files.length} / {MAX_FILES} selected
          </span>
          {files.length > 0 && (
            <button type="button" className="btn-ghost" onClick={() => {
              setFiles([]);
              scan.reset();
            }}>
              Clear
            </button>
          )}
          <button type="button" className="btn-primary ml-auto" disabled={!files.length || scan.isPending} onClick={() => scan.mutate()}>
            {scan.isPending ? <Spinner label={`Scanning ${files.length}…`} /> : 'Scan all'}
          </button>
        </div>
        {rejected.map((problem) => (
          <p key={problem} className="text-sm text-bad" role="alert">
            {problem}
          </p>
        ))}
        <ErrorBanner error={scan.error} />
      </section>

      {scan.data && (
        <section className="card mt-6 space-y-4">
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="filter" className="text-sm">
              Show
            </label>
            <select id="filter" className="field w-auto" value={filter} onChange={(event) => setFilter(event.target.value as Filter)}>
              <option value="all">All</option>
              <option value="stego">Hidden data suspected</option>
              <option value="clean">Not flagged</option>
              <option value="error">Errors</option>
            </select>
            <button type="button" className="btn-secondary ml-auto" onClick={exportCsv}>
              <Download className="h-4 w-4" /> Export CSV
            </button>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full min-w-[36rem] text-sm">
              <caption className="sr-only">Batch scan results</caption>
              <thead>
                <tr className="border-b border-line text-left text-xs uppercase text-muted">
                  <th scope="col" className="py-2">Image</th>
                  <th scope="col" aria-sort={sortKey === 'filename' ? (descending ? 'descending' : 'ascending') : 'none'}>
                    <button type="button" className="inline-flex items-center gap-1 uppercase" onClick={() => toggleSort('filename')}>
                      File <ArrowUpDown className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </th>
                  <th scope="col">Verdict</th>
                  <th scope="col" aria-sort={sortKey === 'probability' ? (descending ? 'descending' : 'ascending') : 'none'}>
                    <button type="button" className="inline-flex items-center gap-1 uppercase" onClick={() => toggleSort('probability')}>
                      Score <ArrowUpDown className="h-3 w-3" aria-hidden="true" />
                    </button>
                  </th>
                  <th scope="col">Top detector</th>
                  <th scope="col"><span className="sr-only">Details</span></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.item.filename + row.file.lastModified} className="border-b border-line/60">
                    <td className="py-2">
                      {thumbs.get(row.file) && (
                        <img src={thumbs.get(row.file)} alt="" className="h-10 w-10 rounded object-cover" />
                      )}
                    </td>
                    <td className="max-w-[12rem] truncate pr-3">{row.item.filename}</td>
                    <td>
                      {row.item.error ? (
                        <Badge tone="warn">{row.item.error.code}</Badge>
                      ) : row.item.result?.label === 'suspected_stego' ? (
                        <Badge tone="bad">Suspected</Badge>
                      ) : (
                        <Badge tone="ok">Not flagged</Badge>
                      )}
                    </td>
                    <td className="mono">{row.item.result ? formatNumber(row.item.result.probability, 3) : '—'}</td>
                    <td>{detectorTitle(topDetector(row.item))}</td>
                    <td>
                      {row.item.result && (
                        <button type="button" className="btn-secondary px-3 py-1 text-xs" onClick={() => setSelected(row)}>
                          Open
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="hint">
            {thresholdNote(scan.data.items)}
            A high score is a reason to look closer, not proof.
          </p>
        </section>
      )}

      {selected?.item.result && selectedUrl && (
        <section ref={detailRef} tabIndex={-1} className="card mt-6 scroll-mt-24 outline-none" aria-label={`Details for ${selected.item.filename}`}>
          <div className="mb-4 flex items-center justify-between">
            <h2 className="font-semibold">{selected.item.filename}</h2>
            <button type="button" className="btn-ghost p-2" onClick={() => setSelected(null)} aria-label="Close details">
              <X className="h-4 w-4" />
            </button>
          </div>
          <DetectResultView result={selected.item.result} imageUrl={selectedUrl} />
        </section>
      )}
    </div>
  );
}
