import { useQuery } from "@tanstack/react-query";
import { api } from "../../api/client";
import type { Category, ServiceAdmin, StaffAdmin } from "../../api/types";
import { useManage } from "./context";

export function useStaffList() {
  const { salonId } = useManage();
  return useQuery({
    queryKey: ["manage", salonId, "staff"],
    queryFn: () => api.get<StaffAdmin[]>(`/manage/${salonId}/staff`),
  });
}

export function useServiceList() {
  const { salonId } = useManage();
  return useQuery({
    queryKey: ["manage", salonId, "services"],
    queryFn: () => api.get<ServiceAdmin[]>(`/manage/${salonId}/services`),
  });
}

export function useCategories() {
  const { salonId } = useManage();
  return useQuery({
    queryKey: ["manage", salonId, "categories"],
    queryFn: () => api.get<Category[]>(`/manage/${salonId}/categories`),
  });
}
