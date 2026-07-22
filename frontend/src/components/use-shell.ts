"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { apiFetch } from "@/lib/api";
import { clearTokens, getAccessToken } from "@/lib/auth";
import { getUnreadCount } from "@/lib/notifications";

export interface Me {
  email: string;
  name: string;
  role: string;
}

/** Auth guard plus the data both shells need: the current user and the unread count. */
export function useShell() {
  const router = useRouter();
  const [me, setMe] = useState<Me | null>(null);
  const [unread, setUnread] = useState(0);

  useEffect(() => {
    if (!getAccessToken()) {
      router.replace("/login");
      return;
    }
    let active = true;
    apiFetch<Me>("/api/v1/auth/me")
      .then((m) => {
        if (!active) return;
        setMe(m);
        getUnreadCount()
          .then((u) => active && setUnread(u.count))
          .catch(() => active && setUnread(0));
      })
      .catch(() => {
        clearTokens();
        router.replace("/login");
      });
    return () => {
      active = false;
    };
  }, [router]);

  function logOut() {
    clearTokens();
    router.replace("/login");
  }

  return { me, unread, logOut };
}
