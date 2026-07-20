"use client";

import { use, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { getAccessToken } from "@/lib/auth";
import {
  deleteProperty,
  getProperty,
  imageSrc,
  updateProperty,
  uploadPropertyImage,
  type Property,
} from "@/lib/properties";

export default function PropertyDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const router = useRouter();
  const [prop, setProp] = useState<Property | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    getProperty(id)
      .then((p) => {
        if (active) setProp(p);
      })
      .catch(() => {
        if (active) setError("Property not found");
      });
    return () => {
      active = false;
    };
  }, [id, router]);

  if (error && !prop) return <main className="p-8 text-red-600">{error}</main>;
  if (!prop) return null;

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
        type: prop.type,
        bedrooms: prop.bedrooms,
        bathrooms: prop.bathrooms,
        parking: prop.parking,
        description: prop.description ?? "",
      });
      router.push("/app/properties");
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

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">Edit property</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      {prop.active_lease ? (
        <div className="mb-4 rounded border border-green-500 bg-green-50 p-3 text-sm">
          <p className="font-semibold text-green-800">Occupied</p>
          <p className="text-gray-700">
            {prop.active_lease.tenant_name} · ${prop.active_lease.rent_amount}/
            {prop.active_lease.rent_frequency}
          </p>
          <p className="text-gray-600">
            {prop.active_lease.start_date} to {prop.active_lease.end_date}
          </p>
        </div>
      ) : (
        <p className="mb-4 text-sm text-gray-600">Vacant — no active lease.</p>
      )}
      <p className="mb-4">
        <Link href={`/app/properties/${id}/leases`} className="text-blue-600">
          Manage leases
        </Link>
      </p>
      <form onSubmit={onSave} className="space-y-3">
        <input
          required
          value={prop.address}
          onChange={(e) => set("address", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <select
          value={prop.type}
          onChange={(e) => set("type", e.target.value as Property["type"])}
          className="w-full rounded border px-3 py-2"
        >
          <option value="house">House</option>
          <option value="apartment">Apartment</option>
          <option value="condo">Condo</option>
          <option value="townhouse">Townhouse</option>
          <option value="other">Other</option>
        </select>
        <div className="flex gap-2">
          <label className="flex-1 text-sm text-gray-600">
            Bedrooms
            <input
              type="number"
              min={0}
              value={prop.bedrooms}
              onChange={(e) => set("bedrooms", Number(e.target.value))}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
          <label className="flex-1 text-sm text-gray-600">
            Bathrooms
            <input
              type="number"
              min={0}
              value={prop.bathrooms}
              onChange={(e) => set("bathrooms", Number(e.target.value))}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
          <label className="flex-1 text-sm text-gray-600">
            Parking
            <input
              type="number"
              min={0}
              value={prop.parking}
              onChange={(e) => set("parking", Number(e.target.value))}
              className="mt-1 w-full rounded border px-3 py-2"
            />
          </label>
        </div>
        <textarea
          placeholder="Description"
          value={prop.description ?? ""}
          onChange={(e) => set("description", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <div>
          {prop.image_urls.length > 0 && (
            <div className="mb-2 flex flex-wrap gap-2">
              {prop.image_urls.map((url) => (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  key={url}
                  src={imageSrc(url)}
                  alt="Property"
                  className="h-24 w-24 rounded object-cover"
                />
              ))}
            </div>
          )}
          <label className="inline-block cursor-pointer rounded border border-gray-300 px-3 py-2 text-sm text-blue-600 transition hover:border-blue-500 hover:bg-blue-50">
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
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Save
        </button>
      </form>
      <button
        onClick={() => setConfirming(true)}
        className="mt-3 w-full rounded border border-red-500 py-2 text-red-600 transition hover:bg-red-50"
      >
        Delete property
      </button>
      <p className="mt-4">
        <Link href="/app/properties" className="text-blue-600">
          Back to properties
        </Link>
      </p>

      {confirming && (
        <div className="fixed inset-0 z-10 flex items-center justify-center bg-black/40 p-4">
          <div className="w-full max-w-sm rounded-lg bg-white p-6 shadow-lg">
            <p className="mb-4 text-gray-800">
              Delete this property? This cannot be undone.
            </p>
            <div className="flex justify-end gap-2">
              <button
                onClick={() => setConfirming(false)}
                className="rounded border px-3 py-1 transition hover:bg-gray-50"
              >
                Cancel
              </button>
              <button
                onClick={onDelete}
                className="rounded bg-red-600 px-3 py-1 text-white transition hover:bg-red-700"
              >
                Yes, delete
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}
