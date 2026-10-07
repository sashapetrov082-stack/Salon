import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api } from "../../api/client";
import type { Category, ServiceAdmin } from "../../api/types";
import { Check, Empty, ErrorView, Field, Row, Section, Spinner, toast } from "../../components/ui";
import { formatDuration, formatPrice } from "../../lib/format";
import { useNavigate } from "react-router-dom";
import { alertDialog, confirmDialog, haptic, useBackButton, useMainButton } from "../../telegram/webapp";
import { useManage } from "./context";
import { useCategories, useServiceList } from "./hooks";

type Draft = Omit<ServiceAdmin, "id"> & { id: number | null };

const emptyDraft = (categoryId: number): Draft => ({
  id: null,
  category_id: categoryId,
  name: "",
  description: "",
  price: 0,
  price_is_from: false,
  duration_min: 60,
  buffer_after_min: 0,
  is_active: true,
  sort_order: 0,
});

function ServiceForm({
  draft,
  categories,
  onChange,
}: {
  draft: Draft;
  categories: Category[];
  onChange: (d: Draft) => void;
}) {
  const set = <K extends keyof Draft>(k: K, v: Draft[K]) => onChange({ ...draft, [k]: v });
  const num = (v: string) => (v === "" ? 0 : Math.max(0, Math.floor(Number(v)) || 0));
  return (
    <Section title={draft.id ? "Редактирование услуги" : "Новая услуга"}>
      <Field label="Название">
        <input className="input" value={draft.name} maxLength={120} onChange={(e) => set("name", e.target.value)} />
      </Field>
      <Field label="Категория">
        <select className="input" value={draft.category_id} onChange={(e) => set("category_id", Number(e.target.value))}>
          {categories.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </Field>
      <Field label="Описание">
        <textarea className="input" rows={2} maxLength={2000} value={draft.description ?? ""} onChange={(e) => set("description", e.target.value)} />
      </Field>
      <Field label="Цена, ₽">
        <input className="input" type="number" inputMode="numeric" min={0} value={draft.price} onChange={(e) => set("price", num(e.target.value))} />
      </Field>
      <Check label="Показывать «от» перед ценой" checked={draft.price_is_from} onChange={(v) => set("price_is_from", v)} />
      <Field label="Длительность, мин">
        <input className="input" type="number" inputMode="numeric" min={5} step={5} value={draft.duration_min} onChange={(e) => set("duration_min", num(e.target.value))} />
      </Field>
      <Field label="Буфер после услуги (уборка), мин">
        <input className="input" type="number" inputMode="numeric" min={0} step={5} value={draft.buffer_after_min} onChange={(e) => set("buffer_after_min", num(e.target.value))} />
      </Field>
      <Field label="Порядок в списке">
        <input className="input" type="number" inputMode="numeric" value={draft.sort_order} onChange={(e) => set("sort_order", Math.floor(Number(e.target.value)) || 0)} />
      </Field>
      <Check label="Доступна для записи" checked={draft.is_active} onChange={(v) => set("is_active", v)} />
    </Section>
  );
}

export function ServicesAdminPage() {
  const { salonId, base } = useManage();
  const queryClient = useQueryClient();
  const categories = useCategories();
  const services = useServiceList();
  const [draft, setDraft] = useState<Draft | null>(null);
  const [newCategory, setNewCategory] = useState("");
  const [editCategory, setEditCategory] = useState<Category | null>(null);
  const navigate = useNavigate();
  useBackButton(draft ? () => setDraft(null) : () => navigate(`${base}/more`, { replace: true }));

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ["manage", salonId] });
    queryClient.invalidateQueries({ queryKey: ["services"] });
  };
  const onError = (e: unknown) => {
    haptic.error();
    alertDialog(e instanceof ApiError ? e.message : "Не удалось сохранить");
  };

  const saveService = useMutation({
    mutationFn: (d: Draft) => {
      const { id, ...body } = d;
      const payload = { ...body, description: body.description?.trim() || null };
      return id
        ? api.put<ServiceAdmin>(`/manage/${salonId}/services/${id}`, payload)
        : api.post<ServiceAdmin>(`/manage/${salonId}/services`, payload);
    },
    onSuccess: () => {
      haptic.success();
      toast("Услуга сохранена");
      setDraft(null);
      invalidate();
    },
    onError,
  });
  const deleteService = useMutation({
    mutationFn: (id: number) => api.delete(`/manage/${salonId}/services/${id}`),
    onSuccess: () => {
      toast("Услуга удалена");
      setDraft(null);
      invalidate();
    },
    onError,
  });
  const saveCategory = useMutation({
    mutationFn: (c: { id?: number; name: string; sort_order: number }) =>
      c.id
        ? api.put<Category>(`/manage/${salonId}/categories/${c.id}`, { name: c.name, sort_order: c.sort_order })
        : api.post<Category>(`/manage/${salonId}/categories`, { name: c.name, sort_order: c.sort_order }),
    onSuccess: () => {
      setNewCategory("");
      setEditCategory(null);
      invalidate();
    },
    onError,
  });
  const deleteCategory = useMutation({
    mutationFn: (id: number) => api.delete(`/manage/${salonId}/categories/${id}`),
    onSuccess: () => {
      setEditCategory(null);
      invalidate();
    },
    onError,
  });

  useMainButton({
    text: "Сохранить услугу",
    visible: !!draft,
    progress: saveService.isPending,
    disabled: saveService.isPending,
    onClick: () => {
      if (!draft) return;
      if (!draft.name.trim()) return void alertDialog("Укажите название");
      if (draft.duration_min < 5) return void alertDialog("Длительность — не меньше 5 минут");
      saveService.mutate({ ...draft, name: draft.name.trim() });
    },
  });

  if (categories.isLoading || services.isLoading) return <Spinner />;
  if (categories.isError) return <ErrorView error={categories.error} />;
  const cats = categories.data ?? [];

  if (draft) {
    return (
      <div className="page">
        <ServiceForm draft={draft} categories={cats} onChange={setDraft} />
        <div className="btn-row">
          <button className="btn secondary" onClick={() => setDraft(null)}>
            Отмена
          </button>
          {draft.id && (
            <button
              className="btn danger"
              onClick={async () => {
                if (await confirmDialog("Удалить услугу? Если по ней были записи, она будет выключена.")) {
                  deleteService.mutate(draft.id!);
                }
              }}
            >
              Удалить
            </button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div className="page">
      <div className="page-title">Услуги</div>
      {cats.length === 0 && <Empty icon="💅">Сначала создайте категорию, например «Стрижки»</Empty>}
      {cats.map((c) => {
        const items = (services.data ?? []).filter((s) => s.category_id === c.id);
        return (
          <div key={c.id}>
            <div className="section-header" style={{ display: "flex", justifyContent: "space-between" }}>
              <span>{c.name}</span>
              <button className="link-btn" onClick={() => setEditCategory(c)}>
                Изменить
              </button>
            </div>
            {editCategory?.id === c.id && (
              <Section>
                <Field label="Название категории">
                  <input className="input" value={editCategory.name} onChange={(e) => setEditCategory({ ...editCategory, name: e.target.value })} />
                </Field>
                <Field label="Порядок">
                  <input className="input" type="number" value={editCategory.sort_order} onChange={(e) => setEditCategory({ ...editCategory, sort_order: Number(e.target.value) || 0 })} />
                </Field>
                <div className="section-pad btn-row">
                  <button className="btn" disabled={!editCategory.name.trim()} onClick={() => saveCategory.mutate({ ...editCategory, name: editCategory.name.trim() })}>
                    Сохранить
                  </button>
                  <button className="btn danger" onClick={() => deleteCategory.mutate(c.id)}>
                    Удалить
                  </button>
                </div>
              </Section>
            )}
            <div className="section">
              {items.map((s) => (
                <Row
                  key={s.id}
                  title={
                    <>
                      {s.name} {!s.is_active && <span className="badge gray">выключена</span>}
                    </>
                  }
                  sub={`${formatDuration(s.duration_min)}${s.buffer_after_min ? ` + ${s.buffer_after_min} мин буфер` : ""}`}
                  side={formatPrice(s.price, s.price_is_from)}
                  onClick={() => setDraft({ ...s })}
                />
              ))}
              <Row title={<span style={{ color: "var(--link)" }}>+ Добавить услугу</span>} onClick={() => setDraft(emptyDraft(c.id))} />
            </div>
          </div>
        );
      })}
      <Section title="Новая категория">
        <Field label="Название">
          <input className="input" value={newCategory} maxLength={120} placeholder="Например, Маникюр" onChange={(e) => setNewCategory(e.target.value)} />
        </Field>
        <div className="section-pad">
          <button
            className="btn secondary block"
            disabled={!newCategory.trim() || saveCategory.isPending}
            onClick={() => saveCategory.mutate({ name: newCategory.trim(), sort_order: cats.length })}
          >
            Добавить категорию
          </button>
        </div>
      </Section>
    </div>
  );
}
