import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError, api } from "../../api/client";
import type { Invite, StaffAdmin, StaffRole, StaffService } from "../../api/types";
import { ImageUpload } from "../../components/ImageUpload";
import { Avatar, Check, ErrorView, Field, Row, Section, Spinner, toast } from "../../components/ui";
import { formatDateTime, formatDuration, formatPrice } from "../../lib/format";
import { useBack } from "../../lib/hooks";
import {
  alertDialog,
  confirmDialog,
  copyText,
  haptic,
  openTelegramLink,
  useMainButton,
} from "../../telegram/webapp";
import { useManage } from "./context";
import { useServiceList, useStaffList } from "./hooks";
import { ROLE_LABELS } from "./ManagePicker";

export function StaffAdminPage() {
  const { salonId, base, role } = useManage();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  useBack(`${base}/more`);
  const staff = useStaffList();
  const [name, setName] = useState("");
  const [newRole, setNewRole] = useState<StaffRole>("master");

  const create = useMutation({
    mutationFn: () =>
      api.post<StaffAdmin>(`/manage/${salonId}/staff`, { display_name: name.trim(), role: newRole }),
    onSuccess: (s) => {
      haptic.success();
      setName("");
      queryClient.invalidateQueries({ queryKey: ["manage", salonId, "staff"] });
      navigate(`${base}/staff/${s.id}`);
    },
    onError: (e) => alertDialog(e instanceof ApiError ? e.message : "Не удалось добавить"),
  });

  if (staff.isLoading) return <Spinner />;
  if (staff.isError) return <ErrorView error={staff.error} />;

  return (
    <div className="page">
      <div className="page-title">Сотрудники</div>
      <Section>
        {staff.data!.map((s) => (
          <Row
            key={s.id}
            left={<Avatar url={s.photo_url} name={s.display_name} />}
            title={
              <>
                {s.display_name} {!s.is_active && <span className="badge gray">отключён</span>}
              </>
            }
            sub={[
              ROLE_LABELS[s.role],
              s.is_linked ? (s.telegram_username ? `@${s.telegram_username}` : "Telegram привязан") : "не привязан к Telegram",
              s.is_bookable ? null : "не принимает записи",
            ]
              .filter(Boolean)
              .join(" · ")}
            chevron
            onClick={() => navigate(`${base}/staff/${s.id}`)}
          />
        ))}
      </Section>
      <Section title="Добавить сотрудника">
        <Field label="Имя (так его увидят клиенты)">
          <input className="input" value={name} maxLength={120} onChange={(e) => setName(e.target.value)} />
        </Field>
        <Field label="Роль">
          <select className="input" value={newRole} onChange={(e) => setNewRole(e.target.value as StaffRole)}>
            <option value="master">Мастер</option>
            <option value="admin">Администратор</option>
            {role === "owner" && <option value="owner">Владелец</option>}
          </select>
        </Field>
        <div className="section-pad">
          <button className="btn block" disabled={!name.trim() || create.isPending} onClick={() => create.mutate()}>
            Добавить
          </button>
        </div>
      </Section>
    </div>
  );
}

type Binding = { enabled: boolean; price: string; duration: string };

