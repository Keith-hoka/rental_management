"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import {
  deleteProperty,
  deletePropertyImage,
  getProperty,
  imageSrc,
  updateProperty,
  uploadPropertyImage,
  type Property,
} from "@/lib/properties";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import { Badge, Button, Card, Field, Input, PageHeader, Select, Textarea } from "@/components/ui";

export default function PropertyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const { me, unread, logOut } = useShell();
  const [prop, setProp] = useState<Property | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!me) return;
    let active = true;
    getProperty(id)
      .then((p) => active && setProp(p))
      .catch(() => active && setError("Property not found"));
    return () => {
      active = false;
    };
  }, [id, me]);

  function set<K extends keyof Property>(key: K, value: Property[K]) {
    setProp((p) => (p ? { ...p, [key]: value } : p));
  }

  async function onSave(e: React.FormEvent) {
    e.preventDefault();
    if (!prop) return;
    setError(null);
    try {
      await updateProperty(id, {
        address: prop.address,
        state: prop.state ?? "",
        postcode: prop.postcode ?? "",
        type: prop.type,
        bedrooms: prop.bedrooms,
        bathrooms: prop.bathrooms,
        parking: prop.parking,
        description: prop.description ?? "",
      });
      router.push(`/app/properties/${id}`);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Save failed");
    }
  }

  async function onDelete() {
    await deleteProperty(id);
    router.push("/app/properties");
  }

  async function onUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setError(null);
    try {
      setProp(await uploadPropertyImage(id, file));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Upload failed");
    }
  }

  async function onRemoveImage(url: string) {
    setError(null);
    try {
      setProp(await deletePropertyImage(id, url));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Remove failed");
    }
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="Edit property" />
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
      </div>
      {!prop ? null : (
        <>
          <Card className="mx-auto mb-4 max-w-2xl">
            {prop.active_lease ? (
              <>
                <p className="font-medium text-text">
                  <Badge tone="success">Occupied</Badge>
                </p>
                <p className="mt-2 text-sm text-text">
                  {prop.active_lease.tenant_name} · ${prop.active_lease.rent_amount}/
                  {prop.active_lease.rent_frequency}
                </p>
                <p className="text-sm text-muted">
                  {prop.active_lease.start_date} to {prop.active_lease.end_date}
                </p>
              </>
            ) : (
              <p className="text-sm text-muted">Vacant — no active lease.</p>
            )}
          </Card>

          <Card className="mx-auto max-w-2xl">
            <form onSubmit={onSave} className="space-y-3">
              <Input
                required
                value={prop.address}
                onChange={(e) => set("address", e.target.value)}
              />
              <div className="flex gap-2">
                <div className="flex-1">
                  <Input
                    placeholder="State / province"
                    value={prop.state ?? ""}
                    onChange={(e) => set("state", e.target.value)}
                  />
                </div>
                <div className="flex-1">
                  <Input
                    placeholder="Postcode"
                    value={prop.postcode ?? ""}
                    onChange={(e) => set("postcode", e.target.value)}
                  />
                </div>
              </div>
              <Select
                value={prop.type}
                onChange={(e) => set("type", e.target.value as Property["type"])}
              >
                <option value="house">House</option>
                <option value="apartment">Apartment</option>
                <option value="condo">Condo</option>
                <option value="townhouse">Townhouse</option>
                <option value="other">Other</option>
              </Select>
              <div className="flex gap-2">
                <div className="flex-1">
                  <Field label="Bedrooms">
                    <Input
                      type="number"
                      min={0}
                      value={prop.bedrooms}
                      onChange={(e) => set("bedrooms", Number(e.target.value))}
                    />
                  </Field>
                </div>
                <div className="flex-1">
                  <Field label="Bathrooms">
                    <Input
                      type="number"
                      min={0}
                      value={prop.bathrooms}
                      onChange={(e) => set("bathrooms", Number(e.target.value))}
                    />
                  </Field>
                </div>
                <div className="flex-1">
                  <Field label="Parking">
                    <Input
                      type="number"
                      min={0}
                      value={prop.parking}
                      onChange={(e) => set("parking", Number(e.target.value))}
                    />
                  </Field>
                </div>
              </div>
              <Textarea
                placeholder="Description"
                value={prop.description ?? ""}
                onChange={(e) => set("description", e.target.value)}
              />
              <div>
                {prop.image_urls.length > 0 && (
                  <div className="mb-2 flex flex-wrap gap-2">
                    {prop.image_urls.map((url) => (
                      <div key={url} className="group relative">
                        {/* eslint-disable-next-line @next/next/no-img-element */}
                        <img
                          src={imageSrc(url)}
                          alt="Property"
                          className="h-24 w-24 rounded-lg object-cover"
                        />
                        {/* Hidden by opacity, not display, so it stays keyboard reachable. */}
                        <button
                          type="button"
                          aria-label="Remove image"
                          onClick={() => onRemoveImage(url)}
                          className="absolute right-1 top-1 flex h-6 w-6 items-center justify-center rounded-full bg-black/60 text-sm leading-none text-white opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
                        >
                          &times;
                        </button>
                      </div>
                    ))}
                  </div>
                )}
                <label className="inline-block cursor-pointer rounded-lg border border-border px-3 py-2 text-sm text-brand hover:bg-brand-soft">
                  Upload image
                  <input
                    type="file"
                    accept="image/*"
                    className="hidden"
                    aria-label="Upload image"
                    onChange={onUpload}
                  />
                </label>
              </div>
              <Button type="submit" className="w-full">
                Save
              </Button>
              <Button
                type="button"
                variant="secondary"
                className="w-full"
                onClick={() => router.push(`/app/properties/${id}`)}
              >
                Cancel
              </Button>
            </form>
            <Button variant="danger" onClick={() => setConfirming(true)} className="mt-3 w-full">
              Delete property
            </Button>
          </Card>
          <p className="mx-auto mt-4 max-w-2xl">
            <Link href={`/app/properties/${id}`} className="text-brand">
              Back
            </Link>
          </p>
        </>
      )}

      {confirming && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          {/* A real dialog: the form behind it also has a Cancel button, and the
              role is what keeps the two distinguishable. */}
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Delete property"
            className="w-full max-w-sm rounded-xl border border-border bg-surface p-6 shadow-lg"
          >
            <p className="mb-4 text-text">Delete this property? This cannot be undone.</p>
            <div className="flex justify-end gap-2">
              <Button variant="secondary" size="sm" onClick={() => setConfirming(false)}>
                Cancel
              </Button>
              <Button variant="danger" size="sm" onClick={onDelete}>
                Yes, delete
              </Button>
            </div>
          </div>
        </div>
      )}
    </AppShell>
  );
}
