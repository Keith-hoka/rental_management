import { Badge } from "@/components/ui";
import type { RecentPayment } from "@/lib/payments";

const COLUMNS = ["Date", "Property info", "Tenant name", "Method", "Amount"];

/**
 * Payment rows. The header always renders, including when there are no
 * payments: hiding it made the columns look broken rather than empty.
 */
export function PaymentTable({ payments }: { payments: RecentPayment[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-border bg-surface-2 text-xs text-muted">
          <tr>
            {COLUMNS.map((column) => (
              <th
                key={column}
                className={`px-3 py-2 font-medium ${column === "Amount" ? "text-right" : ""}`}
              >
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-border">
          {payments.map((p) => (
            <tr key={p.id}>
              <td className="px-3 py-2 text-muted">{p.paid_on}</td>
              <td className="px-3 py-2 text-text">{p.property_address}</td>
              <td className="px-3 py-2 text-muted">{p.tenant_name}</td>
              <td className="px-3 py-2">
                <Badge tone="brand">{p.method.replace("_", " ")}</Badge>
              </td>
              <td className="px-3 py-2 text-right font-medium text-text">${p.amount}</td>
            </tr>
          ))}
          {payments.length === 0 && (
            <tr>
              <td colSpan={COLUMNS.length} className="px-3 py-6 text-center text-muted">
                No payments yet.
              </td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}
