"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { createProperty, type PropertyInput } from "@/lib/properties";

const EMPTY: PropertyInput = {
  address: "",
  type: "house",
  bedrooms: 1,
  bathrooms: 1,
  parking: 0,
  description: "",
  status: "vacant",
  image_urls: [],
};

export default function NewPropertyPage() {
  const router = useRouter();
  const [form, setForm] = useState<PropertyInput>(EMPTY);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof PropertyInput>(key: K, value: PropertyInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      await createProperty(form);
      router.push("/app/properties");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  }

  return (
    <main className="mx-auto max-w-lg p-8">
      <h1 className="mb-4 text-2xl font-semibold">New property</h1>
      {error && (
        <p className="mb-2 text-sm text-red-600" role="alert">
          {error}
        </p>
      )}
      <form onSubmit={onSubmit} className="space-y-3">
        <input
          required
          placeholder="Address"
          value={form.address}
          onChange={(e) => set("address", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <select
          value={form.type}
          onChange={(e) => set("type", e.target.value as PropertyInput["type"])}
          className="w-full rounded border px-3 py-2"
        >
          <option value="house">House</option>
          <option value="apartment">Apartment</option>
          <option value="condo">Condo</option>
          <option value="townhouse">Townhouse</option>
          <option value="other">Other</option>
        </select>
        <div className="flex gap-2">
          <input
            type="number"
            min={0}
            placeholder="Bedrooms"
            value={form.bedrooms}
            onChange={(e) => set("bedrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder="Bathrooms"
            value={form.bathrooms}
            onChange={(e) => set("bathrooms", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
          <input
            type="number"
            min={0}
            placeholder="Parking"
            value={form.parking}
            onChange={(e) => set("parking", Number(e.target.value))}
            className="w-full rounded border px-3 py-2"
          />
        </div>
        <textarea
          placeholder="Description"
          value={form.description}
          onChange={(e) => set("description", e.target.value)}
          className="w-full rounded border px-3 py-2"
        />
        <button type="submit" className="w-full rounded bg-blue-600 py-2 text-white">
          Create property
        </button>
      </form>
      <p className="mt-4">
        <Link href="/app/properties" className="text-blue-600">
          Back to properties
        </Link>
      </p>
    </main>
  );
}
