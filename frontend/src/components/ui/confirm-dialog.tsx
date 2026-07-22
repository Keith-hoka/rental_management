import { Button } from "./button";

/**
 * Confirmation gate for a destructive action.
 *
 * `label` names the dialog for assistive tech and for Playwright; `confirmLabel`
 * is the wording on the button that goes through with it. Both are per-action so
 * two dialogs on one page never share an accessible name.
 */
export function ConfirmDialog({
  open,
  label,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  label: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={label}
        className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
      >
        <p className="mb-4 text-text">{message}</p>
        <div className="flex justify-end gap-2">
          <Button variant="secondary" size="sm" onClick={onCancel}>
            Cancel
          </Button>
          <Button variant="danger" size="sm" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
