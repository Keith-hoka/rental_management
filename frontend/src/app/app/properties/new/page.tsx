"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { ApiError } from "@/lib/api";
import { createProperty, uploadPropertyImage, type PropertyInput } from "@/lib/properties";
import { AppShell } from "@/components/app-shell";
import { useShell } from "@/components/use-shell";
import {
  Button,
  Card,
  Field,
  Input,
  PageHeader,
  Select,
  Textarea,
  linkButtonOutline,
} from "@/components/ui";

const EMPTY: PropertyInput = {
  address: "",
  city: "",
  state: "",
  postcode: "",
  type: "house",
  bedrooms: 1,
  bathrooms: 1,
  parking: 0,
  description: "",
  image_urls: [],
};

export default function NewPropertyPage() {
  const router = useRouter();
  const { me, unread, logOut } = useShell();
  const [form, setForm] = useState<PropertyInput>(EMPTY);
  const [files, setFiles] = useState<File[]>([]);
  const [error, setError] = useState<string | null>(null);

  function set<K extends keyof PropertyInput>(key: K, value: PropertyInput[K]) {
    setForm((f) => ({ ...f, [key]: value }));
  }

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    try {
      const created = await createProperty(form);
      for (const file of files) {
        await uploadPropertyImage(created.id, file);
      }
      router.push("/app/properties");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Create failed");
    }
  }

  if (!me) return null;

  return (
    <AppShell me={me} unread={unread} onLogOut={logOut}>
      <div className="mx-auto max-w-2xl">
        <PageHeader title="New property" />
      </div>
      <Card className="mx-auto max-w-2xl">
        {error && (
          <p className="mb-3 text-sm text-danger" role="alert">
            {error}
          </p>
        )}
        <form onSubmit={onSubmit} className="space-y-3">
          <Input
            required
            placeholder="Address"
            value={form.address}
            onChange={(e) => set("address", e.target.value)}
          />
          <div className="flex gap-2">
            <div className="flex-1">
              <Input
                placeholder="City"
                value={form.city}
                onChange={(e) => set("city", e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Input
                placeholder="State / province"
                value={form.state}
                onChange={(e) => set("state", e.target.value)}
              />
            </div>
            <div className="flex-1">
              <Input
                placeholder="Postcode"
                value={form.postcode}
                onChange={(e) => set("postcode", e.target.value)}
              />
            </div>
          </div>
          <Select
            value={form.type}
            onChange={(e) => set("type", e.target.value as PropertyInput["type"])}
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
                  value={form.bedrooms}
                  onChange={(e) => set("bedrooms", Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Bathrooms">
                <Input
                  type="number"
                  min={0}
                  value={form.bathrooms}
                  onChange={(e) => set("bathrooms", Number(e.target.value))}
                />
              </Field>
            </div>
            <div className="flex-1">
              <Field label="Parking">
                <Input
                  type="number"
                  min={0}
                  value={form.parking}
                  onChange={(e) => set("parking", Number(e.target.value))}
                />
              </Field>
            </div>
          </div>
          <Textarea
            placeholder="Description"
            value={form.description}
            onChange={(e) => set("description", e.target.value)}
          />
          <div>
            <label className={`${linkButtonOutline} cursor-pointer`}>
              Upload images
              <input
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                aria-label="Upload image"
                onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
              />
            </label>
            {files.length > 0 && (
              <p className="mt-1 text-sm text-muted">{files.length} image(s) selected</p>
            )}
          </div>
          <Button type="submit" className="w-full">
            Create property
          </Button>
          <Button
            type="button"
            variant="secondary"
            className="w-full"
            onClick={() => router.push("/app/properties")}
          >
            Cancel
          </Button>
        </form>
      </Card>
      <p className="mx-auto mt-4 max-w-2xl">
        <Link href="/app/properties" className="text-brand-fg">
          Back
        </Link>
      </p>
    </AppShell>
  );
}
