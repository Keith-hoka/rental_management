/**
 * Save a Blob as a file. A fetch-downloaded body cannot be reached by a plain
 * link, so a synthetic anchor at an object URL carries it to disk. Later Phase 2
 * exports (reports, documents) reuse this.
 */
export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
