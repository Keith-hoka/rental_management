/**
 * Save a Blob straight to the default download folder. A fetch-downloaded body
 * cannot be reached by a plain link, so a synthetic anchor at an object URL
 * carries it to disk. Used as the fallback when the save picker is unavailable.
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

/** A Blob-writing subset of the File System Access API (absent from TS's DOM lib). */
type SaveFilePicker = (options?: { suggestedName?: string }) => Promise<{
  createWritable: () => Promise<{
    write: (data: Blob) => Promise<void>;
    close: () => Promise<void>;
  }>;
}>;

/**
 * Save a Blob, letting the user choose where when the browser supports it.
 * Chromium opens a native "Save As" dialog through the File System Access API;
 * Firefox and Safari have no such API and fall back to a normal download. A
 * dismissed dialog saves nothing; any other picker failure also falls back.
 */
export async function saveBlob(blob: Blob, filename: string): Promise<void> {
  const picker = (window as unknown as { showSaveFilePicker?: SaveFilePicker }).showSaveFilePicker;
  if (picker) {
    try {
      const handle = await picker({ suggestedName: filename });
      const writable = await handle.createWritable();
      await writable.write(blob);
      await writable.close();
      return;
    } catch (err) {
      // A dismissed dialog is a deliberate cancel: save nothing. Any other
      // failure (lost activation, denied permission) falls back below.
      if (err instanceof DOMException && err.name === "AbortError") return;
    }
  }
  downloadBlob(blob, filename);
}
