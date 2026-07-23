"use client";

import { useEffect, useState } from "react";
import { fetchDocumentBlob, type DocumentVersionInfo } from "@/lib/documents";
import { saveBlob } from "@/lib/download";
import { Button } from "@/components/ui";

/**
 * In-page preview of one document version. A new browser tab is avoided on
 * purpose: window.open after an async fetch is blocked by popup blockers,
 * because the user-gesture context is gone by the time the blob resolves.
 */
export function DocumentPreview({
  version,
  onClose,
}: {
  version: DocumentVersionInfo;
  onClose: () => void;
}) {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    let created: string | null = null;
    fetchDocumentBlob(version.id)
      .then((blob) => {
        if (!active) return;
        created = URL.createObjectURL(blob);
        setUrl(created);
      })
      .catch(() => active && setUrl(null));
    return () => {
      active = false;
      if (created) URL.revokeObjectURL(created);
    };
  }, [version.id]);

  const isImage = version.content_type.startsWith("image/");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Preview ${version.original_filename}`}
        className="flex h-full w-full max-w-3xl flex-col rounded-xl border border-border bg-surface p-4 shadow-lg"
      >
        <div className="mb-3 flex items-center justify-between gap-2">
          <span className="truncate font-medium text-text">{version.original_filename}</span>
          <span className="flex gap-2">
            <Button
              variant="secondary"
              size="sm"
              onClick={async () => saveBlob(await fetchDocumentBlob(version.id), version.original_filename)}
            >
              Download
            </Button>
            <Button variant="secondary" size="sm" onClick={onClose}>
              Close
            </Button>
          </span>
        </div>
        {url === null ? (
          <p className="text-muted">Loading…</p>
        ) : isImage ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={url} alt={version.original_filename} className="min-h-0 flex-1 object-contain" />
        ) : (
          <iframe src={url} title={version.original_filename} className="min-h-0 flex-1 rounded-lg" />
        )}
      </div>
    </div>
  );
}
