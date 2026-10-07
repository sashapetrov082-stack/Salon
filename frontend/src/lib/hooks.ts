import { useQuery } from "@tanstack/react-query";
import { useCallback } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { CategoryWithServices, Me, SalonPublic, StaffPublic } from "../api/types";
import { useBackButton } from "../telegram/webapp";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => api.get<Me>("/me"), staleTime: 60_000 });
}

export function useSalon(slug: string) {
  return useQuery({
    queryKey: ["salon", slug],
    queryFn: () => api.get<SalonPublic>(`/salons/${slug}`),
    staleTime: 60_000,
  });
}

export function useServices(slug: string) {
  return useQuery({
    queryKey: ["services", slug],
    queryFn: () => api.get<CategoryWithServices[]>(`/salons/${slug}/services`),
    staleTime: 60_000,
  });
}

export function useStaff(slug: string, serviceId: number | null) {
  return useQuery({
    queryKey: ["staff", slug, serviceId],
    queryFn: () =>
      api.get<StaffPublic[]>(
        `/salons/${slug}/staff${serviceId ? `?service_id=${serviceId}` : ""}`,
      ),
  });
}

/** Кнопка «Назад»: по истории, а если истории нет — на fallback (или скрыта). */
export function useBack(fallback?: string) {
  const navigate = useNavigate();
  const idx = (window.history.state as { idx?: number } | null)?.idx ?? 0;
  const back = useCallback(() => {
    if (idx > 0) navigate(-1);
    else if (fallback) navigate(fallback, { replace: true });
  }, [idx, fallback, navigate]);
  useBackButton(idx > 0 || fallback ? back : null);
  return back;
}

export function useNumberParam(params: URLSearchParams, key: string): number | null {
  const v = params.get(key);
  return v && /^\d+$/.test(v) ? Number(v) : null;
}