export function StaffEditPage() {
  const { id = "" } = useParams();
  const staffId = Number(id);
  const { salonId, base, role, staffId: myStaffId, salon } = useManage();
  const queryClient = useQueryClient();
  useBack(`${base}/staff`);
  const staffList = useStaffList();
  const services = useServiceList();
  const staff = staffList.data?.find((s) => s.id === staffId);

  const [form, setForm] = useState<StaffAdmin | null>(null);
  const [bindings, setBindings] = useState<Record<number, Binding>>({});
  const [invite, setInvite] = useState<Invite | null>(null);

  useEffect(() => {
    if (staff && (!form || form.id !== staff.id)) {
      setForm(staff);
      const b: Record<number, Binding> = {};
      for (const ss of staff.services) {
        b[ss.service_id] = {
          enabled: true,
          price: ss.price_override?.toString() ?? "",
          duration: ss.duration_override_min?.toString() ?? "",
        };
      }
      setBindings(b);
    }
  }, [staff, form]);

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["manage", salonId] });
  const onError = (e: unknown) => {
    haptic.error();
    alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить");
  };

  const save = useMutation({
    mutationFn: async () => {
      const f = form!;
      await api.put<StaffAdmin>(`/manage/${salonId}/staff/${staffId}`, {
        display_name: f.display_name.trim(),
        role: f.role,
        photo_url: f.photo_url,
        description: f.description?.trim() || null,
        is_bookable: f.is_bookable,
        is_active: f.is_active,
        sort_order: f.sort_order,
      });
      const items: StaffService[] = Object.entries(bindings)
        .filter(([, b]) => b.enabled)
        .map(([sid, b]) => ({
          service_id: Number(sid),
          price_override: b.price === "" ? null : Math.max(0, Math.floor(Number(b.price))),
          duration_override_min: b.duration === "" ? null : Math.max(5, Math.floor(Number(b.duration))),
        }));
      await api.put(`/manage/${salonId}/staff/${staffId}/services`, items);
    },
    onSuccess: () => {
      haptic.success();
      toast("Сохранено");
      invalidate();
      queryClient.invalidateQueries({ queryKey: ["services"] });
      queryClient.invalidateQueries({ queryKey: ["staff"] });
    },
    onError,
  });

  const createInvite = useMutation({
    mutationFn: () => api.post<Invite>(`/manage/${salonId}/staff/${staffId}/invite`),
    onSuccess: setInvite,
    onError,
  });

  const remove = useMutation({
    mutationFn: () => api.delete(`/manage/${salonId}/staff/${staffId}`),
    onSuccess: () => {
      toast("Сотрудник удалён");
      invalidate();
      history.back();
    },
    onError,
  });

  useMainButton({
    text: "Сохранить",
    visible: !!form,
    progress: save.isPending,
    disabled: save.isPending,
    onClick: () => {
      if (!form?.display_name.trim()) return void alertDialog("Укажите имя");
      save.mutate();
    },
  });

  if (staffList.isLoading || services.isLoading) return <Spinner />;
  if (!staff || !form) return <ErrorView error={new ApiError(404, "not_found", "Сотрудник не найден")} />;
  const set = <K extends keyof StaffAdmin>(k: K, v: StaffAdmin[K]) => setForm({ ...form, [k]: v });
  const isSelf = staff.id === myStaffId;
  const canEditRole = !isSelf && (role === "owner" || staff.role !== "owner");

  const shareInvite = (inv: Invite) => {
    const text = `Приглашение в кабинет салона «${salon.name}»`;
    openTelegramLink(
      `https://t.me/share/url?url=${encodeURIComponent(inv.url)}&text=${encodeURIComponent(text)}`,
    );
  };

  return (
    <div className="page">
      <div className="page-title">{staff.display_name}</div>
      <Section>
        <Field label="Имя">
          <input className="input" value={form.display_name} maxLength={120} onChange={(e) => set("display_name", e.target.value)} />
        </Field>
        <ImageUpload salonId={salonId} label="Фото" round value={form.photo_url} onChange={(u) => set("photo_url", u)} />
        <Field label="Описание для клиентов">
          <textarea className="input" rows={2} maxLength={2000} value={form.description ?? ""} onChange={(e) => set("description", e.target.value)} />
        </Field>
        <Field label="Роль">
          <select
            className="input"
            disabled={!canEditRole}
            value={form.role}
            onChange={(e) => set("role", e.target.value as StaffRole)}
          >
            <option value="master">Мастер</option>
            <option value="admin">Администратор</option>
            {(role === "owner" || form.role === "owner") && <option value="owner">Владелец</option>}
          </select>
        </Field>
        <Field label="Порядок в списке">
          <input className="input" type="number" value={form.sort_order} onChange={(e) => set("sort_order", Math.floor(Number(e.target.value)) || 0)} />
        </Field>
        <Check label="Принимает записи (показывать клиентам)" checked={form.is_bookable} onChange={(v) => set("is_bookable", v)} />
        {!isSelf && <Check label="Активен" checked={form.is_active} onChange={(v) => set("is_active", v)} />}
      </Section>

      <Section title="Telegram">
        {staff.is_linked ? (
          <Row title="Привязан" sub={staff.telegram_username ? `@${staff.telegram_username}` : undefined} />
        ) : invite ? (
          <div className="section-pad">
            <div className="hint" style={{ marginBottom: 8 }}>
              Отправьте ссылку сотруднику. Действует до {formatDateTime(invite.expires_at, salon.timezone)}.
            </div>
            <div className="input-boxed" style={{ wordBreak: "break-all", fontSize: 13, marginBottom: 10 }}>{invite.url}</div>
            <div className="btn-row">
              <button className="btn" onClick={() => shareInvite(invite)}>
                Поделиться
              </button>
              <button
                className="btn secondary"
                onClick={async () => toast((await copyText(invite.url)) ? "Ссылка скопирована" : "Не удалось скопировать")}
              >
                Копировать
              </button>
            </div>
          </div>
        ) : (
          <div className="section-pad">
            <div className="hint" style={{ marginBottom: 8 }}>
              Сотрудник ещё не вошёл в кабинет. Создайте ссылку-приглашение.
            </div>
            <button className="btn secondary block" disabled={createInvite.isPending} onClick={() => createInvite.mutate()}>
              Создать приглашение
            </button>
          </div>
        )}
      </Section>

      <Section title="Услуги мастера">
        {(services.data ?? []).length === 0 && <div className="row static hint">Сначала добавьте услуги</div>}
        {(services.data ?? []).map((s) => {
          const b = bindings[s.id] ?? { enabled: false, price: "", duration: "" };
          const update = (patch: Partial<Binding>) => setBindings({ ...bindings, [s.id]: { ...b, ...patch } });
          return (
            <div key={s.id}>
              <Check
                label={
                  <>
                    {s.name}{" "}
                    <span className="hint">
                      · {formatPrice(s.price, s.price_is_from)} · {formatDuration(s.duration_min)}
                    </span>
                  </>
                }
                checked={b.enabled}
                onChange={(v) => update({ enabled: v })}
              />
              {b.enabled && (
                <div className="split" style={{ padding: "0 16px 10px 46px" }}>
                  <input
                    className="input input-boxed"
                    type="number"
                    inputMode="numeric"
                    placeholder={`Цена: ${s.price}`}
                    value={b.price}
                    onChange={(e) => update({ price: e.target.value })}
                  />
                  <input
                    className="input input-boxed"
                    type="number"
                    inputMode="numeric"
                    placeholder={`Мин: ${s.duration_min}`}
                    value={b.duration}
                    onChange={(e) => update({ duration: e.target.value })}
                  />
                </div>
              )}
            </div>
          );
        })}
        <div className="section-pad hint">Пустые поля — цена и длительность из карточки услуги.</div>
      </Section>

      {!isSelf && canEditRole && (
        <button
          className="btn danger block"
          onClick={async () => {
            if (await confirmDialog("Удалить сотрудника? Если у него были записи, он будет отключён.")) remove.mutate();
          }}
        >
          Удалить сотрудника
        </button>
      )}
    </div>
  );
}
