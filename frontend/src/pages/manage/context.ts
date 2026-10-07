import { createContext, useContext } from "react";
import type { SalonSettings, StaffRole } from "../../api/types";

export interface ManageCtx {
  salonId: number;
  staffId: number;
  role: StaffRole;
  isAdmin: boolean;
  salon: SalonSettings;
  base: string; // «/manage/<id>»
}

export const ManageContext = createContext<ManageCtx | null>(null);

export function useManage(): ManageCtx {
  const ctx = useContext(ManageContext);
  if (!ctx) throw new Error("ManageContext missing");
  return ctx;
}
